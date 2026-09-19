# Anva SDKs

Clients for Anva's session, billing, capability and realtime-control APIs.
API keys and authenticated sockets belong on your backend; give browsers only
the returned `embed_url` for WebRTC audio/video.

Install SDK **0.5.0**:

| Language | Install | Import |
|---|---|---|
| Python | `pip install "anva[ws]==0.5.0"` | `from anva import Anva` |
| JavaScript / TypeScript | `npm install anva-sdk@0.5.0` | `import { Anva } from "anva-sdk"` |
| Go | `go get github.com/Anva-avatars/anva-sdk/go@v0.5.0` | `import anva "github.com/Anva-avatars/anva-sdk/go"` |

The production base defaults to `https://anva.ai`. Set `base_url`, `baseUrl`, or
`Client.BaseURL` to your updated deployment for local integration.

## Voice-agent frameworks

Agents on LiveKit Agents or Pipecat (including Daily) keep their own STT, LLM
and TTS and get an Anva face from a framework package, under
[`integrations/`](integrations/):

| Framework | Install | Use |
|---|---|---|
| LiveKit Agents | `pip install livekit-plugins-anva` | `avatar = anva.AvatarSession(avatar_id="av_..."); await avatar.start(session, room=ctx.room)` |
| Pipecat / Daily | `pip install pipecat-anva` | `AnvaVideoService(api_key=..., avatar_id="av_...")` after the TTS in the pipeline |

Both run an `avatar_only` session (10 tokens per connected minute, Developer
plan or above). Each package has its own README and version.

## Modes

Select `service_mode` at creation. Python uses `service_mode`, JS
`serviceMode`, and Go `ServiceMode`. It is pinned to the session grant.

| Mode | Input supplied by your app | Token-plan rate / connected minute |
|---|---|---:|
| `avatar_only` | PCM voice audio; you supply LLM/voice/transcription | 10 |
| `byo_llm` | Text deltas for requested turns; optionally your own transcriptions (`speech_input: "off"`) and host lines (`say`) | 50 |
| `anva_light` | User interaction and instructions | 60 |
| `anva_expressive` | User interaction and instructions | 80 |
| `elevenagents_max` | User interaction and agent configuration | 120 |

Always check `capabilities().modes` for deployment availability. Billing comes
from the server, not these SDK constants; legacy accounts retain their own unit
and contract. `GET /billing` returns the account view directly. Creating a mode
that is unknown, inconsistent or unavailable fails with a structured API error.

## Start a managed conversation

```js
import { Anva } from "anva-sdk";
const client = new Anva(process.env.ANVA_KEY);
const capabilities = await client.capabilities();
const mode = capabilities.modes.find(item => item.id === "anva_light");
if (!mode?.available) throw new Error(mode?.reason || "Mode unavailable");
const session = await client.createSession({
  presetId: "YOUR_PRESET_ID", serviceMode: "anva_light"
});
// Embed session.embed_url with microphone and autoplay permission.
```

Supply exactly one of a saved preset ID or an avatar ID with optional inline
`systemPrompt`, `voiceId`, and `languageCode`. Deprecated `llmMode` aliases remain
available. The server rejects conflicting canonical and legacy options.

`sendMessage` supplies **user input** to the conversation, not verbatim speech.
Use `byo_llm` with `turnDelta` / `turnDone` for your AI's replies, and `say` to
speak a line of your own — a greeting or a lesson's opening — without a fake
user message. Managed presentation uses `updateContext`, its acknowledgement,
then `startPresentation`.

## One socket for events and commands

```js
const stream = await client.connect(session.session_id);
await stream.live; // the viewer's embed is connected; commands are accepted
try {
  for await (const event of stream) {
    console.log(event.type, event.payload);
    // On a BYO LLM turn.request, generate in a cancellable worker and send:
    // await stream.turnDelta(event.payload.turn_id, textChunk);
    // await stream.turnDone(event.payload.turn_id);
    // On turn.cancel, stop that worker and discard its pending chunks.
  }
} finally {
  stream.close();
  await client.endSession(session.session_id);
}
```

