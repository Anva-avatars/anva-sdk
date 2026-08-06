/**
 * Official JavaScript/TypeScript SDK for Anva (https://anva.ai).
 *
 *   import { Anva } from "anva";
 *   const client = new Anva(process.env.ANVA_KEY);
 *   const session = await client.createSession({ presetId: "..." });
 *   // put session.embed_url in an <iframe allow="camera; microphone; autoplay">
 *
 * Works in Node 18+ (global fetch/WebSocket) and modern browsers — but keep
 * your API key server-side; mint sessions on your backend and hand the
 * embed_url to the client.
 */

const DEFAULT_BASE_URL = "https://anva.ai";

export class AnvaError extends Error {
  constructor(status, code, message) {
    super(`${code}: ${message} (HTTP ${status})`);
    this.name = "AnvaError";
    this.status = status;
    this.code = code;
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
   * @param {{presetId?: string, avatarId?: string, systemPrompt?: string,
   *   voiceId?: string, languageCode?: string, llmMode?: string,
   *   webhookUrl?: string, webhookSecret?: string}} params
   */
  createSession(params = {}) {
    const { presetId, avatarId, systemPrompt, voiceId, languageCode, llmMode, webhookUrl, webhookSecret } = params;
    if (!presetId && !avatarId) {
      throw new Error("createSession requires either presetId (embed) or avatarId (advanced persona)");
    }
    const body = {};
    if (presetId) body.preset_id = presetId;
    if (avatarId) body.avatar_id = avatarId;
    if (systemPrompt) body.system_prompt = systemPrompt;
    if (voiceId) body.voice_id = voiceId;
    if (languageCode) body.language_code = languageCode;
    if (llmMode) body.llm_mode = llmMode;
    if (webhookUrl) body.webhook_url = webhookUrl;
    if (webhookSecret) body.webhook_secret = webhookSecret;
    return this._request("POST", "/api/v2/sessions", body);
  }

  getSession(sessionId) {
    return this._request("GET", `/api/v2/sessions/${enc(sessionId)}`);
  }

  endSession(sessionId) {
    return this._request("DELETE", `/api/v2/sessions/${enc(sessionId)}`);
  }

  /** Have the avatar speak `text` to the user. */
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

  /** The authenticated WebSocket URL for the session's event stream. */
  eventsUrl(sessionId) {
    const ws = this.baseUrl.replace(/^http/, "ws");
    return `${ws}/api/v2/sessions/${enc(sessionId)}/events?api_key=${encodeURIComponent(this.apiKey)}`;
  }

  /**
   * Async-iterate live events (transcripts, state changes):
   *
   *   for await (const event of client.events(sessionId)) { ... }
   */
  async *events(sessionId, { WebSocketImpl } = {}) {
    const WS = WebSocketImpl || globalThis.WebSocket;
    if (!WS) throw new Error("no WebSocket implementation available — pass { WebSocketImpl }");
    const ws = new WS(this.eventsUrl(sessionId));
    const queue = [];
    let notify = null;
    let done = false;
    let failure = null;
    ws.onmessage = (m) => {
      try {
        queue.push(JSON.parse(m.data));
      } catch {
        /* non-JSON frame */
      }
      if (notify) notify();
    };
    ws.onclose = () => {
      done = true;
      if (notify) notify();
    };
    ws.onerror = () => {
      failure = new Error("events socket error");
      done = true;
      if (notify) notify();
    };
    try {
      while (!done || queue.length) {
        if (!queue.length) {
          await new Promise((resolve) => (notify = resolve));
          notify = null;
          continue;
        }
        yield queue.shift();
      }
      if (failure) throw failure;
    } finally {
      try {
        ws.close();
      } catch {
        /* already closed */
      }
    }
  }

  // -- presets --------------------------------------------------------------

  listPresets() {
    return this._request("GET", "/api/v2/presets");
  }

  createPreset({ name, visualCharacterId, systemPrompt, voiceId, languageCode }) {
    const body = { name };
    if (visualCharacterId) body.visual_character_id = visualCharacterId;
    if (systemPrompt) body.system_prompt = systemPrompt;
    if (voiceId) body.voice_id = voiceId;
    if (languageCode) body.language_code = languageCode;
    return this._request("POST", "/api/v2/presets", body);
  }

  getPreset(presetId) {
    return this._request("GET", `/api/v2/presets/${enc(presetId)}`);
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
        "User-Agent": "anva-js/0.2.0",
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
      const err = payload.error || payload;
      throw new AnvaError(res.status, err.code || "request_failed", err.message || "request failed");
    }
    return payload;
  }
}

function enc(part) {
  return encodeURIComponent(String(part));
}

export default Anva;
