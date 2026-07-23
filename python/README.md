# anva — Python SDK

Official Python SDK for [Anva](https://anva.ai) — live AI avatars.

```bash
pip install anva          # REST client, zero dependencies
pip install "anva[ws]"    # + live event stream (WebSocket)
```

```python
from anva import Anva

client = Anva("anva_key_...")

session = client.create_session(character_id="char_...")
print(session["embed_url"])

client.send_message(session["session_id"], "Welcome!")
client.interrupt(session["session_id"])

for event in client.events(session["session_id"]):
    print(event)

chars = client.list_characters()
```

Errors raise `anva.AnvaError` with `.status`, `.code` and `.message`.
MIT © Penguin Robotics
