/** Official Anva SDK. All API keys and authenticated realtime sockets belong on your server. */
export type ServiceMode = 'avatar_only' | 'byo_llm' | 'anva_light' | 'anva_standard' | 'anva_expressive' | 'elevenagents_max';
/** The voice a session uses: `fast` (anva_light), `standard` (anva_standard, no speaking-rate control) or `expressive`. Each managed mode pins its own. */
export type PerformanceMode = 'fast' | 'standard' | 'expressive' | (string & {});
/** "off": the host transcribes the user and sends text (push-to-talk); no microphone. */
export type SpeechInput = 'on' | 'off';
export interface AnvaOptions { baseUrl?: string; }
export interface PerformanceOptions {
  conversation_provider?: string;
  performance_mode?: PerformanceMode;
  elevenlabs_agent_id?: string;
  dynamic_expressions?: boolean;
  speech_speed?: number;
  wake_up?: boolean;
  [key: string]: unknown;
}
export interface CreateSessionParams {
  presetId?: string;
  avatarId?: string;
  systemPrompt?: string;
  voiceId?: string;
  languageCode?: string;
  /** Omitted, the server uses anva_standard (Anva Realtime, 70 tokens/min), or anva_light when `speechSpeed` is set. */
  serviceMode?: ServiceMode;
  /** Deprecated compatibility alias. Conflicts with serviceMode are rejected by the server. */
  llmMode?: string;
  performanceOptions?: PerformanceOptions;
  conversationProvider?: string;
  performanceMode?: PerformanceMode;
  elevenlabsAgentId?: string;
  dynamicExpressions?: boolean;
  webhookUrl?: string;
  webhookSecret?: string;
  /** Ends the session this many seconds (60–7200) after it goes live. Omitted = the 2-hour ceiling. */
  maxDurationSeconds?: number;
  /** Flat map (string/number/boolean values, ≤20 keys, ≤4 KB) echoed on the session, session.info and webhooks. */
  metadata?: Record<string, string | number | boolean>;
  /** "off" for byo_llm, anva_light, anva_standard or anva_expressive hosts that transcribe the user themselves. */
  speechInput?: SpeechInput;
  /** Speaking rate, 0.7–1.2 (1 is the voice's natural pace). anva_light and byo_llm voices; with no `serviceMode` the session is created as anva_light. anva_standard (or performance mode `standard`) has no speaking-rate control and is refused with 400 `speed_unsupported`. */
  speechSpeed?: number;
  /** Start with the avatar's eyes closed; they open once the viewer's video is showing. session.info reports wake_up false for avatars that cannot close their eyes convincingly. */
  wakeUp?: boolean;
  /** Sent as the Idempotency-Key header (16–128 letters, digits, - or _): a retry with the same key and body within 24 hours returns the first session. */
  idempotencyKey?: string;
}
export interface ModeCapability { id: ServiceMode; name: string; available: boolean; reason?: string; input?: string[];
  /** True on the mode a session gets when it names none. */
  default?: boolean;
  /** Whether the mode has a speaking-rate control (`speechSpeed`, per-line `speed`). */
  speech_speed?: boolean;
  [key: string]: unknown; }
/** `capabilities().lipsync`: the Lipsync API (Enterprise) on this deployment. */
export interface LipsyncCapability {
  available?: boolean; plan?: string; endpoints?: string[];
  fps?: number; channels?: number; stream_sample_rates?: number[];
  /** Longest clip `lipsync()` accepts, in seconds. */
  max_seconds?: number;
  tokens_per_minute?: number;
  [key: string]: unknown;
}
/** `capabilities().speech`: the Speech API (Enterprise) on this deployment. */
export interface SpeechCapability {
  available?: boolean; plan?: string; endpoints?: string[];
  /** Audio sample rate in Hz (24000). */
  sample_rate?: number;
  fps?: number; channels?: number;
  max_text_chars?: number; max_seconds?: number;
  formats?: Array<'wav' | 'pcm' | (string & {})>;
  tokens_per_minute?: number;
  [key: string]: unknown;
}
export interface Capabilities { api_version: string; modes: ModeCapability[]; audio_input?: Record<string, unknown>;
  lipsync?: LipsyncCapability;
  speech?: SpeechCapability;
  [key: string]: unknown; }
