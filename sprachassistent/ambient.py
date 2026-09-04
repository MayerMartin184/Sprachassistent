"""Mithör-Modus: Gespräche im Raum still mitschreiben, Zusagen/Aufgaben/Termine extrahieren, Sitzungen reviewen.

Ablauf: Der Listener liefert Sprachabschnitte (WAV) -> Transkription (Azure) -> Tagesprotokoll (Textdatei) ->
alle paar Minuten prüft ein eigener, stiller Agent den neuen Abschnitt und legt über die normalen Werkzeuge
To-Dos, Erinnerungen und Gedächtniseinträge an. Nach einer längeren Gesprächsphase folgt ein Review als Datei.
Es wird nur Text gespeichert, kein Audio.
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Callable

from .agent.agent import Agent
from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)

EXTRACT_PROMPT = """Du bist der stille Mithör-Assistent von {name}. Du bekommst Ausschnitte aus Gesprächen, Telefonaten und Sitzungen des Nutzers als Text (Sprecher nicht getrennt, Spracherkennung fehlerbehaftet). Du sprichst nie mit dem Nutzer und stellst keine Rückfragen.

Erfasse ausschließlich konkrete, für den Nutzer relevante Punkte:
1. Aufgaben, die der Nutzer zusagt oder die ihm zugewiesen werden -> todo_add (Fälligkeit setzen, wenn genannt oder klar ableitbar; sonst ohne).
2. Termine, Rückrufe, Fristen -> reminder_set, sinnvoll vorab (Rückruf: zur genannten Zeit; Abgabe: Vortag 10:00; Termin: 15 Minuten davor).
3. Absprachen, Zuständigkeiten, Fakten zu Personen und Projekten -> memory_save (Kategorie absprache/person/projekt).

Regeln: Vor dem Anlegen mit todo_list und reminder_list prüfen, ob es den Punkt schon gibt; nichts doppelt anlegen. Bei Unsicherheit lieber nichts anlegen. Relative Zeitangaben anhand des aktuellen Datums umrechnen. Antworte zum Schluss in höchstens zwei kurzen Sätzen, was du angelegt hast, oder exakt: Nichts Neues.
"""

REVIEW_PROMPT = """Du bist der stille Mithör-Assistent von {name}. Erstelle aus dem folgenden Gesprächsprotokoll ein Review als Markdown-Datei mit files_write unter Jarvis/Reviews/<Datum>_<Uhrzeit>_Review.md (Ordner anlegen, wenn nötig):
Thema (eine Zeile), Teilnehmer/Beteiligte soweit erkennbar, Ergebnisse und Entscheidungen, offene Punkte und Aufgaben des Nutzers (mit Fälligkeit), nächste Schritte. Sachlich, knapp, keine Erfindungen; unsichere Stellen als solche markieren.
Antworte zum Schluss in einem Satz mit Thema und Anzahl der offenen Punkte für den Nutzer.
"""


class AmbientRecorder:
    def __init__(
        self,
        settings: Settings,
        assistant: Assistant,
        notify: Callable[[str, str], None],
        announce: Callable[[str], None] | None = None,
    ) -> None:
        self.s = settings
        self.assistant = assistant
        self.notify = notify
        self.announce = announce
        self.enabled = False
        self._queue: queue.Queue[list[bytes]] = queue.Queue()
        self._buffer: list[str] = []  # noch nicht ausgewertete Zeilen
        self._session_lines = 0
        self._session_start: float | None = None
        self._last_speech = 0.0
        self._last_extract = time.time()
        self._lock = threading.Lock()
        self.dir = settings.data_dir / "transcripts"
        self.dir.mkdir(parents=True, exist_ok=True)
        threading.Thread(target=self._worker, name="ambient-transcribe", daemon=True).start()
        threading.Thread(target=self._ticker, name="ambient-extract", daemon=True).start()

    # --- Eingang -------------------------------------------------------------
    def submit(self, wavs: list[bytes]) -> None:
        if self.enabled:
            self._queue.put(wavs)

    def today_file(self) -> Path:
        return self.dir / f"{datetime.now():%Y-%m-%d}.txt"

    def _worker(self) -> None:
        while True:
            wavs = self._queue.get()
            try:
                text = self.assistant.transcribe(wavs)
            except Exception as exc:  # noqa: BLE001
                log.warning("Mithören: Transkription fehlgeschlagen: %s", exc)
                continue
            if not text or len(text.split()) < 2:
                continue
            line = f"[{datetime.now():%H:%M}] {text}"
            with self._lock:
                self._buffer.append(line)
                self._session_lines += 1
                now = time.time()
                if self._session_start is None:
                    self._session_start = now
                self._last_speech = now
            with self.today_file().open("a", encoding="utf-8") as fh:
                fh.write(line + "\n")

    # --- Auswertung -------------------------------------------------------------
    def _agent(self, prompt: str) -> Agent:
        return Agent(
            self.s, self.assistant.registry, lambda _m: None,
            memory_summary=self.assistant.memory.summary, system_text=prompt.format(name=self.s.assistant_name),
        )

    def _ticker(self) -> None:
        while True:
            time.sleep(15)
            if not self.enabled and not self._buffer:
                continue
            try:
                self._maybe_extract()
                self._maybe_review()
            except Exception as exc:  # noqa: BLE001
                log.exception("Mithören: Auswertung fehlgeschlagen")
                self.notify("System", f"Mithören: Auswertung fehlgeschlagen: {exc}")

    def _maybe_extract(self) -> None:
        with self._lock:
            words = sum(len(line.split()) for line in self._buffer)
            due = self._buffer and (time.time() - self._last_extract >= self.s.ambient_extract_minutes * 60 or words >= 700)
            if not due:
                return
            chunk, self._buffer = "\n".join(self._buffer), []
            self._last_extract = time.time()
        result = self._agent(EXTRACT_PROMPT).run(f"Neuer Gesprächsausschnitt:\n{chunk}")
        if result and "nichts neues" not in result.lower():
            self.notify("Mithören", result)

    def _maybe_review(self) -> None:
        with self._lock:
            if self._session_start is None:
                return
            idle = time.time() - self._last_speech
            duration = self._last_speech - self._session_start
            if idle < self.s.ambient_review_idle_minutes * 60:
                return
            long_enough = duration >= self.s.ambient_review_min_minutes * 60 and self._session_lines >= 12
            self._session_start, self._session_lines = None, 0
        if not long_enough:
            return
        start = datetime.fromtimestamp(time.time() - idle - duration)
        transcript = self._transcript_since(start)
        if not transcript:
            return
        result = self._agent(REVIEW_PROMPT).run(f"Gesprächsprotokoll ({start:%d.%m.%Y %H:%M} bis {datetime.fromtimestamp(self._last_speech):%H:%M}):\n{transcript}")
        self.notify("Mithören", result)
        if self.announce is not None:
            self.announce(f"Ein Review der Sitzung wurde abgelegt: {result}")

    def _transcript_since(self, start: datetime) -> str:
        path = self.today_file()
        if not path.exists():
            return ""
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line[1:6] >= f"{start:%H:%M}"]
        return "\n".join(lines)[-60000:]

    def transcript_today(self, max_chars: int = 20000) -> str:
        path = self.today_file()
        if not path.exists():
            return "Heute wurde noch nichts mitgeschrieben."
        text = path.read_text(encoding="utf-8")
        return text[-max_chars:] if len(text) > max_chars else text
