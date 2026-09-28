package anva

import (
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
)

// SpeechParams is one Speech API line. Text (at most 2,000 characters) and
// VoiceID (a voice from ListVoices) are required. Speed is 0.7–1.2 (0 keeps
// the server default, 0.85); Preset is "hybrid" (default) or "lowlat";
// Format is "wav" (default, a complete WAV file) or "pcm" (raw 16-bit
// little-endian mono samples).
type SpeechParams struct {
	Text    string  `json:"text"`
	VoiceID string  `json:"voice_id"`
	Speed   float64 `json:"speed,omitempty"`
	Preset  string  `json:"preset,omitempty"`
	Format  string  `json:"format,omitempty"`
}

// SpeechAudio is a line's audio. Data is decoded from the API's base64.
type SpeechAudio struct {
	Format string `json:"format"`
	Data   []byte `json:"data"`
}

// SpeechCurves are the 24 ARKit mouth channels measured on the audio:
// Frames[n][i] is Channels[i] at n/FPS seconds, and
// FrameCount = ceil(samples / 800).
type SpeechCurves struct {
	FPS        int         `json:"fps"`
	Channels   []string    `json:"channels"`
	FrameCount int         `json:"frame_count"`
	Preset     string      `json:"preset"`
	Model      string      `json:"model"`
	Release    string      `json:"release"`
	Frames     [][]float64 `json:"frames"`
}

// SpeechAlignment times each character of the text, in seconds on the audio
// clock.
type SpeechAlignment struct {
	Characters []string  `json:"characters"`
	Starts     []float64 `json:"starts"`
	Ends       []float64 `json:"ends"`
}

// SpeechResult is a synthesized line: 24 kHz audio and its mouth curves on
// one clock. Alignment is nil when the voice provider does not return it.
type SpeechResult struct {
	ID         string           `json:"id"`
	VoiceID    string           `json:"voice_id"`
	SampleRate int              `json:"sample_rate"`
	DurationS  float64          `json:"duration_s"`
	Audio      SpeechAudio      `json:"audio"`
	Curves     SpeechCurves     `json:"curves"`
	Alignment  *SpeechAlignment `json:"alignment,omitempty"`
	Billing    map[string]any   `json:"billing"`
}

// Synthesize turns text into Anva TTS audio plus its mouth curves (Speech
// API, Enterprise).
func (c *Client) Synthesize(ctx context.Context, p SpeechParams) (*SpeechResult, error) {
	if p.VoiceID == "" {
		return nil, fmt.Errorf("synthesize requires VoiceID (a voice from ListVoices)")
	}
	var out SpeechResult
	err := c.do(ctx, http.MethodPost, "/api/v2/speech", p, &out)
	return &out, err
}

// SpeakOptions sets a spoken line's voice, speed (0.7–1.2) and mouth preset.
// Empty fields keep the stream's defaults (or, as stream defaults, the
// server's).
type SpeakOptions struct {
	VoiceID string
	Speed   float64
	Preset  string
}

// SpeechStreamURL is the Speech stream's WebSocket URL; dial it with
// AuthHeader. defaults apply to every line on the stream.
func (c *Client) SpeechStreamURL(defaults SpeakOptions) string {
	query := url.Values{}
	if defaults.VoiceID != "" {
		query.Set("voice_id", defaults.VoiceID)
	}
	if defaults.Speed != 0 {
		query.Set("speed", strconv.FormatFloat(defaults.Speed, 'f', -1, 64))
	}
	if defaults.Preset != "" {
		query.Set("preset", defaults.Preset)
	}
	u := strings.Replace(c.BaseURL, "http", "ws", 1) + "/api/v2/speech/stream"
	if len(query) > 0 {
		u += "?" + query.Encode()
	}
	return u
}

// SpeechEvent is one message on a Speech stream: "ready", "curves", "audio",
// "alignment", "done", "cancelled" or "error". ID names the line. Data holds
// an audio message's 16-bit little-endian mono PCM, decoded from base64.
type SpeechEvent struct {
	Type string `json:"type"`
	ID   string `json:"id"`
	// ready
	SampleRate   int      `json:"sample_rate"`
	FPS          int      `json:"fps"`
	Channels     []string `json:"channels"`
	Preset       string   `json:"preset"`
	MaxTextChars int      `json:"max_text_chars"`
	Release      string   `json:"release"`
	// curves: frames Start onwards
	Start  int         `json:"start"`
	Values [][]float64 `json:"values"`
	// audio
	StartSample int64  `json:"start_sample"`
	Samples     int64  `json:"samples"`
	Data        []byte `json:"data"`
	// alignment
	Characters []string  `json:"characters"`
	Starts     []float64 `json:"starts"`
	Ends       []float64 `json:"ends"`
	// done and cancelled
	TotalSamples int64   `json:"total_samples"`
	FrameCount   int     `json:"frame_count"`
	DurationS    float64 `json:"duration_s"`
	// error
	Code    string `json:"code"`
	Message string `json:"message"`
}

// SpeechStream speaks lines over one WebSocket (Enterprise). A line's curves
// always arrive before the audio they describe. One line is spoken at a time:
// a Speak while a line runs is refused with error busy_line, so wait for its
// "done" or Cancel it. The server closes a stream that receives no command
// for 60 seconds while nothing is spoken (error idle_timeout). It supports
// one reader and serialized writers.
type SpeechStream struct {
	socket  JSONSocket
	writeMu sync.Mutex
}

// NewSpeechStream wraps a socket dialled at Client.SpeechStreamURL with
// Client.AuthHeader.
func NewSpeechStream(socket JSONSocket) *SpeechStream { return &SpeechStream{socket: socket} }

func (s *SpeechStream) write(message map[string]any) error {
	s.writeMu.Lock()
	defer s.writeMu.Unlock()
	return s.socket.WriteJSON(message)
}

// Speak speaks one line. id (1–128 characters) is yours and is echoed on
// every event for the line.
func (s *SpeechStream) Speak(id, text string, opts SpeakOptions) error {
	message := map[string]any{"type": "speak", "id": id, "text": text}
	if opts.VoiceID != "" {
		message["voice_id"] = opts.VoiceID
	}
	if opts.Speed != 0 {
		message["speed"] = opts.Speed
	}
	if opts.Preset != "" {
		message["preset"] = opts.Preset
	}
	return s.write(message)
}

// Cancel stops a line; it ends with "cancelled".
func (s *SpeechStream) Cancel(id string) error {
	return s.write(map[string]any{"type": "cancel", "id": id})
}

// Receive reads the next event.
func (s *SpeechStream) Receive() (SpeechEvent, error) {
	var event SpeechEvent
	err := s.socket.ReadJSON(&event)
	return event, err
}

// Close tells the server the stream is finished and closes the socket.
func (s *SpeechStream) Close() error {
	_ = s.write(map[string]any{"type": "close"})
	return s.socket.Close()
}