export interface SessionBilling { unit: string; tokens_per_minute?: number; credits_per_minute?: number; rate_version: string; basis: string; [key: string]: unknown; }
export interface Session {
  session_id: string;
  session_token: string;
  instance_id: string;
  preset_id?: string;
  avatar_id?: string;
  service_mode?: ServiceMode;
  llm_mode?: string;
  billing?: SessionBilling;
  expires_at: string;
  max_duration_seconds: number;
  speech_input?: SpeechInput;
  metadata?: Record<string, string | number | boolean>;
  embed_url: string;
  events_ws_url: string;
  [key: string]: unknown;
}
/** Metered connected time, from GET /sessions/{id}: running while active, final once ended. */
export interface SessionUsage { seconds: number; tokens: number; unit: string; }
/** Why a host line ended. New reasons may be added. */
export type LineEndReason = 'completed' | 'host_interrupt' | 'new_line' | 'user_message' | 'barge_in' | 'playback_unconfirmed' | 'failed' | 'session_ended';
/** How much of a host line the viewer heard; exactly one per `say` line. `spoken_text` is the line's authoritative text. */
export interface LineEnded {
  say_id: string;
  status: 'completed' | 'interrupted' | 'failed';
  reason: LineEndReason;
  spoken_text: string;
  /** How far into the line's audio playback got; absent when the session ended mid-line (`reason: "session_ended"`). */
  spoken_until_ms?: number;
}
/** The `transcript` event. An assistant caption of a host line carries its `say_id`; a line cut short ends with a final caption of what was heard, `interrupted: true`. */
export interface Transcript { role: 'user' | 'assistant'; text: string; final: boolean; say_id?: string; interrupted?: boolean; }
/** `error` event codes a live session sends. New codes may be added: treat an unknown one as a failure of the current turn. */
export type SessionErrorCode = 'command_failed' | 'session_not_connected' | 'conversation_failed' | 'external_reply_limit' | 'audio_buffer_overflow' | 'unsupported_input' | 'say_id_reused' | 'say_queue_full' | 'speed_unsupported' | 'core_disconnected' | (string & {});
/** The `error` event; `say_id` names the host line it is about. */
export interface SessionError { code: SessionErrorCode; message: string; say_id?: string; }
/** Why a session ended (`session.ended.reason`, `end_reason` on getSession). `standby_expired`: a prepared (`standby=1`) session was not activated within 120 seconds and was never billed. `connection_ended`: metering stopped because the session's connection was gone and no other reason had been recorded. Treat an unknown reason like `session_closed`. */
export type SessionEndReason = 'ended_by_host' | 'client_disconnect' | 'viewer_left' | 'max_duration' | 'idle' | 'standby_expired' | 'credits_exhausted' | 'billing_unavailable' | 'core_disconnected' | 'connection_ended' | 'session_closed' | (string & {});
/** The `session.ended` event; every open host line gets its `line.ended` first. */
export interface SessionEnded { session_id: string; reason: SessionEndReason; }
/** The `control.speech_state` event. `content_s` is the position in the current audio generation: it resets after an interrupt and is not per line. */
export interface SpeechState { speaking: boolean; content_s: number; generation: number; barge_in: boolean; }
export interface Preset {
  id: string; name: string; avatar_id: string;
  /** Deprecated alias. */ visual_character_id?: string;
  system_prompt: string; voice_id: string; language_code?: string;
  disabled: boolean; active: boolean;
  [key: string]: unknown;
}
export interface Instance { id: string; [key: string]: unknown; }
export interface SessionEvent { type: string; payload?: Record<string, unknown>; [key: string]: unknown; }
export interface PresentationContext {
  version: 1; demo: string; revision: number; page: string; highlight: string;
  brief?: string; opening?: string;
  pages: Array<{ id: string; title: string; items: Array<{id: string; text: string}> }>;
}
export interface PresentationStart { version: 1; demo: string; revision: number; }
export interface EventsOptions {
  WebSocketImpl?: new (url: string, options: { headers: Record<string, string> }) => WebSocket;
  /** false leaves the per-frame face stream (`controls`) out of the events. `controls` is sent only on this socket, never to the embed page. */
  controls?: boolean;
}
export interface LineOptions {
  /** This line's speaking rate, 0.7–1.2. Refused with `speed_unsupported` on a session using the Anva Realtime voice (anva_standard), and the line gets no `line.ended`. */
  speed?: number;
  /** Wait behind the line being spoken instead of interrupting it (at most 8 wait; one more gets an `error` `say_queue_full`). */
  queue?: boolean;
}
export interface SayOptions extends LineOptions { sayId?: string; }
export type PCMBytes = Uint8Array | ArrayBuffer;
export declare class AnvaError extends Error {
  constructor(status: number, code: string, message: string, details?: Record<string, unknown>);
  status: number; code: string; details: Record<string, unknown>;
}
/** One active event reader per connection. Breaking iteration closes the socket. */
export declare class RealtimeSession implements AsyncIterable<SessionEvent> {
  constructor(socket: WebSocket);
  ready: Promise<RealtimeSession>;
  /** Resolves with the session.live payload once the viewer's embed is connected. */
  live: Promise<Record<string, unknown>>;
  closed: boolean;
  send(type: string, payload?: Record<string, unknown>): Promise<void>;
  message(text: string): Promise<void>;
  interrupt(): Promise<void>;
  updateContext(context: PresentationContext): Promise<void>;
  startPresentation(start: PresentationStart): Promise<void>;
  turnDelta(turnId: string, text: string): Promise<void>;
  turnDone(turnId: string): Promise<void>;
  turnCancel(turnId: string, reason?: string): Promise<void>;
  say(text: string, sayId?: string, options?: LineOptions): Promise<void>;
  /** Put `speed` and `queue` on a streamed line's first delta. */
  sayDelta(sayId: string, text: string, options?: LineOptions): Promise<void>;
  /** Replace a managed session's instructions mid-call (session.update). */
  updatePrompt(systemPrompt: string): Promise<void>;
  sayDone(sayId: string): Promise<void>;
  startSpeech(turnId: string, options?: {text?: string}): Promise<void>;
  appendSpeech(turnId: string, seq: number, startSample: number, pcm: PCMBytes): Promise<void>;
  finishSpeech(turnId: string, totalSamples: number): Promise<void>;
  cancelSpeech(turnId: string): Promise<void>;
  close(): void;
  [Symbol.asyncIterator](): AsyncGenerator<SessionEvent, void, void>;
}
export type LipsyncPreset = 'hybrid' | 'lowlat';
export interface LipsyncOptions { sampleRate?: number; preset?: LipsyncPreset; contentType?: string; }
export interface LipsyncStreamOptions extends EventsOptions { sampleRate?: 16000 | 24000; preset?: LipsyncPreset; }
/** frames[n][i] is channels[i] at n / fps seconds. */
export interface LipsyncResult {
  id: string; fps: number; frame_count: number; duration_s: number;
  channels: string[]; frames: number[][]; preset: LipsyncPreset; model: string;
  billing: { unit: string; basis: string; seconds: number; tokens_per_minute: number };
  [key: string]: unknown;
}
export interface LipsyncMessage {
  type: 'ready' | 'frames' | 'flushed' | 'error';
  start?: number; values?: number[][]; frame_count?: number;
  fps?: number; channels?: string[]; delay_ms?: number; input_sample_rate?: number;
  code?: string; message?: string;
  [key: string]: unknown;
}
export declare class LipsyncStream implements AsyncIterable<LipsyncMessage> {
  constructor(socket: WebSocket);
  ready: Promise<LipsyncStream>;
  closed: boolean;
  audio(pcm: PCMBytes): Promise<void>;
  flush(): Promise<void>;
  send(type: string, payload?: Record<string, unknown>): Promise<void>;
  close(): void;
  [Symbol.asyncIterator](): AsyncGenerator<LipsyncMessage, void, void>;
}
export type SpeechFormat = 'wav' | 'pcm';
export interface SynthesizeOptions {
  /** Required: a voice from listVoices() (its id, e.g. "elevenlabs:…"). */
  voiceId: string;
  /** 0.7–1.2; the server default is 0.85. */
  speed?: number;
  preset?: LipsyncPreset;
  /** "wav" (default): a complete WAV file. "pcm": raw 16-bit little-endian mono samples. */
  format?: SpeechFormat;
}
/** Mouth curves on the audio's clock: frames[n][i] is channels[i] at n / fps seconds; frame_count = ceil(samples / 800). */
export interface SpeechCurves {
  fps: number; channels: string[]; frame_count: number;
  preset: LipsyncPreset; model: string; release: string; frames: number[][];
}
/** Character timing in seconds on the audio clock. */
export interface SpeechAlignment { characters: string[]; starts: number[]; ends: number[]; }
export interface SpeechResult {
  id: string; voice_id: string; sample_rate: number; duration_s: number;
  /** `data` is decoded from base64 by the SDK. */
  audio: { format: SpeechFormat; data: Uint8Array };
  curves: SpeechCurves;
  /** Present when the voice provider returns it. */
  alignment?: SpeechAlignment;
  billing: { unit: string; basis: string; seconds: number; tokens_per_minute: number };
  [key: string]: unknown;
}
export interface SpeechStreamDefaults { voiceId?: string; speed?: number; preset?: LipsyncPreset; }
export interface SpeechStreamOptions extends EventsOptions, SpeechStreamDefaults {}
export type SpeechStreamErrorCode = 'bad_request' | 'text_too_long' | 'invalid_voice' | 'voice_unavailable' | 'insufficient_tokens' | 'busy_line' | 'speech_busy' | 'speech_failed' | 'speech_unavailable' | 'credits_exhausted' | 'idle_timeout' | (string & {});
export type SpeechMessage =
  | { type: 'ready'; sample_rate: number; fps: number; channels: string[]; preset: LipsyncPreset; max_text_chars: number; release: string }
  | { type: 'curves'; id: string; start: number; values: number[][] }
  | { type: 'audio'; id: string; start_sample: number; samples: number; sample_rate: number; /** 16-bit little-endian mono PCM, decoded by the SDK. */ data: Uint8Array }
  | { type: 'alignment'; id: string; characters: string[]; starts: number[]; ends: number[] }
  | { type: 'done'; id: string; total_samples: number; frame_count: number; duration_s: number }
  | { type: 'cancelled'; id: string; total_samples: number; frame_count: number }
  | { type: 'error'; id?: string; code: SpeechStreamErrorCode; message: string };
