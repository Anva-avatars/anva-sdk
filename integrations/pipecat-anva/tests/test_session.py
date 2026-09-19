"""The session on its own: what it sends Anva and what it makes of the answers."""
from __future__ import annotations

import asyncio

import numpy as np
import pytest

from pipecat_anva import AnvaError, AnvaSession
from pipecat_anva.session import CHUNK_SAMPLES, CORE_RATE, Utterance

from .fake_anva import FakeAnva


def tone(seconds: float, rate: int, channels: int = 1) -> bytes:
    t = np.arange(int(seconds * rate)) / rate
    mono = (np.sin(2 * np.pi * 300 * t) * 6000).astype(np.int16)
    return (np.repeat(mono, channels) if channels > 1 else mono).tobytes()


def test_one_avatar_reference_and_a_key_are_required():
    with pytest.raises(AnvaError, match="exactly one"):
        AnvaSession(api_key="k")
    with pytest.raises(AnvaError, match="exactly one"):
        AnvaSession(api_key="k", avatar_id="a", preset_id="p")
    with pytest.raises(AnvaError, match="api_key"):
        AnvaSession(api_key="", avatar_id="a")
    AnvaSession(api_key="k", preset_id="p", api_url="https://anva.ai/")


def test_utterances_are_taken_in_chunks_and_the_tail_only_when_closed():
    u = Utterance(turn_id="t")
    u.push(b"\0\0" * (CHUNK_SAMPLES + 10))
    assert len(u.take()) == CHUNK_SAMPLES * 2
    assert u.take() == b"", "a partial chunk waits for more audio"
    u.close()
    assert len(u.take()) == 20
    assert u.take() == b""
    u.cancel()
    u.push(b"\0\0" * 5)
    assert u.take() == b"" and u.cancelled


def test_pipeline_audio_is_converted_to_what_anva_takes():
    s = AnvaSession(api_key="k", avatar_id="a")
    u = s.begin_utterance()
    s.push_audio(u, tone(0.5, 48000, 2), 48000, 2)
    s.push_audio(u, tone(0.25, 48000, 2), 48000, 2)
    s.end_utterance(u)
    assert abs(u.pushed - int(0.75 * CORE_RATE)) <= 64
    # Native audio is taken as it is, sample for sample.
    v = s.begin_utterance()
    s.push_audio(v, tone(0.1, CORE_RATE), CORE_RATE, 1)
    assert v.pushed == int(0.1 * CORE_RATE)


@pytest.mark.asyncio
async def test_speech_reaches_anva_as_turns_with_receipts():
    anva = FakeAnva()
    base = await anva.start()
    frames: list = []

    async def on_video(frame):
        frames.append(frame)

    session = AnvaSession(api_key="key-1", avatar_id="av_1", api_url=base, metadata={"k": "v"},
                          on_video=on_video)
    try:
        await session.start()
        assert anva.created[0]["auth"] == "Bearer key-1"
        assert anva.created[0]["body"] == {"service_mode": "avatar_only", "avatar_id": "av_1", "metadata": {"k": "v"}}
        assert anva.ws_auth == "Bearer key-1"
        assert anva.offers[0]["session_id"] == "apisess-1" and anva.offers[0]["session_url_token"] == "anva_gr_test"
        assert anva.offers[0]["type"] == "offer" and anva.offers[0]["client_generation"] == 1

        u = session.begin_utterance()
        session.push_audio(u, tone(1.2, 16000), 16000, 1)
        session.end_utterance(u)
        for _ in range(100):
            if anva.commands_of("speech.done"):
                break
            await asyncio.sleep(0.05)
        starts = anva.commands_of("speech.start")
        assert starts == [{"turn_id": "pipecat-1", "codec": "pcm_s16le", "sample_rate": CORE_RATE, "channels": 1}]
        appends = anva.commands_of("speech.append")
        assert [a["seq"] for a in appends] == list(range(len(appends)))
        assert all(a["samples"] <= CHUNK_SAMPLES for a in appends)
        total = sum(a["samples"] for a in appends)
        assert abs(total - int(1.2 * CORE_RATE)) <= 64
        assert anva.commands_of("speech.done") == [{"turn_id": "pipecat-1", "total_samples": total}]

        # An interruption cancels what is playing and drops what waits.
        second = session.begin_utterance()
        session.push_audio(second, tone(3, CORE_RATE), CORE_RATE, 1)
        third = session.begin_utterance()
        session.push_audio(third, tone(1, CORE_RATE), CORE_RATE, 1)
        for _ in range(100):
            if any(a["turn_id"] == "pipecat-2" for a in anva.commands_of("speech.append")):
                break
            await asyncio.sleep(0.05)
        await session.interrupt()
        for _ in range(100):
            if anva.commands_of("speech.cancel"):
                break
            await asyncio.sleep(0.05)
        assert [c["turn_id"] for c in anva.commands_of("speech.cancel")] == ["pipecat-2"]
        await asyncio.sleep(0.3)
        assert not any(c["payload"].get("turn_id") == "pipecat-3" for c in anva.commands), \
            "a queued utterance dropped by the interruption must never start"

        # The viewer receives the avatar's picture.
        for _ in range(100):
            if len(frames) >= 3:
                break
            await asyncio.sleep(0.05)
        assert len(frames) >= 3 and frames[0].width == 160 and frames[0].height == 120
    finally:
        await session.close()
        await anva.stop()
    assert anva.deleted == ["apisess-1"]
    assert session.ended.is_set()


@pytest.mark.asyncio
async def test_a_refusal_is_an_error_not_a_hang():
    anva = FakeAnva()
    anva.refuse_with = 503
    base = await anva.start()
    session = AnvaSession(api_key="k", avatar_id="a", api_url=base)
    try:
        with pytest.raises(AnvaError, match="503"):
            await session.start()
    finally:
        await session.close()
        await anva.stop()
