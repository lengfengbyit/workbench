"""HTTP server: serves the static UI, the cached data, and the few write endpoints (notes, archive, config, refresh)."""
import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from .build import build
from .notes import Notes
from .providers import load_provider
from .settings import validate_ui_config

PKG = os.path.dirname(os.path.abspath(__file__))
MAX_BODY = 1 << 20
CTYPES = {".css": "text/css", ".js": "application/javascript"}


class App:
    def __init__(self, settings, provider=None):
        self.settings = settings
        self.provider = provider or load_provider(settings.config)
        self.notes = Notes(settings.notes_path)
        self._lock = threading.Lock()

    def refresh(self, fetch=True):
        with self._lock:
            started = time.monotonic()
            data = build(self.settings, self.provider, self.notes, fetch)
            data["refreshMs"] = round((time.monotonic() - started) * 1000)
            os.makedirs(self.settings.home, exist_ok=True)
            tmp = self.settings.cache_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            os.replace(tmp, self.settings.cache_path)
            return data

    def cached_bytes(self):
        if not os.path.exists(self.settings.cache_path):
            return json.dumps(self.refresh(fetch=False), ensure_ascii=False).encode()
        with open(self.settings.cache_path, "rb") as f:
            return f.read()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _body(self):
            n = int(self.headers.get("Content-Length") or 0)
            if n > MAX_BODY:
                raise ValueError("request body too large")
            return json.loads(self.rfile.read(n) or b"{}")

        def do_GET(self):
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                with open(os.path.join(PKG, "index.html"), "rb") as f:
                    return self._send(200, f.read(), "text/html; charset=utf-8")
            if path.startswith("/static/"):
                name = os.path.basename(path)
                ctype = CTYPES.get(os.path.splitext(name)[1])
                file = os.path.join(PKG, "static", name)
                if ctype and os.path.isfile(file):
                    with open(file, "rb") as f:
                        return self._send(200, f.read(), ctype + "; charset=utf-8")
                return self._send(404, {"error": "not found"})
            if path == "/api/data":
                try:
                    return self._send(200, app.cached_bytes())
                except Exception as e:  # noqa: BLE001  shown as-is in the page
                    return self._send(500, {"error": str(e)})
            self._send(404, {"error": "not found"})

        def do_POST(self):
            # No login: refuse browser requests that come from another origin (a page on the web posting to localhost)
            origin = self.headers.get("Origin")
            if origin and urlparse(origin).netloc != self.headers.get("Host"):
                return self._send(403, {"error": "cross-origin request refused"})
            path = self.path.split("?")[0]
            try:
                if path == "/api/refresh":
                    return self._send(200, app.refresh(fetch="nofetch" not in self.path))
                if path == "/api/doc":
                    app.notes.save_doc(self._body())
                    return self._send(200, app.refresh(fetch=False))
                if path == "/api/requirement":
                    app.notes.save_requirement(self._body())
                    return self._send(200, app.refresh(fetch=False))
                if path == "/api/local-requirement":
                    rid = app.notes.save_local_requirement(self._body())
                    return self._send(200, {**app.refresh(fetch=False), "savedId": rid})
                if path == "/api/config":
                    app.settings.update_config(validate_ui_config(self._body()))
                    return self._send(200, app.refresh(fetch=False))
                if path == "/api/archive":
                    body = self._body()
                    app.notes.archive(body["id"], body.get("title", ""))
                    return self._send(200, app.refresh(fetch=False))
            except Exception as e:  # noqa: BLE001
                return self._send(500, {"error": str(e)})
            self._send(404, {"error": "not found"})

        def log_message(self, fmt, *args):
            print(time.strftime("%H:%M:%S"), self.address_string(), fmt % args, flush=True)

    return Handler


def serve(app, host, port):
    print(f"workbench: http://{host}:{port}/", flush=True)
    if host not in ("127.0.0.1", "localhost", "::1"):
        print("warning: listening beyond localhost and there is no login; anyone who can reach this port sees your items", flush=True)
    ThreadingHTTPServer((host, port), make_handler(app)).serve_forever()
