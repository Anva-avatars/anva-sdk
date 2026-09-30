"""Bidirectional session commands. PCM is signed 16-bit little-endian, 24kHz mono."""
from __future__ import annotations
import base64
import json
from typing import Any, Dict, Iterator, List, Optional


def speech_start(turn_id: str, text: Optional[str] = None) -> Dict[str, Any]:
    payload = {"turn_id": turn_id, "codec": "pcm_s16le", "sample_rate": 24000, "channels": 1}
    if text is not None:
        payload["text"] = text
    return payload


def speech_append(turn_id: str, seq: int, start_sample: int, pcm: bytes) -> Dict[str, Any]:
    size = memoryview(pcm).nbytes if isinstance(pcm, (bytes, bytearray, memoryview)) else 0
    if not size or size % 2 or size > 24000:
        raise ValueError("PCM chunk must contain 1–12000 signed 16-bit samples")
    if isinstance(seq, bool) or not isinstance(seq, int) or seq < 0 or isinstance(start_sample, bool) or not isinstance(start_sample, int) or start_sample < 0:
        raise ValueError("seq and start_sample must be nonnegative integers")
    return {"turn_id": turn_id, "seq": seq, "start_sample": start_sample,
            "data": base64.b64encode(bytes(pcm)).decode("ascii")}


