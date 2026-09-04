"""Fensterprozess: zeigt die Oberfläche in einer eingebetteten Web-Ansicht (pywebview) und startet das Backend
als eigenen Prozess. So kann kein langer Schritt des Assistenten das Fenster einfrieren."""

from __future__ import annotations

import logging
import socket
import subprocess
import sys
import time
import urllib.request

import webview

from .config import Settings

log = logging.getLogger(__name__)

LOADING_HTML = """<!doctype html><html><head><meta charset="utf-8"><style>
body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:{bg};color:{primary};
font-family:Consolas,monospace;font-size:11px;letter-spacing:.3em;text-transform:uppercase}
.d{display:flex;flex-direction:column;align-items:center;gap:22px}
.bar{width:220px;height:1px;background:{line};position:relative;overflow:hidden}
.bar::after{content:"";position:absolute;left:-40%;width:40%;height:100%;background:{primary};animation:m 1.4s ease-in-out infinite}
@keyframes m{to{left:100%}}</style></head><body><div class="d"><div>{name} startet</div><div class="bar"></div>
<div style="color:{muted};letter-spacing:.2em">Modelle und Kamera werden geladen</div></div></body></html>"""


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _wait_for_backend(port: int, timeout: float = 120.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/config", timeout=2) as resp:
                if resp.status == 200:
                    return True
        except Exception:  # noqa: BLE001
            time.sleep(0.5)
    return False


def run(settings: Settings) -> None:
    port = _free_port()
    creation = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    backend = subprocess.Popen(
        [sys.executable, "-m", "sprachassistent", "--backend", "--port", str(port)], **creation
    )
    html = LOADING_HTML
    for key, value in {"{bg}": settings.brand_bg, "{primary}": settings.brand_primary, "{line}": settings.brand_line,
                       "{muted}": settings.brand_muted, "{name}": settings.assistant_name}.items():
        html = html.replace(key, value)
    window = webview.create_window(
        f"{settings.assistant_name} – {settings.brand_title}",
        html=html,
        width=1000,
        height=760,
        min_size=(760, 560),
        background_color=settings.brand_bg,
        text_select=True,
    )

    def connect() -> None:
        if backend.poll() is not None:
            window.load_html(html.replace("startet", "konnte nicht starten").replace("Modelle und Kamera werden geladen", "Details in jarvis.log"))
            return
        if _wait_for_backend(port):
            window.load_url(f"http://127.0.0.1:{port}/")
        else:
            window.load_html(html.replace("startet", "antwortet nicht").replace("Modelle und Kamera werden geladen", "Details in jarvis.log"))

    def on_closed() -> None:
        try:
            backend.terminate()
        except Exception:  # noqa: BLE001
            pass

    window.events.closed += on_closed
    webview.start(connect, private_mode=False)
