# anva — Python SDK

Install with `pip install "anva[ws]==0.5.0"`.
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
own; `lipsync()` and `connect_lipsync()` reach the Enterprise Lipsync API.

All five service modes are supported as request values, subject to deployment
capabilities. PCM methods accept `bytes`, `bytearray` or byte-oriented `memoryview`:
24kHz signed16 little-endian mono, maximum 24,000 bytes per chunk. Read the
repository README for sample offsets, backpressure and real playback requirements.
