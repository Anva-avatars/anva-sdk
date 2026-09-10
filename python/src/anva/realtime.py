"""Bidirectional session commands. PCM is signed 16-bit little-endian, 24kHz mono."""
from __future__ import annotations
import base64
import json
from typing import Any, Dict, Iterator, Optional


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

    def start_speech(self, turn_id: str, *, text: Optional[str] = None) -> None:
        self.send("speech.start", speech_start(turn_id, text))

    def append_speech(self, turn_id: str, seq: int, start_sample: int, pcm: bytes) -> None:
        self.send("speech.append", speech_append(turn_id, seq, start_sample, pcm))

    def finish_speech(self, turn_id: str, total_samples: int) -> None:
        self.send("speech.done", {"turn_id": turn_id, "total_samples": total_samples})

    def cancel_speech(self, turn_id: str) -> None:
        self.send("speech.cancel", {"turn_id": turn_id})
