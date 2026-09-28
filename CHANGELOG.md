# Changelog

All notable changes to the SDKs are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
SemVer. Server-side API changes are announced in the Anva dashboard.
Release steps are in RELEASING.md.

## Unreleased

## 0.7.0 — 2026-09-29

- Speech API (Enterprise): `synthesize` / `synthesize` / `Synthesize`
  (`POST /speech`) turns text into 24 kHz Anva TTS audio plus the 24 ARKit
  mouth curves measured on it, with optional character alignment. The SDKs
  decode the audio (`Uint8Array` / `bytes` / `[]byte`). Types: JS
  `SpeechResult`, Python `SpeechResult` (a TypedDict), Go `SpeechResult`.
- Speech stream (Enterprise): `connectSpeech` / `connect_speech` and Go
  `NewSpeechStream` with `SpeechStreamURL` (`/speech/stream`) speak lines over
  one socket with `speak(id, text)`, `cancel(id)` and `close()`, yielding
  `ready`, `curves`, `audio` (PCM decoded to bytes), `alignment`, `done`,
  `cancelled` and `error`. Curves arrive before their audio; one line at a
  time (`busy_line`); the server closes a stream idle for 60 seconds.
- Queued host lines: `queue: true` / `queue=True` / `LineOptions{Queue: true}`
  on REST `say`, socket `say` and a streamed line's first `sayDelta`
  (Go: new `SayWith` and `SayDeltaWith`). A queued line waits for the one
  being spoken instead of interrupting it; a ninth waiting line gets an `error`
  `say_queue_full`.
- TypeScript: `LineEnded` gains `reason` (`completed`, `host_interrupt`,
  `new_line`, `user_message`, `barge_in`, `playback_unconfirmed`, `failed`,
  `session_ended`) and `status: "failed"`; `spoken_until_ms` is now optional
  (absent when the session ended mid-line). New `Transcript` (`say_id`,
  `interrupted`), `SessionError` (`say_id`; codes including `say_id_reused`
  and `say_queue_full`), `SessionEnded` / `SessionEndReason` (`ended_by_host`,
  `client_disconnect`, `viewer_left`, `max_duration`, `idle`,
  `credits_exhausted`, `billing_unavailable`, `core_disconnected`,
  `session_closed`) and `SpeechState` (`control.speech_state`, which no longer
  carries `duration_ms`; the SDK never typed it). `getSession` types
  `end_reason`.
- Server changes these releases follow (anva.ai since 2026-09-28): a session
  ended with `DELETE` now reports `ended_by_host` (was `session_closed`), the
  face stream (`controls`) reaches only the events socket and no longer the
  embed page, the Lipsync API runs eight clips and streams at once per account
  (was two) and closes a stream after 60 seconds without audio or a command,
  and new HTTP error codes `speech_busy`, `speech_concurrency_limit`,
  `speech_failed`, `speech_unavailable`, `voice_unavailable` and
  `text_too_long` arrive as `AnvaError` / `*anva.Error` codes.

## 0.6.0 — 2026-09-27

- `speech_speed` / `speechSpeed` / `SpeechSpeed` on session creation: the
  speaking rate (0.7–1.2) for anva_light and byo_llm voices.
- `wake_up` / `wakeUp` / `WakeUp` on session creation: the call starts with the
  avatar's eyes closed and they open once the viewer's video is showing.
  `session.info` reports `wake_up: false` for avatars that cannot close their
  eyes convincingly.
- Retry-safe session creation: `idempotencyKey` / `idempotency_key` /
  `IdempotencyKey` is sent as the `Idempotency-Key` header, so a retry with the
  same key and body within 24 hours returns the first session.
- Change a managed session's instructions mid-call: `updateSession` /
  `update_session` / `UpdateSession` (`PATCH /sessions/{id}`), and
  `updatePrompt` / `update_prompt` / `UpdatePrompt` on a realtime connection
  (`session.update`).
- Per-line speaking rate for host lines: `say(..., {speed})` / `say(...,
  speed=)` / `SayAtSpeed`, on the REST call and on the socket, including the
  first delta of a streamed line (`SayDeltaAtSpeed` in Go).
- Events without the face stream: `connect(id, {controls: false})` /
  `connect(id, controls=False)` / `EventsWSURL(id, WithoutControls())`.
- TypeScript: `SessionUsage` (the `usage` on `getSession`) and `LineEnded`
  (the `line.ended` event) types.

## Integrations — 2026-09-20

- Published to PyPI: `pip install livekit-plugins-anva` and
  `pip install pipecat-anva`. Both verified against production anva.ai — the
  avatar joins a real LiveKit Cloud room and speaks the agent's words, and the
  Pipecat service returns the avatar's video and voice into the pipeline.
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
