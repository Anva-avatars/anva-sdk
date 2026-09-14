# Changelog

All notable changes to the SDKs are recorded here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
SemVer. Server-side API changes are announced in the Anva dashboard.
Release steps are in RELEASING.md.

## Unreleased

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
