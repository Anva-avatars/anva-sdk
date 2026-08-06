# anva — JavaScript / TypeScript SDK

Official JS/TS SDK for [Anva](https://anva.ai) — live AI avatars.
ESM, zero dependencies, typed. Node 18+ and modern browsers (keep your API
key server-side; hand only the `embed_url` to clients).

```bash
npm install anva-sdk
```

```js
import { Anva } from "anva-sdk";

const client = new Anva(process.env.ANVA_KEY);

// Embed tier: start from a preset saved in the Playground.
const session = await client.createSession({ presetId: "preset_..." });
console.log(session.embed_url);

await client.sendMessage(session.session_id, "Welcome!");

for await (const event of client.events(session.session_id)) {
  console.log(event);
}

const presets = await client.listPresets();
```

Advanced tier — skip presets and pass an avatar plus an inline persona
(nothing is stored server-side):

```js
const session = await client.createSession({
  avatarId: "avatar_...",
  systemPrompt: "You are a friendly guide.",
  voiceId: "voice_...",
  languageCode: "en-US",
});
```

Errors throw `AnvaError` with `.status` and `.code`. MIT © Penguin Robotics