The events socket never starts a session: the viewer's embed does, and billing
runs only while it is connected. The socket reports `session.info` at once and
`session.live` when the viewer is connected; send commands after it (JS
`stream.live`, Python `stream.wait_live()`, Go `stream.WaitLive()`).

`connect` gives access to `message`, `interrupt`, `turnDelta`, `turnDone`,
`turnCancel`, `say`, `sayDelta`, `sayDone`, `updateContext`, `startPresentation`,
and PCM methods. Python has the
same methods in snake_case. Go's `NewRealtime(socket)` accepts a connection
implementing `ReadJSON`, `WriteJSON`, and `Close` (for example Gorilla WebSocket).
The SDK does not add a Go WebSocket dependency. Only one event reader may consume
a socket. Do slow LLM work separately so cancellation events remain responsive.

`events()` remains a receive-only convenience. Closing a control socket does not
end the session. Explicitly call `endSession` when finished.

## PCM voice input

Available only with `avatar_only` and an audio-capable deployment. Supply raw
signed 16-bit little-endian PCM, 24 kHz mono, with no WAV header. Open the media
embed first; an events socket cannot render or acknowledge media playback.

- `startSpeech(turnId, {text?})` sends codec metadata; await `speech.state: started`.
- `appendSpeech(turnId, seq, startSample, pcmBytes)` sends at most 12,000 samples.
- `seq` starts at 0; `startSample` is the exact cumulative sample count.
- `finishSpeech(turnId, totalSamples)` finalizes the accepted total.
- `cancelSpeech(turnId)` abandons the utterance; session `interrupt()` also stops it.

Only one utterance may be active. Keep unplayed audio below five seconds using
`speech.state.accepted_samples` and `played_samples`. `finished` confirms media
playback, not upload completion. Errors remain structured `speech.state` events;
stop the producer instead of blindly retrying old chunks. Optional text is caption
metadata, not a TTS prompt. Use a fresh turn ID after cancellation.

REST equivalents exist on the client for speech, context and presentation. An
HTTP acceptance only forwards a command; keep the event socket open for the
core acknowledgement. See [API docs](https://anva.ai/docs) for envelopes and limits.

## Push-to-talk and host lines (BYO LLM)

If your app transcribes the user itself, create the session with
`speechInput: "off"` (Python `speech_input`, Go `SpeechInput`). The embed then
opens no microphone and no speech recognition runs; send each transcribed turn
with `message` and answer the resulting `turn.request` as usual. A message sent
while the avatar speaks takes the floor.

`say(text, sayId?)` speaks a line of your own in the session voice without a
`turn.request`; stream one with `sayDelta(sayId, text)` and `sayDone(sayId)`.
The line's `turn.complete` carries its `say_id`; `interrupt()` or a new
`say_id` stops it. REST has `say(sessionId, text, {sayId})` too.

```js
const session = await client.createSession({
  avatarId: "AVATAR_ID", serviceMode: "byo_llm", speechInput: "off"
});
// Hand session.embed_url to the learner's browser.
const stream = await client.connect(session.session_id);
await stream.live;
await stream.say("Welcome to lesson three.", "lesson-3");
await stream.message(transcribedLearnerText); // comes back as a turn.request
```

## Lipsync API (Enterprise)

`lipsync(audio, {sampleRate?, preset?})` returns the 24 ARKit mouth curves at
30 fps for a WAV, FLAC or OGG clip, or for raw 16-bit mono PCM when
`sampleRate` is given. `connectLipsync({sampleRate: 16000})` streams PCM in with
`audio(bytes)` and `flush()`, and yields `ready`, `frames`, `flushed` and
`error` messages. Python has `lipsync()` and `connect_lipsync()`; Go has
`Lipsync()`, and `LipsyncStreamURL()` with `NewLipsyncStream(socket)`. The API
is billed at 10 tokens per minute of audio.

## Validation

```sh
node --test js/test/*.test.js
PYTHONPATH=python/src python3 -m unittest discover -s python/tests
(cd go && go test ./...)
```

Tests use fake sockets and local HTTP fixtures. No provider calls are made.
