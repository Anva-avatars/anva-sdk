# anva — Python SDK

Install with `pip install "anva[ws]==0.7.0"`.
The REST client uses the standard library. Realtime uses `websockets`' sync API.

```python
import os
from anva import Anva, AnvaError
client = Anva(os.environ["ANVA_KEY"])
capabilities = client.capabilities()
session = client.create_session(
    preset_id="YOUR_PRESET_ID", service_mode="byo_llm")
# Attach session["embed_url"] in your browser.
try:
    with client.connect(session["session_id"]) as stream:
        stream.wait_live()  # the viewer's embed is connected
        for event in stream:
            if event["type"] == "turn.request":
                turn_id = event["payload"]["turn_id"]
                # Replace the immediate sample with your cancellable LLM worker.
                stream.turn_delta(turn_id, "Hello from your application.")
                stream.turn_done(turn_id)
finally:
    client.end_session(session["session_id"])
```

Use one reader per connection; perform slow LLM work in a separate cancellable
worker so it can react to `turn.cancel`. `send_message` is user input, not
verbatim assistant speech. `AnvaError` includes `status`, `code`, `message`,
and `details`. Realtime command failures remain structured events.

`create_session(speech_input="off")` suits hosts that transcribe the user
themselves (push-to-talk); `say` / `say_delta` / `say_done` speak lines of your
own (`speed=` sets a line's rate); `update_session(id, system_prompt=...)` and
`update_prompt` on a connection change a managed session's instructions
mid-call; `create_session(..., idempotency_key=...)` makes a retried create
return the first session; `connect(id, controls=False)` leaves out the face
stream; `lipsync()` and `connect_lipsync()` reach the Enterprise Lipsync API
(up to eight jobs at once per account; a stream idle for 60 seconds is
closed). `say(..., queue=True)` and `say_delta(..., queue=True)` on its first
delta make a line wait behind the one being spoken instead of interrupting it.

Speech API (Enterprise): text to 24 kHz speech plus its mouth curves.

```python
line = client.synthesize("Welcome back.", voice_id="elevenlabs:JBFqnCBsd6RMkjVDRZzb")
with open("line.wav", "wb") as f:
    f.write(line["audio"]["data"])          # decoded bytes
curves = line["curves"]                     # frame n is n / curves["fps"] seconds in
jaw = [row[curves["channels"].index("jawOpen")] for row in curves["frames"]]

with client.connect_speech(voice_id="elevenlabs:JBFqnCBsd6RMkjVDRZzb") as speech:
    speech.speak("line-1", "Hello there.")
    for msg in speech:
        if msg["type"] == "curves":
            queue_curves(msg["start"], msg["values"])   # arrive before their audio
        elif msg["type"] == "audio":
            play(msg["data"])                           # 24 kHz s16le mono bytes
        elif msg["type"] in ("done", "error"):
            break
```

One line is spoken at a time per stream (`busy_line` otherwise; `cancel(id)`
stops one), and the server closes a stream that gets no command for 60 seconds
while nothing is spoken.

All five service modes are supported as request values, subject to deployment
capabilities. PCM methods accept `bytes`, `bytearray` or byte-oriented `memoryview`:
24kHz signed16 little-endian mono, maximum 24,000 bytes per chunk. Read the
repository README for sample offsets, backpressure and real playback requirements.
