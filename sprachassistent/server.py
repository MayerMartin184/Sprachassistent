"""Lokaler HTTP-Server: liefert die Oberfläche (ui/index.html) und JSON-Endpunkte für das Backend.

Läuft als eigener Prozess: `python -m sprachassistent --backend --port 12345`.
Beendet sich selbst, wenn die Oberfläche 30 s lang nicht mehr abfragt (Fenster geschlossen).
"""

from __future__ import annotations

import json
import logging
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .config import Settings
from .webapp import Api, create_backend

log = logging.getLogger(__name__)
UI_DIR = Path(__file__).with_name("ui")


def make_handler(api: Api):  # noqa: ANN201
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt: str, *args: Any) -> None:  # leise
            log.debug("HTTP " + fmt, *args)

        def _json(self, payload: Any, status: int = 200) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length") or 0)
            if not length:
                return {}
            return json.loads(self.rfile.read(length).decode("utf-8") or "{}")

        def do_GET(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            if path in ("/", "/index.html"):
                body = (UI_DIR / "index.html").read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)
            elif path == "/api/config":
                self._json(api.config())
            elif path == "/api/poll":
                self._json(api.poll())
            elif path == "/api/settings":
                self._json(api.get_settings())
            else:
                self._json({"error": "not found"}, 404)

        def do_POST(self) -> None:  # noqa: N802
            path = self.path.split("?")[0]
            try:
                data = self._body()
                if path == "/api/send":
                    api.send(data.get("text", ""))
                    self._json({"ok": True})
                elif path == "/api/set_mic":
                    api.set_mic(bool(data.get("on")))
                    self._json({"ok": True})
                elif path == "/api/settings":
                    self._json({"message": api.save_settings(data)})
                elif path == "/api/open_settings":
                    api.open_settings()
                    self._json({"ok": True})
                elif path == "/api/confirm":
                    api.answer_confirm(str(data.get("id")), bool(data.get("ok")))
                    self._json({"ok": True})
                else:
                    self._json({"error": "not found"}, 404)
            except Exception as exc:  # noqa: BLE001
                log.exception("Anfrage fehlgeschlagen: %s", path)
                self._json({"error": str(exc)}, 500)

    return Handler


def serve(settings: Settings, port: int, idle_timeout: float = 30.0) -> None:
    api = create_backend(settings)
    server = ThreadingHTTPServer(("127.0.0.1", port), make_handler(api))
    server.daemon_threads = True
    threading.Thread(target=api.start, name="backend-start", daemon=True).start()

    def watchdog() -> None:
        started = time.time()
        while True:
            time.sleep(5)
            silent = time.time() - api.last_poll
            if silent > idle_timeout and time.time() - started > 60:
                log.info("Oberfläche meldet sich nicht mehr – Backend beendet sich.")
                api.shutdown()
                server.shutdown()
                return

    threading.Thread(target=watchdog, name="watchdog", daemon=True).start()
    log.info("Backend bereit auf http://127.0.0.1:%s", port)
    try:
        server.serve_forever()
    finally:
        api.shutdown()
