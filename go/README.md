# anva — Go SDK

Official Go SDK for [Anva](https://anva.ai) — live AI avatars.
Standard library only.

```bash
go get github.com/C-L-2013/anva-sdk/go
```

```go
import anva "github.com/C-L-2013/anva-sdk/go"

client := anva.New(os.Getenv("ANVA_KEY"))

session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    CharacterID: "char_...",
})
// session.EmbedURL → your frontend

_ = client.SendMessage(ctx, session.SessionID, "Welcome!")

// live events: connect any WebSocket client to
// client.EventsURL(session.SessionID)
```

Errors are `*anva.Error` with `Status`, `Code`, `Message`. MIT © Penguin Robotics
