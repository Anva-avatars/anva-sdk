/** Official JavaScript/TypeScript SDK for Anva (https://anva.ai). */

export interface AnvaOptions {
  /** Override for self-hosted / testing setups. Default: https://anva.ai */
  baseUrl?: string;
}

export interface CreateSessionParams {
  characterId: string;
  /** Omit for the built-in conversation engine, or "external" to drive the LLM yourself. */
  llmMode?: "external";
  webhookUrl?: string;
  webhookSecret?: string;
}

export interface Session {
  session_id: string;
  session_token: string;
  character_id: string;
  llm_mode?: string;
  expires_at: string;
  /** Ready to drop into an <iframe allow="camera; microphone; autoplay">. */
  embed_url: string;
  events_ws_url: string;
  [key: string]: unknown;
}

export interface Character {
  id: string;
  name: string;
  visual_character_id: string;
  system_prompt: string;
  voice_id: string;
  language_code?: string;
  disabled: boolean;
  active: boolean;
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

  listCharacters(): Promise<{ characters: Character[] }>;
  createCharacter(params: {
    name: string;
    visualCharacterId?: string;
    systemPrompt?: string;
    voiceId?: string;
    languageCode?: string;
  }): Promise<Character>;
  getCharacter(characterId: string): Promise<Character>;
  deleteCharacter(characterId: string): Promise<{ id: string; status: string }>;
}

export default Anva;
