package anva

import (
	"encoding/json"
	"strings"
	"testing"
)

func TestEventsURLKeepsKeyOutOfURL(t *testing.T) {
	c := New("fixture-key")
	c.BaseURL = "https://fixture.invalid"
	if got := c.EventsWSURL("s"); got != "wss://fixture.invalid/api/v2/sessions/s/events" {
		t.Fatal(got)
	}
	if got := c.AuthHeader().Get("Authorization"); got != "Bearer fixture-key" {
		t.Fatal(got)
	}
	if got := c.EventsURL("s"); got != "wss://fixture.invalid/api/v2/sessions/s/events?api_key=fixture-key" {
		t.Fatal(got)
	}
}

func TestMaxDurationSecondsOmittedWhenZero(t *testing.T) {
	for limit, want := range map[int]bool{0: false, 600: true} {
		raw, _ := json.Marshal(CreateSessionParams{PresetID: "p", MaxDurationSeconds: limit})
		if got := strings.Contains(string(raw), `"max_duration_seconds":600`); got != want {
			t.Fatalf("limit %d: %s", limit, raw)
		}
	}
}
