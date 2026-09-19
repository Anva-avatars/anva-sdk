# Anva avatars for Pipecat

Give your Pipecat voice agent a face. The pipeline keeps its own STT, LLM and
TTS; `AnvaVideoService` sits after the TTS, sends its audio to Anva and pushes
back the avatar's video and voice, lips in time, as ordinary output frames for
whatever transport you use: Daily, LiveKit, WebRTC, anything with video out.

```sh
pip install pipecat-anva
```

```python
from pipecat_anva import AnvaVideoService

anva = AnvaVideoService(api_key=os.environ["ANVA_API_KEY"], avatar_id="av_...")

pipeline = Pipeline([
    transport.input(),
    stt,
    context_aggregator.user(),
    llm,
    tts,
    anva,                     # after the TTS, before the transport
    transport.output(),
    context_aggregator.assistant(),
])
```

Give the transport video out at the avatar's size, for example with Daily:

```python
DailyParams(video_out_enabled=True, video_out_width=480, video_out_height=480, ...)
```

Anva renders 480×480 at 25 fps by default. The service does not scale the
picture; set `video_out_width`/`video_out_height` to what the avatar sends
or let your transport scale it.

## What happens

1. On pipeline start the service creates an Anva `avatar_only` session with
   your API key, opens its events socket and connects a WebRTC viewer to it,
   the way Anva's embed player does. Nothing is billed until the viewer is
   connected.
2. `TTSAudioRawFrame`s are converted to what Anva's lip-sync takes (24 kHz
   mono PCM) and sent as one utterance per `TTSStartedFrame` /
   `TTSStoppedFrame`. The pipeline's own copy of the audio stops at the
   service.
3. The avatar's video comes back as `OutputImageRawFrame`s (RGB) and its
   voice as `TTSAudioRawFrame`s at the pipeline's TTS sample rate, in sync.
4. An `InterruptionFrame` stops the avatar mid-sentence and drops what was
   queued.
5. `EndFrame` / `CancelFrame` end the Anva session, which is what stops the
   billing.

Sending is paced by Anva's playback reports: the service keeps at most four
seconds of unplayed audio in flight, so a long answer is never front-loaded.

## Options

| Argument | Meaning |
|---|---|
| `api_key` | Anva API key (anva.ai → API keys). The events socket needs the Developer plan or above. |
| `avatar_id` / `preset_id` | Exactly one. A preset's voice and prompt do not apply: the pipeline speaks. |
| `api_url` | Anva base URL (`https://anva.ai`). |
| `max_duration_seconds` | End the Anva session this long after it goes live. |
| `metadata` | Echoed on Anva's session and webhooks. |

A refused session (wrong avatar, plan limits, no capacity) is reported with
`push_error`; the pipeline keeps running without a face.

## Tests

The tests run against a stand-in for Anva, no account needed:

```sh
pip install -e . pytest pytest-asyncio
python -m pytest tests
```
