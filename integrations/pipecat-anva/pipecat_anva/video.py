"""Anva as a Pipecat video service.

Sits after the TTS in the pipeline. The TTS audio goes to Anva instead of the
transport; what comes back is the avatar's video and its audio, in sync, which
the service pushes downstream as ordinary output frames for whatever transport
the pipeline uses -- Daily, LiveKit, a phone line's video, a browser.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
from av.audio.resampler import AudioResampler
from pipecat.frames.frames import (
    CancelFrame,
    EndFrame,
    Frame,
    InterruptionFrame,
    OutputImageRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.processors.frame_processor import FrameDirection, FrameProcessorSetup
from pipecat.services.ai_service import AIService
from pipecat.services.settings import ServiceSettings

from .session import AnvaSession, Utterance


@dataclass
class AnvaVideoSettings(ServiceSettings):
    """Settings for the Anva video service."""


class AnvaVideoService(AIService):
    """Anva video service: a lip-synced avatar for the pipeline's TTS.

    Consumes ``TTSAudioRawFrame``s and produces ``OutputImageRawFrame``s and
    ``TTSAudioRawFrame``s carrying the avatar's synchronized video and audio.
    An interruption stops the avatar mid-sentence.
    """

    Settings = AnvaVideoSettings
    _settings: Settings

    def __init__(
        self,
        *,
        api_key: str,
        avatar_id: str | None = None,
        preset_id: str | None = None,
        api_url: str = "https://anva.ai",
        max_duration_seconds: int | None = None,
        metadata: dict[str, Any] | None = None,
        settings: Settings | None = None,
        **kwargs,
    ):
        """Create the service.

        Args:
            api_key: Anva API key.
            avatar_id: An avatar from your Anva account. Exactly one of this and preset_id.
            preset_id: A saved preset. Its voice and prompt do not apply: the pipeline speaks.
            api_url: Anva base URL.
            max_duration_seconds: End the Anva session this long after it goes live.
            metadata: Echoed on the Anva session and its webhooks.
            settings: Service settings.
            **kwargs: Passed to AIService.
        """
        default_settings = ServiceSettings(model=None)
        if settings is not None:
            default_settings.apply_update(settings)
        super().__init__(settings=default_settings, **kwargs)
        self._session = AnvaSession(
            api_key=api_key, avatar_id=avatar_id, preset_id=preset_id, api_url=api_url,
            max_duration_seconds=max_duration_seconds, metadata=metadata,
            on_video=self._on_video, on_audio=self._on_audio,
            task_factory=self.create_task, task_cancel=self.cancel_task,
        )
        self._utterance: Utterance | None = None
        self._out_rate = 24000
        self._out_resampler: AudioResampler | None = None
        self._out_key: tuple[int, int] | None = None
        self._started = False

    async def setup(self, setup: FrameProcessorSetup):
        await super().setup(setup)
        await self._start_connection()

    async def stop(self, frame: EndFrame):
        await super().stop(frame)
        await self._stop_connection()

    async def cancel(self, frame: CancelFrame):
        await super().cancel(frame)
        await self._stop_connection()

    async def cleanup(self):
        await super().cleanup()
        await self._stop_connection()

    async def _start_connection(self):
        if self._started:
            return
        try:
            await self._session.start()
            self._started = True
        except Exception as e:  # noqa: BLE001
            await self.push_error(error_msg=f"Unable to start the Anva avatar: {e}", exception=e)

    async def _stop_connection(self):
        if not self._started:
            return
        self._started = False
        await self._session.close()

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if not self._started:
            # No avatar: the pipeline speaks on its own.
            await self.push_frame(frame, direction)
            return
        if isinstance(frame, TTSStartedFrame):
            self._utterance = self._session.begin_utterance()
        elif isinstance(frame, TTSAudioRawFrame):
            # The avatar's own audio comes back in sync with its face; the
            # pipeline's copy stops here.
            self._out_rate = frame.sample_rate
            if self._utterance is None:
                self._utterance = self._session.begin_utterance()
            self._session.push_audio(self._utterance, frame.audio, frame.sample_rate, frame.num_channels)
            return
        elif isinstance(frame, TTSStoppedFrame):
            if self._utterance is not None:
                self._session.end_utterance(self._utterance)
                self._utterance = None
            return
        elif isinstance(frame, InterruptionFrame):
            await self._session.interrupt()
            self._utterance = None
        await self.push_frame(frame, direction)

    async def _on_video(self, frame) -> None:
        rgb = frame.to_ndarray(format="rgb24")
        await self.push_frame(OutputImageRawFrame(image=rgb.tobytes(), size=(frame.width, frame.height), format="RGB"))

    async def _on_audio(self, frame) -> None:
        key = (frame.sample_rate, self._out_rate)
        if self._out_key != key:
            self._out_resampler = AudioResampler("s16", "mono", self._out_rate)
            self._out_key = key
        assert self._out_resampler is not None
        for out in self._out_resampler.resample(frame):
            samples = out.to_ndarray().astype(np.int16)
            if samples.any():
                await self.push_frame(TTSAudioRawFrame(audio=samples.tobytes(), sample_rate=self._out_rate, num_channels=1))

    def __repr__(self) -> str:
        return f"AnvaVideoService(session={self._session.session_id})"


__all__ = ["AnvaVideoService", "AnvaVideoSettings"]
