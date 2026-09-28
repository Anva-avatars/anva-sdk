"""Thin, dependency-free client for the Anva REST API.

Every method mirrors one endpoint and returns the decoded JSON body.
Errors raise AnvaError carrying the API's machine-readable code.
The events stream (WebSocket) needs the optional extra: pip install anva[ws].
"""
from __future__ import annotations

import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
import warnings
from typing import Any, Dict, Iterator, List, Optional

from .realtime import LipsyncStream, RealtimeSession, SpeechStream, speech_start, speech_append

if sys.version_info >= (3, 11):
    from typing import NotRequired, TypedDict
else:  # before 3.11, alignment is typed as Optional rather than NotRequired
    from typing import TypedDict
    NotRequired = Optional

DEFAULT_BASE_URL = "https://anva.ai"


class SpeechAudio(TypedDict):
    """``format`` is ``"wav"`` (a complete WAV file) or ``"pcm"`` (16-bit
    little-endian mono); ``data`` is decoded from the API's base64."""
    format: str
    data: bytes


class SpeechCurves(TypedDict):
    """``frames[n][i]`` is ``channels[i]`` at ``n / fps`` seconds;
    ``frame_count = ceil(samples / 800)``."""
    fps: int
    channels: List[str]
    frame_count: int
    preset: str
    model: str
    release: str
    frames: List[List[float]]


class SpeechAlignment(TypedDict):
    """Character timing in seconds on the audio clock."""
    characters: List[str]
    starts: List[float]
    ends: List[float]


class SpeechResult(TypedDict):
    """What ``Anva.synthesize`` returns (a plain dict at runtime)."""
    id: str
    voice_id: str
    sample_rate: int
    duration_s: float
    audio: SpeechAudio
    curves: SpeechCurves
    alignment: NotRequired[SpeechAlignment]
    billing: Dict[str, Any]


class AnvaError(Exception):
    """API error with the server's machine-readable code and HTTP status."""

    def __init__(self, status: int, code: str, message: str, details=None):
        super().__init__(f"{code}: {message} (HTTP {status})")
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}


