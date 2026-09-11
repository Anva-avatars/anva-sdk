# Changelog

## Unreleased

- Realtime connections authenticate with an `Authorization` header instead of
  putting the API key in the WebSocket URL. Python `connect()` and JS `connect()`
  switch automatically; Go callers dial `EventsWSURL` with `AuthHeader()`.
- Deprecated: `events_url` / `eventsUrl` / `EventsURL`. They still work, and warn
  (Python `DeprecationWarning`, Node `DeprecationWarning`, Go `Deprecated:`).
- JS: a custom `WebSocketImpl` is now constructed as `new WebSocketImpl(url, { headers })`.
- `max_duration_seconds` / `maxDurationSeconds` / `MaxDurationSeconds` on session
  creation (60–7200). Requires a deployment with session duration limits.

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
