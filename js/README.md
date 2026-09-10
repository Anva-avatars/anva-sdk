# anva-sdk — JavaScript / TypeScript

Install with `npm install anva-sdk@0.3.0`. REST uses Node 18+'s fetch. Realtime needs
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

Inject WebSocket on older Node: `client.connect(id, {WebSocketImpl})`. Keep keys
and sockets server-side. `AnvaError` exposes `status`, `code`, and `details`;
command errors arrive as structured events. Never log authenticated event URLs.

All five canonical modes, capability/billing discovery, REST interrupt,
presentation and PCM methods are typed in `index.d.ts`. Read the repository
README for mode availability and flow-control requirements. Preset updates use
the REST API's snake_case patch fields.