class Anva:
    """Client for the Anva API.

    Args:
        api_key: an API key from the dashboard (anva_key_...).
        base_url: override for self-hosted / testing setups.
        timeout: per-request timeout in seconds.
    """

    def __init__(self, api_key: str, *, base_url: str = DEFAULT_BASE_URL,
                 timeout: float = 30.0):
        if not api_key or not api_key.strip():
            raise ValueError("api_key is required")
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    # -- sessions -----------------------------------------------------------

    def create_session(self, preset_id: Optional[str] = None, *,
                       avatar_id: Optional[str] = None,
                       system_prompt: Optional[str] = None,
                       voice_id: Optional[str] = None,
                       language_code: Optional[str] = None,
                       service_mode: Optional[str] = None,
                       llm_mode: Optional[str] = None,
                       performance_options: Optional[Dict[str, Any]] = None,
                       conversation_provider: Optional[str] = None,
                       performance_mode: Optional[str] = None,
                       elevenlabs_agent_id: Optional[str] = None,
                       dynamic_expressions: Optional[bool] = None,
                       speech_input: Optional[str] = None,
                       speech_speed: Optional[float] = None,
                       wake_up: Optional[bool] = None,
                       idempotency_key: Optional[str] = None,
                       webhook_url: Optional[str] = None,
                       webhook_secret: Optional[str] = None,
                       max_duration_seconds: Optional[int] = None,
                       metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Create a live session, one of two ways:

        - Embed tier: pass ``preset_id`` (a saved preset from the Playground).
        - Advanced tier: pass ``avatar_id`` plus the persona (``system_prompt``,
          ``voice_id``, ``language_code``) directly — nothing is stored.

        ``max_duration_seconds`` (60–7200) ends the session that long after it
        goes live; omitted, the server's 2-hour ceiling applies.

        ``metadata`` is an optional flat dict (str, int, float or bool values,
        up to 20 keys, 4 KB serialized) stored with the session and echoed on
        the session, on ``session.info`` and in every webhook payload.

        ``speech_input="off"`` (byo_llm, anva_light, anva_expressive) is for
        hosts that transcribe the user themselves, such as push-to-talk: the
        embed opens no microphone and each user turn arrives through
        ``send_message``.

        ``speech_speed`` (0.7–1.2) sets the speaking rate for anva_light and
        byo_llm voices. ``wake_up=True`` starts the call with the avatar's
        eyes closed; they open once the viewer's video is showing
        (``session.info`` reports ``wake_up: false`` for avatars that cannot
        close their eyes convincingly).

        ``idempotency_key`` (16–128 letters, digits, ``-`` or ``_``) is sent as
        the ``Idempotency-Key`` header: a retry with the same key and body
        within 24 hours returns the first session instead of a second one.

        Returns session_id, session_token, embed_url (iframe-ready),
        events_ws_url, instance_id, preset_id, avatar_id, max_duration_seconds.
        """
        if (not preset_id and not avatar_id) or (preset_id and avatar_id):
            raise ValueError("create_session requires exactly one of preset_id or avatar_id")
        body: Dict[str, Any] = {}
        if preset_id:
            body["preset_id"] = preset_id
        if avatar_id:
            body["avatar_id"] = avatar_id
        if system_prompt:
            body["system_prompt"] = system_prompt
        if voice_id:
            body["voice_id"] = voice_id
        if language_code:
            body["language_code"] = language_code
        for key, value in {"service_mode": service_mode, "llm_mode": llm_mode,
                           "performance_options": performance_options, "conversation_provider": conversation_provider,
                           "performance_mode": performance_mode, "elevenlabs_agent_id": elevenlabs_agent_id,
                           "dynamic_expressions": dynamic_expressions, "speech_input": speech_input,
                           "speech_speed": speech_speed, "wake_up": wake_up}.items():
            if value is not None:
                body[key] = value
        if webhook_url:
            body["webhook_url"] = webhook_url
        if webhook_secret:
            body["webhook_secret"] = webhook_secret
        if max_duration_seconds is not None:
            body["max_duration_seconds"] = max_duration_seconds
        if metadata is not None:
            body["metadata"] = metadata
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else None
        return self._request("POST", "/api/v2/sessions", body, headers=headers)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v2/sessions/{_esc(session_id)}")

    def end_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v2/sessions/{_esc(session_id)}")

    def update_session(self, session_id: str, *, system_prompt: str) -> Dict[str, Any]:
        """Replace a managed session's instructions while it runs; they apply
        from the next reply (anva_light, anva_expressive; added as context for
        elevenagents_max). On a live connection, ``update_prompt`` does the
        same."""
        return self._request("PATCH", f"/api/v2/sessions/{_esc(session_id)}",
                             {"system_prompt": system_prompt})

    def send_message(self, session_id: str, text: str) -> Dict[str, Any]:
        """Send ``text`` as a user message; the avatar hears it and replies (it
        does NOT speak ``text`` verbatim). External replies use
        ``service_mode="byo_llm"`` with ``turn_delta`` / ``turn_done`` on a realtime connection."""
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/messages",
            {"text": text})

    def say(self, session_id: str, text: str, *, say_id: Optional[str] = None,
            speed: Optional[float] = None, queue: Optional[bool] = None) -> Dict[str, Any]:
        """Speak ``text`` verbatim in the session voice (byo_llm), without a
        turn.request. Returns ``{"status", "say_id"}``; the line's
        ``turn.complete`` event carries the same ``say_id`` and it ends with
        one ``line.ended``. ``speed`` (0.7–1.2) sets this line's speaking
        rate. ``queue=True`` waits behind the line being spoken instead of
        interrupting it. Needs the viewer connected."""
        body: Dict[str, Any] = {"text": text}
        if say_id:
            body["say_id"] = say_id
        if speed is not None:
            body["speed"] = speed
        if queue is not None:
            body["queue"] = queue
        return self._request("POST", f"/api/v2/sessions/{_esc(session_id)}/say", body)

    def interrupt(self, session_id: str) -> Dict[str, Any]:
        """Stop the avatar mid-sentence."""
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/interrupt", {})

    def trigger_action(self, session_id: str, name: str) -> Dict[str, Any]:
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/actions",
            {"name": name})

    def events_ws_url(self, session_id: str, *, controls: bool = True) -> str:
        """The session's event-stream WebSocket URL. It carries no credentials:
        authenticate the handshake with ``auth_headers()``. ``controls=False``
        leaves out the per-frame face stream."""
        ws_base = self.base_url.replace("http", "ws", 1)
        return f"{ws_base}/api/v2/sessions/{_esc(session_id)}/events" + ("" if controls else "?controls=false")

    def auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self.api_key}"}

    def events_url(self, session_id: str) -> str:
        """Deprecated: puts the API key in the URL, where proxies and access
        logs record it. Use ``connect()``, or ``events_ws_url()`` with
        ``auth_headers()``."""
        warnings.warn("events_url() puts the API key in the URL; use events_ws_url() with auth_headers()",
                      DeprecationWarning, stacklevel=2)
        return f"{self.events_ws_url(session_id)}?api_key={urllib.parse.quote(self.api_key)}"

    def connect(self, session_id: str, *, controls: bool = True) -> RealtimeSession:
        """Open a bidirectional connection. Requires ``pip install anva[ws]``.
        ``controls=False`` leaves out the per-frame face stream."""
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            raise RuntimeError("realtime requires pip install anva[ws]") from e
        return RealtimeSession(connect(self.events_ws_url(session_id, controls=controls),
                                       additional_headers=self.auth_headers()))

    def events(self, session_id: str, *, controls: bool = True) -> Iterator[Dict[str, Any]]:
        with self.connect(session_id, controls=controls) as stream:
            yield from stream

    def lipsync(self, audio: bytes, *, sample_rate: Optional[int] = None,
                preset: Optional[str] = None,
                content_type: Optional[str] = None) -> Dict[str, Any]:
        """Mouth curves for one audio clip (Enterprise): the 24 ARKit mouth
        channels at 30 fps. ``audio`` is WAV, FLAC or OGG bytes, or raw 16-bit
        little-endian mono PCM when ``sample_rate`` is given."""
        query: Dict[str, str] = {}
        if sample_rate is not None:
            query["sample_rate"] = str(sample_rate)
        if preset:
            query["preset"] = preset
        path = "/api/v2/lipsync" + ("?" + urllib.parse.urlencode(query) if query else "")
        kind = content_type or ("audio/pcm" if sample_rate is not None else "application/octet-stream")
        return self._request("POST", path, raw=bytes(audio), content_type=kind)

    def lipsync_stream_url(self, *, sample_rate: int = 24000, preset: Optional[str] = None) -> str:
        """The Lipsync stream's WebSocket URL; authenticate with ``auth_headers()``."""
        query = {"sample_rate": str(sample_rate)}
        if preset:
            query["preset"] = preset
        ws_base = self.base_url.replace("http", "ws", 1)
        return f"{ws_base}/api/v2/lipsync/stream?{urllib.parse.urlencode(query)}"

    def connect_lipsync(self, *, sample_rate: int = 24000,
                        preset: Optional[str] = None) -> LipsyncStream:
        """Stream 16 or 24 kHz PCM in and mouth curves out (Enterprise).
        Requires ``pip install anva[ws]``."""
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            raise RuntimeError("realtime requires pip install anva[ws]") from e
        return LipsyncStream(connect(self.lipsync_stream_url(sample_rate=sample_rate, preset=preset),
                                     additional_headers=self.auth_headers()))

    def synthesize(self, text: str, *, voice_id: str, speed: Optional[float] = None,
                   preset: Optional[str] = None, format: Optional[str] = None) -> SpeechResult:
        """Text to speech plus mouth curves (Speech API, Enterprise): Anva TTS
        audio at 24 kHz and the 24 ARKit mouth channels at 30 fps measured on
        it. ``voice_id`` is a voice from ``list_voices()``; ``speed`` is
        0.7–1.2; ``preset`` is ``hybrid`` or ``lowlat``; ``format`` is ``wav``
        (default) or ``pcm``. ``result["audio"]["data"]`` is decoded bytes."""
        body: Dict[str, Any] = {"text": text, "voice_id": voice_id}
        for key, value in {"speed": speed, "preset": preset, "format": format}.items():
            if value is not None:
                body[key] = value
        result = self._request("POST", "/api/v2/speech", body)
        audio = result.get("audio")
        if isinstance(audio, dict) and isinstance(audio.get("data"), str):
            audio["data"] = base64.b64decode(audio["data"])
        return result  # type: ignore[return-value]

    def speech_stream_url(self, *, voice_id: Optional[str] = None, speed: Optional[float] = None,
                          preset: Optional[str] = None) -> str:
        """The Speech stream's WebSocket URL; authenticate with
        ``auth_headers()``. The arguments are defaults for the lines on it."""
        query: Dict[str, str] = {}
        if voice_id:
            query["voice_id"] = voice_id
        if speed is not None:
            query["speed"] = str(speed)
        if preset:
            query["preset"] = preset
        ws_base = self.base_url.replace("http", "ws", 1)
        return f"{ws_base}/api/v2/speech/stream" + ("?" + urllib.parse.urlencode(query) if query else "")

    def connect_speech(self, *, voice_id: Optional[str] = None, speed: Optional[float] = None,
                       preset: Optional[str] = None) -> SpeechStream:
        """Speak lines over one socket (Enterprise): ``speak``, ``cancel`` and
        ``close``. Requires ``pip install anva[ws]``."""
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            raise RuntimeError("realtime requires pip install anva[ws]") from e
        return SpeechStream(connect(self.speech_stream_url(voice_id=voice_id, speed=speed, preset=preset),
                                    additional_headers=self.auth_headers()))

    def capabilities(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/capabilities")

    def billing(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/billing")

    def list_avatars(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/avatars")

    def list_voices(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/voices")

    def list_languages(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/languages")

    def update_context(self, session_id: str, context: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/api/v2/sessions/{_esc(session_id)}/context", context)

    def start_presentation(self, session_id: str, start: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/api/v2/sessions/{_esc(session_id)}/presentation", start)

    def speech(self, session_id: str, type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        return self._request("POST", f"/api/v2/sessions/{_esc(session_id)}/speech", {"type": type, "payload": payload})

    def start_speech(self, session_id: str, turn_id: str, *, text: Optional[str] = None) -> Dict[str, Any]:
        return self.speech(session_id, "speech.start", speech_start(turn_id, text))

    def append_speech(self, session_id: str, turn_id: str, seq: int, start_sample: int, pcm: bytes) -> Dict[str, Any]:
        return self.speech(session_id, "speech.append", speech_append(turn_id, seq, start_sample, pcm))

    def finish_speech(self, session_id: str, turn_id: str, total_samples: int) -> Dict[str, Any]:
        return self.speech(session_id, "speech.done", {"turn_id": turn_id, "total_samples": total_samples})

    def cancel_speech(self, session_id: str, turn_id: str) -> Dict[str, Any]:
        return self.speech(session_id, "speech.cancel", {"turn_id": turn_id})

    # -- presets ------------------------------------------------------------

    def list_presets(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/presets")

    def create_preset(self, name: str, *,
                      avatar_id: Optional[str] = None,
                      visual_character_id: Optional[str] = None,
                      system_prompt: Optional[str] = None,
                      voice_id: Optional[str] = None,
                      language_code: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name}
        if avatar_id or visual_character_id:
            body["avatar_id"] = avatar_id or visual_character_id
        if system_prompt:
            body["system_prompt"] = system_prompt
        if voice_id:
            body["voice_id"] = voice_id
        if language_code:
            body["language_code"] = language_code
        return self._request("POST", "/api/v2/presets", body)

    def get_preset(self, preset_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v2/presets/{_esc(preset_id)}")

    def update_preset(self, preset_id: str, **patch: Any) -> Dict[str, Any]:
        return self._request("PATCH", f"/api/v2/presets/{_esc(preset_id)}", patch)

    def delete_preset(self, preset_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v2/presets/{_esc(preset_id)}")

    # -- instances ----------------------------------------------------------

    def list_instances(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v2/instances")

    # -- plumbing -----------------------------------------------------------

    def _request(self, method: str, path: str,
                 body: Optional[Dict[str, Any]] = None, *,
                 raw: Optional[bytes] = None,
                 content_type: str = "application/json",
                 headers: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": content_type,
                "User-Agent": "anva-python/0.6.0",
                **(headers or {}),
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            err = {}
            code, message = "request_failed", raw.decode(errors="replace")[:300]
            try:
                payload = json.loads(raw)
                err = payload.get("error") or payload
                code = err.get("code", code)
                message = err.get("message", message)
            except (AttributeError, TypeError, ValueError):
                pass
            raise AnvaError(e.code, code, message, err if isinstance(err, dict) else {}) from None


def _esc(part: str) -> str:
    return urllib.parse.quote(str(part), safe="")
