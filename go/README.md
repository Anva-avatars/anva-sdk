# Anva Go SDK

Standard-library REST client and a bidirectional wrapper for your chosen
WebSocket library. Install with
`go get github.com/Anva-avatars/anva-sdk/go@v0.5.0`.

```go
import (
    "context"
    "os"
    anva "github.com/Anva-avatars/anva-sdk/go"
)

client := anva.New(os.Getenv("ANVA_KEY"))
session, err := client.CreateSession(context.Background(), anva.CreateSessionParams{
    PresetID: "YOUR_PRESET_ID", ServiceMode: anva.AnvaLight,
})
if err != nil { panic(err) }
// Attach session.EmbedURL in your frontend.
```

`Capabilities` and `Billing` return decoded maps. Service modes are `AvatarOnly`,
`BYOLLM`, `AnvaLight`, `AnvaExpressive`, and `ElevenAgentsMax`. The server resolves
availability, conflicts and billing. `LLMMode` remains a deprecated alias.

Connect a WebSocket to `client.EventsWSURL(session.SessionID)` on your backend,
sending `client.AuthHeader()` with the handshake (for Gorilla:
`websocket.DefaultDialer.Dial(client.EventsWSURL(id), client.AuthHeader())`),
then use `stream := anva.NewRealtime(socket)`. `EventsURL`, which puts the key in
the query string, is deprecated. The socket implements `ReadJSON`,
`WriteJSON`, `Close`. `stream.Receive()` reads an envelope; `TurnDelta`, `TurnDone`,
`TurnCancel`, `Interrupt`, `UpdateContext`, `StartPresentation`, and speech methods
send commands on the same socket. Writers are serialized; use one event reader.

Speech uses `StartSpeech(turnID, text)`,
`AppendSpeech(turnID, seq, startSample, pcmBytes)`,
`FinishSpeech(turnID, totalSamples)` and `CancelSpeech(turnID)`. Text may be empty.
Raw PCM must be signed16 little-endian, 24kHz mono. Chunks are at most 24,000 bytes;
observe `speech.state` and bound unplayed audio to five seconds. Closing the
control socket does not end a session; call `EndSession` when finished.

The events socket never starts a session; call `stream.WaitLive()` before
sending commands. `CreateSessionParams.SpeechInput = "off"` suits hosts that
transcribe the user themselves (push-to-talk). `Client.Say` and
`Realtime.Say` / `SayDelta` / `SayDone` speak lines of your own (BYOLLM).
`Client.Lipsync` returns a clip's mouth curves; stream with
`NewLipsyncStream(socket)` dialled at `client.LipsyncStreamURL(16000, "")` with
`client.AuthHeader()` (Enterprise).

Errors are `*anva.Error` with `Status`, `Code`, `Message`. See the repository
README for protocol details.
