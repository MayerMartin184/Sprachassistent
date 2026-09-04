"""Präsenz über die Webcam: erkennt, wenn der Nutzer kommt oder wiederholt jemand dazukommt.

Die Gesichtserkennung läuft komplett lokal (OpenCV Haar-Kaskade). Nur bei einem Ereignis wird ein Bild
an Claude gegeben, und das höchstens einmal pro Abkühlzeit. Keine Identifikation von Personen.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

log = logging.getLogger(__name__)

EventCallback = Callable[[str, str, bytes | None], None]  # (ereignis, beschreibung, jpeg)


class PresenceLogic:
    """Zustandsautomat ohne Kamera – testbar. update() erhält die Gesichtszahl je Messung."""

    def __init__(self, sample_s: float = 2.5, absence_min: float = 10, cooldown_min: float = 10) -> None:
        self.sample_s = sample_s
        self.absence_s = absence_min * 60
        self.cooldown_s = cooldown_min * 60
        self.present = False
        self.last_seen: float | None = None
        self.last_absent_since: float | None = None  # None = seit Start noch nie abwesend gewesen
        self.last_comment = -1e9
        self._present_run = 0
        self._absent_run = 0
        self._multi_run = 0
        self._visits: deque[float] = deque()
        self._visitor_active = False

    def update(self, faces: int, now: float) -> tuple[str, str] | None:
        """Rückgabe: (ereignis, beschreibung) oder None."""
        event = None
        if faces >= 1:
            self._present_run += 1
            self._absent_run = 0
            if self._present_run >= 3 and not self.present:
                self.present = True
                away = (now - self.last_absent_since) if self.last_absent_since is not None else None
                if away is not None and away >= self.absence_s:
                    event = ("arrival", f"Der Nutzer ist nach etwa {int(away // 60)} Minuten Abwesenheit zurück am Platz.")
            self.last_seen = now
        else:
            self._absent_run += 1
            self._present_run = 0
            if self._absent_run >= 8 and self.present:  # ~20 s ohne Gesicht
                self.present = False
                self.last_absent_since = now
        if faces >= 2:
            self._multi_run += 1
            if self._multi_run >= 4 and not self._visitor_active:  # ~10 s zu zweit
                self._visitor_active = True
                self._visits.append(now)
                while self._visits and now - self._visits[0] > 3600:
                    self._visits.popleft()
                if len(self._visits) >= 2:
                    event = ("visitor", f"Zum {len(self._visits)}. Mal innerhalb einer Stunde ist jemand zum Nutzer gekommen und unterbricht ihn.")
        else:
            self._multi_run = 0
            if faces <= 1 and self._multi_run == 0:
                self._visitor_active = False
        if event and now - self.last_comment >= self.cooldown_s:
            self.last_comment = now
            return event
        return None


class PresenceWatcher:
    """Hintergrund-Thread mit Kamera. Besitzt die Kamera und liefert auch Schnappschüsse für das Webcam-Werkzeug."""

    def __init__(self, camera_index: int, on_event: EventCallback, absence_min: float = 10, cooldown_min: float = 10) -> None:
        self.camera_index = camera_index
        self.on_event = on_event
        self.logic = PresenceLogic(absence_min=absence_min, cooldown_min=cooldown_min)
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._last_frame = None
        self._thread: threading.Thread | None = None
        self.faces = 0
        self.error: str | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="presence", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def snapshot_jpeg(self, max_width: int = 1024) -> bytes | None:
        import cv2

        with self._lock:
            frame = None if self._last_frame is None else self._last_frame.copy()
        if frame is None:
            return None
        h, w = frame.shape[:2]
        if w > max_width:
            frame = cv2.resize(frame, (max_width, int(h * max_width / w)), interpolation=cv2.INTER_AREA)
        ok, jpg = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
        return jpg.tobytes() if ok else None

    def _run(self) -> None:
        import sys

        import cv2

        backend = cv2.CAP_DSHOW if sys.platform == "win32" else cv2.CAP_ANY
        cap = cv2.VideoCapture(self.camera_index, backend)
        if not cap.isOpened():
            self.error = f"Kamera {self.camera_index} nicht verfügbar"
            log.warning(self.error)
            return
        cascade = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
        try:
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok:
                    time.sleep(1)
                    continue
                with self._lock:
                    self._last_frame = frame
                small = cv2.resize(frame, (480, int(frame.shape[0] * 480 / frame.shape[1])))
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                faces = cascade.detectMultiScale(gray, scaleFactor=1.2, minNeighbors=5, minSize=(50, 50))
                self.faces = len(faces)
                event = self.logic.update(self.faces, time.time())
                if event:
                    kind, description = event
                    try:
                        self.on_event(kind, description, self.snapshot_jpeg())
                    except Exception:  # noqa: BLE001
                        log.exception("Präsenz-Ereignis fehlgeschlagen")
                self._stop.wait(self.logic.sample_s)
        finally:
            cap.release()
