// Package anva is the official Go SDK for Anva (https://anva.ai) —
// live AI avatars for your product.
//
//	client := anva.New(os.Getenv("ANVA_KEY"))
//	session, err := client.CreateSession(ctx, anva.CreateSessionParams{
//		PresetID: "...",
//	})
//	// put session.EmbedURL in an <iframe allow="camera; microphone; autoplay">
//
// The event stream is a WebSocket at Client.EventsWSURL(sessionID) — bring the
// WebSocket library of your choice and send Client.AuthHeader() with the
// handshake.
package anva

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"
)

type ServiceMode string

const (
	AvatarOnly      ServiceMode = "avatar_only"
	BYOLLM          ServiceMode = "byo_llm"
	AnvaLight       ServiceMode = "anva_light"
	AnvaStandard    ServiceMode = "anva_standard"
	AnvaExpressive  ServiceMode = "anva_expressive"
	ElevenAgentsMax ServiceMode = "elevenagents_max"
)

// Voice performance modes (CreateSessionParams.PerformanceMode). Each managed
// service mode pins its own: AnvaLight fast, AnvaStandard standard,
// AnvaExpressive expressive. PerformanceStandard has no speaking-rate control.
const (
	PerformanceFast       = "fast"
	PerformanceStandard   = "standard"
	PerformanceExpressive = "expressive"
)

const DefaultBaseURL = "https://anva.ai"

// Client talks to the Anva REST API. Safe for concurrent use.
type Client struct {
	APIKey     string
	BaseURL    string
	HTTPClient *http.Client
}

// New returns a Client with sane defaults.
func New(apiKey string) *Client {
	return &Client{
		APIKey:     strings.TrimSpace(apiKey),
		BaseURL:    DefaultBaseURL,
		HTTPClient: &http.Client{Timeout: 30 * time.Second},
	}
}

// Error is an API error with the server's machine-readable code.
type Error struct {
	Status  int    `json:"-"`
	Code    string `json:"code"`
	Message string `json:"message"`
}

func (e *Error) Error() string {
	return fmt.Sprintf("%s: %s (HTTP %d)", e.Code, e.Message, e.Status)
}

// CreateSessionParams configures a new live session. Provide PresetID (embed
// tier) OR AvatarID plus the persona fields (advanced tier, nothing stored).
// With ServiceMode left empty the server uses AnvaStandard (Anva Realtime, 70
// tokens/min), or AnvaLight when SpeechSpeed is set.
type CreateSessionParams struct {
	PresetID             string         `json:"preset_id,omitempty"`
	AvatarID             string         `json:"avatar_id,omitempty"`
	SystemPrompt         string         `json:"system_prompt,omitempty"`
	VoiceID              string         `json:"voice_id,omitempty"`
	LanguageCode         string         `json:"language_code,omitempty"`
	ServiceMode          ServiceMode    `json:"service_mode,omitempty"`
	LLMMode              string         `json:"llm_mode,omitempty"` // Deprecated compatibility alias.
	PerformanceOptions   map[string]any `json:"performance_options,omitempty"`
	ConversationProvider string         `json:"conversation_provider,omitempty"`
	PerformanceMode      string         `json:"performance_mode,omitempty"`
	ElevenLabsAgentID    string         `json:"elevenlabs_agent_id,omitempty"`
	DynamicExpressions   *bool          `json:"dynamic_expressions,omitempty"`
	// SpeechInput "off" (BYOLLM, AnvaLight, AnvaStandard, AnvaExpressive) is
	// for hosts that transcribe the user themselves, such as push-to-talk: the
	// embed opens no microphone and each user turn arrives through SendMessage.
	SpeechInput string `json:"speech_input,omitempty"`
	// SpeechSpeed is the speaking rate, 0.7–1.2 (1 is the voice's natural
	// pace), for anva_light and byo_llm voices; nil keeps the default.
	// AnvaStandard (or PerformanceStandard) has no speaking-rate control and
	// the create fails with a 400 *Error, Code "speed_unsupported".
	SpeechSpeed *float64 `json:"speech_speed,omitempty"`
	// WakeUp starts the call with the avatar's eyes closed; they open once
	// the viewer's video is showing. session.info reports wake_up false for
	// avatars that cannot close their eyes convincingly.
	WakeUp *bool `json:"wake_up,omitempty"`
	// IdempotencyKey (16–128 letters, digits, - or _) is sent as the
	// Idempotency-Key header: a retry with the same key and body within 24
	// hours returns the first session instead of a second one.
	IdempotencyKey string `json:"-"`
	WebhookURL     string `json:"webhook_url,omitempty"`
	WebhookSecret  string `json:"webhook_secret,omitempty"`
	// MaxDurationSeconds (60–7200) ends the session that long after it goes
	// live; 0 applies the server's 2-hour ceiling.
	MaxDurationSeconds int `json:"max_duration_seconds,omitempty"`
	// Metadata is an optional flat map (string, number or bool values, up to
	// 20 keys, 4 KB serialized) stored with the session and echoed on the
	// session, on session.info and in every webhook payload.
	Metadata map[string]any `json:"metadata,omitempty"`
}

