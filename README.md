# Anva SDKs

Clients for Anva's session, billing, capability and realtime-control APIs.
API keys and authenticated sockets belong on your backend; give browsers only
the returned `embed_url` for WebRTC audio/video.

Install SDK **0.8.1**:

| Language | Install | Import |
|---|---|---|
| Python | `pip install "anva[ws]==0.8.1"` | `from anva import Anva` |
| JavaScript / TypeScript | `npm install anva-sdk@0.8.1` | `import { Anva } from "anva-sdk"` |
| Go | `go get github.com/Anva-avatars/anva-sdk/go@v0.8.1` | `import anva "github.com/Anva-avatars/anva-sdk/go"` |

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
| `anva_light` (Anva Realtime Lite) | User interaction and instructions; speaking-rate control | 60 |
| `anva_standard` (Anva Realtime, the default) | User interaction and instructions | 70 |
| `anva_expressive` (Anva Realtime Expressive) | User interaction and instructions | 80 |
| `elevenagents_max` | User interaction and agent configuration | 120 |

A session that names no mode is `anva_standard` (Anva Realtime): Anva's newest
voice model, in 85 languages, with no speaking-rate control. `anva_light`
(Anva Realtime Lite) has the lowest managed price and the speaking-rate control
(`speech_speed`, per-line `speed`), in 32 languages; a session that sets
`speech_speed` and names no mode is created as `anva_light`. The voice
performance modes (`performance_mode`) are `fast` (Lite), `standard`
(Realtime) and `expressive`; each managed mode pins its own.

Before 1 October 2026 a session without a mode was `anva_light` at 60
tokens/minute. Pass `anva_light` to keep that voice and price.

Always check `capabilities().modes` for deployment availability; each row
carries `default` (the mode a session gets when it names none) and
`speech_speed` (whether it has a speaking-rate control). Billing comes
from the server, not these SDK constants; legacy accounts retain their own unit
and contract. `GET /billing` returns the account view directly. Creating a mode
that is unknown, inconsistent or unavailable fails with a structured API error.

## Start a managed conversation

```js
import { Anva } from "anva-sdk";
const client = new Anva(process.env.ANVA_KEY);
const capabilities = await client.capabilities();
const mode = capabilities.modes.find(item => item.id === "anva_standard");
if (!mode?.available) throw new Error(mode?.reason || "Mode unavailable");
const session = await client.createSession({
  presetId: "YOUR_PRESET_ID", serviceMode: "anva_standard"
});
// Embed session.embed_url with microphone and autoplay permission.
```

Omitting `serviceMode` gives the same session: Anva Realtime is the default.
For a speaking rate, use Anva Realtime Lite:

```js
const slower = await client.createSession({
  presetId: "YOUR_PRESET_ID", serviceMode: "anva_light", speechSpeed: 0.9
});
```

