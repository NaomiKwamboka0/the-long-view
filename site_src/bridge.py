"""Run the Hatua portal inside a web browser, for the practice website only.

The practice website (https://naomikwamboka0.github.io/the-long-view/try/) loads
Python in the browser (Pyodide), then this file. The page's requests to /api/... never
leave the browser: they come here and go to the same portal code a laptop runs.

Differences from a laptop, all because this is a practice website with made-up people:
* PINs are hashed with SHA-256, because the browser's Python has no scrypt. The
  practice school is built with the same function (scripts/build_site.py).
* Qwen is off. The assistant gives Hatua's built-in answers.
* Nothing is saved. Reloading the page starts the practice school again.
"""
import hashlib
import io
import json
import os
import sys
from email.message import Message

os.environ.setdefault("HATUA_HOME", "/app/home")  # the build sets its own folder
os.environ.update(HATUA_TODAY="2026-11-04", HATUA_LLM="off")
if "/app" not in sys.path:
    sys.path.insert(0, "/app")


def web_hash(pin: str, salt: bytes) -> str:
    return hashlib.sha256(b"hatua-practice-website|" + salt + pin.encode("utf-8")).hexdigest()


from hatua import auth, portal  # noqa: E402 - the settings above must come first

auth._hash = web_hash


class _Server:
    server_address = ("127.0.0.1", 8765)


class WebHandler(portal.Handler):
    """The portal's own request handler, without a network socket."""

    def __init__(self, method: str, path: str, headers: dict, body: bytes):  # no super(): there is no socket
        self.command, self.path, self.server, self.result = method, path, _Server(), None
        self.headers = Message()
        for key, value in headers.items():
            self.headers[key] = value
        self.headers["Content-Length"] = str(len(body))
        self.rfile = io.BytesIO(body)

    def _send(self, status, body, ctype="application/json; charset=utf-8", extra=None):
        data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False, default=str).encode()
        self.result = (status, data, ctype, dict(extra or {}))


def handle(method: str, path: str, headers_json: str, body=None):
    raw = bytes(body.to_py()) if body is not None else b""
    h = WebHandler(method, path, json.loads(headers_json), raw)
    h._run(method)
    return h.result
