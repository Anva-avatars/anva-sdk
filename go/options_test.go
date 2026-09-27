package anva

import (
	"context"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"
)

func TestRetrySafeCreateLineSpeedAndLiveInstructions(t *testing.T) {
	var method, path, key string
	var body map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		method, path, key = r.Method, r.URL.Path, r.Header.Get("Idempotency-Key")
		body = nil
		json.NewDecoder(r.Body).Decode(&body)
		w.Header().Set("Content-Type", "application/json")
		json.NewEncoder(w).Encode(map[string]any{"session_id": "s", "say_id": "l1"})
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	ctx := context.Background()

	c.CreateSession(ctx, CreateSessionParams{AvatarID: "a", IdempotencyKey: "portrait-request-0001"})
	if key != "portrait-request-0001" || body["IdempotencyKey"] != nil {
		t.Fatalf("header %q, body %v", key, body)
	}
	c.CreateSession(ctx, CreateSessionParams{AvatarID: "a"})
	if key != "" {
		t.Fatalf("unexpected Idempotency-Key %q", key)
	}
	if id, err := c.SayAtSpeed(ctx, "s", "Slowly now.", "l1", 0.8); err != nil || id != "l1" || body["speed"] != 0.8 || body["say_id"] != "l1" {
		t.Fatal(id, err, body)
	}
	c.Say(ctx, "s", "Plain.", "")
	if _, ok := body["speed"]; ok {
		t.Fatal("Say must not send a speed", body)
	}
	if err := c.UpdateSession(ctx, "s", "The learner is a beginner."); err != nil || method != http.MethodPatch || path != "/api/v2/sessions/s" || body["system_prompt"] != "The learner is a beginner." {
		t.Fatal(err, method, path, body)
	}
	c.BaseURL = "https://fixture.invalid"
	if got := c.EventsWSURL("s", WithoutControls()); got != "wss://fixture.invalid/api/v2/sessions/s/events?controls=false" {
		t.Fatal(got)
	}
}

func TestRealtimeLineSpeedAndPrompt(t *testing.T) {
	s := &fakeSocket{}
	r := NewRealtime(s)
	r.SayAtSpeed("Slowly.", "a", 0.8)
	r.SayDeltaAtSpeed("b", "Try ", 0.9)
	r.UpdatePrompt("Speak slowly.")
	want := []Envelope{
		{Type: "say", Payload: map[string]any{"text": "Slowly.", "say_id": "a", "speed": 0.8}},
		{Type: "say.delta", Payload: map[string]any{"say_id": "b", "text": "Try ", "speed": 0.9}},
		{Type: "session.update", Payload: map[string]any{"system_prompt": "Speak slowly."}},
	}
	got, _ := json.Marshal(s.sent)
	exp, _ := json.Marshal(want)
	if string(got) != string(exp) {
		t.Fatalf("sent %s\nwant %s", got, exp)
	}
}
