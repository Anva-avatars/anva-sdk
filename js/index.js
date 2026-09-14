/**
 * Official JavaScript/TypeScript SDK for Anva (https://anva.ai).
 *
 *   import { Anva } from "anva-sdk";
 *   const client = new Anva(process.env.ANVA_KEY);
 *   const session = await client.createSession({ presetId: "..." });
 *   // put session.embed_url in an <iframe allow="camera; microphone; autoplay">
 *
 * Works in Node 18+ (supply a WebSocket implementation before Node 22) and modern browsers — but keep
 * your API key server-side; mint sessions on your backend and hand the
 * embed_url to the client.
 */

import { RealtimeSession, speechStart, speechAppend } from "./realtime.js";
export { RealtimeSession } from "./realtime.js";

const DEFAULT_BASE_URL = "https://anva.ai";
let warnedEventsUrl = false;

export class AnvaError extends Error {
  constructor(status, code, message, details = {}) {
    super(`${code}: ${message} (HTTP ${status})`);
    this.name = "AnvaError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export class Anva {
  /**
   * @param {string} apiKey an API key from the dashboard (anva_key_...)
   * @param {{baseUrl?: string}} [opts]
   */
  constructor(apiKey, opts = {}) {
    if (!apiKey || !apiKey.trim()) throw new Error("apiKey is required");
    this.apiKey = apiKey.trim();
    this.baseUrl = (opts.baseUrl || DEFAULT_BASE_URL).replace(/\/+$/, "");
  }

  // -- sessions -------------------------------------------------------------

  /**
   * Create a live session, one of two ways:
   *  - Embed tier: pass `presetId` (a saved preset from the Playground).
   *  - Advanced tier: pass `avatarId` + the persona (`systemPrompt`, `voiceId`,
   *    `languageCode`) directly — nothing is stored server-side.
   * Returns { session_id, session_token, embed_url, events_ws_url, expires_at,
   * instance_id, preset_id, avatar_id, ... }.
   *
   * `maxDurationSeconds` (60–7200) ends the session that long after it goes
   * live; omitted, the server's 2-hour ceiling applies.
   *
   * `metadata` is an optional flat object (string, number or boolean values,
   * up to 20 keys, 4 KB serialized) stored with the session and echoed on
   * the session, on `session.info`, and in every webhook payload.
   *
   * @param {{presetId?: string, avatarId?: string, systemPrompt?: string,
   *   voiceId?: string, languageCode?: string, llmMode?: string,
   *   webhookUrl?: string, webhookSecret?: string, maxDurationSeconds?: number,
   *   metadata?: Record<string, string | number | boolean>}} params
   */
  createSession(params = {}) {
    const { presetId, avatarId, systemPrompt, voiceId, languageCode, llmMode, serviceMode, performanceOptions, conversationProvider, performanceMode, elevenlabsAgentId, dynamicExpressions, webhookUrl, webhookSecret, maxDurationSeconds, metadata } = params;
    if ((!presetId && !avatarId) || (presetId && avatarId)) {
      throw new Error("createSession requires exactly one of presetId or avatarId");
    }
    const body = {};
    if (presetId) body.preset_id = presetId;
    if (avatarId) body.avatar_id = avatarId;
    if (systemPrompt) body.system_prompt = systemPrompt;
    if (voiceId) body.voice_id = voiceId;
    if (languageCode) body.language_code = languageCode;
    if (llmMode !== undefined) body.llm_mode = llmMode;
    if (serviceMode !== undefined) body.service_mode = serviceMode;
    if (performanceOptions !== undefined) body.performance_options = performanceOptions;
    if (conversationProvider !== undefined) body.conversation_provider = conversationProvider;
    if (performanceMode !== undefined) body.performance_mode = performanceMode;
    if (elevenlabsAgentId !== undefined) body.elevenlabs_agent_id = elevenlabsAgentId;
    if (dynamicExpressions !== undefined) body.dynamic_expressions = dynamicExpressions;
    if (webhookUrl) body.webhook_url = webhookUrl;
    if (webhookSecret) body.webhook_secret = webhookSecret;
    if (maxDurationSeconds !== undefined) body.max_duration_seconds = maxDurationSeconds;
    if (metadata !== undefined) body.metadata = metadata;
    return this._request("POST", "/api/v2/sessions", body);
  }

  getSession(sessionId) {
    return this._request("GET", `/api/v2/sessions/${enc(sessionId)}`);
  }

  endSession(sessionId) {
    return this._request("DELETE", `/api/v2/sessions/${enc(sessionId)}`);
  }

  /** Send `text` as a user message; the avatar hears it and replies (it does
   * NOT speak `text` verbatim). For external replies, use serviceMode:"byo_llm" and turnDelta/turnDone on a realtime connection. */
  sendMessage(sessionId, text) {
    return this._request("POST", `/api/v2/sessions/${enc(sessionId)}/messages`, { text });
  }

  /** Stop the avatar mid-sentence. */
  interrupt(sessionId) {
    return this._request("POST", `/api/v2/sessions/${enc(sessionId)}/interrupt`, {});
  }

  triggerAction(sessionId, name) {
    return this._request("POST", `/api/v2/sessions/${enc(sessionId)}/actions`, { name });
  }

  /** The session's event-stream WebSocket URL. It carries no credentials:
   * authenticate the handshake with `authHeaders()`. */
  eventsWsUrl(sessionId) {
    const ws = this.baseUrl.replace(/^http/, "ws");
    return `${ws}/api/v2/sessions/${enc(sessionId)}/events`;
  }

  authHeaders() {
    return { Authorization: `Bearer ${this.apiKey}` };
  }

  /** @deprecated Puts the API key in the URL, where proxies and access logs
   * record it. Use `connect()`, or `eventsWsUrl()` with `authHeaders()`. */
  eventsUrl(sessionId) {
    if (!warnedEventsUrl) {
      warnedEventsUrl = true;
      globalThis.process?.emitWarning?.("eventsUrl() puts the API key in the URL; use eventsWsUrl() with authHeaders()", "DeprecationWarning");
    }
    return `${this.eventsWsUrl(sessionId)}?api_key=${encodeURIComponent(this.apiKey)}`;
  }

  /** Open a single socket for both events and turn/presentation/speech commands.
   * The key travels in the handshake's Authorization header, which Node's
   * WebSocket and the `ws` package accept as `{ headers }`; browsers cannot
   * send it, and the key does not belong in a browser anyway. */
  async connect(sessionId, { WebSocketImpl } = {}) {
    const WS = WebSocketImpl || globalThis.WebSocket;
    if (!WS) throw new Error('No WebSocket implementation; pass { WebSocketImpl }');
    const stream = new RealtimeSession(new WS(this.eventsWsUrl(sessionId), { headers: this.authHeaders() }));
    try { await stream.ready; return stream; } catch (error) { stream.close(); throw error; }
  }
  async *events(sessionId, options = {}) {
    const stream = await this.connect(sessionId, options);
    try { yield* stream; } finally { stream.close(); }
  }
  capabilities() { return this._request('GET', '/api/v2/capabilities'); }
  billing() { return this._request('GET', '/api/v2/billing'); }
  listAvatars() { return this._request('GET', '/api/v2/avatars'); }
  listVoices() { return this._request('GET', '/api/v2/voices'); }
  listLanguages() { return this._request('GET', '/api/v2/languages'); }
  updateContext(sessionId, context) { return this._request('POST', `/api/v2/sessions/${enc(sessionId)}/context`, context); }
  startPresentation(sessionId, start) { return this._request('POST', `/api/v2/sessions/${enc(sessionId)}/presentation`, start); }
  speech(sessionId, type, payload) { return this._request('POST', `/api/v2/sessions/${enc(sessionId)}/speech`, { type, payload }); }
  startSpeech(sessionId, turnId, { text } = {}) { return this.speech(sessionId, 'speech.start', speechStart(turnId, text)); }
  appendSpeech(sessionId, turnId, seq, startSample, pcm) { return this.speech(sessionId, 'speech.append', speechAppend(turnId, seq, startSample, pcm)); }
  finishSpeech(sessionId, turnId, totalSamples) { return this.speech(sessionId, 'speech.done', { turn_id: turnId, total_samples: totalSamples }); }
  cancelSpeech(sessionId, turnId) { return this.speech(sessionId, 'speech.cancel', { turn_id: turnId }); }

  // -- presets --------------------------------------------------------------

  listPresets() {
    return this._request("GET", "/api/v2/presets");
  }

  createPreset({ name, avatarId, visualCharacterId, systemPrompt, voiceId, languageCode }) {
    const body = { name };
    if (avatarId || visualCharacterId) body.avatar_id = avatarId || visualCharacterId;
    if (systemPrompt) body.system_prompt = systemPrompt;
    if (voiceId) body.voice_id = voiceId;
    if (languageCode) body.language_code = languageCode;
    return this._request("POST", "/api/v2/presets", body);
  }

  getPreset(presetId) {
    return this._request("GET", `/api/v2/presets/${enc(presetId)}`);
  }

  updatePreset(presetId, patch) {
    return this._request("PATCH", `/api/v2/presets/${enc(presetId)}`, patch);
  }

  deletePreset(presetId) {
    return this._request("DELETE", `/api/v2/presets/${enc(presetId)}`);
  }

  // -- instances ------------------------------------------------------------

  listInstances() {
    return this._request("GET", "/api/v2/instances");
  }

  // -- plumbing -------------------------------------------------------------

  async _request(method, path, body) {
    const res = await fetch(this.baseUrl + path, {
      method,
      headers: {
        Authorization: `Bearer ${this.apiKey}`,
        "Content-Type": "application/json",
        "User-Agent": "anva-js/0.4.0",
      },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const raw = await res.text();
    let payload = {};
    try {
      payload = raw ? JSON.parse(raw) : {};
    } catch {
      payload = { message: raw.slice(0, 300) };
    }
    if (!res.ok) {
      const err = payload?.error || payload || {};
      throw new AnvaError(res.status, err.code || "request_failed", err.message || "request failed", err);
    }
    return payload;
  }
}

function enc(part) {
  return encodeURIComponent(String(part));
}

export default Anva;
