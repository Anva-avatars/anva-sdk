// Package anva is the official Go SDK for Anva (https://anva.ai) —
// live AI avatars for your product.
//
//	client := anva.New(os.Getenv("ANVA_KEY"))
//	session, err := client.CreateSession(ctx, anva.CreateSessionParams{
//		CharacterID: "char_...",
//	})
//	// put session.EmbedURL in an <iframe allow="camera; microphone; autoplay">
//
// The event stream is a WebSocket at Client.EventsURL(sessionID) — bring the
// WebSocket library of your choice; the URL carries authentication.
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

// CreateSessionParams configures a new live session.
type CreateSessionParams struct {
	CharacterID   string `json:"character_id"`
	LLMMode       string `json:"llm_mode,omitempty"`
	WebhookURL    string `json:"webhook_url,omitempty"`
	WebhookSecret string `json:"webhook_secret,omitempty"`
}

// Session is the create-session response.
type Session struct {
	SessionID    string `json:"session_id"`
	SessionToken string `json:"session_token"`
	CharacterID  string `json:"character_id"`
	LLMMode      string `json:"llm_mode"`
	ExpiresAt    string `json:"expires_at"`
	EmbedURL     string `json:"embed_url"`
	EventsWSURL  string `json:"events_ws_url"`
}

// Character mirrors the public character resource.
type Character struct {
	ID                 string `json:"id"`
	Name               string `json:"name"`
	VisualCharacterID  string `json:"visual_character_id"`
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

// CreateCharacterParams configures a new character.
type CreateCharacterParams struct {
	Name              string `json:"name"`
	VisualCharacterID string `json:"visual_character_id,omitempty"`
	SystemPrompt      string `json:"system_prompt,omitempty"`
	VoiceID           string `json:"voice_id,omitempty"`
	LanguageCode      string `json:"language_code,omitempty"`
}

// -- sessions ---------------------------------------------------------------

func (c *Client) CreateSession(ctx context.Context, p CreateSessionParams) (*Session, error) {
	var out Session
	err := c.do(ctx, http.MethodPost, "/api/v1/sessions", p, &out)
	return &out, err
}

func (c *Client) GetSession(ctx context.Context, sessionID string) (map[string]any, error) {
	var out map[string]any
	err := c.do(ctx, http.MethodGet, "/api/v1/sessions/"+esc(sessionID), nil, &out)
	return out, err
}

func (c *Client) EndSession(ctx context.Context, sessionID string) error {
	return c.do(ctx, http.MethodDelete, "/api/v1/sessions/"+esc(sessionID), nil, nil)
}

// SendMessage has the avatar speak text to the user.
func (c *Client) SendMessage(ctx context.Context, sessionID, text string) error {
	body := map[string]string{"text": text}
	return c.do(ctx, http.MethodPost, "/api/v1/sessions/"+esc(sessionID)+"/messages", body, nil)
}

// Interrupt stops the avatar mid-sentence.
func (c *Client) Interrupt(ctx context.Context, sessionID string) error {
	return c.do(ctx, http.MethodPost, "/api/v1/sessions/"+esc(sessionID)+"/interrupt", struct{}{}, nil)
}

func (c *Client) TriggerAction(ctx context.Context, sessionID, name string) error {
	body := map[string]string{"name": name}
	return c.do(ctx, http.MethodPost, "/api/v1/sessions/"+esc(sessionID)+"/actions", body, nil)
}

// EventsURL is the authenticated WebSocket URL for the session's live event
// stream (transcripts, state changes). Connect with any WebSocket client.
func (c *Client) EventsURL(sessionID string) string {
	base := strings.Replace(c.BaseURL, "http", "ws", 1)
	return base + "/api/v1/sessions/" + esc(sessionID) + "/events?api_key=" +
		url.QueryEscape(c.APIKey)
}

// -- characters -------------------------------------------------------------

func (c *Client) ListCharacters(ctx context.Context) ([]Character, error) {
	var out struct {
		Characters []Character `json:"characters"`
	}
	err := c.do(ctx, http.MethodGet, "/api/v1/characters", nil, &out)
	return out.Characters, err
}

func (c *Client) CreateCharacter(ctx context.Context, p CreateCharacterParams) (*Character, error) {
	var out Character
	err := c.do(ctx, http.MethodPost, "/api/v1/characters", p, &out)
	return &out, err
}

func (c *Client) GetCharacter(ctx context.Context, characterID string) (*Character, error) {
	var out Character
	err := c.do(ctx, http.MethodGet, "/api/v1/characters/"+esc(characterID), nil, &out)
	return &out, err
}

func (c *Client) DeleteCharacter(ctx context.Context, characterID string) error {
	return c.do(ctx, http.MethodDelete, "/api/v1/characters/"+esc(characterID), nil, nil)
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
	req.Header.Set("User-Agent", "anva-go/0.1.0")
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
