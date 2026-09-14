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
	AnvaExpressive  ServiceMode = "anva_expressive"
	ElevenAgentsMax ServiceMode = "elevenagents_max"
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
	WebhookURL           string         `json:"webhook_url,omitempty"`
	WebhookSecret        string         `json:"webhook_secret,omitempty"`
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
	ExpiresAt    string         `json:"expires_at"`
	// MaxDurationSeconds is how long the session may stay live once connected.
	MaxDurationSeconds int    `json:"max_duration_seconds"`
	// Metadata echoes the map passed at creation, if any.
	Metadata map[string]any `json:"metadata,omitempty"`
	EmbedURL           string `json:"embed_url"`
	EventsWSURL        string `json:"events_ws_url"`
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
	err := c.do(ctx, http.MethodPost, "/api/v2/sessions", p, &out)
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

// EventsWSURL is the WebSocket URL for the session's live event stream
// (transcripts, state changes). It carries no credentials; send AuthHeader
// with the handshake, e.g.
// websocket.DefaultDialer.Dial(c.EventsWSURL(id), c.AuthHeader()).
func (c *Client) EventsWSURL(sessionID string) string {
	base := strings.Replace(c.BaseURL, "http", "ws", 1)
	return base + "/api/v2/sessions/" + esc(sessionID) + "/events"
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

func (c *Client) do(ctx context.Context, method, path string, body, out any) error {
	var reader io.Reader
	if body != nil {
		raw, err := json.Marshal(body)
		if err != nil {
			return err
		}
		reader = bytes.NewReader(raw)
	}
	req, err := http.NewRequestWithContext(ctx, method, c.BaseURL+path, reader)
	if err != nil {
		return err
	}
	req.Header.Set("Authorization", "Bearer "+c.APIKey)
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("User-Agent", "anva-go/0.4.0")
	httpc := c.HTTPClient
	if httpc == nil {
		httpc = http.DefaultClient
	}
	resp, err := httpc.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	raw, err := io.ReadAll(io.LimitReader(resp.Body, 4<<20))
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
