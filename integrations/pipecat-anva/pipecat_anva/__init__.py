"""Anva avatars for Pipecat.

    from pipecat_anva import AnvaVideoService

    avatar = AnvaVideoService(api_key=..., avatar_id="av_...")
    pipeline = Pipeline([transport.input(), stt, llm, tts, avatar, transport.output()])

The service takes the TTS audio, sends it to Anva, and puts back the avatar's
video and its audio, in sync, for whatever transport the pipeline uses.
"""
from .session import AnvaError, AnvaSession
from .version import __version__
from .video import AnvaVideoService

__all__ = ["AnvaVideoService", "AnvaSession", "AnvaError", "__version__"]
