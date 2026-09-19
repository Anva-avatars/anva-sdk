# Changelog

All notable changes to the SDKs are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
SemVer. Server-side API changes are announced in the Anva dashboard.
Release steps are in RELEASING.md.

## Unreleased

- New framework packages under `integrations/`, versioned on their own:
  `livekit-plugins-anva` 0.1.0 (LiveKit Agents `AvatarSession`: Anva joins the
  room as an avatar participant, following LiveKit's avatar protocol) and
  `pipecat-anva` 0.1.0 (Pipecat `AnvaVideoService`: a lip-synced avatar for
  the pipeline's TTS on any transport, Daily included). Both need an Anva
  deployment with LiveKit room support (anva.ai from the release that ships
  `livekit: {url, token}` on session creation) for the LiveKit package; the
  Pipecat package works with every deployment that offers `avatar_only`.

## 0.5.0 — 2026-09-15

- `speech_input` / `speechInput` / `SpeechInput` on session creation: `"off"`
  for hosts that transcribe the user themselves (push-to-talk). The embed opens
  no microphone; send each user turn with `send_message` / `sendMessage` /
  `SendMessage`.
- Host lines for `byo_llm`: REST `say` / `Say`, and realtime `say`,
  `say_delta` / `sayDelta` / `SayDelta` and `say_done` / `sayDone` / `SayDone`.
  The line's `turn.complete` event carries its `say_id`.
- Waiting for the viewer: the events socket reports `session.live` once the
  viewer's embed is connected, and refuses commands before it. JS
  `RealtimeSession.live` (a promise), Python `RealtimeSession.wait_live()` and
  Go `Realtime.WaitLive()`. Requires a deployment where the events socket no
  longer starts sessions (anva.ai from this release).
- Lipsync API (Enterprise): `lipsync()` / `Lipsync()` for a clip;
  `connect_lipsync()` / `connectLipsync()` and Go `NewLipsyncStream` with
  `LipsyncStreamURL` for streaming PCM.
- JS types: `AvatarInfo` with `icon_url` and `icon_expires_at`, `LipsyncResult`,
  `LipsyncStream`.

## 0.4.0 — 2026-09-12

- Realtime connections authenticate with an `Authorization` header instead of
  putting the API key in the WebSocket URL. Python `connect()` and JS `connect()`
  switch automatically; Go callers dial `EventsWSURL` with `AuthHeader()`.
- Deprecated: `events_url` / `eventsUrl` / `EventsURL`. They still work, and warn
  (Python `DeprecationWarning`, Node `DeprecationWarning`, Go `Deprecated:`).
- JS: a custom `WebSocketImpl` is now constructed as `new WebSocketImpl(url, { headers })`.
- `max_duration_seconds` / `maxDurationSeconds` / `MaxDurationSeconds` on session
  creation (60–7200). Requires a deployment with session duration limits.
- `metadata` on session creation: a flat map echoed on the session,
  `session.info` and every webhook payload. Requires a deployment that
  supports it (anva.ai since 2026-09-14).

## 0.3.0 — 2026-09-11

- Explicit service modes: Avatar Only, BYO LLM, Anva Light, Anva Expressive and ElevenAgents Max.
- Capability discovery and account billing, including per-session billing metadata.
- Bidirectional realtime controls for BYO text turns, interruptions and cancellation.
- Raw PCM speech input helpers with sample offsets, byte validation and completion/cancellation commands.
- Presentation context updates and presentation start controls over REST and WebSocket.
- JavaScript/TypeScript declarations and matching Python and Go interfaces.
- Preserve legacy mode aliases; the server rejects conflicting configuration.

New methods require an updated Anva deployment. Check capabilities before selecting a mode.
Session creation is not media readiness; attach the embed and observe session events.
Keep API keys on the server and explicitly end sessions when finished.
