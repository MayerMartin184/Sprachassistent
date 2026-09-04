"""Webcam-Schnappschuss als Bild für Claude (Dokumente, Whiteboards, Gegenstände zeigen)."""

from __future__ import annotations

import base64
import sys
from datetime import datetime
from typing import Any

from .base import Tool, schema


def available() -> bool:
    try:
        import cv2  # noqa: F401
    except ImportError:
        return False
    return True


def capture(index: int = 0, max_width: int = 1024) -> list[dict[str, Any]]:
    import cv2

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Webcam {index} konnte nicht geöffnet werden. {probe_cameras()}")
    try:
        frame = None
        for _ in range(8):  # Belichtung einpendeln lassen
            ok, frame = cap.read()
            if not ok:
                frame = None
        if frame is None:
            raise RuntimeError("Kein Bild von der Webcam erhalten.")
    finally:
        cap.release()
    h, w = frame.shape[:2]
    if w > max_width:
        frame = cv2.resize(frame, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
    ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError("Bild konnte nicht kodiert werden.")
    return [
        {
            "type": "image",
            "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpg.tobytes()).decode()},
        },
        {"type": "text", "text": f"Webcam-Aufnahme vom {datetime.now():%d.%m.%Y %H:%M:%S}."},
    ]


def probe_cameras(max_index: int = 6) -> str:
    """Prüft, welche Kameranummern ein Bild liefern (für WEBCAM_INDEX in der .env)."""
    import cv2

    backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
    working = []
    for i in range(max_index):
        cap = cv2.VideoCapture(i, backend)
        try:
            if cap.isOpened():
                ok, _ = cap.read()
                if ok:
                    working.append(str(i))
        finally:
            cap.release()
    if not working:
        return "Keine funktionierende Kamera gefunden. Ist sie angeschlossen und in Windows für Desktop-Apps freigegeben?"
    return "Funktionierende Kameranummern: " + ", ".join(working) + ". In der .env WEBCAM_INDEX=<Nummer> setzen."


def build_tools(index: int = 0) -> list[Tool]:
    return [
        Tool(
            name="webcam_capture",
            description=(
                "Nimmt ein Bild mit der Webcam auf und liefert es dir zur Analyse (z. B. Dokument, Whiteboard, "
                "Gegenstand oder Umgebung des Nutzers). Nur auf Aufforderung des Nutzers verwenden."
            ),
            input_schema=schema({}),
            handler=lambda: capture(index),
        )
    ]
