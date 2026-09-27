/** A single bidirectional events connection. Keep the API key on your server. */
export class RealtimeSession {
  constructor(socket) {
    this.socket = socket;
    this.queue = [];
    this.waiters = [];
    this.closed = false;
    this.closeRequested = false;
    this.failure = null;
    this.ready = new Promise((resolve, reject) => {
      this.resolveReady = resolve;
      this.rejectReady = reject;
    });
    // Resolves with the session.live payload once the viewer's embed is
    // connected; commands sent before it are refused.
    this.live = new Promise((resolve, reject) => {
      this.resolveLive = resolve;
      this.rejectLive = reject;
    });
    this.live.catch(() => {});
    socket.onopen = () => this.resolveReady(this);
    socket.onmessage = event => {
      let message;
      try { message = JSON.parse(event.data); } catch { return; }
      if (message?.type === 'session.live') this.resolveLive(message.payload ?? {});
      this.queue.push(message);
      this.wake();
    };
    socket.onclose = event => {
      this.closed = true;
      if (event.code !== 1000 && event.code !== undefined) this.failure ||= new Error(`Events socket closed (${event.code})`);
      this.rejectReady(this.failure || new Error('Events socket closed before opening'));
      this.rejectLive(this.failure || new Error('Events socket closed before the viewer connected'));
      this.wake();
    };
    socket.onerror = () => {
      this.failure = new Error('Events socket error');
      this.closed = true;
      this.rejectReady(this.failure);
      this.rejectLive(this.failure);
      this.close();
      this.wake();
    };
    if (socket.readyState === 1) this.resolveReady(this);
  }
  wake() { for (const resolve of this.waiters.splice(0)) resolve(); }
  async send(type, payload = {}) {
    await this.ready;
    if (this.closed || this.socket.readyState !== 1) throw new Error('Events socket is not open');
    this.socket.send(JSON.stringify({ type, payload }));
  }
  message(text) { return this.send('message', { text }); }
  interrupt() { return this.send('interrupt'); }
  updateContext(context) { return this.send('context.update', context); }
  startPresentation(start) { return this.send('presentation.start', start); }
  turnDelta(turnId, text) { return this.send('turn.delta', { turn_id: turnId, text }); }
  turnDone(turnId) { return this.send('turn.done', { turn_id: turnId }); }
  turnCancel(turnId, reason = '') { return this.send('turn.cancel', { turn_id: turnId, reason }); }
  /** Speak a host line in the session voice (byo_llm). */
  /** Speak `text` verbatim; `speed` (0.7–1.2) sets this line's rate. */
  say(text, sayId, { speed } = {}) {
    const payload = sayId ? { text, say_id: sayId } : { text };
    if (speed !== undefined) payload.speed = speed;
    return this.send('say', payload);
  }
  /** Stream a line; put `speed` on its first delta. */
  sayDelta(sayId, text, { speed } = {}) {
    const payload = { say_id: sayId, text };
    if (speed !== undefined) payload.speed = speed;
    return this.send('say.delta', payload);
  }
  /** Replace a managed session's instructions mid-call (session.update). */
  updatePrompt(systemPrompt) { return this.send('session.update', { system_prompt: systemPrompt }); }
  sayDone(sayId) { return this.send('say.done', { say_id: sayId }); }
  startSpeech(turnId, { text } = {}) { return this.send('speech.start', speechStart(turnId, text)); }
  appendSpeech(turnId, seq, startSample, pcm) { return this.send('speech.append', speechAppend(turnId, seq, startSample, pcm)); }
  finishSpeech(turnId, totalSamples) { return this.send('speech.done', { turn_id: turnId, total_samples: totalSamples }); }
  cancelSpeech(turnId) { return this.send('speech.cancel', { turn_id: turnId }); }
  close() {
    if (this.closeRequested) return;
    this.closeRequested = true;
    this.closed = true;
    this.rejectReady(new Error('Events socket closed before opening'));
    this.rejectLive(new Error('Events socket closed before the viewer connected'));
    try { this.socket.close(1000); } finally { this.wake(); }
  }
  async *[Symbol.asyncIterator]() {
    await this.ready;
    try {
      while (!this.closed || this.queue.length) {
        if (!this.queue.length) { await new Promise(resolve => this.waiters.push(resolve)); continue; }
        yield this.queue.shift();
      }
      if (this.failure) throw this.failure;
    } finally { this.close(); }
  }
}
/** Lipsync API stream (Enterprise): binary PCM in, curve frames out. Iterate
 * for `ready`, `frames`, `flushed` and `error` messages. */
export class LipsyncStream extends RealtimeSession {
  /** One binary frame of 16-bit little-endian mono PCM at the stream's rate. */
  audio(pcm) {
    const bytes = pcm instanceof Uint8Array ? pcm : pcm instanceof ArrayBuffer ? new Uint8Array(pcm) : null;
    if (!bytes || bytes.length === 0 || bytes.length % 2 || bytes.length > 196608) throw new Error('PCM frame must hold 1–98304 signed 16-bit samples');
    return this.ready.then(() => {
      if (this.closed || this.socket.readyState !== 1) throw new Error('Lipsync socket is not open');
      this.socket.send(bytes);
    });
  }
  /** End an utterance: the remaining frames arrive, then `flushed`. */
  flush() { return this.send('flush'); }
}
export const speechStart = (turnId, text) => ({ turn_id: turnId, codec: 'pcm_s16le', sample_rate: 24000, channels: 1, ...(text === undefined ? {} : { text }) });
export function speechAppend(turnId, seq, startSample, pcm) {
  const bytes = pcm instanceof Uint8Array ? pcm : pcm instanceof ArrayBuffer ? new Uint8Array(pcm) : null;
  if (!bytes || bytes.length === 0 || bytes.length % 2 || bytes.length > 24000) throw new Error('PCM chunk must contain 1–12000 signed 16-bit samples');
  if (!Number.isSafeInteger(seq) || seq < 0 || !Number.isSafeInteger(startSample) || startSample < 0) throw new Error('seq and startSample must be nonnegative integers');
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  const data = typeof globalThis.btoa === 'function' ? globalThis.btoa(binary) : globalThis.Buffer.from(bytes).toString('base64');
  return { turn_id: turnId, seq, start_sample: startSample, data };
}
