# anva — Python SDK

Official Python SDK for [Anva](https://anva.ai) — live AI avatars.

```bash
pip install anva          # REST client, zero dependencies
pip install "anva[ws]"    # + live event stream (WebSocket)
```

```python
from anva import Anva

client = Anva("anva_key_...")

# Embed tier: start from a preset saved in the Playground.
session = client.create_session(preset_id="preset_...")
print(session["embed_url"])

client.send_message(session["session_id"], "Welcome!")
client.interrupt(session["session_id"])

for event in client.events(session["session_id"]):
    print(event)

presets = client.list_presets()
instances = client.list_instances()
```

Advanced tier — skip presets and pass an avatar plus an inline persona
(nothing is stored server-side):

```python
session = client.create_session(
    avatar_id="avatar_...",
    system_prompt="You are a friendly guide.",
    voice_id="voice_...",
    language_code="en-US",
)
```

Errors raise `anva.AnvaError` with `.status`, `.code` and `.message`.
MIT © Penguin Robotics
