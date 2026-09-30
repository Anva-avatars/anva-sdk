# Anva Go SDK

Standard-library REST client and a bidirectional wrapper for your chosen
WebSocket library. Install with
`go get github.com/Anva-avatars/anva-sdk/go@v0.8.1`.

```go
import (
    "context"
    "os"
    anva "github.com/Anva-avatars/anva-sdk/go"
)

client := anva.New(os.Getenv("ANVA_KEY"))
session, err := client.CreateSession(context.Background(), anva.CreateSessionParams{
    PresetID: "YOUR_PRESET_ID", ServiceMode: anva.AnvaStandard,
})
if err != nil { panic(err) }
// Attach session.EmbedURL in your frontend.
```

`Capabilities` and `Billing` return decoded maps. Service modes are `AvatarOnly`,
`BYOLLM`, `AnvaLight`, `AnvaStandard`, `AnvaExpressive`, and `ElevenAgentsMax`. The
server resolves availability, conflicts and billing. A session with no
`ServiceMode` is `AnvaStandard` (Anva Realtime, 70 tokens/minute), which has no
speaking-rate control: for `SpeechSpeed` or a per-line speed use `AnvaLight`
(Anva Realtime Lite), otherwise the server answers `speed_unsupported` (a 400
`*anva.Error`, or an `error` event on the socket). `PerformanceFast`,
`PerformanceStandard` and `PerformanceExpressive` name the voice performance
modes. `LLMMode` remains a deprecated alias.

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
`Realtime.Say` / `SayDelta` / `SayDone` speak lines of your own (BYOLLM);
`SayAtSpeed` / `SayDeltaAtSpeed` set a line's rate. `Client.UpdateSession` and
`Realtime.UpdatePrompt` change a managed session's instructions mid-call,
`CreateSessionParams.IdempotencyKey` makes a retried create return the first
session, and `EventsWSURL(id, anva.WithoutControls())` leaves out the face
stream.
`Client.SayWith` and `Realtime.SayWith` / `SayDeltaWith` take
`anva.LineOptions{Speed, Queue}`; `Queue: true` makes a line wait behind the
one being spoken instead of interrupting it.
`Client.Lipsync` returns a clip's mouth curves; stream with
`NewLipsyncStream(socket)` dialled at `client.LipsyncStreamURL(16000, "")` with
`client.AuthHeader()` (Enterprise; up to eight jobs at once per account, and a
stream idle for 60 seconds is closed).

Speech API (Enterprise): text to 24 kHz speech plus its mouth curves.

```go
line, err := client.Synthesize(ctx, anva.SpeechParams{
    Text: "Welcome back.", VoiceID: "elevenlabs:JBFqnCBsd6RMkjVDRZzb",
})
if err != nil { return err }
os.WriteFile("line.wav", line.Audio.Data, 0o644) // decoded bytes
// line.Curves.Frames[n][i] is line.Curves.Channels[i] at n/30 s.

conn, _, err := websocket.DefaultDialer.Dial(
    client.SpeechStreamURL(anva.SpeakOptions{VoiceID: "elevenlabs:JBFqnCBsd6RMkjVDRZzb"}),
    client.AuthHeader())
if err != nil { return err }
speech := anva.NewSpeechStream(conn)
defer speech.Close()
speech.Speak("line-1", "Hello there.", anva.SpeakOptions{})
for {
    ev, err := speech.Receive()
    if err != nil { return err }
    switch ev.Type {
    case "curves": queueCurves(ev.Start, ev.Values) // before their audio
    case "audio":  play(ev.Data)                    // 24 kHz s16le mono
    case "done", "error": return nil
    }
}
```

One line is spoken at a time per stream (`busy_line` otherwise; `Cancel(id)`
stops one), and the server closes a stream that gets no command for 60 seconds
while nothing is spoken.

A prepared (`standby=1`) session goes live with
`stream.Send("activate", map[string]any{})`; one not activated within 120
seconds ends with `standby_expired`. Not in the SDK yet: custom voices (design, save/clone, read, delete), voice catalogue filters,
standby activation over REST (`POST /sessions/{id}/activate`), the `livekit`
block on create session, avatar creation, and instance create/read/rename/delete
have no SDK method yet: call the REST API directly (see the repository README,
"Not in the SDK yet").

Errors are `*anva.Error` with `Status`, `Code`, `Message`. See the repository
README for protocol details.
