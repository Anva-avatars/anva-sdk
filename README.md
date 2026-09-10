# Anva SDKs

Clients for Anva's session, billing, capability and realtime-control APIs.
API keys and authenticated sockets belong on your backend; give browsers only
the returned `embed_url` for WebRTC audio/video.

Install SDK **0.3.0**:

| Language | Install | Import |
|---|---|---|
| Python | `pip install "anva[ws]==0.3.0"` | `from anva import Anva` |
| JavaScript / TypeScript | `npm install anva-sdk@0.3.0` | `import { Anva } from "anva-sdk"` |
| Go | `go get github.com/Anva-avatars/anva-sdk/go@v0.3.0` | `import anva "github.com/Anva-avatars/anva-sdk/go"` |

The production base defaults to `https://anva.ai`. Set `base_url`, `baseUrl`, or
`Client.BaseURL` to your updated deployment for local integration.

## Modes

Select `service_mode` at creation. Python uses `service_mode`, JS
`serviceMode`, and Go `ServiceMode`. It is pinned to the session grant.

| Mode | Input supplied by your app | Token-plan rate / connected minute |
|---|---|---:|
| `avatar_only` | PCM voice audio; you supply LLM/voice/transcription | 10 |
| `byo_llm` | Text deltas for requested turns | 50 |
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
Use `byo_llm` with `turnDelta` / `turnDone` for your AI's replies. The old `say`
command is unavailable. Do not create a fake user message for a greeting; managed
presentation uses `updateContext`, its acknowledgement, then `startPresentation`.

## One socket for events and commands

```js
const stream = await client.connect(session.session_id);
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

`connect` gives access to `message`, `interrupt`, `turnDelta`, `turnDone`,
`turnCancel`, `updateContext`, `startPresentation`, and PCM methods. Python has the
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

## Validation

```sh
node --test js/test/*.test.js
PYTHONPATH=python/src python3 -m unittest discover -s python/tests
(cd go && go test ./...)
```

Tests use fake sockets and local HTTP fixtures. No provider calls are made.
