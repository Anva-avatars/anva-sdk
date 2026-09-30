# anva-sdk — JavaScript / TypeScript

Install with `npm install anva-sdk@0.8.1`. REST uses Node 18+'s fetch. Realtime needs
Node 22+'s WebSocket or an injected compatible constructor.

```js
import { Anva, AnvaError } from "anva-sdk";
const client = new Anva(process.env.ANVA_KEY);
const capabilities = await client.capabilities();
const session = await client.createSession({
  presetId:"YOUR_PRESET_ID", serviceMode:"byo_llm"
});
// Attach session.embed_url in your browser.
const stream = await client.connect(session.session_id);
await stream.live; // the viewer's embed is connected
try {
  for await (const event of stream) {
    if (event.type === "turn.request") {
      // Replace this immediate sample reply with your cancellable LLM worker.
      await stream.turnDelta(event.payload.turn_id, "Hello from your application.");
      await stream.turnDone(event.payload.turn_id);
    }
  }
} finally {
  stream.close();
  await client.endSession(session.session_id);
}
```

Inject WebSocket on older Node: `client.connect(id, {WebSocketImpl})`; it is
constructed as `new WebSocketImpl(url, { headers })`, which Node's WebSocket and
the `ws` package both accept. The API key travels in the handshake's
`Authorization` header, never the URL (`eventsUrl()` is deprecated). Keep keys
and sockets server-side. `AnvaError` exposes `status`, `code`, and `details`;
command errors arrive as structured events. Never log authenticated event URLs.

A session that names no `serviceMode` is `anva_standard` (Anva Realtime, 70
tokens/minute). It has no speaking-rate control: for `speechSpeed` or a
per-line `speed`, create the session with `serviceMode: "anva_light"` (Anva
Realtime Lite), otherwise the server answers `speed_unsupported` (an
`AnvaError` with status 400, or an `error` event on the socket).

Host lines queue with `say(text, sayId, {queue: true})` (REST
`say(sessionId, text, {sayId, queue: true})`, or `queue` on a streamed line's
first `sayDelta`): the line waits for the one being spoken instead of
interrupting it. The `line.ended` (`reason`, `status: "failed"`), `transcript`
(`say_id`, `interrupted`), `error` (`say_id`) and `session.ended` payloads are
typed as `LineEnded`, `Transcript`, `SessionError` and `SessionEnded`.

## Speech API (Enterprise)

```js
import { writeFile } from "node:fs/promises";
const line = await client.synthesize("Welcome back.", { voiceId: "elevenlabs:JBFqnCBsd6RMkjVDRZzb" });
await writeFile("line.wav", line.audio.data);          // decoded Uint8Array
const jaw = line.curves.channels.indexOf("jawOpen");
const jawAt = n => line.curves.frames[n][jaw];          // frame n is n / 30 s into the audio

const speech = await client.connectSpeech({ voiceId: "elevenlabs:JBFqnCBsd6RMkjVDRZzb" });
await speech.speak("line-1", "Hello there.");
for await (const msg of speech) {
  if (msg.type === "curves") queueCurves(msg.start, msg.values); // before their audio
  if (msg.type === "audio") play(msg.data);                      // 24 kHz s16le mono Uint8Array
  if (msg.type === "done" || msg.type === "error") break;
}
```

One line at a time per stream (`busy_line` otherwise; `cancel(id)` stops one),
and the server closes a stream idle for 60 seconds. Lipsync streams also close
after 60 seconds without audio or a command, and an account runs up to eight
Lipsync jobs at once.

All six canonical modes, capability/billing discovery, REST interrupt,
presentation, PCM, push-to-talk (`speechInput`), host lines (`say`, `sayDelta`,
`sayDone`), Lipsync API (`lipsync`, `connectLipsync`) and Speech API
(`synthesize`, `connectSpeech`) methods are typed in `index.d.ts`. The older
`speech(sessionId, type, payload)` is the avatar_only PCM command, not the
Speech API. Read the repository
README for mode availability and flow-control requirements. Preset updates use
the REST API's snake_case patch fields. `Capabilities` types the `lipsync` and
`speech` blocks, and `SessionEndReason` includes `standby_expired`.

A prepared (`standby=1`) session goes live with `await stream.send("activate")`
on the events socket. Not in the SDK yet: custom voices (design, save/clone, read, delete), voice catalogue filters,
standby activation over REST (`POST /sessions/{id}/activate`), the `livekit`
block on create session, avatar creation, and instance create/read/rename/delete
have no SDK method yet: call the REST API directly (see the repository README,
"Not in the SDK yet").
