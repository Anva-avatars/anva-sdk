# Anva SDKs

Official SDKs for [Anva](https://anva.ai) — live AI avatars for your product.
Turn a photo into a talking avatar your audience can speak with, then serve
it from your own stack.

| Language | Install | Docs |
|---|---|---|
| Python | `pip install anva` | [python/](python/) |
| JavaScript / TypeScript | `npm install anva` | [js/](js/) |
| Go | `go get github.com/C-L-2013/anva-sdk/go` | [go/](go/) |

All three are thin, dependency-free clients over the same REST API
(`https://anva.ai/api/v1`), authenticated with an API key from your
[dashboard](https://anva.ai/dashboard/keys).

## The 60-second version

```python
from anva import Anva

client = Anva("anva_key_...")
session = client.create_session(character_id="char_...")
print(session["embed_url"])   # drop into an <iframe allow="camera; microphone; autoplay">

client.send_message(session["session_id"], "Welcome to the demo!")

for event in client.events(session["session_id"]):   # pip install anva[ws]
    print(event)              # {"type": "transcript", "role": "user", "text": "..."}
```

```js
import { Anva } from "anva";

const client = new Anva(process.env.ANVA_KEY);
const session = await client.createSession({ characterId: "char_..." });
// hand session.embed_url to your frontend

for await (const event of client.events(session.session_id)) {
  console.log(event);
}
```

```go
client := anva.New(os.Getenv("ANVA_KEY"))
session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    CharacterID: "char_...",
})
// session.EmbedURL → your frontend; client.EventsURL(id) → any WebSocket lib
```

## What you can do

- **Sessions** — create (returns an iframe-ready `embed_url`), inspect, end.
- **Speak** — `send_message` makes the avatar say something; `interrupt`
  stops it mid-sentence; `trigger_action` fires character actions.
- **Live events** — a WebSocket stream of transcripts and state changes.
- **Characters** — list, create, fetch and delete characters programmatically.

Keep your API key server-side: mint sessions on your backend and hand only
the `embed_url` to browsers.

## License

MIT © Penguin Robotics
