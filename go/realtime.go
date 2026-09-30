package anva

import (
	"context"
	"fmt"
	"sync"
)

// JSONSocket is implemented by WebSocket libraries such as gorilla/websocket.
// Establish the socket at Client.EventsWSURL with Client.AuthHeader.
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

// Say speaks one host line in the session voice (BYOLLM); sayID may be empty.
func (r *Realtime) Say(text, sayID string) error {
	p := map[string]any{"text": text}
	if sayID != "" {
		p["say_id"] = sayID
	}
	return r.Send("say", p)
}

// SayAtSpeed is Say with this line's speaking rate (0.7–1.2). On the Anva
// Realtime voice (AnvaStandard), which has no rate control, the server answers
// with an error event, code speed_unsupported.
func (r *Realtime) SayAtSpeed(text, sayID string, speed float64) error {
	p := map[string]any{"text": text, "speed": speed}
	if sayID != "" {
		p["say_id"] = sayID
	}
	return r.Send("say", p)
}
func (r *Realtime) SayDelta(sayID, text string) error {
	return r.Send("say.delta", map[string]any{"say_id": sayID, "text": text})
}

// SayDeltaAtSpeed starts a streamed line at the given rate; put it on the
// line's first delta.
func (r *Realtime) SayDeltaAtSpeed(sayID, text string, speed float64) error {
	return r.Send("say.delta", map[string]any{"say_id": sayID, "text": text, "speed": speed})
}

// SayWith speaks one host line with LineOptions; LineOptions{Queue: true}
// waits behind the line being spoken instead of interrupting it.
func (r *Realtime) SayWith(text, sayID string, opts LineOptions) error {
	p := map[string]any{"text": text}
	if sayID != "" {
		p["say_id"] = sayID
	}
	opts.apply(p)
	return r.Send("say", p)
}

// SayDeltaWith starts a streamed line with LineOptions; send it as the line's
// first delta.
func (r *Realtime) SayDeltaWith(sayID, text string, opts LineOptions) error {
	p := map[string]any{"say_id": sayID, "text": text}
	opts.apply(p)
	return r.Send("say.delta", p)
}

// UpdatePrompt replaces a managed session's instructions mid-call
// (session.update).
func (r *Realtime) UpdatePrompt(systemPrompt string) error {
	return r.Send("session.update", map[string]any{"system_prompt": systemPrompt})
}
func (r *Realtime) SayDone(sayID string) error {
	return r.Send("say.done", map[string]any{"say_id": sayID})
}

// WaitLive reads until the viewer's embed is connected and returns the
// session.live envelope; commands sent before it are refused. Only
// session.info and error frames can precede it, and they are discarded.
func (r *Realtime) WaitLive() (Envelope, error) {
	for {
		event, err := r.Receive()
		if err != nil {
			return event, err
		}
		switch event.Type {
		case "session.live":
			return event, nil
		case "session.ended":
			return event, fmt.Errorf("the session ended before the viewer connected")
		}
	}
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
