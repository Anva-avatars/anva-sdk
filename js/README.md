# anva — JavaScript / TypeScript SDK

Official JS/TS SDK for [Anva](https://anva.ai) — live AI avatars.
ESM, zero dependencies, typed. Node 18+ and modern browsers (keep your API
key server-side; hand only the `embed_url` to clients).

```bash
npm install anva
```

```js
import { Anva } from "anva";

const client = new Anva(process.env.ANVA_KEY);

const session = await client.createSession({ characterId: "char_..." });
console.log(session.embed_url);

await client.sendMessage(session.session_id, "Welcome!");

for await (const event of client.events(session.session_id)) {
  console.log(event);
}
```

Errors throw `AnvaError` with `.status` and `.code`. MIT © Penguin Robotics