`anva_standard` with `speechSpeed`, or a per-line `speed` on `say` /
`sayDelta` sent to a session using its voice, is refused with
`400 speed_unsupported` ("Anva Realtime (anva_standard) has no speaking-rate
control; use anva_light"): an `AnvaError` / `*anva.Error` from `createSession`
and REST `say`, and an `error` event with that code on the socket. A line
refused this way produces no `line.ended`.

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
`turnCancel`, `say`, `sayDelta`, `sayDone`, `updatePrompt`, `updateContext`,
`startPresentation`, and PCM methods; `connect(id, {controls: false})` leaves
out the per-frame face stream. Python has the
same methods in snake_case.

Any other command goes through the generic send. `activate` takes a prepared
(`standby=1`) session live: its conversation, the viewer's microphone and
billing start, and the socket reports `session.activated`. Until then the
session takes only `context.update`, `action` and `activate`, and one not
activated within 120 seconds ends with `standby_expired`.

| SDK | Activate on the socket |
|---|---|
| JavaScript | `await stream.send("activate")` |
| Python | `stream.send("activate")` |
| Go | `stream.Send("activate", map[string]any{})` |

The REST equivalent, `POST /api/v2/sessions/{id}/activate`, has no SDK method
yet (see [Not in the SDK yet](#not-in-the-sdk-yet)). Go's `NewRealtime(socket)` accepts a connection
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

`say(text, sayId?, {speed?})` speaks a line of your own in the session voice
without a `turn.request`; stream one with `sayDelta(sayId, text)` and
`sayDone(sayId)` (put `speed`, 0.7–1.2, on the first delta). The line's
`turn.complete` carries its `say_id`, and it ends with one `line.ended` saying
what the viewer heard, with a `status` (`completed`, `interrupted` or
`failed`) and a `reason` (`completed`, `host_interrupt`, `new_line`,
`user_message`, `barge_in`, `playback_unconfirmed`, `failed` or
`session_ended`); `interrupt()` or a new `say_id` stops it. REST has
`say(sessionId, text, {sayId, speed, queue})` too.

`{queue: true}` (Python `queue=True`, Go `LineOptions{Queue: true}` with
`SayWith` / `SayDeltaWith`) makes a line wait until the one being spoken has
finished instead of interrupting it; on a streamed line put it on the first
delta. At most 8 lines wait: one more gets an `error` event
`{code: "say_queue_full", say_id}` and never plays. `interrupt()` clears the
queue, and each waiting line gets its `line.ended`. A `say_id` is single-use:
reusing a finished one gets `say_id_reused`. `updateSession(id, {systemPrompt})`
(or `updatePrompt` on the socket) changes a managed session's instructions
mid-call, and `createSession({..., idempotencyKey})` makes a retried create
return the first session.

```js
const session = await client.createSession({
  avatarId: "AVATAR_ID", serviceMode: "byo_llm", speechInput: "off"
});
// Hand session.embed_url to the learner's browser.
const stream = await client.connect(session.session_id);
await stream.live;
await stream.say("Welcome to lesson three.", "lesson-3");
await stream.say("Take your time.", "lesson-3-hint", { queue: true }); // plays after lesson-3
await stream.message(transcribedLearnerText); // comes back as a turn.request
```

A host line's captions (`transcript`) carry its `say_id`, and a line cut short
ends with a final caption `{interrupted: true}` of what was heard. A session
that ends mid-line sends each open line's `line.ended` (`reason:
"session_ended"`) before `session.ended`, whose `reason` is `ended_by_host`
(your `endSession`), `client_disconnect`, `viewer_left`, `max_duration`,
`idle`, `standby_expired` (a prepared session not activated within 120
seconds; never billed), `credits_exhausted`, `billing_unavailable`,
`core_disconnected`, `connection_ended` or `session_closed`; treat an unknown
one like `session_closed`. The face stream
(`controls`) is sent only on the events socket, never to the embed page.

## Lipsync API (Enterprise)

`lipsync(audio, {sampleRate?, preset?})` returns the 24 ARKit mouth curves at
30 fps for a WAV, FLAC or OGG clip, or for raw 16-bit mono PCM when
`sampleRate` is given. `connectLipsync({sampleRate: 16000})` streams PCM in with
`audio(bytes)` and `flush()`, and yields `ready`, `frames`, `flushed` and
`error` messages. Python has `lipsync()` and `connect_lipsync()`; Go has
`Lipsync()`, and `LipsyncStreamURL()` with `NewLipsyncStream(socket)`. The API
is billed at 10 tokens per minute of audio. An account runs up to eight clips
and streams at once (`429 lipsync_concurrency_limit` past that); keep one
stream open across lines and `flush()` between them, and know that a stream
with no audio or command for 60 seconds is closed after an `idle_timeout`
error.

## Speech API (Enterprise)

`synthesize(text, {voiceId, speed?, preset?, format?})` turns text into Anva
TTS audio (24 kHz, 16-bit mono) plus the same 24 ARKit mouth curves as the
Lipsync API, measured on that audio: sample `s` plays at `s / 24000` seconds
and frame `n` describes the mouth at `n / 30` seconds. The SDK decodes the
audio for you (`audio.data` is a `Uint8Array`, Python `bytes`, Go `[]byte`).
`voiceId` must be a voice from `listVoices()`; `format` is `"wav"` (default)
or `"pcm"`.

```js
import { writeFile } from "node:fs/promises";
const line = await client.synthesize("Welcome back. Shall we pick up where we left off?", {
  voiceId: "elevenlabs:JBFqnCBsd6RMkjVDRZzb",
});
await writeFile("line.wav", line.audio.data);
const { fps, channels, frames } = line.curves;
const jaw = channels.indexOf("jawOpen");
frames.forEach((row, n) => rig.setAt(n / fps, "jawOpen", row[jaw])); // your renderer
```

`connectSpeech({voiceId?, speed?, preset?})` keeps one socket open for many
lines: `speak(id, text, opts?)`, `cancel(id)` and `close()`, and iterate for
`ready`, `curves`, `audio` (PCM decoded to bytes), `alignment`, `done`,
`cancelled` and `error`. A line's curves always arrive **before** the audio
they describe, so buffer curves until their audio plays. One line is spoken at
a time: a `speak` while a line runs is refused with `busy_line`, so wait for
its `done` or `cancel` it. A stream that gets no command for 60 seconds while
nothing is spoken is closed after an `idle_timeout` error.

```js
const speech = await client.connectSpeech({ voiceId: "elevenlabs:JBFqnCBsd6RMkjVDRZzb" });
await speech.speak("line-1", "Hello there.");
for await (const msg of speech) {
  if (msg.type === "curves") rig.queueCurves(msg.start, msg.values);
  if (msg.type === "audio") player.enqueue(msg.data); // 24 kHz s16le mono
  if (msg.type === "done" || msg.type === "error") break; // breaking closes the stream
}
```

Python has `synthesize()` and `connect_speech()`; Go has `Synthesize()`, and
`SpeechStreamURL()` with `NewSpeechStream(socket)`. Billing is per minute of
audio generated (`capabilities().speech.tokens_per_minute`). An account holds
four Speech requests and streams at once (`429 speech_concurrency_limit`);
other errors are `text_too_long` (over 2,000 characters or 180 seconds of
audio), `invalid_voice`, `voice_unavailable` (pick another voice),
`speech_busy` (retry after `Retry-After`), `speech_failed` (retry) and
`speech_unavailable` (not on this deployment).

## Not in the SDK yet

These API features have no SDK method in 0.8.1. Call the REST API directly
(`https://anva.ai/api/v2`, `Authorization: Bearer <key>`); the
[API docs](https://anva.ai/docs) give the requests and responses.

- Custom voices (Enterprise): design (`POST /voices/designs`), save or clone
  (`POST /voices`), read (`GET /voices/{id}`) and delete
  (`DELETE /voices/{id}`). `listVoices()` returns your own voices first but
  takes no filters.
- Voice catalogue filters: `GET /voices?language=&accent=&gender=&age=&tone=&q=&owned=true`.
- Standby activation over REST: `POST /sessions/{id}/activate` (on the socket,
  send `activate` with the generic send, as above).
- The `livekit` block on `POST /sessions` (the LiveKit integration,
  `livekit-plugins-anva`, sends it for you).
- Avatar creation (Enterprise): `/avatar-creations` and
  `/avatar-creations/capabilities`.
- Instances: create (`POST /instances`), read (`GET /instances/{id}`), rename
  (`PATCH /instances/{id}`) and delete (`DELETE /instances/{id}`);
  `listInstances()` exists.

## Validation

```sh
node --test js/test/*.test.js
PYTHONPATH=python/src python3 -m unittest discover -s python/tests
(cd go && go test ./...)
```

Tests use fake sockets and local HTTP fixtures. No provider calls are made.
