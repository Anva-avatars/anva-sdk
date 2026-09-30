package anva

import (
	"context"
	"encoding/json"
	"errors"
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

func TestAnvaRealtimeDefaultAndSpeedUnsupported(t *testing.T) {
	const message = "Anva Realtime (anva_standard) has no speaking-rate control; use anva_light"
	var body map[string]any
	refuse := false
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body = nil
		json.NewDecoder(r.Body).Decode(&body)
		w.Header().Set("Content-Type", "application/json")
		if refuse {
			w.WriteHeader(http.StatusBadRequest)
			json.NewEncoder(w).Encode(map[string]any{"error": map[string]any{"code": "speed_unsupported", "message": message}})
			return
		}
		json.NewEncoder(w).Encode(map[string]any{"session_id": "s", "service_mode": "anva_standard"})
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	ctx := context.Background()

	if AnvaStandard != "anva_standard" || PerformanceStandard != "standard" {
		t.Fatal(AnvaStandard, PerformanceStandard)
	}
	got, err := c.CreateSession(ctx, CreateSessionParams{PresetID: "p"})
	if _, named := body["service_mode"]; err != nil || named || got.ServiceMode != AnvaStandard {
		t.Fatal(got, err, body)
	}
	c.CreateSession(ctx, CreateSessionParams{PresetID: "p", ServiceMode: AnvaStandard, PerformanceMode: PerformanceStandard})
	if body["service_mode"] != "anva_standard" || body["performance_mode"] != "standard" {
		t.Fatal(body)
	}

	refuse = true
	rate := 0.9
	_, err = c.CreateSession(ctx, CreateSessionParams{PresetID: "p", ServiceMode: AnvaStandard, SpeechSpeed: &rate})
	var apiErr *Error
	if !errors.As(err, &apiErr) || apiErr.Status != 400 || apiErr.Code != "speed_unsupported" || apiErr.Message != message {
		t.Fatal(err)
	}
	apiErr = nil
	if _, err = c.SayAtSpeed(ctx, "s", "Slowly.", "", 0.8); !errors.As(err, &apiErr) || apiErr.Code != "speed_unsupported" {
		t.Fatal(err)
	}
}