class RealtimeSession:
    """Wrap one connected WebSocket. Iterate events and send commands on the same socket.

    One reader at a time. Use a worker for slow LLM generation so the reader can
    process cancellation and speech.state events promptly.
    """
    def __init__(self, socket: Any):
        self.socket = socket
        self._pending: List[Dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.socket.close()

    def _events(self) -> Iterator[Dict[str, Any]]:
        for raw in self.socket:
            try:
                yield json.loads(raw)
            except (TypeError, ValueError):
                continue

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        while self._pending:
            yield self._pending.pop(0)
        yield from self._events()

    def wait_live(self) -> Dict[str, Any]:
        """Block until the viewer's embed is connected and return the
        ``session.live`` payload. Events read meanwhile stay queued for
        iteration. Commands sent before this are refused."""
        for event in self._events():
            self._pending.append(event)
            if event.get("type") == "session.live":
                return event.get("payload") or {}
            if event.get("type") == "session.ended":
                raise RuntimeError("the session ended before the viewer connected")
        raise RuntimeError("the events socket closed before the viewer connected")

    def send(self, type: str, payload: Optional[Dict[str, Any]] = None) -> None:
        self.socket.send(json.dumps({"type": type, "payload": payload or {}}))

    def message(self, text: str) -> None:
        self.send("message", {"text": text})

    def interrupt(self) -> None:
        self.send("interrupt")

    def update_context(self, context: Dict[str, Any]) -> None:
        self.send("context.update", context)

    def start_presentation(self, start: Dict[str, Any]) -> None:
        self.send("presentation.start", start)

    def turn_delta(self, turn_id: str, text: str) -> None:
        self.send("turn.delta", {"turn_id": turn_id, "text": text})

    def turn_done(self, turn_id: str) -> None:
        self.send("turn.done", {"turn_id": turn_id})

    def turn_cancel(self, turn_id: str, reason: str = "") -> None:
        self.send("turn.cancel", {"turn_id": turn_id, "reason": reason})

    def say(self, text: str, say_id: Optional[str] = None, *, speed: Optional[float] = None,
            queue: Optional[bool] = None) -> None:
        """Speak a host line in the session voice (byo_llm); ``speed``
        (0.7–1.2) sets this line's rate (an ``error`` event
        ``speed_unsupported`` on the Anva Realtime voice, which has no rate
        control). ``queue=True`` waits behind the line
        being spoken instead of interrupting it (at most 8 wait; one more is
        refused with an ``error`` event ``say_queue_full``)."""
        payload: Dict[str, Any] = {"text": text}
        if say_id:
            payload["say_id"] = say_id
        if speed is not None:
            payload["speed"] = speed
        if queue is not None:
            payload["queue"] = queue
        self.send("say", payload)

    def say_delta(self, say_id: str, text: str, *, speed: Optional[float] = None,
                  queue: Optional[bool] = None) -> None:
        """Stream a host line; put ``speed`` and ``queue`` on its first delta."""
        payload: Dict[str, Any] = {"say_id": say_id, "text": text}
        if speed is not None:
            payload["speed"] = speed
        if queue is not None:
            payload["queue"] = queue
        self.send("say.delta", payload)

    def update_prompt(self, system_prompt: str) -> None:
        """Replace a managed session's instructions mid-call (session.update)."""
        self.send("session.update", {"system_prompt": system_prompt})

    def say_done(self, say_id: str) -> None:
        self.send("say.done", {"say_id": say_id})

    def start_speech(self, turn_id: str, *, text: Optional[str] = None) -> None:
        self.send("speech.start", speech_start(turn_id, text))

    def append_speech(self, turn_id: str, seq: int, start_sample: int, pcm: bytes) -> None:
        self.send("speech.append", speech_append(turn_id, seq, start_sample, pcm))

    def finish_speech(self, turn_id: str, total_samples: int) -> None:
        self.send("speech.done", {"turn_id": turn_id, "total_samples": total_samples})

    def cancel_speech(self, turn_id: str) -> None:
        self.send("speech.cancel", {"turn_id": turn_id})


class LipsyncStream:
    """Lipsync API stream (Enterprise): binary PCM in, curve frames out.

    Iterate for ``ready``, ``frames``, ``flushed`` and ``error`` messages.
    """
    def __init__(self, socket: Any):
        self.socket = socket

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        self.socket.close()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for raw in self.socket:
            try:
                yield json.loads(raw)
            except (TypeError, ValueError):
                continue

    def audio(self, pcm: bytes) -> None:
        """Send one binary frame of 16-bit little-endian mono PCM at the stream's rate."""
        size = memoryview(pcm).nbytes if isinstance(pcm, (bytes, bytearray, memoryview)) else 0
        if not size or size % 2 or size > 196608:
            raise ValueError("PCM frame must hold 1–98304 signed 16-bit samples")
        self.socket.send(bytes(pcm))

    def flush(self) -> None:
        """End an utterance: the remaining frames arrive, then ``flushed``."""
        self.socket.send(json.dumps({"type": "flush"}))


class SpeechStream:
    """Speech API stream (Enterprise): text in, mouth curves and 24 kHz PCM out.

    Iterate for ``ready``, ``curves``, ``audio``, ``alignment``, ``done``,
    ``cancelled`` and ``error`` messages. An ``audio`` message's ``data`` is
    decoded to ``bytes`` of 16-bit little-endian mono PCM. A line's curves
    always arrive before the audio they describe. One line is spoken at a
    time: a ``speak`` while a line runs is refused with ``busy_line``, so wait
    for its ``done`` or ``cancel`` it. The server closes a stream that gets no
    command for 60 seconds while nothing is spoken (``idle_timeout``).
    """
    def __init__(self, socket: Any):
        self.socket = socket
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self) -> None:
        """Send ``{"type": "close"}`` and close the socket."""
        if self._closed:
            return
        self._closed = True
        try:
            self.socket.send(json.dumps({"type": "close"}))
        except Exception:  # the socket may already be gone; close it anyway
            pass
        self.socket.close()

    def __iter__(self) -> Iterator[Dict[str, Any]]:
        for raw in self.socket:
            try:
                message = json.loads(raw)
            except (TypeError, ValueError):
                continue
            if isinstance(message, dict) and message.get("type") == "audio" and isinstance(message.get("data"), str):
                message["data"] = base64.b64decode(message["data"])
            yield message

    def speak(self, id: str, text: str, *, voice_id: Optional[str] = None,
              speed: Optional[float] = None, preset: Optional[str] = None) -> None:
        """Speak one line. ``id`` (1–128 characters) is yours and is echoed on
        every event for the line; ``voice_id``, ``speed`` and ``preset``
        override the stream's defaults."""
        message: Dict[str, Any] = {"type": "speak", "id": id, "text": text}
        if voice_id is not None:
            message["voice_id"] = voice_id
        if speed is not None:
            message["speed"] = speed
        if preset is not None:
            message["preset"] = preset
        self.socket.send(json.dumps(message))

    def cancel(self, id: str) -> None:
        """Stop a line; it ends with ``cancelled``."""
        self.socket.send(json.dumps({"type": "cancel", "id": id}))
