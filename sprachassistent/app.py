"""Tkinter-Desktop-Oberfläche: Push-to-Talk, Texteingabe, Verlauf, Bestätigungsdialoge."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from .assistant import Assistant
from .audio.io import Recorder
from .config import Settings

log = logging.getLogger(__name__)


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.root = tk.Tk()
        self.root.title("Sprachassistent")
        self.root.geometry("760x560")
        self.root.minsize(560, 420)

        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False
        self.recorder = Recorder()

        self._build_widgets()
        self.assistant = Assistant(settings, confirm=self._confirm, notify=self._notify, on_status=self._status)
        self._status(f"Bereit – {self.assistant.capabilities}")
        self._log("System", "Halte die Sprechtaste (oder die Leertaste) gedrückt, sprich, und lass wieder los.")
        if not settings.speech_enabled:
            self._log("System", "Azure Speech ist nicht konfiguriert – Eingabe nur per Text.")
        self.root.after(100, self._drain_queue)

    # --- Aufbau -----------------------------------------------------------
    def _build_widgets(self) -> None:
        self.status_var = tk.StringVar(value="Starte …")
        tk.Label(self.root, textvariable=self.status_var, anchor="w", fg="#555").pack(fill="x", padx=10, pady=(8, 0))

        self.transcript = scrolledtext.ScrolledText(self.root, wrap="word", state="disabled", font=("Segoe UI", 11))
        self.transcript.pack(fill="both", expand=True, padx=10, pady=8)
        self.transcript.tag_config("Du", foreground="#0a5fb4", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_config("Assistent", foreground="#1b7f3b", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_config("System", foreground="#888", font=("Segoe UI", 10, "italic"))

        row = tk.Frame(self.root)
        row.pack(fill="x", padx=10, pady=(0, 8))
        self.entry = tk.Entry(row, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self._send_text())
        tk.Button(row, text="Senden", command=self._send_text).pack(side="left", padx=(6, 0))

        self.talk_button = tk.Button(
            self.root, text="🎙  Halten zum Sprechen", font=("Segoe UI", 13, "bold"), height=2, bg="#e8eef7"
        )
        self.talk_button.pack(fill="x", padx=10, pady=(0, 10))
        self.talk_button.bind("<ButtonPress-1>", lambda _e: self._start_recording())
        self.talk_button.bind("<ButtonRelease-1>", lambda _e: self._stop_recording())
        self.root.bind("<KeyPress-space>", self._space_down)
        self.root.bind("<KeyRelease-space>", self._space_up)

    # --- Push-to-Talk -----------------------------------------------------
    def _space_down(self, event: tk.Event) -> None:
        if event.widget is not self.entry and not self.recorder.recording:
            self._start_recording()

    def _space_up(self, event: tk.Event) -> None:
        if event.widget is not self.entry and self.recorder.recording:
            self._stop_recording()

    def _start_recording(self) -> None:
        if self._busy or not self.settings.speech_enabled:
            if not self.settings.speech_enabled:
                self._status("Spracherkennung nicht konfiguriert – bitte Text eingeben.")
            return
        try:
            self.recorder.start()
        except Exception as exc:  # noqa: BLE001
            self._log("System", f"Mikrofon konnte nicht gestartet werden: {exc}")
            return
        self.talk_button.config(bg="#f7c9c9", text="●  Aufnahme … loslassen zum Senden")
        self._status("Ich höre zu …")

    def _stop_recording(self) -> None:
        if not self.recorder.recording:
            return
        wav = self.recorder.stop()
        self.talk_button.config(bg="#e8eef7", text="🎙  Halten zum Sprechen")
        if self.recorder.duration_seconds(wav) < 0.4:
            self._status("Aufnahme zu kurz.")
            return
        self._run_in_background(self._process_audio, wav)

    # --- Verarbeitung -----------------------------------------------------
    def _send_text(self) -> None:
        text = self.entry.get().strip()
        if not text or self._busy:
            return
        self.entry.delete(0, "end")
        self._log("Du", text)
        self._run_in_background(self._process_text, text)

    def _run_in_background(self, target, *args) -> None:  # noqa: ANN001
        self._busy = True
        self.talk_button.config(state="disabled")
        threading.Thread(target=self._guarded, args=(target, *args), daemon=True).start()

    def _guarded(self, target, *args) -> None:  # noqa: ANN001
        try:
            target(*args)
        except Exception as exc:  # noqa: BLE001
            log.exception("Verarbeitung fehlgeschlagen")
            self._post(self._log, "System", f"Fehler: {exc}")
        finally:
            self._post(self._done)

    def _process_audio(self, wav: bytes) -> None:
        self._status("Erkenne Sprache …")
        text = self.assistant.transcribe(wav)
        if not text:
            self._post(self._log, "System", "Nichts verstanden.")
            return
        self._post(self._log, "Du", text)
        self._process_text(text)

    def _process_text(self, text: str) -> None:
        answer = self.assistant.handle_text(text)
        self._post(self._log, "Assistent", answer)
        self._status("Spreche …")
        self.assistant.speak(answer)

    def _done(self) -> None:
        self._busy = False
        self.talk_button.config(state="normal")
        self._status("Bereit")

    # --- Thread-sichere UI-Helfer -----------------------------------------
    def _post(self, fn, *args) -> None:  # noqa: ANN001
        self._ui_queue.put((fn, args))

    def _drain_queue(self) -> None:
        try:
            while True:
                fn, args = self._ui_queue.get_nowait()
                fn(*args)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    def _status(self, text: str) -> None:
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self._post(self.status_var.set, text)

    def _log(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who}: ", who)
        self.transcript.insert("end", text.strip() + "\n\n")
        self.transcript.config(state="disabled")
        self.transcript.see("end")

    def _confirm(self, message: str) -> bool:
        """Wird aus dem Arbeits-Thread aufgerufen; blockiert bis der Nutzer im Dialog entschieden hat."""
        result: dict[str, bool] = {}
        done = threading.Event()

        def ask() -> None:
            result["ok"] = messagebox.askyesno("Bestätigung", message, parent=self.root)
            done.set()

        self._post(ask)
        done.wait()
        return result.get("ok", False)

    def _notify(self, message: str) -> None:
        self._post(self._log, "System", message)
        self._post(messagebox.showinfo, "Microsoft-Anmeldung", message)

    def run(self) -> None:
        self.root.mainloop()
