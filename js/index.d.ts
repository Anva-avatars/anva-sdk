/** Official JavaScript/TypeScript SDK for Anva (https://anva.ai). */

export interface AnvaOptions {
  /** Override for self-hosted / testing setups. Default: https://anva.ai */
  baseUrl?: string;
}

/**
 * Parameters for `createSession`. Provide **either** `presetId` (embed tier —
 * a persona saved in the Playground) **or** `avatarId` plus the inline persona
 * fields (advanced tier — nothing is stored server-side). At least one of
 * `presetId` / `avatarId` is required.
 */
export interface CreateSessionParams {
  /** Embed tier: a saved preset id. */
  presetId?: string;
  /** Advanced tier: the avatar to drive with an inline persona. */
  avatarId?: string;
  systemPrompt?: string;
  voiceId?: string;
  languageCode?: string;
  /** Omit for the built-in conversation engine, or "external" to drive the LLM yourself. */
  llmMode?: string;
  webhookUrl?: string;
  webhookSecret?: string;
}

export interface Session {
  session_id: string;
  session_token: string;
  instance_id: string;
  preset_id?: string;
  avatar_id?: string;
  llm_mode?: string;
  expires_at: string;
  /** Ready to drop into an <iframe allow="camera; microphone; autoplay">. */
  embed_url: string;
  events_ws_url: string;
  [key: string]: unknown;
}

export interface Preset {
  id: string;
  name: string;
  visual_character_id: string;
  system_prompt: string;
  voice_id: string;
  language_code?: string;
  disabled: boolean;
  active: boolean;
  barge_in?: boolean;
  proactive_questions?: boolean;
  greeting_enabled?: boolean;
  greeting_text?: string;
  [key: string]: unknown;
}

/** A per-key usage bucket. */
export interface Instance {
  id: string;
  [key: string]: unknown;
}

export interface SessionEvent {
  type: string;
  [key: string]: unknown;
}

export interface EventsOptions {
  /** A WebSocket-compatible constructor (e.g. `ws` in older Node versions). */
  WebSocketImpl?: new (url: string) => WebSocket;
}

export declare class AnvaError extends Error {
  status: number;
  code: string;
}

export declare class Anva {
  constructor(apiKey: string, opts?: AnvaOptions);
  apiKey: string;
  baseUrl: string;

  createSession(params: CreateSessionParams): Promise<Session>;
  getSession(sessionId: string): Promise<Record<string, unknown>>;
  endSession(sessionId: string): Promise<Record<string, unknown>>;
  sendMessage(sessionId: string, text: string): Promise<{ status: string }>;
  interrupt(sessionId: string): Promise<{ status: string }>;
  triggerAction(sessionId: string, name: string): Promise<{ status: string }>;
  eventsUrl(sessionId: string): string;
  events(sessionId: string, opts?: EventsOptions): AsyncGenerator<SessionEvent, void, void>;

  listPresets(): Promise<{ presets: Preset[] }>;
  createPreset(params: {
    name: string;
    visualCharacterId?: string;
    systemPrompt?: string;
    voiceId?: string;
    languageCode?: string;
  }): Promise<Preset>;
  getPreset(presetId: string): Promise<Preset>;
  deletePreset(presetId: string): Promise<{ id: string; status: string }>;

  listInstances(): Promise<{ instances: Instance[] }>;
}

export default Anva;
