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

DEFAULT_BASE_URL = "https://anva.ai"


class AnvaError(Exception):
    """API error with the server's machine-readable code and HTTP status."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(f"{code}: {message} (HTTP {status})")
        self.status = status
        self.code = code
        self.message = message


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

    def create_session(self, character_id: str, *, llm_mode: Optional[str] = None,
                       webhook_url: Optional[str] = None,
                       webhook_secret: Optional[str] = None) -> Dict[str, Any]:
        """Create a live session. Returns session_id, session_token,
        embed_url (iframe-ready) and events_ws_url."""
        body: Dict[str, Any] = {"character_id": character_id}
        if llm_mode:
            body["llm_mode"] = llm_mode
        if webhook_url:
            body["webhook_url"] = webhook_url
        if webhook_secret:
            body["webhook_secret"] = webhook_secret
        return self._request("POST", "/api/v1/sessions", body)

    def get_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/sessions/{_esc(session_id)}")

    def end_session(self, session_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v1/sessions/{_esc(session_id)}")

    def send_message(self, session_id: str, text: str) -> Dict[str, Any]:
        """Have the avatar speak `text` to the user."""
        return self._request(
            "POST", f"/api/v1/sessions/{_esc(session_id)}/messages",
            {"text": text})

    def interrupt(self, session_id: str) -> Dict[str, Any]:
        """Stop the avatar mid-sentence."""
        return self._request(
            "POST", f"/api/v1/sessions/{_esc(session_id)}/interrupt", {})

    def trigger_action(self, session_id: str, name: str) -> Dict[str, Any]:
        return self._request(
            "POST", f"/api/v1/sessions/{_esc(session_id)}/actions",
            {"name": name})

    def events_url(self, session_id: str) -> str:
        """The authenticated WebSocket URL for the session's event stream."""
        ws_base = self.base_url.replace("http", "ws", 1)
        return (f"{ws_base}/api/v1/sessions/{_esc(session_id)}/events"
                f"?api_key={urllib.parse.quote(self.api_key)}")

    def events(self, session_id: str) -> Iterator[Dict[str, Any]]:
        """Yield event dicts (transcripts, state changes) as they happen.

        Requires the ws extra: pip install anva[ws]
        """
        try:
            from websockets.sync.client import connect
        except ImportError as e:  # pragma: no cover
            raise RuntimeError(
                "the events stream needs the websockets package: "
                "pip install anva[ws]") from e
        with connect(self.events_url(session_id)) as ws:
            for raw in ws:
                try:
                    yield json.loads(raw)
                except (TypeError, ValueError):
                    continue

    # -- characters ---------------------------------------------------------

    def list_characters(self) -> Dict[str, Any]:
        return self._request("GET", "/api/v1/characters")

    def create_character(self, name: str, *,
                         visual_character_id: Optional[str] = None,
                         system_prompt: Optional[str] = None,
                         voice_id: Optional[str] = None,
                         language_code: Optional[str] = None) -> Dict[str, Any]:
        body: Dict[str, Any] = {"name": name}
        if visual_character_id:
            body["visual_character_id"] = visual_character_id
        if system_prompt:
            body["system_prompt"] = system_prompt
        if voice_id:
            body["voice_id"] = voice_id
        if language_code:
            body["language_code"] = language_code
        return self._request("POST", "/api/v1/characters", body)

    def get_character(self, character_id: str) -> Dict[str, Any]:
        return self._request("GET", f"/api/v1/characters/{_esc(character_id)}")

    def delete_character(self, character_id: str) -> Dict[str, Any]:
        return self._request("DELETE", f"/api/v1/characters/{_esc(character_id)}")

    # -- plumbing -----------------------------------------------------------

    def _request(self, method: str, path: str,
                 body: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(
            self.base_url + path, data=data, method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "User-Agent": "anva-python/0.1.0",
            })
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else {}
        except urllib.error.HTTPError as e:
            raw = e.read()
            code, message = "request_failed", raw.decode(errors="replace")[:300]
            try:
                payload = json.loads(raw)
                err = payload.get("error") or payload
                code = err.get("code", code)
                message = err.get("message", message)
            except (TypeError, ValueError):
                pass
            raise AnvaError(e.code, code, message) from None


def _esc(part: str) -> str:
    return urllib.parse.quote(str(part), safe="")
