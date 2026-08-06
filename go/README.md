# anva — Go SDK

Official Go SDK for [Anva](https://anva.ai) — live AI avatars.
Standard library only.

```bash
go get github.com/Anva-avatars/anva-sdk/go
```

```go
import anva "github.com/Anva-avatars/anva-sdk/go"

client := anva.New(os.Getenv("ANVA_KEY"))

// Embed tier: start from a preset saved in the Playground.
session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    PresetID: "preset_...",
})
// session.EmbedURL → your frontend

_ = client.SendMessage(ctx, session.SessionID, "Welcome!")

presets, _ := client.ListPresets(ctx)

// live events: connect any WebSocket client to
// client.EventsURL(session.SessionID)
```

Advanced tier — skip presets and pass an avatar plus an inline persona
(nothing is stored server-side):

```go
session, err := client.CreateSession(ctx, anva.CreateSessionParams{
    AvatarID:     "avatar_...",
    SystemPrompt: "You are a friendly guide.",
    VoiceID:      "voice_...",
    LanguageCode: "en-US",
})
```

Errors are `*anva.Error` with `Status`, `Code`, `Message`. MIT © Penguin Robotics
