"""The plugin's side of the contract, against a real LiveKit server.

A stand-in for Anva's API receives the plugin's request, checks the token it
minted and joins the room the way Anva's node does, publishing a video track.
Run `livekit-server --dev` and set LIVEKIT_TEST_URL=ws://127.0.0.1:7880.
"""
from __future__ import annotations

import asyncio
import os
import time

import jwt
import pytest
from aiohttp import web
from livekit import api, rtc
from livekit.agents import AgentSession
from livekit.agents.voice.avatar import DataStreamAudioOutput

from livekit.plugins.anva import AnvaException, AvatarSession

LIVEKIT_URL = os.getenv("LIVEKIT_TEST_URL")
KEY, SECRET = os.getenv("LIVEKIT_TEST_KEY", "devkey"), os.getenv("LIVEKIT_TEST_SECRET", "secret")


def test_one_avatar_reference_and_a_key_are_required(monkeypatch):
    monkeypatch.delenv("ANVA_API_KEY", raising=False)
    monkeypatch.delenv("ANVA_AVATAR_ID", raising=False)
    with pytest.raises(AnvaException, match="exactly one"):
        AvatarSession(api_key="k")
    with pytest.raises(AnvaException, match="exactly one"):
        AvatarSession(avatar_id="a", preset_id="p", api_key="k")
    with pytest.raises(AnvaException, match="ANVA_API_KEY"):
        AvatarSession(avatar_id="a")
    monkeypatch.setenv("ANVA_API_KEY", "from-env")
    monkeypatch.setenv("ANVA_AVATAR_ID", "av_env")
    session = AvatarSession(metadata={"lesson": "3"}, max_duration_seconds=600)
    body = session._session_body("wss://rooms.example", "tok")
    assert body == {
        "service_mode": "avatar_only",
        "livekit": {"url": "wss://rooms.example", "token": "tok"},
        "avatar_id": "av_env",
        "max_duration_seconds": 600,
        "metadata": {"lesson": "3"},
    }
    monkeypatch.delenv("ANVA_AVATAR_ID")
    assert AvatarSession(preset_id="p", api_key="k")._session_body("u", "t")["preset_id"] == "p"
    assert session.provider == "anva" and session.avatar_identity == "anva-avatar"


class FakeAnva:
    """Anva's API as the plugin sees it, joining the room as the avatar."""

    def __init__(self) -> None:
        self.requests: list[dict] = []
        self.deleted: list[str] = []
        self.room: rtc.Room | None = None
        self.app = web.Application()
        self.app.router.add_post("/api/v2/sessions", self.create)
        self.app.router.add_delete("/api/v2/sessions/{id}", self.delete)

    async def create(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.requests.append({"auth": request.headers.get("Authorization"), "body": body})
        target = body["livekit"]
        self.room = rtc.Room()
        await self.room.connect(target["url"], target["token"])
        source = rtc.VideoSource(320, 240)
        track = rtc.LocalVideoTrack.create_video_track("anva-video", source)
        await self.room.local_participant.publish_track(
            track, rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_CAMERA)
        )
        return web.json_response(
            {"session_id": "apisess-test", "status": "active", "livekit": {
                "room": self.room.name, "participant_identity": self.room.local_participant.identity}},
            status=201,
        )

    async def delete(self, request: web.Request) -> web.Response:
        self.deleted.append(request.match_info["id"])
        return web.json_response({"session_id": request.match_info["id"], "status": "ended"})


@pytest.mark.skipif(not LIVEKIT_URL, reason="LIVEKIT_TEST_URL not set")
@pytest.mark.asyncio
async def test_avatar_joins_the_room_on_behalf_of_the_agent():
    anva = FakeAnva()
    runner = web.AppRunner(anva.app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    room_name = "anva-plugin-" + time.strftime("%H%M%S")

    agent_room = rtc.Room()
    agent_token = (
        api.AccessToken(api_key=KEY, api_secret=SECRET)
        .with_identity("agent-under-test")
        .with_kind("agent")
        .with_grants(api.VideoGrants(room_join=True, room=room_name))
        .to_jwt()
    )
    await agent_room.connect(LIVEKIT_URL, agent_token)
    agent_session = AgentSession()
    avatar = AvatarSession(avatar_id="av_test", api_key="test-key", api_url=f"http://127.0.0.1:{port}")
    try:
        await avatar.start(agent_session, agent_room,
                           livekit_url=LIVEKIT_URL, livekit_api_key=KEY, livekit_api_secret=SECRET)
        await avatar.wait_for_join(timeout=20)

        assert avatar.session_id == "apisess-test"
        request = anva.requests[0]
        assert request["auth"] == "Bearer test-key"
        assert request["body"]["service_mode"] == "avatar_only" and request["body"]["avatar_id"] == "av_test"
        assert request["body"]["livekit"]["url"] == LIVEKIT_URL
        # The token the plugin minted lets Anva join this room, as an agent
        # participant publishing on behalf of the agent.
        token = request["body"]["livekit"]["token"]
        claims = api.TokenVerifier(KEY, SECRET).verify(token)
        assert claims.identity == "anva-avatar"
        assert claims.video.room == room_name and claims.video.room_join
        assert claims.attributes == {"lk.publish_on_behalf": "agent-under-test"}
        raw = jwt.decode(token, SECRET, algorithms=["HS256"], options={"verify_aud": False})
        assert raw["kind"] == "agent"
        # The agent's speech is routed to the avatar participant.
        assert isinstance(agent_session.output.audio, DataStreamAudioOutput)
        assert anva.room is not None and anva.room.name == room_name
    finally:
        await avatar.aclose()
        assert anva.deleted == ["apisess-test"]
        if anva.room is not None:
            await anva.room.disconnect()
        await agent_room.disconnect()
        await runner.cleanup()


@pytest.mark.asyncio
async def test_refusals_are_not_retried_and_outages_are():
    calls = {"n": 0}
    app = web.Application()

    async def refuse(request: web.Request) -> web.Response:
        calls["n"] += 1
        return web.json_response({"error": {"code": "livekit_requires_avatar_only", "message": "no"}}, status=400)

    app.router.add_post("/api/v2/sessions", refuse)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]  # noqa: SLF001
    avatar = AvatarSession(avatar_id="av_test", api_key="k", api_url=f"http://127.0.0.1:{port}")
    try:
        with pytest.raises(AnvaException, match="400"):
            await avatar._create_session("wss://x", "t")
        assert calls["n"] == 1, "a refused request must not be retried"
    finally:
        await avatar.aclose()
        await runner.cleanup()
