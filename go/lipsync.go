package anva

import (
	"bytes"
	"context"
	"fmt"
	"net/http"
	"net/url"
	"strconv"
	"strings"
	"sync"
)

// LipsyncOptions configures one Lipsync API request. SampleRate marks the
// audio as raw 16-bit little-endian mono PCM; leave it zero for WAV, FLAC or
// OGG. Preset is "hybrid" (the default) or "lowlat".
type LipsyncOptions struct {
	SampleRate  int
	Preset      string
	ContentType string
}

// LipsyncResult holds a clip's 24 ARKit mouth curves: Frames[n][i] is
// Channels[i] at n/FPS seconds.
type LipsyncResult struct {
	ID         string         `json:"id"`
	FPS        int            `json:"fps"`
	FrameCount int            `json:"frame_count"`
	DurationS  float64        `json:"duration_s"`
	Channels   []string       `json:"channels"`
	Frames     [][]float64    `json:"frames"`
	Preset     string         `json:"preset"`
	Model      string         `json:"model"`
	Billing    map[string]any `json:"billing"`
}

// Lipsync returns the mouth curves for one audio clip (Enterprise).
func (c *Client) Lipsync(ctx context.Context, audio []byte, opts LipsyncOptions) (*LipsyncResult, error) {
	query := url.Values{}
	if opts.SampleRate != 0 {
		query.Set("sample_rate", strconv.Itoa(opts.SampleRate))
	}
	if opts.Preset != "" {
		query.Set("preset", opts.Preset)
	}
	path := "/api/v2/lipsync"
	if len(query) > 0 {
		path += "?" + query.Encode()
	}
	contentType := opts.ContentType
	if contentType == "" {
		contentType = "application/octet-stream"
		if opts.SampleRate != 0 {
			contentType = "audio/pcm"
		}
	}
	var out LipsyncResult
	err := c.send(ctx, http.MethodPost, path, contentType, bytes.NewReader(audio), &out)
	return &out, err
}

// LipsyncStreamURL is the Lipsync stream's WebSocket URL; dial it with
// AuthHeader. sampleRate is 16000 or 24000; preset may be empty.
func (c *Client) LipsyncStreamURL(sampleRate int, preset string) string {
	query := url.Values{"sample_rate": {strconv.Itoa(sampleRate)}}
	if preset != "" {
		query.Set("preset", preset)
	}
	return strings.Replace(c.BaseURL, "http", "ws", 1) + "/api/v2/lipsync/stream?" + query.Encode()
}

// BinarySocket is implemented by WebSocket libraries such as gorilla/websocket.
type BinarySocket interface {
	ReadJSON(any) error
	WriteMessage(messageType int, data []byte) error
	Close() error
}

// WebSocket message types as RFC 6455 (and gorilla/websocket) number them.
const (
	textMessage   = 1
	binaryMessage = 2
)

// LipsyncFrame is one message on a Lipsync stream: "ready", "frames",
// "flushed" or "error".
type LipsyncFrame struct {
	Type       string      `json:"type"`
	Start      int         `json:"start"`
	Values     [][]float64 `json:"values"`
	FrameCount int         `json:"frame_count"`
	FPS        int         `json:"fps"`
	Channels   []string    `json:"channels"`
	DelayMS    int         `json:"delay_ms"`
	Code       string      `json:"code"`
	Message    string      `json:"message"`
}

// LipsyncStream streams PCM in and mouth curves out (Enterprise). It supports
// one reader and serialized writers.
type LipsyncStream struct {
	socket  BinarySocket
	writeMu sync.Mutex
}

func NewLipsyncStream(socket BinarySocket) *LipsyncStream { return &LipsyncStream{socket: socket} }

// Audio sends one binary frame of 16-bit little-endian mono PCM at the
// stream's sample rate, at most 192 KB.
func (l *LipsyncStream) Audio(pcm []byte) error {
	if len(pcm) == 0 || len(pcm)%2 != 0 || len(pcm) > 192*1024 {
		return fmt.Errorf("PCM frame must hold 1–98304 signed 16-bit samples")
	}
	l.writeMu.Lock()
	defer l.writeMu.Unlock()
	return l.socket.WriteMessage(binaryMessage, pcm)
}

// Flush ends an utterance: the remaining frames arrive, then "flushed".
func (l *LipsyncStream) Flush() error {
	l.writeMu.Lock()
	defer l.writeMu.Unlock()
	return l.socket.WriteMessage(textMessage, []byte(`{"type":"flush"}`))
}

func (l *LipsyncStream) Receive() (LipsyncFrame, error) {
	var frame LipsyncFrame
	err := l.socket.ReadJSON(&frame)
	return frame, err
}

func (l *LipsyncStream) Close() error { return l.socket.Close() }
