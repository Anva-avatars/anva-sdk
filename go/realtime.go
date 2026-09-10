package anva

import (
	"context"
	"fmt"
	"sync"
)

// JSONSocket is implemented by WebSocket libraries such as gorilla/websocket.
// Establish the socket using Client.EventsURL; keep that authenticated URL private.
type JSONSocket interface {
	ReadJSON(any) error
	WriteJSON(any) error
	Close() error
}
type Envelope struct {
	Type    string         `json:"type"`
	Payload map[string]any `json:"payload,omitempty"`
}

// Realtime wraps one socket. It supports one event reader and serialized writers.
// Calling Interrupt cancels speech; closing a control socket is not EndSession.
type Realtime struct {
	socket  JSONSocket
	writeMu sync.Mutex
}

func NewRealtime(socket JSONSocket) *Realtime { return &Realtime{socket: socket} }
func (r *Realtime) Receive() (Envelope, error) {
	var event Envelope
	err := r.socket.ReadJSON(&event)
	return event, err
}
func (r *Realtime) Close() error { return r.socket.Close() }
func (r *Realtime) Send(kind string, payload map[string]any) error {
	r.writeMu.Lock()
	defer r.writeMu.Unlock()
	return r.socket.WriteJSON(Envelope{Type: kind, Payload: payload})
}
func (r *Realtime) Message(text string) error { return r.Send("message", map[string]any{"text": text}) }
func (r *Realtime) Interrupt() error          { return r.Send("interrupt", map[string]any{}) }
func (r *Realtime) UpdateContext(context map[string]any) error {
	return r.Send("context.update", context)
}
func (r *Realtime) StartPresentation(start map[string]any) error {
	return r.Send("presentation.start", start)
}
func (r *Realtime) TurnDelta(turnID, text string) error {
	return r.Send("turn.delta", map[string]any{"turn_id": turnID, "text": text})
}
func (r *Realtime) TurnDone(turnID string) error {
	return r.Send("turn.done", map[string]any{"turn_id": turnID})
}
func (r *Realtime) TurnCancel(turnID, reason string) error {
	return r.Send("turn.cancel", map[string]any{"turn_id": turnID, "reason": reason})
}
func speechStart(turnID, text string) map[string]any {
	p := map[string]any{"turn_id": turnID, "codec": "pcm_s16le", "sample_rate": 24000, "channels": 1}
	if text != "" {
		p["text"] = text
	}
	return p
}
func speechAppend(turnID string, seq, startSample int64, pcm []byte) (map[string]any, error) {
	if len(pcm) == 0 || len(pcm)%2 != 0 || len(pcm) > 24000 {
		return nil, fmt.Errorf("PCM chunk must contain 1–12000 signed 16-bit samples")
	}
	if seq < 0 || startSample < 0 {
		return nil, fmt.Errorf("seq and startSample must be nonnegative")
	}
	// encoding/json marshals []byte as base64, preserving the exact byte order.
	return map[string]any{"turn_id": turnID, "seq": seq, "start_sample": startSample, "data": pcm}, nil
}
func (r *Realtime) StartSpeech(turnID, text string) error {
	return r.Send("speech.start", speechStart(turnID, text))
}
func (r *Realtime) AppendSpeech(turnID string, seq, startSample int64, pcm []byte) error {
	p, e := speechAppend(turnID, seq, startSample, pcm)
	if e != nil {
		return e
	}
	return r.Send("speech.append", p)
}
func (r *Realtime) FinishSpeech(turnID string, totalSamples int64) error {
	return r.Send("speech.done", map[string]any{"turn_id": turnID, "total_samples": totalSamples})
}
func (r *Realtime) CancelSpeech(turnID string) error {
	return r.Send("speech.cancel", map[string]any{"turn_id": turnID})
}

func (c *Client) Capabilities(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/capabilities", nil, &out)
	return out, e
}
func (c *Client) Billing(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/billing", nil, &out)
	return out, e
}
func (c *Client) ListAvatars(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/avatars", nil, &out)
	return out, e
}
func (c *Client) ListVoices(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/voices", nil, &out)
	return out, e
}
func (c *Client) ListLanguages(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/languages", nil, &out)
	return out, e
}
func (c *Client) ListInstances(ctx context.Context) (map[string]any, error) {
	var out map[string]any
	e := c.do(ctx, "GET", "/api/v2/instances", nil, &out)
	return out, e
}
func (c *Client) UpdatePreset(ctx context.Context, id string, patch map[string]any) (*Preset, error) {
	var out Preset
	e := c.do(ctx, "PATCH", "/api/v2/presets/"+esc(id), patch, &out)
	return &out, e
}
func (c *Client) UpdateContext(ctx context.Context, id string, payload map[string]any) error {
	return c.do(ctx, "POST", "/api/v2/sessions/"+esc(id)+"/context", payload, nil)
}
func (c *Client) StartPresentation(ctx context.Context, id string, payload map[string]any) error {
	return c.do(ctx, "POST", "/api/v2/sessions/"+esc(id)+"/presentation", payload, nil)
}
func (c *Client) Speech(ctx context.Context, id, kind string, payload map[string]any) error {
	return c.do(ctx, "POST", "/api/v2/sessions/"+esc(id)+"/speech", Envelope{Type: kind, Payload: payload}, nil)
}
func (c *Client) StartSpeech(ctx context.Context, id, turnID, text string) error {
	return c.Speech(ctx, id, "speech.start", speechStart(turnID, text))
}
func (c *Client) AppendSpeech(ctx context.Context, id, turnID string, seq, startSample int64, pcm []byte) error {
	p, e := speechAppend(turnID, seq, startSample, pcm)
	if e != nil {
		return e
	}
	return c.Speech(ctx, id, "speech.append", p)
}
func (c *Client) FinishSpeech(ctx context.Context, id, turnID string, totalSamples int64) error {
	return c.Speech(ctx, id, "speech.done", map[string]any{"turn_id": turnID, "total_samples": totalSamples})
}
func (c *Client) CancelSpeech(ctx context.Context, id, turnID string) error {
	return c.Speech(ctx, id, "speech.cancel", map[string]any{"turn_id": turnID})
}
