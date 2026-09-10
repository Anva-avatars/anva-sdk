/** Official Anva SDK. All API keys and authenticated realtime sockets belong on your server. */
export type ServiceMode = 'avatar_only' | 'byo_llm' | 'anva_light' | 'anva_expressive' | 'elevenagents_max';
export interface AnvaOptions { baseUrl?: string; }
export interface PerformanceOptions {
  conversation_provider?: string;
  performance_mode?: string;
  elevenlabs_agent_id?: string;
  dynamic_expressions?: boolean;
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
  embed_url: string;
  events_ws_url: string;
  [key: string]: unknown;
}
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
export interface EventsOptions { WebSocketImpl?: new (url: string) => WebSocket; }
export type PCMBytes = Uint8Array | ArrayBuffer;
export declare class AnvaError extends Error {
  constructor(status: number, code: string, message: string, details?: Record<string, unknown>);
  status: number; code: string; details: Record<string, unknown>;
}
/** One active event reader per connection. Breaking iteration closes the socket. */
export declare class RealtimeSession implements AsyncIterable<SessionEvent> {
  constructor(socket: WebSocket);
  ready: Promise<RealtimeSession>;
  closed: boolean;
  send(type: string, payload?: Record<string, unknown>): Promise<void>;
  message(text: string): Promise<void>;
  interrupt(): Promise<void>;
  updateContext(context: PresentationContext): Promise<void>;
  startPresentation(start: PresentationStart): Promise<void>;
  turnDelta(turnId: string, text: string): Promise<void>;
  turnDone(turnId: string): Promise<void>;
  turnCancel(turnId: string, reason?: string): Promise<void>;
  startSpeech(turnId: string, options?: {text?: string}): Promise<void>;
  appendSpeech(turnId: string, seq: number, startSample: number, pcm: PCMBytes): Promise<void>;
  finishSpeech(turnId: string, totalSamples: number): Promise<void>;
  cancelSpeech(turnId: string): Promise<void>;
  close(): void;
  [Symbol.asyncIterator](): AsyncGenerator<SessionEvent, void, void>;
}
export declare class Anva {
  constructor(apiKey: string, opts?: AnvaOptions);
  apiKey: string; baseUrl: string;
  createSession(params: CreateSessionParams): Promise<Session>;
  getSession(sessionId: string): Promise<Record<string, unknown>>;
  endSession(sessionId: string): Promise<Record<string, unknown>>;
  sendMessage(sessionId: string, text: string): Promise<{status: string}>;
  interrupt(sessionId: string): Promise<{status: string}>;
  triggerAction(sessionId: string, name: string): Promise<{status: string}>;
  eventsUrl(sessionId: string): string;
  connect(sessionId: string, options?: EventsOptions): Promise<RealtimeSession>;
  events(sessionId: string, options?: EventsOptions): AsyncGenerator<SessionEvent, void, void>;
  capabilities(): Promise<Capabilities>;
  billing(): Promise<Record<string, unknown>>;
  listAvatars(): Promise<Record<string, unknown>>;
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