/** Speech API stream (Enterprise). Curves arrive before their audio; one line
 * at a time (a speak during a line is refused with busy_line); closed by the
 * server after 60 s idle. Breaking iteration closes the socket. */
export declare class SpeechStream implements AsyncIterable<SpeechMessage> {
  constructor(socket: WebSocket);
  ready: Promise<SpeechStream>;
  closed: boolean;
  speak(id: string, text: string, options?: SpeechStreamDefaults): Promise<void>;
  cancel(id: string): Promise<void>;
  /** Sends {type: "close"} and closes the socket. */
  close(): void;
  [Symbol.asyncIterator](): AsyncGenerator<SpeechMessage, void, void>;
}
export interface AvatarInfo {
  id: string; name: string; kind: 'builtin' | 'official' | 'custom'; ready: boolean;
  icon?: string;
  /** Absolute portrait URL, fetchable without credentials until icon_expires_at. */
  icon_url?: string; icon_expires_at?: string;
}
export declare class Anva {
  constructor(apiKey: string, opts?: AnvaOptions);
  apiKey: string; baseUrl: string;
  createSession(params: CreateSessionParams): Promise<Session>;
  getSession(sessionId: string): Promise<Record<string, unknown> & { usage?: SessionUsage; end_reason?: SessionEndReason }>;
  endSession(sessionId: string): Promise<Record<string, unknown>>;
  /** Replace a managed session's instructions while it runs (PATCH /sessions/{id}). */
  updateSession(sessionId: string, params: { systemPrompt: string }): Promise<Record<string, unknown>>;
  sendMessage(sessionId: string, text: string): Promise<{status: string}>;
  say(sessionId: string, text: string, options?: SayOptions): Promise<{status: string; say_id: string}>;
  interrupt(sessionId: string): Promise<{status: string}>;
  triggerAction(sessionId: string, name: string): Promise<{status: string}>;
  /** Credential-free events URL; authenticate with authHeaders(). */
  eventsWsUrl(sessionId: string, options?: { controls?: boolean }): string;
  authHeaders(): { Authorization: string };
  /** @deprecated Puts the API key in the URL. Use connect(), or eventsWsUrl() with authHeaders(). */
  eventsUrl(sessionId: string): string;
  connect(sessionId: string, options?: EventsOptions): Promise<RealtimeSession>;
  events(sessionId: string, options?: EventsOptions): AsyncGenerator<SessionEvent, void, void>;
  capabilities(): Promise<Capabilities>;
  billing(): Promise<Record<string, unknown>>;
  listAvatars(): Promise<{avatars: AvatarInfo[]}>;
  lipsync(audio: PCMBytes | Blob, options?: LipsyncOptions): Promise<LipsyncResult>;
  lipsyncStreamUrl(options?: {sampleRate?: 16000 | 24000; preset?: LipsyncPreset}): string;
  connectLipsync(options?: LipsyncStreamOptions): Promise<LipsyncStream>;
  listVoices(): Promise<Record<string, unknown>>;
  /** Speech API (Enterprise): text to 24 kHz audio plus its mouth curves. */
  synthesize(text: string, options: SynthesizeOptions): Promise<SpeechResult>;
  speechStreamUrl(options?: SpeechStreamDefaults): string;
  connectSpeech(options?: SpeechStreamOptions): Promise<SpeechStream>;
  listLanguages(): Promise<Record<string, unknown>>;
  updateContext(sessionId: string, context: PresentationContext): Promise<Record<string, unknown>>;
  startPresentation(sessionId: string, start: PresentationStart): Promise<Record<string, unknown>>;
  speech(sessionId: string, type: string, payload: Record<string, unknown>): Promise<Record<string, unknown>>;
  startSpeech(sessionId: string, turnId: string, options?: {text?: string}): Promise<Record<string, unknown>>;
  appendSpeech(sessionId: string, turnId: string, seq: number, startSample: number, pcm: PCMBytes): Promise<Record<string, unknown>>;
  finishSpeech(sessionId: string, turnId: string, totalSamples: number): Promise<Record<string, unknown>>;
  cancelSpeech(sessionId: string, turnId: string): Promise<Record<string, unknown>>;
  listPresets(): Promise<{presets: Preset[]}>;
  createPreset(params: {name: string; avatarId?: string; visualCharacterId?: string; systemPrompt?: string; voiceId?: string; languageCode?: string}): Promise<Preset>;
  /** Patch uses the REST API's snake_case field names. */
  updatePreset(presetId: string, patch: Record<string, unknown>): Promise<Preset>;
  getPreset(presetId: string): Promise<Preset>;
  deletePreset(presetId: string): Promise<{id: string; status: string}>;
  listInstances(): Promise<{instances: Instance[]}>;
}
export default Anva;