// Session is the create-session response.
type Session struct {
	SessionID    string         `json:"session_id"`
	SessionToken string         `json:"session_token"`
	InstanceID   string         `json:"instance_id"`
	PresetID     string         `json:"preset_id"`
	AvatarID     string         `json:"avatar_id"`
	LLMMode      string         `json:"llm_mode"`
	ServiceMode  ServiceMode    `json:"service_mode"`
	Billing      map[string]any `json:"billing"`
	SpeechInput  string         `json:"speech_input"`
	ExpiresAt    string         `json:"expires_at"`
	// MaxDurationSeconds is how long the session may stay live once connected.
	MaxDurationSeconds int `json:"max_duration_seconds"`
	// Metadata echoes the map passed at creation, if any.
	Metadata    map[string]any `json:"metadata,omitempty"`
	EmbedURL    string         `json:"embed_url"`
	EventsWSURL string         `json:"events_ws_url"`
}

// Preset mirrors the public preset resource.
type Preset struct {
	ID                 string `json:"id"`
	Name               string `json:"name"`
	AvatarID           string `json:"avatar_id"`
	VisualCharacterID  string `json:"visual_character_id"` // Deprecated alias.
	SystemPrompt       string `json:"system_prompt"`
	VoiceID            string `json:"voice_id"`
	LanguageCode       string `json:"language_code"`
	Disabled           bool   `json:"disabled"`
	Active             bool   `json:"active"`
	BargeIn            bool   `json:"barge_in"`
	ProactiveQuestions bool   `json:"proactive_questions"`
	GreetingEnabled    bool   `json:"greeting_enabled"`
	GreetingText       string `json:"greeting_text"`
}

// CreatePresetParams configures a new preset.
type CreatePresetParams struct {
	Name              string `json:"name"`
	AvatarID          string `json:"avatar_id,omitempty"`
	VisualCharacterID string `json:"visual_character_id,omitempty"` // Deprecated alias.
	SystemPrompt      string `json:"system_prompt,omitempty"`
	VoiceID           string `json:"voice_id,omitempty"`
	LanguageCode      string `json:"language_code,omitempty"`
}

// -- sessions ---------------------------------------------------------------

func (c *Client) CreateSession(ctx context.Context, p CreateSessionParams) (*Session, error) {
	if (p.PresetID == "") == (p.AvatarID == "") {
		return nil, fmt.Errorf("provide exactly one of PresetID or AvatarID")
	}
	var out Session
	var header http.Header
	if p.IdempotencyKey != "" {
		header = http.Header{"Idempotency-Key": []string{p.IdempotencyKey}}
	}
	err := c.do(ctx, http.MethodPost, "/api/v2/sessions", p, &out, header)
	return &out, err
}

func (c *Client) GetSession(ctx context.Context, sessionID string) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodGet, "/api/v2/sessions/"+esc(sessionID), nil, &out)
	return out, err
}

func (c *Client) EndSession(ctx context.Context, sessionID string) error {
	return c.do(ctx, http.MethodDelete, "/api/v2/sessions/"+esc(sessionID), nil, nil)
}

