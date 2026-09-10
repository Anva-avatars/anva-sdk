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
    socket.onopen = () => this.resolveReady(this);
    socket.onmessage = event => {
      try { this.queue.push(JSON.parse(event.data)); } catch { return; }
      this.wake();
    };
    socket.onclose = event => {
      this.closed = true;
      if (event.code !== 1000 && event.code !== undefined) this.failure ||= new Error(`Events socket closed (${event.code})`);
      this.rejectReady(this.failure || new Error('Events socket closed before opening'));
      this.wake();
    };
    socket.onerror = () => {
      this.failure = new Error('Events socket error');
      this.closed = true;
      this.rejectReady(this.failure);
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
  startSpeech(turnId, { text } = {}) { return this.send('speech.start', speechStart(turnId, text)); }
  appendSpeech(turnId, seq, startSample, pcm) { return this.send('speech.append', speechAppend(turnId, seq, startSample, pcm)); }
  finishSpeech(turnId, totalSamples) { return this.send('speech.done', { turn_id: turnId, total_samples: totalSamples }); }
  cancelSpeech(turnId) { return this.send('speech.cancel', { turn_id: turnId }); }
  close() {
    if (this.closeRequested) return;
    this.closeRequested = true;
    this.closed = true;
    this.rejectReady(new Error('Events socket closed before opening'));
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
