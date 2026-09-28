package anva

import (
	"context"
	"encoding/binary"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSynthesizeDecodesAudio(t *testing.T) {
	var path string
	var body map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path = r.URL.Path
		body = nil
		json.NewDecoder(r.Body).Decode(&body)
		w.Header().Set("Content-Type", "application/json")
		w.Write([]byte(`{"id":"speech_1","voice_id":"elevenlabs:v","sample_rate":24000,"duration_s":0.1,
			"audio":{"format":"pcm","data":"AID/fw=="},
			"curves":{"fps":30,"channels":["jawOpen"],"frame_count":1,"preset":"hybrid","model":"m","release":"r","frames":[[0.5]]},
			"alignment":{"characters":["H"],"starts":[0],"ends":[0.1]},
			"billing":{"unit":"tokens","basis":"audio_time","seconds":0.1,"tokens_per_minute":120}}`))
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	ctx := context.Background()
	result, err := c.Synthesize(ctx, SpeechParams{Text: "Hi.", VoiceID: "elevenlabs:v", Speed: 0.9, Preset: "lowlat", Format: "pcm"})
	if err != nil || path != "/api/v2/speech" || body["voice_id"] != "elevenlabs:v" || body["speed"] != 0.9 || body["format"] != "pcm" {
		t.Fatal(err, path, body)
	}
	if string(result.Audio.Data) != "\x00\x80\xff\x7f" || result.Audio.Format != "pcm" || result.Curves.Frames[0][0] != 0.5 ||
		result.Curves.Release != "r" || result.Alignment == nil || result.Alignment.Characters[0] != "H" || result.SampleRate != 24000 {
		t.Fatalf("%+v", result)
	}
	if _, err := c.Synthesize(ctx, SpeechParams{Text: "Hi.", VoiceID: "elevenlabs:v"}); err != nil {
		t.Fatal(err)
	}
	if _, ok := body["speed"]; ok || len(body) != 2 {
		t.Fatal("unset options must be omitted", body)
	}
	if _, err := c.Synthesize(ctx, SpeechParams{Text: "Hi."}); err == nil {
		t.Fatal("missing VoiceID must fail")
	}
}

// speechSocket replays frames and records the JSON commands written.
type speechSocket struct {
	frames []string
	sent   []string
	closed bool
}

func (s *speechSocket) ReadJSON(out any) error {
	if len(s.frames) == 0 {
		return io.EOF
	}
	frame := s.frames[0]
	s.frames = s.frames[1:]
	return json.Unmarshal([]byte(frame), out)
}
func (s *speechSocket) WriteJSON(in any) error {
	raw, err := json.Marshal(in)
	s.sent = append(s.sent, string(raw))
	return err
}
func (s *speechSocket) Close() error { s.closed = true; return nil }

func TestSpeechStream(t *testing.T) {
	c := New("fixture-key")
	c.BaseURL = "https://fixture.invalid"
	if got := c.SpeechStreamURL(SpeakOptions{}); got != "wss://fixture.invalid/api/v2/speech/stream" {
		t.Fatal(got)
	}
	if got := c.SpeechStreamURL(SpeakOptions{VoiceID: "elevenlabs:v", Speed: 0.9, Preset: "lowlat"}); got != "wss://fixture.invalid/api/v2/speech/stream?preset=lowlat&speed=0.9&voice_id=elevenlabs%3Av" {
		t.Fatal(got)
	}
	s := &speechSocket{frames: []string{
		`{"type":"ready","sample_rate":24000,"fps":30,"channels":["jawOpen"],"preset":"hybrid","max_text_chars":2000,"release":"r"}`,
		`{"type":"curves","id":"l1","start":0,"values":[[0.5]]}`,
		`{"type":"audio","id":"l1","start_sample":0,"samples":2,"sample_rate":24000,"data":"AID/fw=="}`,
		`{"type":"done","id":"l1","total_samples":2,"frame_count":1,"duration_s":0.0001}`,
		`{"type":"error","id":"l2","code":"busy_line","message":"a line is running"}`,
	}}
	stream := NewSpeechStream(s)
	stream.Speak("l1", "Hello.", SpeakOptions{})
	stream.Speak("l2", "Hi.", SpeakOptions{VoiceID: "elevenlabs:w", Speed: 1.1, Preset: "lowlat"})
	stream.Cancel("l2")
	var events []SpeechEvent
	for {
		event, err := stream.Receive()
		if err != nil {
			break
		}
		events = append(events, event)
	}
	if len(events) != 5 || events[0].MaxTextChars != 2000 || events[1].Values[0][0] != 0.5 || events[3].FrameCount != 1 || events[4].Code != "busy_line" {
		t.Fatalf("%+v", events)
	}
	if pcm := events[2].Data; len(pcm) != 4 || int16(binary.LittleEndian.Uint16(pcm[2:])) != 32767 || events[2].Samples != 2 {
		t.Fatal(pcm)
	}
	stream.Close()
	want := []string{
		`{"id":"l1","text":"Hello.","type":"speak"}`,
		`{"id":"l2","preset":"lowlat","speed":1.1,"text":"Hi.","type":"speak","voice_id":"elevenlabs:w"}`,
		`{"id":"l2","type":"cancel"}`,
		`{"type":"close"}`,
	}
	if strings.Join(s.sent, "\n") != strings.Join(want, "\n") || !s.closed {
		t.Fatalf("sent %v closed %v", s.sent, s.closed)
	}
}

func TestSayQueue(t *testing.T) {
	var body map[string]any
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		body = nil
		json.NewDecoder(r.Body).Decode(&body)
		w.Write([]byte(`{"status":"queued","say_id":"l2"}`))
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	if id, err := c.SayWith(context.Background(), "s", "Next.", "l2", LineOptions{Queue: true}); err != nil || id != "l2" || body["queue"] != true || body["speed"] != nil {
		t.Fatal(id, err, body)
	}
	c.Say(context.Background(), "s", "Now.", "")
	if _, ok := body["queue"]; ok {
		t.Fatal("Say must not queue", body)
	}
	f := &fakeSocket{}
	r := NewRealtime(f)
	r.SayWith("After.", "a", LineOptions{Queue: true})
	r.SayDeltaWith("b", "Then ", LineOptions{Speed: 0.9, Queue: true})
	r.SayWith("Now.", "c", LineOptions{})
	got, _ := json.Marshal(f.sent)
	exp, _ := json.Marshal([]Envelope{
		{Type: "say", Payload: map[string]any{"text": "After.", "say_id": "a", "queue": true}},
		{Type: "say.delta", Payload: map[string]any{"say_id": "b", "text": "Then ", "speed": 0.9, "queue": true}},
		{Type: "say", Payload: map[string]any{"text": "Now.", "say_id": "c"}},
	})
	if string(got) != string(exp) {
		t.Fatalf("sent %s\nwant %s", got, exp)
	}
}