// UpdateSession replaces a managed session's instructions while it runs; they
// apply from the next reply (AnvaLight, AnvaStandard, AnvaExpressive; added as context for
// ElevenAgentsMax). On a live connection, Realtime.UpdatePrompt does the same.
func (c *Client) UpdateSession(ctx context.Context, sessionID, systemPrompt string) error {
	body := map[string]string{"system_prompt": systemPrompt}
	return c.do(ctx, http.MethodPatch, "/api/v2/sessions/"+esc(sessionID), body, nil)
}

// SendMessage sends text as a user message; the avatar hears it and replies
// (it does NOT speak text verbatim). External replies use BYOLLM and
// Realtime.TurnDelta / TurnDone.
func (c *Client) SendMessage(ctx context.Context, sessionID, text string) error {
	body := map[string]string{"text": text}
	return c.do(ctx, http.MethodPost, "/api/v2/sessions/"+esc(sessionID)+"/messages", body, nil)
}

// Interrupt stops the avatar mid-sentence.
func (c *Client) Interrupt(ctx context.Context, sessionID string) error {
	return c.do(ctx, http.MethodPost, "/api/v2/sessions/"+esc(sessionID)+"/interrupt", struct{}{}, nil)
}

func (c *Client) TriggerAction(ctx context.Context, sessionID, name string) error {
	body := map[string]string{"name": name}
	return c.do(ctx, http.MethodPost, "/api/v2/sessions/"+esc(sessionID)+"/actions", body, nil)
}

// Say speaks text verbatim in the session voice (BYOLLM), without a
// turn.request, and returns the line's say_id (generated when sayID is empty).
// The line's turn.complete event carries the same say_id. The viewer's embed
// must be connected.
func (c *Client) Say(ctx context.Context, sessionID, text, sayID string) (string, error) {
	return c.say(ctx, sessionID, text, sayID, nil)
}

// SayAtSpeed is Say with this line's speaking rate (0.7–1.2). Every line ends
// with one line.ended event saying how much of it the viewer heard. A session
// on the Anva Realtime voice (AnvaStandard) has no speaking-rate control: the
// call fails with a 400 *Error, Code "speed_unsupported", and the line gets
// no line.ended.
func (c *Client) SayAtSpeed(ctx context.Context, sessionID, text, sayID string, speed float64) (string, error) {
	return c.say(ctx, sessionID, text, sayID, &speed)
}

// LineOptions shape one host line. Speed (0.7–1.2) sets its speaking rate; 0
// keeps the session's (a session on AnvaStandard refuses a Speed with
// speed_unsupported). Queue waits behind the line being spoken instead of
// interrupting it (at most 8 wait; one more is refused with an error event
// say_queue_full). On a streamed line, both are read from its first delta.
type LineOptions struct {
	Speed float64
	Queue bool
}

func (o LineOptions) apply(p map[string]any) {
	if o.Speed != 0 {
		p["speed"] = o.Speed
	}
	if o.Queue {
		p["queue"] = true
	}
}

// SayWith is Say with LineOptions, e.g. LineOptions{Queue: true} to queue
// the line behind the one being spoken.
func (c *Client) SayWith(ctx context.Context, sessionID, text, sayID string, opts LineOptions) (string, error) {
	var speed *float64
	if opts.Speed != 0 {
		speed = &opts.Speed
	}
	return c.sayLine(ctx, sessionID, text, sayID, speed, opts.Queue)
}

func (c *Client) say(ctx context.Context, sessionID, text, sayID string, speed *float64) (string, error) {
	return c.sayLine(ctx, sessionID, text, sayID, speed, false)
}

func (c *Client) sayLine(ctx context.Context, sessionID, text, sayID string, speed *float64, queue bool) (string, error) {
	body := map[string]any{"text": text}
	if sayID != "" {
		body["say_id"] = sayID
	}
	if speed != nil {
		body["speed"] = *speed
	}
	if queue {
		body["queue"] = true
	}
	var out struct {
		SayID string `json:"say_id"`
	}
	err := c.do(ctx, http.MethodPost, "/api/v2/sessions/"+esc(sessionID)+"/say", body, &out)
	return out.SayID, err
}

