"""The service inside a Pipecat pipeline, against the fake Anva."""
from __future__ import annotations

import numpy as np
import pytest
from pipecat.frames.frames import (
    InterruptionFrame,
    OutputImageRawFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    TTSStoppedFrame,
)
from pipecat.tests.utils import SleepFrame, run_test

from pipecat_anva import AnvaVideoService
from pipecat_anva.session import CORE_RATE

from .fake_anva import FakeAnva
from .test_session import tone


@pytest.mark.asyncio
async def test_tts_audio_becomes_the_avatars_picture_and_voice():
    anva = FakeAnva()
    base = await anva.start()
    service = AnvaVideoService(api_key="k", avatar_id="av_1", api_url=base)
    sent = [TTSAudioRawFrame(audio=tone(0.4, 16000), sample_rate=16000, num_channels=1) for _ in range(3)]
    try:
        down, _ = await run_test(
            service,
            frames_to_send=[TTSStartedFrame(), *sent, TTSStoppedFrame(), SleepFrame(2.0)],
        )
    finally:
        await anva.stop()

    assert anva.created[0]["body"]["service_mode"] == "avatar_only"
    assert anva.commands_of("speech.start")[0]["turn_id"] == "pipecat-1"
    total = sum(a["samples"] for a in anva.commands_of("speech.append"))
    assert abs(total - int(1.2 * CORE_RATE)) <= 64
    assert anva.commands_of("speech.done") == [{"turn_id": "pipecat-1", "total_samples": total}]

    assert any(isinstance(f, TTSStartedFrame) for f in down), "the start of speech is passed on"
    assert not any(isinstance(f, TTSStoppedFrame) for f in down), "the pipeline's own audio and its end stop here"
    images = [f for f in down if isinstance(f, OutputImageRawFrame)]
    assert len(images) >= 5 and images[0].size == (160, 120) and images[0].format == "RGB"
    assert len(images[0].image) == 160 * 120 * 3
    audio = [f for f in down if isinstance(f, TTSAudioRawFrame)]
    assert audio, "the avatar's voice comes back as audio"
    assert all(f.sample_rate == 16000 and f.num_channels == 1 for f in audio), "at the pipeline's TTS rate"
    assert not any(f.audio in {s.audio for s in sent} for f in audio), "and it is the avatar's, not the copy"
    samples = np.frombuffer(b"".join(f.audio for f in audio), dtype=np.int16)
    assert samples.size >= 16000 and np.abs(samples).max() > 3000, "a second or more of a real tone"
    assert anva.deleted == ["apisess-1"], "the end of the pipeline ends the Anva session"


@pytest.mark.asyncio
async def test_an_interruption_stops_the_avatar():
    anva = FakeAnva()
    base = await anva.start()
    service = AnvaVideoService(api_key="k", avatar_id="av_1", api_url=base)
    try:
        await run_test(
            service,
            frames_to_send=[
                TTSStartedFrame(),
                TTSAudioRawFrame(audio=tone(0.5, CORE_RATE), sample_rate=CORE_RATE, num_channels=1),
                SleepFrame(0.5),
                InterruptionFrame(),
                SleepFrame(0.5),
            ],
        )
    finally:
        await anva.stop()
    assert [c["turn_id"] for c in anva.commands_of("speech.cancel")] == ["pipecat-1"]
    assert not anva.commands_of("speech.done")
