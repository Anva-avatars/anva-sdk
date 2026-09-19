"""Anva avatars for LiveKit Agents.

    from livekit.plugins import anva

    avatar = anva.AvatarSession(avatar_id="av_...")
    await avatar.start(session, room=ctx.room)

The avatar joins the room as its own participant and speaks whatever the
agent says, with the lips in time. The agent keeps its own STT, LLM and TTS.
"""
from .avatar import AnvaException, AvatarSession
from .version import __version__

__all__ = ["AvatarSession", "AnvaException", "__version__"]

from livekit.agents import Plugin

from .log import logger


class AnvaPlugin(Plugin):
    def __init__(self) -> None:
        super().__init__(__name__, __version__, __package__, logger)


Plugin.register_plugin(AnvaPlugin())
