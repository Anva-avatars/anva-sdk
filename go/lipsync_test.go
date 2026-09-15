package anva

import (
	"context"
	"encoding/json"
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
)

func TestSpeechInputSayAndLipsyncClip(t *testing.T) {
	var path, query, contentType string
	var body []byte
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		path, query, contentType = r.URL.Path, r.URL.RawQuery, r.Header.Get("Content-Type")
		body, _ = io.ReadAll(r.Body)
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/api/v2/lipsync" {
			w.Write([]byte(`{"id":"lipsync_1","fps":30,"frame_count":1,"channels":["jawOpen"],"frames":[[0.5]]}`))
			return
		}
		w.Write([]byte(`{"session_id":"s","speech_input":"off","say_id":"say_1"}`))
	}))
	defer server.Close()
	c := New("fixture-key")
	c.BaseURL = server.URL
	ctx := context.Background()
	session, err := c.CreateSession(ctx, CreateSessionParams{AvatarID: "a", ServiceMode: BYOLLM, SpeechInput: "off"})
	if err != nil || session.SpeechInput != "off" || !strings.Contains(string(body), `"speech_input":"off"`) {
		t.Fatal(session, err, string(body))
	}
	id, err := c.Say(ctx, "s", "Welcome.", "")
	if err != nil || id != "say_1" || path != "/api/v2/sessions/s/say" || string(body) != `{"text":"Welcome."}` {
		t.Fatal(id, err, path, string(body))
	}
	result, err := c.Lipsync(ctx, []byte{1, 2}, LipsyncOptions{SampleRate: 16000, Preset: "lowlat"})
	if err != nil || result.Frames[0][0] != 0.5 || path != "/api/v2/lipsync" || query != "preset=lowlat&sample_rate=16000" ||
		contentType != "audio/pcm" || string(body) != "\x01\x02" {
		t.Fatal(result, err, path, query, contentType, body)
	}
	if _, err := c.Lipsync(ctx, []byte("RIFF"), LipsyncOptions{}); err != nil || query != "" || contentType != "application/octet-stream" {
		t.Fatal(err, query, contentType)
	}
	if got := c.LipsyncStreamURL(16000, ""); got != strings.Replace(server.URL, "http", "ws", 1)+"/api/v2/lipsync/stream?sample_rate=16000" {
		t.Fatal(got)
	}
}

// scriptedSocket replays frames and records what is written.
type scriptedSocket struct {
	frames []string
	sent   []Envelope
	binary [][]byte
	text   []string
}

func (s *scriptedSocket) ReadJSON(out any) error {
	if len(s.frames) == 0 {
		return io.EOF
	}
	frame := s.frames[0]
	s.frames = s.frames[1:]
	return json.Unmarshal([]byte(frame), out)
}
func (s *scriptedSocket) WriteJSON(in any) error { s.sent = append(s.sent, in.(Envelope)); return nil }
func (s *scriptedSocket) WriteMessage(kind int, data []byte) error {
	if kind == binaryMessage {
		s.binary = append(s.binary, data)
	} else {
		s.text = append(s.text, string(data))
	}
	return nil
}
func (s *scriptedSocket) Close() error { return nil }

func TestHostLinesWaitForTheViewer(t *testing.T) {
	s := &scriptedSocket{frames: []string{`{"type":"session.info","payload":{"status":"pending"}}`, `{"type":"session.live","payload":{"status":"active"}}`}}
	r := NewRealtime(s)
	live, err := r.WaitLive()
	if err != nil || live.Payload["status"] != "active" {
		t.Fatal(live, err)
	}
	r.Say("Welcome.", "lesson-3")
	r.SayDelta("hint", "Try ")
	r.SayDone("hint")
	if len(s.sent) != 3 || s.sent[0].Type != "say" || s.sent[0].Payload["say_id"] != "lesson-3" ||
		s.sent[1].Type != "say.delta" || s.sent[1].Payload["text"] != "Try " || s.sent[2].Type != "say.done" {
		t.Fatal(s.sent)
	}
	ended := &scriptedSocket{frames: []string{`{"type":"session.ended","payload":{"reason":"expired"}}`}}
	if _, err := NewRealtime(ended).WaitLive(); err == nil {
		t.Fatal("WaitLive ignored session.ended")
	}
}

func TestLipsyncStreamSendsBinaryPCM(t *testing.T) {
	s := &scriptedSocket{frames: []string{`{"type":"ready","fps":30,"delay_ms":133}`, `{"type":"frames","start":0,"values":[[0.25]]}`}}
	l := NewLipsyncStream(s)
	if ready, err := l.Receive(); err != nil || ready.Type != "ready" || ready.DelayMS != 133 {
		t.Fatal(ready, err)
	}
	if err := l.Audio([]byte{1, 2}); err != nil {
		t.Fatal(err)
	}
	if err := l.Audio([]byte{1}); err == nil {
		t.Fatal("odd PCM must fail")
	}
	if err := l.Flush(); err != nil {
		t.Fatal(err)
	}
	if frames, err := l.Receive(); err != nil || frames.Values[0][0] != 0.25 {
		t.Fatal(frames, err)
	}
	if len(s.binary) != 1 || len(s.text) != 1 || s.text[0] != `{"type":"flush"}` {
		t.Fatal(s.binary, s.text)
	}
}
