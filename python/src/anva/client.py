"""Thin, dependency-free client for the Anva REST API.

Every method mirrors one endpoint and returns the decoded JSON body.
Errors raise AnvaError carrying the API's machine-readable code.
The events stream (WebSocket) needs the optional extra: pip install anva[ws].
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Iterator, Optional

from .realtime import RealtimeSession, speech_start, speech_append

DEFAULT_BASE_URL = "https://anva.ai"


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
                       webhook_url: Optional[str] = None,
                       webhook_secret: Optional[str] = None) -> Dict[str, Any]:
        """Create a live session, one of two ways:

        - Embed tier: pass ``preset_id`` (a saved preset from the Playground).
        - Advanced tier: pass ``avatar_id`` plus the persona (``system_prompt``,
          ``voice_id``, ``language_code``) directly — nothing is stored.

        Returns session_id, session_token, embed_url (iframe-ready),
        events_ws_url, instance_id, preset_id, avatar_id.
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
                           "dynamic_expressions": dynamic_expressions}.items():
            if value is not None:
                body[key] = value
        if webhook_url:
            body["webhook_url"] = webhook_url
        if webhook_secret:
            body["webhook_secret"] = webhook_secret
        return self._request("POST", "/api/v2/sessions", body)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v2/sessions/{_esc(session_id)}")

    def end_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v2/sessions/{_esc(session_id)}")

    def send_message(self, session_id: str, text: str) -> Dict[str, Any]:
        """Send ``text`` as a user message; the avatar hears it and replies (it
        does NOT speak ``text`` verbatim). External replies use
        ``service_mode="byo_llm"`` with ``turn_delta`` / ``turn_done`` on a realtime connection."""
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/messages",
            {"text": text})

    def interrupt(self, session_id: str) -> Dict[str, Any]:
        """Stop the avatar mid-sentence."""
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/interrupt", {})

    def trigger_action(self, session_id: str, name: str) -> Dict[str, Any]:
        return self._request(
            "POST", f"/api/v2/sessions/{_esc(session_id)}/actions",
            {"name": name})

    def events_url(self, session_id: str) -> str:
        """The authenticated WebSocket URL for the session's event stream."""
        ws_base = self.base_url.replace("http", "ws", 1)
        return (f"{ws_base}/api/v2/sessions/{_esc(session_id)}/events"
                f"?api_key={urllib.parse.quote(self.api_key)}")

    def connect(self, session_id: str) -> RealtimeSession:
        """Open a bidirectional connection. Requires ``pip install anva[ws]``."""
        try:
            from websockets.sync.client import connect
        except ImportError as e:
            raise RuntimeError("realtime requires pip install anva[ws]") from e
        return RealtimeSession(connect(self.events_url(session_id)))

    def events(self, session_id: str) -> Iterator[Dict[str, Any]]:
        with self.connect(session_id) as stream:
            yield from stream

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
                 body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "anva-python/0.3.0",
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
