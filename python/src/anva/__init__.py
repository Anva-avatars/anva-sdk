"""Official Python SDK for Anva (https://anva.ai) — live AI avatars.

Quickstart:

    from anva import Anva

    client = Anva("anva_key_...")
    session = client.create_session(character_id="char_...")
    print(session["embed_url"])

    for event in client.events(session["session_id"]):   # pip install anva[ws]
        print(event)
"""
from .client import Anva, AnvaError

__all__ = ["Anva", "AnvaError"]
__version__ = "0.1.0"
