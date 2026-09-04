"""Rechner-Werkzeuge: Programme starten, Webseiten öffnen, Zwischenablage, Bildschirmfoto."""

from __future__ import annotations

import base64
import os
import subprocess
import sys
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

from .base import Tool, schema

KNOWN_APPS = {
    "outlook": "outlook", "excel": "excel", "word": "winword", "powerpoint": "powerpnt", "teams": "ms-teams:",
    "explorer": "explorer", "rechner": "calc", "taschenrechner": "calc", "notepad": "notepad", "editor": "notepad",
    "edge": "msedge", "chrome": "chrome", "browser": "msedge", "onenote": "onenote", "acrobat": "acrobat",
}


def _start_menu_shortcuts() -> dict[str, Path]:
    if sys.platform != "win32":
        return {}
    bases = [
        Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "Microsoft/Windows/Start Menu/Programs",
        Path(os.environ.get("AppData", Path.home() / "AppData/Roaming")) / "Microsoft/Windows/Start Menu/Programs",
    ]
    found: dict[str, Path] = {}
    for base in bases:
        if base.exists():
            for lnk in base.rglob("*.lnk"):
                found.setdefault(lnk.stem.lower(), lnk)
    return found


def app_open(name: str) -> str:
    key = name.strip().lower()
    if key in KNOWN_APPS:
        target = KNOWN_APPS[key]
        if sys.platform == "win32":
            os.startfile(target)  # type: ignore[attr-defined]
        else:
            subprocess.Popen([target])
        return f"{name} gestartet."
    shortcuts = _start_menu_shortcuts()
    for stem, lnk in shortcuts.items():
        if key in stem:
            os.startfile(str(lnk))  # type: ignore[attr-defined]
            return f"{lnk.stem} gestartet."
    if sys.platform == "win32":
        try:
            os.startfile(name)  # type: ignore[attr-defined]
            return f"{name} gestartet."
        except OSError:
            pass
    candidates = sorted(s for s in shortcuts if any(w in s for w in key.split()))[:15]
    raise FileNotFoundError(f"Programm '{name}' nicht gefunden." + (f" Ähnlich: {', '.join(candidates)}" if candidates else ""))


def url_open(url: str) -> str:
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    webbrowser.open(url)
    return f"Geöffnet: {url}"


def clipboard_get() -> str:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        text = root.clipboard_get()
    except tk.TclError:
        text = ""
    finally:
        root.destroy()
    return text[:20000] if text else "(Zwischenablage ist leer oder enthält keinen Text)"


def clipboard_set(text: str) -> str:
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    root.clipboard_clear()
    root.clipboard_append(text)
    root.update()
    root.destroy()
    return f"In die Zwischenablage kopiert ({len(text)} Zeichen)."


def screen_capture(max_width: int = 1600) -> list[dict[str, Any]]:
    import io

    from PIL import ImageGrab

    img = ImageGrab.grab(all_screens=True) if sys.platform == "win32" else ImageGrab.grab()
    if img.width > max_width:
        img = img.resize((max_width, int(img.height * max_width / img.width)))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=80)
    return [
        {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}},
        {"type": "text", "text": f"Bildschirmfoto vom {datetime.now():%d.%m.%Y %H:%M:%S} ({img.width}x{img.height})."},
    ]


def build_tools() -> list[Tool]:
    return [
        Tool("app_open", "Startet ein Programm auf dem Rechner (z. B. Outlook, Excel, Teams, Revit, Explorer) über Namen.",
             schema({"name": {"type": "string"}}, ["name"]), app_open),
        Tool("url_open", "Öffnet eine Webseite im Standardbrowser.", schema({"url": {"type": "string"}}, ["url"]), url_open),
        Tool("clipboard_get", "Liest den Text aus der Zwischenablage des Nutzers.", schema({}), clipboard_get),
        Tool("clipboard_set", "Legt Text in die Zwischenablage, damit der Nutzer ihn einfügen kann.", schema({"text": {"type": "string"}}, ["text"]), clipboard_set),
        Tool("screen_capture", "Macht ein Bildschirmfoto und liefert es dir zur Analyse (auf Aufforderung: „schau auf meinen Bildschirm“).",
             schema({}), lambda: screen_capture()),
    ]