// EventsWSURL is the WebSocket URL for the session's live event stream
// (transcripts, state changes). It carries no credentials; send AuthHeader
// with the handshake, e.g.
// websocket.DefaultDialer.Dial(c.EventsWSURL(id), c.AuthHeader()).
func (c *Client) EventsWSURL(sessionID string, opts ...EventsOption) string {
	base := strings.Replace(c.BaseURL, "http", "ws", 1)
	u := base + "/api/v2/sessions/" + esc(sessionID) + "/events"
	q := url.Values{}
	for _, opt := range opts {
		opt(q)
	}
	if len(q) > 0 {
		u += "?" + q.Encode()
	}
	return u
}

// EventsOption adjusts what the events socket carries.
type EventsOption func(url.Values)

// WithoutControls leaves the per-frame face stream (controls) out of the events.
func WithoutControls() EventsOption {
	return func(q url.Values) { q.Set("controls", "false") }
}

// AuthHeader authenticates a WebSocket handshake to EventsWSURL.
func (c *Client) AuthHeader() http.Header {
	return http.Header{"Authorization": []string{"Bearer " + c.APIKey}}
}

// EventsURL is the events WebSocket URL with the API key in its query string.
//
// Deprecated: proxies and access logs record query strings. Use EventsWSURL
// with AuthHeader.
func (c *Client) EventsURL(sessionID string) string {
	return c.EventsWSURL(sessionID) + "?api_key=" + url.QueryEscape(c.APIKey)
}

// -- presets ----------------------------------------------------------------

func (c *Client) ListPresets(ctx context.Context) ([]Preset, error) {
	var out struct {
		Presets []Preset `json:"presets"`
	}
	err := c.do(ctx, http.MethodGet, "/api/v2/presets", nil, &out)
	return out.Presets, err
}

func (c *Client) CreatePreset(ctx context.Context, p CreatePresetParams) (*Preset, error) {
	if p.AvatarID == "" {
		p.AvatarID = p.VisualCharacterID
	}
	p.VisualCharacterID = ""
	var out Preset
	err := c.do(ctx, http.MethodPost, "/api/v2/presets", p, &out)
	return &out, err
}

func (c *Client) GetPreset(ctx context.Context, presetID string) (*Preset, error) {
	var out Preset
	err := c.do(ctx, http.MethodGet, "/api/v2/presets/"+esc(presetID), nil, &out)
	return &out, err
}

func (c *Client) DeletePreset(ctx context.Context, presetID string) error {
	return c.do(ctx, http.MethodDelete, "/api/v2/presets/"+esc(presetID), nil, nil)
}

// -- plumbing ---------------------------------------------------------------

func (c *Client) do(ctx context.Context, method, path string, body, out any, headers ...http.Header) error {
	var reader io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(raw)
	}
	return c.send(ctx, method, path, "application/json", reader, out, headers...)
}

// send performs one request with a body of the given content type and decodes
// a JSON reply into out.
func (c *Client) send(ctx context.Context, method, path, contentType string, body io.Reader, out any, headers ...http.Header) error {
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, body)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.APIKey)
	req.Header.Set("Content-Type", contentType)
	req.Header.Set("User-Agent", "anva-go/0.8.0")
	for _, h := range headers {
		for k, vs := range h {
			for _, v := range vs {
				req.Header.Add(k, v)
			}
		}
	}
	httpc := c.HTTPClient
	if httpc == nil {
		httpc = http.DefaultClient
	}
	resp, err := httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 64<<20))
	if err != nil {
		return err
	}
	if resp.StatusCode >= 300 {
		apiErr := &Error{Status: resp.StatusCode, Code: "request_failed"}
		var wrapped struct {
			Error *Error `json:"error"`
		}
		if json.Unmarshal(raw, &wrapped) == nil && wrapped.Error != nil {
			apiErr.Code, apiErr.Message = wrapped.Error.Code, wrapped.Error.Message
		} else if json.Unmarshal(raw, apiErr) != nil || apiErr.Message == "" {
			apiErr.Message = strings.TrimSpace(string(raw))
			if len(apiErr.Message) > 300 {
				apiErr.Message = apiErr.Message[:300]
			}
		}
		apiErr.Status = resp.StatusCode
		return apiErr
	}
	if out != nil && len(raw) > 0 {
		return json.Unmarshal(raw, out)
	}
	return nil
}

func esc(part string) string {
	return url.PathEscape(part)
}
