"""An Anva ``avatar_only`` session driven from Python.

Three connections make one avatar: the REST call that creates the session, the
events socket that carries speech in and progress out, and a WebRTC viewer that
receives the avatar's video and audio -- the same media a browser would get
from Anva's embed player, decoded here instead. Speech goes in as raw PCM in
utterances; Anva's core plays each one through the avatar and reports what it
accepted and played, which is what paces the sending.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

import aiohttp
import numpy as np
import websockets
from aiortc import RTCPeerConnection, RTCSessionDescription
from av.audio.frame import AudioFrame
from av.audio.resampler import AudioResampler

log = logging.getLogger("pipecat_anva")

DEFAULT_API_URL = "https://anva.ai"
#: What Anva's speech ingress takes.
CORE_RATE = 24000
#: The most one append may carry.
CHUNK_SAMPLES = 12000
#: Keep a second under the core's five-second window of unplayed audio.
OUTSTANDING_LIMIT = 4 * CORE_RATE
#: Anva's longest utterance.
UTTERANCE_LIMIT = 120 * CORE_RATE

FrameCallback = Callable[[Any], Awaitable[None]]


class AnvaError(Exception):
    """Anva could not start or run the session."""


async def _cancel_task(task: asyncio.Task) -> None:
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):  # noqa: BLE001
        pass


@dataclass
class Utterance:
    """One stretch of speech from the agent, converted to core samples."""

    turn_id: str
    pending: bytearray = field(default_factory=bytearray)
    pushed: int = 0
    closed: bool = False
    cancelled: bool = False
    wake: asyncio.Event = field(default_factory=asyncio.Event)

    def push(self, pcm: bytes) -> None:
        if self.cancelled or not pcm:
            return
        room = UTTERANCE_LIMIT - self.pushed
        if room <= 0:
            return
        pcm = pcm[: room * 2]
        self.pending.extend(pcm)
        self.pushed += len(pcm) // 2
        self.wake.set()

    def close(self) -> None:
        self.closed = True
        self.wake.set()

    def cancel(self) -> None:
        self.cancelled = True
        self.pending.clear()
        self.wake.set()

    def take(self) -> bytes:
        """A full chunk, or whatever is left once the utterance is closed."""
        if len(self.pending) >= CHUNK_SAMPLES * 2 or (self.closed and self.pending):
            n = min(len(self.pending), CHUNK_SAMPLES * 2)
            chunk = bytes(self.pending[:n])
            del self.pending[:n]
            return chunk
        return b""


class AnvaSession:
    """Create, watch and speak through one Anva avatar session.

    ``on_video`` and ``on_audio`` receive PyAV frames as they arrive from the
    avatar. ``task_factory`` is how background tasks are started, so a host
    such as Pipecat can own them.
    """

    def __init__(
        self,
        *,
        api_key: str,
        avatar_id: str | None = None,
        preset_id: str | None = None,
        api_url: str = DEFAULT_API_URL,
        max_duration_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        on_video: FrameCallback | None = None,
        on_audio: FrameCallback | None = None,
        task_factory: Callable[[Awaitable[Any]], asyncio.Task] | None = None,
        task_cancel: Callable[[asyncio.Task], Awaitable[None]] | None = None,
    ) -> None:
        if bool(avatar_id) == bool(preset_id):
            raise AnvaError("give exactly one of avatar_id and preset_id")
        if not api_key:
            raise AnvaError("api_key is required")
        self._api_key = api_key
        self._avatar_id, self._preset_id = avatar_id, preset_id
        self._api_url = api_url.rstrip("/")
        self._max_duration_seconds = max_duration_seconds
        self._metadata = metadata
        self._on_video, self._on_audio = on_video, on_audio
        self._task_factory = task_factory or asyncio.create_task
        self._task_cancel = task_cancel or _cancel_task
        self._http: aiohttp.ClientSession | None = None
        self._ws: Any = None
        self._pc: RTCPeerConnection | None = None
        self._tasks: list[asyncio.Task] = []
        self.session_id: str | None = None
        self.session_token: str | None = None
        self.live = asyncio.Event()
        self.ended = asyncio.Event()
        # Every sentence the pipeline speaks waits its turn; an interruption drains it.
        self._queue: asyncio.Queue[Utterance] = asyncio.Queue()
        self._current: Utterance | None = None
        self._states: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)
        self._turns = 0
        self._resampler: AudioResampler | None = None
        self._resampler_key: tuple[int, int] | None = None

    # -- lifecycle ---------------------------------------------------------
    async def start(self) -> None:
        self._http = aiohttp.ClientSession()
        await self._create()
        await self._connect_events()
        await self._attach_viewer()
        try:
            await asyncio.wait_for(self.live.wait(), timeout=60)
        except asyncio.TimeoutError as exc:
            raise AnvaError("Anva did not report the session live within 60 s") from exc
        self._tasks.append(self._task_factory(self._feed()))

    async def close(self) -> None:
        for task in list(self._tasks):
            await self._task_cancel(task)
        self._tasks.clear()
        if self._pc is not None:
            await self._pc.close()
            self._pc = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None
        if self._http is not None:
            if self.session_id:
                try:
                    async with self._http.delete(
                        f"{self._api_url}/api/v2/sessions/{self.session_id}", headers=self._auth(),
                        timeout=aiohttp.ClientTimeout(total=15),
                    ):
                        pass
                except Exception:  # noqa: BLE001
                    log.debug("could not end the Anva session", exc_info=True)
            await self._http.close()
            self._http = None
        self.ended.set()

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _create(self) -> None:
        assert self._http is not None
        body: dict[str, Any] = {"service_mode": "avatar_only"}
        if self._avatar_id:
            body["avatar_id"] = self._avatar_id
        else:
            body["preset_id"] = self._preset_id
        if self._max_duration_seconds:
            body["max_duration_seconds"] = self._max_duration_seconds
        if self._metadata:
            body["metadata"] = self._metadata
        async with self._http.post(f"{self._api_url}/api/v2/sessions", json=body, headers=self._auth(),
                                   timeout=aiohttp.ClientTimeout(total=30)) as response:
            text = await response.text()
            if response.status != 201:
                raise AnvaError(f"Anva refused the session ({response.status}): {text}")
            data = json.loads(text)
        self.session_id = data["session_id"]
        self.session_token = data["session_token"]
        self._events_url = data["events_ws_url"]
        log.info("Anva session %s created", self.session_id)

    async def _connect_events(self) -> None:
        self._ws = await websockets.connect(self._events_url, additional_headers=self._auth(), max_size=1 << 20)
        self._tasks.append(self._task_factory(self._read_events()))

    async def _read_events(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    event = json.loads(raw)
                except ValueError:
                    continue
                typ, payload = event.get("type"), event.get("payload") or {}
                if typ == "session.live":
                    self.live.set()
                elif typ == "session.ended":
                    log.info("Anva session %s ended: %s", self.session_id, payload.get("reason"))
                    self.ended.set()
                elif typ == "speech.state":
                    if self._states.full():
                        self._states.get_nowait()
                    self._states.put_nowait(payload)
                elif typ == "error":
                    log.warning("Anva session %s error: %s", self.session_id, payload)
        except websockets.ConnectionClosed:
            log.info("Anva events socket closed for %s", self.session_id)
            self.ended.set()

    async def _attach_viewer(self) -> None:
        """Receive the avatar over WebRTC, as the embed player does."""
        assert self._http is not None
        pc = RTCPeerConnection()
        self._pc = pc
        pc.addTransceiver("video", direction="recvonly")
        pc.addTransceiver("audio", direction="recvonly")

        @pc.on("track")
        def on_track(track):
            self._tasks.append(self._task_factory(self._consume(track)))

        offer = await pc.createOffer()
        await pc.setLocalDescription(offer)
        body = {"session_id": self.session_id, "session_url_token": self.session_token,
                "sdp": pc.localDescription.sdp, "type": pc.localDescription.type,
                "client_instance_id": "pipecat-anva-" + uuid.uuid4().hex[:12], "client_generation": 1}
        for attempt in range(8):
            async with self._http.post(f"{self._api_url}/offer", json=body,
                                       timeout=aiohttp.ClientTimeout(total=60)) as response:
                text = await response.text()
                if response.status == 200:
                    answer = json.loads(text)
                    break
                # Capacity and warming answers say when to try again.
                retry_after = 5
                try:
                    retry_after = int(json.loads(text).get("retry_after", retry_after))
                except (ValueError, AttributeError):
                    pass
                if response.status == 503 and attempt < 7:
                    log.info("Anva viewer not admitted yet (%s); retrying in %ss", text[:120], retry_after)
                    await asyncio.sleep(retry_after)
                    continue
                raise AnvaError(f"Anva refused the viewer ({response.status}): {text}")
        await pc.setRemoteDescription(RTCSessionDescription(sdp=answer["sdp"], type=answer["type"]))

    async def _consume(self, track) -> None:
        callback = self._on_video if track.kind == "video" else self._on_audio
        try:
            while True:
                frame = await track.recv()
                if callback is not None:
                    await callback(frame)
        except Exception:  # noqa: BLE001  the track ended with the connection
            log.debug("Anva %s track ended", track.kind, exc_info=True)

    # -- speech in ---------------------------------------------------------
    def begin_utterance(self) -> Utterance:
        """The agent starts speaking; audio follows in push_audio."""
        self._turns += 1
        u = Utterance(turn_id=f"pipecat-{self._turns}")
        self._queue.put_nowait(u)
        return u

    def push_audio(self, u: Utterance, pcm: bytes, sample_rate: int, channels: int) -> None:
        """Add TTS audio to an utterance, converting it to what Anva takes."""
        if u.cancelled or not pcm:
            return
        if channels == 1 and sample_rate == CORE_RATE:
            u.push(pcm)
            return
        if self._resampler_key != (sample_rate, channels):
            self._resampler = AudioResampler("s16", "mono", CORE_RATE)
            self._resampler_key = (sample_rate, channels)
        frame = AudioFrame.from_ndarray(np.frombuffer(pcm, dtype=np.int16)[None, :],
                                        layout="mono" if channels == 1 else "stereo")
        frame.sample_rate = sample_rate
        assert self._resampler is not None
        for out in self._resampler.resample(frame):
            u.push(out.to_ndarray().astype(np.int16).tobytes())

    def end_utterance(self, u: Utterance) -> None:
        if self._resampler is not None:
            for out in self._resampler.resample(None):
                u.push(out.to_ndarray().astype(np.int16).tobytes())
            self._resampler, self._resampler_key = None, None
        u.close()

    async def interrupt(self) -> None:
        """Stop what is playing and drop what is queued."""
        while not self._queue.empty():
            self._queue.get_nowait().cancel()
        if self._current is not None:
            self._current.cancel()
        # What the resampler still holds belonged to the cut-off sentence.
        self._resampler, self._resampler_key = None, None

    async def _send(self, typ: str, payload: dict[str, Any]) -> None:
        if self._ws is None:
            raise AnvaError("events socket is not connected")
        await self._ws.send(json.dumps({"type": typ, "payload": payload}))

    async def _feed(self) -> None:
        """Serve utterances to the core one at a time, within its window."""
        while True:
            u = await self._queue.get()
            self._current = u
            try:
                await self._serve(u)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001
                log.warning("Anva utterance %s failed", u.turn_id, exc_info=True)
            finally:
                self._current = None

    async def _serve(self, u: Utterance) -> None:
        if u.cancelled:
            return
        await self._send("speech.start", {"turn_id": u.turn_id, "codec": "pcm_s16le",
                                          "sample_rate": CORE_RATE, "channels": 1})
        sent = played = seq = 0
        done = False

        def note(state: dict) -> None:
            nonlocal played, done
            if state.get("turn_id") != u.turn_id:
                return
            played = max(played, int(state.get("played_samples") or 0))
            if state.get("state") in ("finished", "cancelled", "error"):
                done = True

        while not done:
            if u.cancelled:
                await self._send("speech.cancel", {"turn_id": u.turn_id})
                return
            chunk = u.take()
            if chunk:
                while sent - played > OUTSTANDING_LIMIT and not u.cancelled:
                    try:
                        note(await asyncio.wait_for(self._states.get(), timeout=0.25))
                    except asyncio.TimeoutError:
                        pass
                if u.cancelled:
                    continue
                await self._send("speech.append", {"turn_id": u.turn_id, "seq": seq, "start_sample": sent,
                                                   "data": base64.b64encode(chunk).decode()})
                seq += 1
                sent += len(chunk) // 2
                continue
            if u.closed:
                if sent == 0:
                    await self._send("speech.cancel", {"turn_id": u.turn_id})
                    return
                await self._send("speech.done", {"turn_id": u.turn_id, "total_samples": sent})
                remaining = (sent - played) / CORE_RATE + 10
                deadline = asyncio.get_running_loop().time() + remaining
                while not done and not u.cancelled:
                    wait = deadline - asyncio.get_running_loop().time()
                    if wait <= 0:
                        log.info("Anva did not confirm playback of %s; moving on", u.turn_id)
                        return
                    try:
                        note(await asyncio.wait_for(self._states.get(), timeout=min(wait, 0.5)))
                    except asyncio.TimeoutError:
                        pass
                if u.cancelled and not done:
                    await self._send("speech.cancel", {"turn_id": u.turn_id})
                return
            # Nothing ready: wait for audio, a report, or the end.
            u.wake.clear()
            state_wait = asyncio.ensure_future(self._states.get())
            wake_wait = asyncio.ensure_future(u.wake.wait())
            finished, _ = await asyncio.wait({state_wait, wake_wait}, return_when=asyncio.FIRST_COMPLETED)
            for task in (state_wait, wake_wait):
                if task in finished:
                    result = task.result()
                    if task is state_wait:
                        note(result)
                else:
                    task.cancel()
