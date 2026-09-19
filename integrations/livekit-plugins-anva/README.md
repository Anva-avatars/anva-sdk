# Anva avatars for LiveKit Agents

Give your LiveKit voice agent a face. The agent keeps its own STT, LLM and
TTS; Anva joins the room as a second participant and speaks the agent's words
with the lips in time, video and audio published together.

```sh
pip install livekit-plugins-anva
```

```python
from livekit import agents, rtc
from livekit.agents import Agent, AgentSession
from livekit.plugins import anva, deepgram, openai, silero

async def entrypoint(ctx: agents.JobContext):
    session = AgentSession(
        stt=deepgram.STT(), llm=openai.LLM(), tts=openai.TTS(), vad=silero.VAD.load(),
    )
    avatar = anva.AvatarSession(avatar_id="av_...")   # or preset_id="..."
    await avatar.start(session, room=ctx.room)
    await session.start(agent=Agent(instructions="You are a friendly guide."), room=ctx.room)
```

Set `ANVA_API_KEY` (from anva.ai → API keys) and the usual `LIVEKIT_URL`,
`LIVEKIT_API_KEY` and `LIVEKIT_API_SECRET`. `ANVA_AVATAR_ID` can stand in for
`avatar_id`.

## What happens

1. `start()` mints a room token for the avatar participant (kind `agent`,
   attribute `lk.publish_on_behalf` naming your agent) and asks Anva to create
   an `avatar_only` session that joins your room with it. Anva answers once the
   avatar is in the room with its video and audio tracks published.
2. The agent's audio output is replaced by LiveKit's `DataStreamAudioOutput`,
   so speech goes to the avatar over the room's data stream rather than
   straight to the room. Interruptions and playback receipts use LiveKit's
   standard `lk.clear_buffer`, `lk.playback_started` and
   `lk.playback_finished` RPCs.
3. `aclose()` (called for you when the job shuts down) ends the Anva session.

Billing is Anva's `avatar_only` rate per connected minute. The audio can be any
sample rate and channel count; Anva converts it to what its lip-sync takes.

## Options

| Argument | Meaning |
|---|---|
| `avatar_id` / `preset_id` | Exactly one. A preset's voice and prompt do not apply: the agent speaks. |
| `api_key`, `api_url` | Anva API key and base URL (`https://anva.ai`). |
| `avatar_participant_identity`, `avatar_participant_name` | Defaults `anva-avatar`, `Anva avatar`. |
| `max_duration_seconds` | End the Anva session this long after it goes live. |
| `metadata` | Echoed on Anva's session and webhooks. |
| `conn_options` | LiveKit `APIConnectOptions`: retries and timeouts for the Anva call. |

A `400` from Anva (wrong mode, bad avatar, plan limits) raises `AnvaException`
without retrying; a `503 no_capacity` is retried after Anva's `Retry-After`.

## Front end

Your front end sees two agent participants. LiveKit's components pick the
avatar's tracks automatically; by hand, it is the participant whose
`lk.publish_on_behalf` attribute equals your agent's identity.

## Tests

```sh
livekit-server --dev &
LIVEKIT_TEST_URL=ws://127.0.0.1:7880 python -m pytest tests
```
