"""Anva's API and node as the Pipecat service sees them, without a network.

Creates sessions, runs the events socket with instant playback reports, and
answers the viewer's WebRTC offer with a moving picture and a tone, the way the
real node does.
"""
from __future__ import annotations

import asyncio
import base64
import fractions
import json
import time

import numpy as np
from aiohttp import WSMsgType, web
from aiortc import RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack, VideoStreamTrack
from av import AudioFrame, VideoFrame

WIDTH, HEIGHT = 160, 120
TONE_RATE = 48000


class Picture(VideoStreamTrack):
    """A frame whose colour moves, so decoded frames are not all alike."""

    async def recv(self):
        pts, time_base = await self.next_timestamp()
        arr = np.zeros((HEIGHT, WIDTH, 3), np.uint8)
        arr[..., 0] = (pts // 3000) % 256
        arr[..., 2] = 120
        frame = VideoFrame.from_ndarray(arr, format="rgb24")
        frame.pts, frame.time_base = pts, time_base
        return frame


class Tone(MediaStreamTrack):
    """A 440 Hz tone at 48 kHz stereo, 20 ms a frame, as the node's Opus track decodes."""

    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._pos = 0
        self._start: float | None = None

    async def recv(self):
        samples = 960
        if self._start is None:
            self._start = time.monotonic()
        wait = self._start + self._pos / TONE_RATE - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait)
        t = (np.arange(samples) + self._pos) / TONE_RATE
        mono = (np.sin(2 * np.pi * 440 * t) * 8000).astype(np.int16)
        frame = AudioFrame.from_ndarray(np.repeat(mono, 2)[None, :], format="s16", layout="stereo")
        frame.sample_rate = TONE_RATE
        frame.pts, frame.time_base = self._pos, fractions.Fraction(1, TONE_RATE)
        self._pos += samples
        return frame


class FakeAnva:
    """The parts of Anva that pipecat-anva talks to."""

    def __init__(self) -> None:
        self.app = web.Application()
        self.app.router.add_post("/api/v2/sessions", self.create)
        self.app.router.add_delete("/api/v2/sessions/{id}", self.delete)
        self.app.router.add_get("/api/v2/sessions/{id}/events", self.events)
        self.app.router.add_post("/offer", self.offer)
        self.created: list[dict] = []
        self.deleted: list[str] = []
        self.offers: list[dict] = []
        self.commands: list[dict] = []
        self.ws_auth: str | None = None
        self.pcs: list[RTCPeerConnection] = []
        self.port = 0
        #: When set, session creation answers with this status instead.
        self.refuse_with: int | None = None
        self._runner: web.AppRunner | None = None

    async def start(self) -> str:
        self._runner = web.AppRunner(self.app)
        await self._runner.setup()
        site = web.TCPSite(self._runner, "127.0.0.1", 0)
        await site.start()
        self.port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
        return f"http://127.0.0.1:{self.port}"

    async def stop(self) -> None:
        for pc in self.pcs:
            await pc.close()
        if self._runner is not None:
            await self._runner.cleanup()

    def commands_of(self, typ: str) -> list[dict]:
        return [c["payload"] for c in self.commands if c["type"] == typ]

    async def create(self, request: web.Request) -> web.Response:
        if self.refuse_with:
            return web.json_response({"error": {"code": "no_capacity", "message": "busy"}}, status=self.refuse_with)
        body = await request.json()
        self.created.append({"auth": request.headers.get("Authorization"), "body": body})
        sid = f"apisess-{len(self.created)}"
        return web.json_response({
            "session_id": sid, "session_token": "anva_gr_test", "status": "created",
            "events_ws_url": f"ws://127.0.0.1:{self.port}/api/v2/sessions/{sid}/events",
        }, status=201)

    async def delete(self, request: web.Request) -> web.Response:
        self.deleted.append(request.match_info["id"])
        return web.json_response({"session_id": request.match_info["id"], "status": "ended"})

    async def events(self, request: web.Request) -> web.WebSocketResponse:
        self.ws_auth = request.headers.get("Authorization")
        sid = request.match_info["id"]
        ws = web.WebSocketResponse()
        await ws.prepare(request)
        await ws.send_json({"type": "session.info", "payload": {"session_id": sid, "status": "created"}})
        await ws.send_json({"type": "session.live", "payload": {"session_id": sid}})
        accepted = 0

        async def report(turn: str, state: str, played: int, **extra) -> None:
            await ws.send_json({"type": "speech.state", "payload": {
                "turn_id": turn, "state": state, "accepted_samples": accepted, "played_samples": played, **extra}})

        async for msg in ws:
            if msg.type != WSMsgType.TEXT:
                continue
            env = json.loads(msg.data)
            typ, payload = env["type"], env.get("payload") or {}
            record = dict(payload)
            if "data" in record:
                record["samples"] = len(base64.b64decode(record.pop("data"))) // 2
            self.commands.append({"type": typ, "payload": record})
            turn = payload.get("turn_id", "")
            # Playback is instant here: what is accepted is played.
            if typ == "speech.start":
                accepted = 0
                await report(turn, "started", 0)
            elif typ == "speech.append":
                accepted += record["samples"]
                await report(turn, "accepted", accepted, next_seq=payload["seq"] + 1)
            elif typ == "speech.done":
                await report(turn, "finished", payload["total_samples"])
            elif typ == "speech.cancel":
                await report(turn, "cancelled", accepted)
        return ws

    async def offer(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.offers.append(body)
        pc = RTCPeerConnection()
        self.pcs.append(pc)
        pc.addTrack(Picture())
        pc.addTrack(Tone())
        await pc.setRemoteDescription(RTCSessionDescription(sdp=body["sdp"], type=body["type"]))
        await pc.setLocalDescription(await pc.createAnswer())
        return web.json_response({"type": pc.localDescription.type, "sdp": pc.localDescription.sdp})
