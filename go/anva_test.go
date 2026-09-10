package anva

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestCanonicalModesAndCommands(t *testing.T) {
	var path string
	var body map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path = r.URL.Path
		body = nil
		if r.Body != nil {
			json.NewDecoder(r.Body).Decode(&body)
		}
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"session_id": "s", "service_mode": body["service_mode"]})
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	ctx := context.Background()
	for _, mode := range []ServiceMode{AvatarOnly, BYOLLM, AnvaLight, AnvaExpressive, ElevenAgentsMax} {
		got, e := c.CreateSession(ctx, CreateSessionParams{AvatarID: "a", ServiceMode: mode})
		if e != nil || got.ServiceMode != mode {
			t.Fatal(got, e)
		}
	}
	if _, e := c.CreateSession(ctx, CreateSessionParams{PresetID: "p", AvatarID: "a"}); e == nil {
		t.Fatal("expected exclusive IDs")
	}
	c.Capabilities(ctx)
	if path != "/api/v2/capabilities" {
		t.Fatal(path)
	}
	c.Billing(ctx)
	if path != "/api/v2/billing" {
		t.Fatal(path)
	}
	c.CreatePreset(ctx, CreatePresetParams{Name: "Guide", VisualCharacterID: "legacy"})
	if body["avatar_id"] != "legacy" || body["visual_character_id"] != nil {
		t.Fatal(body)
	}
	c.AppendSpeech(ctx, "s", "t", 0, 0, []byte{0, 128, 255, 127})
	p := body["payload"].(map[string]any)
	if p["data"] != "AID/fw==" || p["start_sample"] != float64(0) {
		t.Fatal(p)
	}
	if e := c.AppendSpeech(ctx, "s", "t", 0, 0, []byte{1}); e == nil {
		t.Fatal("odd PCM must fail")
	}
	c.UpdateContext(ctx, "s", map[string]any{"version": 1})
	if path != "/api/v2/sessions/s/context" {
		t.Fatal(path)
	}
	c.StartPresentation(ctx, "s", map[string]any{"version": 1})
	if path != "/api/v2/sessions/s/presentation" {
		t.Fatal(path)
	}
}
func TestStructuredError(t *testing.T) {
	s := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.WriteHeader(503)
		w.Write([]byte(`{"error":{"code":"mode_unavailable","message":"Unavailable"}}`))
	}))
	defer s.Close()
	c := New("fixture")
	c.BaseURL = s.URL
	_, e := c.Capabilities(context.Background())
	var apiError *Error
	if !errors.As(e, &apiError) || apiError.Code != "mode_unavailable" || apiError.Status != 503 {
		t.Fatal(e)
	}
}

type fakeSocket struct {
	sent   []Envelope
	closed bool
}

func (s *fakeSocket) ReadJSON(out any) error {
	return json.Unmarshal([]byte(`{"type":"speech.state","payload":{"state":"error","code":"stale_turn"}}`), out)
}
func (s *fakeSocket) WriteJSON(in any) error { s.sent = append(s.sent, in.(Envelope)); return nil }
func (s *fakeSocket) Close() error           { s.closed = true; return nil }
func TestRealtime(t *testing.T) {
	s := &fakeSocket{}
	r := NewRealtime(s)
	r.TurnDelta("t", "Hello")
	r.TurnDone("t")
	r.UpdateContext(map[string]any{"version": 1})
	r.StartPresentation(map[string]any{"version": 1})
	r.Interrupt()
	r.AppendSpeech("t", 0, 0, []byte{1, 2})
	e, err := r.Receive()
	if err != nil || e.Payload["code"] != "stale_turn" {
		t.Fatal(e, err)
	}
	r.Close()
	if len(s.sent) != 6 || !s.closed {
		t.Fatal(s)
	}
}
