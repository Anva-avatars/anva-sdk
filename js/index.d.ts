/** Official Anva SDK. All API keys and authenticated realtime sockets belong on your server. */
export type ServiceMode = 'avatar_only' | 'byo_llm' | 'anva_light' | 'anva_expressive' | 'elevenagents_max';
/** "off": the host transcribes the user and sends text (push-to-talk); no microphone. */
export type SpeechInput = 'on' | 'off';
export interface AnvaOptions { baseUrl?: string; }
export interface PerformanceOptions {
  conversation_provider?: string;
  performance_mode?: string;
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
  serviceMode?: ServiceMode;
  /** Deprecated compatibility alias. Conflicts with serviceMode are rejected by the server. */
  llmMode?: string;
  performanceOptions?: PerformanceOptions;
  conversationProvider?: string;
  performanceMode?: string;
  elevenlabsAgentId?: string;
  dynamicExpressions?: boolean;
  webhookUrl?: string;
  webhookSecret?: string;
  /** Ends the session this many seconds (60–7200) after it goes live. Omitted = the 2-hour ceiling. */
  maxDurationSeconds?: number;
  /** Flat map (string/number/boolean values, ≤20 keys, ≤4 KB) echoed on the session, session.info and webhooks. */
  metadata?: Record<string, string | number | boolean>;
  /** "off" for byo_llm, anva_light or anva_expressive hosts that transcribe the user themselves. */
  speechInput?: SpeechInput;
  /** Speaking rate, 0.7–1.2 (1 is the voice's natural pace). anva_light and byo_llm voices. */
  speechSpeed?: number;
  /** Start with the avatar's eyes closed; they open once the viewer's video is showing. session.info reports wake_up false for avatars that cannot close their eyes convincingly. */
  wakeUp?: boolean;
  /** Sent as the Idempotency-Key header (16–128 letters, digits, - or _): a retry with the same key and body within 24 hours returns the first session. */
  idempotencyKey?: string;
}
export interface ModeCapability { id: ServiceMode; name: string; available: boolean; reason?: string; input?: string[]; [key: string]: unknown; }
export interface Capabilities { api_version: string; modes: ModeCapability[]; audio_input?: Record<string, unknown>; [key: string]: unknown; }
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
/** How much of a host line the viewer heard; exactly one per `say` line. */
export interface LineEnded { say_id: string; status: 'completed' | 'interrupted'; spoken_text: string; spoken_until_ms: number; }
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
  /** false leaves the per-frame face stream (`controls`) out of the events. */
  controls?: boolean;
}
export interface SayOptions { sayId?: string; /** This line's speaking rate, 0.7–1.2. */ speed?: number; }
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
  say(text: string, sayId?: string, options?: { speed?: number }): Promise<void>;
  /** Put `speed` on a streamed line's first delta. */
  sayDelta(sayId: string, text: string, options?: { speed?: number }): Promise<void>;
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
  getSession(sessionId: string): Promise<Record<string, unknown> & { usage?: SessionUsage }>;
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
