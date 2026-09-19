"""An Anva avatar as a LiveKit Agents avatar session.

The agent does what it already does: listens, thinks, speaks. Its speech goes
to the avatar participant over the room's data stream instead of straight to
the room, and the avatar publishes the face and the voice together, in sync.
On Anva's side that is an ``avatar_only`` session: Anva supplies no voice of
its own, only the lip-synced video for the audio it is given.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

import aiohttp

from livekit import api, rtc
from livekit.agents import (
    DEFAULT_API_CONNECT_OPTIONS,
    NOT_GIVEN,
    AgentSession,
    APIConnectionError,
    APIConnectOptions,
    APIStatusError,
    NotGivenOr,
    get_job_context,
    utils,
)
from livekit.agents.voice.avatar import AvatarSession as BaseAvatarSession, DataStreamAudioOutput
from livekit.agents.voice.room_io import ATTRIBUTE_PUBLISH_ON_BEHALF

from .log import logger

DEFAULT_API_URL = "https://anva.ai"
DEFAULT_AVATAR_IDENTITY = "anva-avatar"
DEFAULT_AVATAR_NAME = "Anva avatar"


class AnvaException(Exception):
    """Anva could not start or run the avatar."""


class AvatarSession(BaseAvatarSession):
    """An Anva avatar session.

    Exactly one of ``avatar_id`` (an avatar from your Anva account) or
    ``preset_id`` (a saved preset, whose voice and prompt are ignored here
    because the agent speaks) is required. The API key comes from
    ``api_key`` or ``ANVA_API_KEY``.
    """

    def __init__(
        self,
        *,
        avatar_id: NotGivenOr[str] = NOT_GIVEN,
        preset_id: NotGivenOr[str] = NOT_GIVEN,
        api_url: NotGivenOr[str] = NOT_GIVEN,
        api_key: NotGivenOr[str] = NOT_GIVEN,
        avatar_participant_identity: NotGivenOr[str] = NOT_GIVEN,
        avatar_participant_name: NotGivenOr[str] = NOT_GIVEN,
        max_duration_seconds: NotGivenOr[int] = NOT_GIVEN,
        metadata: NotGivenOr[dict[str, Any]] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> None:
        super().__init__()
        self._avatar_id = avatar_id or os.getenv("ANVA_AVATAR_ID") or None
        self._preset_id = preset_id or None
        if bool(self._avatar_id) == bool(self._preset_id):
            raise AnvaException("give exactly one of avatar_id (or ANVA_AVATAR_ID) and preset_id")
        self._api_url = (api_url or os.getenv("ANVA_API_URL", DEFAULT_API_URL)).rstrip("/")
        self._api_key = api_key or os.getenv("ANVA_API_KEY")
        if not self._api_key:
            raise AnvaException("api_key is required: pass it or set ANVA_API_KEY")
        self._avatar_participant_identity = avatar_participant_identity or DEFAULT_AVATAR_IDENTITY
        self._avatar_participant_name = avatar_participant_name or DEFAULT_AVATAR_NAME
        self._max_duration_seconds = max_duration_seconds or None
        self._metadata = metadata or None
        self._conn_options = conn_options
        self._http_session: aiohttp.ClientSession | None = None
        self._owns_http_session = False
        self._session_id: str | None = None

    @property
    def avatar_identity(self) -> str:
        return self._avatar_participant_identity

    @property
    def provider(self) -> str:
        return "anva"

    @property
    def session_id(self) -> str | None:
        """The Anva session behind this avatar, once started."""
        return self._session_id

    def _ensure_http_session(self) -> aiohttp.ClientSession:
        if self._http_session is None:
            try:
                self._http_session = utils.http_context.http_session()
            except RuntimeError:
                # Outside a job (a script, a test) there is no shared session.
                self._http_session = aiohttp.ClientSession()
                self._owns_http_session = True
        return self._http_session

    async def start(
        self,
        agent_session: AgentSession,
        room: rtc.Room,
        *,
        livekit_url: NotGivenOr[str] = NOT_GIVEN,
        livekit_api_key: NotGivenOr[str] = NOT_GIVEN,
        livekit_api_secret: NotGivenOr[str] = NOT_GIVEN,
    ) -> None:
        await super().start(agent_session, room)

        livekit_url = livekit_url or (os.getenv("LIVEKIT_URL") or NOT_GIVEN)
        livekit_api_key = livekit_api_key or (os.getenv("LIVEKIT_API_KEY") or NOT_GIVEN)
        livekit_api_secret = livekit_api_secret or (os.getenv("LIVEKIT_API_SECRET") or NOT_GIVEN)
        if not livekit_url or not livekit_api_key or not livekit_api_secret:
            raise AnvaException(
                "livekit_url, livekit_api_key and livekit_api_secret must be set, "
                "by argument or by the LIVEKIT_URL, LIVEKIT_API_KEY and LIVEKIT_API_SECRET variables"
            )

        job_ctx = get_job_context(required=False)
        local_identity = (
            job_ctx.local_participant_identity if job_ctx is not None else room.local_participant.identity
        )
        # The avatar joins as an agent participant publishing on behalf of this
        # agent: that attribute is how LiveKit front ends pair the two.
        livekit_token = (
            api.AccessToken(api_key=livekit_api_key, api_secret=livekit_api_secret)
            .with_kind("agent")
            .with_identity(self._avatar_participant_identity)
            .with_name(self._avatar_participant_name)
            .with_grants(api.VideoGrants(room_join=True, room=room.name))
            .with_attributes({ATTRIBUTE_PUBLISH_ON_BEHALF: local_identity})
            .to_jwt()
        )

        logger.debug("starting Anva avatar session", extra={"room": room.name})
        await self._create_session(livekit_url, livekit_token)

        # The agent's speech now goes to the avatar, and the agent waits for
        # the avatar's video before it speaks its first word.
        agent_session.output.replace_audio_tail(
            DataStreamAudioOutput(
                room=room,
                destination_identity=self._avatar_participant_identity,
                wait_remote_track=rtc.TrackKind.KIND_VIDEO,
            )
        )

    def _session_body(self, livekit_url: str, livekit_token: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "service_mode": "avatar_only",
            "livekit": {"url": livekit_url, "token": livekit_token},
        }
        if self._avatar_id:
            body["avatar_id"] = self._avatar_id
        else:
            body["preset_id"] = self._preset_id
        if self._max_duration_seconds:
            body["max_duration_seconds"] = self._max_duration_seconds
        if self._metadata:
            body["metadata"] = self._metadata
        return body

    async def _create_session(self, livekit_url: str, livekit_token: str) -> None:
        """Ask Anva to join the room. Anva answers once the avatar is in it."""
        assert self._api_key is not None
        body = self._session_body(livekit_url, livekit_token)
        last_error: Exception | None = None
        for attempt in range(self._conn_options.max_retry):
            try:
                async with self._ensure_http_session().post(
                    f"{self._api_url}/api/v2/sessions",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    json=body,
                    timeout=aiohttp.ClientTimeout(total=90, sock_connect=self._conn_options.timeout),
                ) as response:
                    if response.status == 201:
                        data = await response.json()
                        self._session_id = data.get("session_id")
                        logger.info(
                            "Anva avatar joined the room",
                            extra={"session_id": self._session_id, "livekit": data.get("livekit")},
                        )
                        return
                    text = await response.text()
                    # 4xx other than capacity is about the request; say so at once.
                    if 400 <= response.status < 500 and response.status not in (408, 429):
                        raise AnvaException(f"Anva refused the session ({response.status}): {text}")
                    retry_after = response.headers.get("Retry-After")
                    last_error = APIStatusError(
                        "Anva could not start the session", status_code=response.status, body=text
                    )
                    logger.warning(
                        "Anva session not started yet",
                        extra={"status": response.status, "retry_after": retry_after, "body": text[:300]},
                    )
                    if attempt < self._conn_options.max_retry - 1:
                        await asyncio.sleep(
                            float(retry_after) if retry_after and retry_after.isdigit()
                            else self._conn_options.retry_interval
                        )
                        continue
            except AnvaException:
                raise
            except Exception as e:  # noqa: BLE001
                last_error = e
                logger.warning("could not reach the Anva API", extra={"error": str(e)})
                if attempt < self._conn_options.max_retry - 1:
                    await asyncio.sleep(self._conn_options.retry_interval)
        raise APIConnectionError(f"failed to start the Anva avatar session: {last_error}")

    async def aclose(self) -> None:
        # Ending the Anva session is what stops its billing; leaving the room
        # alone would stop it too, a reconnect grace later.
        if self._session_id and self._api_key:
            try:
                async with self._ensure_http_session().delete(
                    f"{self._api_url}/api/v2/sessions/{self._session_id}",
                    headers={"Authorization": f"Bearer {self._api_key}"},
                    timeout=aiohttp.ClientTimeout(total=15),
                ) as response:
                    if response.status >= 400:
                        logger.debug("Anva session already ended", extra={"status": response.status})
            except Exception:  # noqa: BLE001
                logger.debug("could not end the Anva session", exc_info=True)
            self._session_id = None
        if self._owns_http_session and self._http_session is not None:
            await self._http_session.close()
            self._http_session = None
        await super().aclose()
