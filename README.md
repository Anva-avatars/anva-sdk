# Anva SDKs

Official SDKs for [Anva](https://anva.ai) — live AI avatars for your product.
Turn a photo into a talking avatar your audience can speak with, then serve
it from your own stack.

| Language | Install | Docs |
|---|---|---|
| Python | `pip install anva` | [python/](python/) |
| JavaScript / TypeScript | `npm install anva-sdk` | [js/](js/) |
| Go | `go get github.com/Anva-avatars/anva-sdk/go` | [go/](go/) |

All three are thin, dependency-free clients over the same REST API
(`https://anva.ai/api/v2`), authenticated with an API key from your
[dashboard](https://anva.ai/dashboard/keys).

## The 60-second version

```python
from anva import Anva

client = Anva("anva_key_...")
session = client.create_session(preset_id="preset_...")
print(session["embed_url"])   # drop into an <iframe allow="camera; microphone; autoplay">

client.send_message(session["session_id"], "Welcome to the demo!")

for event in client.events(session["session_id"]):   # pip install anva[ws]
    print(event)              # {"type": "transcript", "role": "user", "text": "..."}
```

```js
import { Anva } from "anva-sdk";

const client = new Anva(process.env.ANVA_KEY);
const session = await client.createSession({ presetId: "preset_..." });
// hand session.embed_url to your frontend

for await (const event of client.events(session.session_id)) {
  console.log(event);
}
```

```go
client := anva.New(os.Getenv("ANVA_KEY"))
session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    PresetID: "preset_...",
})
// session.EmbedURL → your frontend; client.EventsURL(id) → any WebSocket lib
```

## Two ways to start a session

`create_session` accepts **either** a saved preset **or** an avatar plus an
inline persona:

- **Embed tier** — pass a `preset_id` (a persona you saved in the Playground).
- **Advanced tier** — pass an `avatar_id` and supply the persona
  (`system_prompt`, `voice_id`, `language_code`) inline; nothing is stored
  server-side.

```python
session = client.create_session(
    avatar_id="avatar_...",
    system_prompt="You are a friendly guide.",
    voice_id="voice_...",
    language_code="en-US",
)
```

```js
const session = await client.createSession({
  avatarId: "avatar_...",
  systemPrompt: "You are a friendly guide.",
  voiceId: "voice_...",
  languageCode: "en-US",
});
```

```go
session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    AvatarID:     "avatar_...",
    SystemPrompt: "You are a friendly guide.",
    VoiceID:      "voice_...",
    LanguageCode: "en-US",
})
```

## What you can do

- **Sessions** — create (returns an iframe-ready `embed_url`), inspect, end.
- **Speak** — `send_message` makes the avatar say something; `interrupt`
  stops it mid-sentence; `trigger_action` fires avatar actions.
- **Live events** — a WebSocket stream of transcripts and state changes.
- **Presets** — list, create, fetch and delete saved personas (avatar +
  system prompt + voice) programmatically.
- **Instances** — list per-key usage buckets (the Python and JS clients
  expose `list_instances` / `listInstances`).

Keep your API key server-side: mint sessions on your backend and hand only
the `embed_url` to browsers.

## License

MIT © Penguin Robotics
