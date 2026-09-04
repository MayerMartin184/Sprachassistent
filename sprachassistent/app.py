"""Tkinter-Desktop-Oberfläche: Wake-Word „Hey Jarvis“, Verlauf, Texteingabe, Bestätigungsdialoge."""

from __future__ import annotations

import logging
import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext

from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)

STATE_TEXT = {
    "listening": "Wartet auf „Hey {name}“ …",
    "wake": "Ja? Ich höre …",
    "processing": "Verarbeite …",
}


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.name = settings.assistant_name
        self.root = tk.Tk()
        self.root.title(self.name)
        self.root.geometry("760x560")
        self.root.minsize(560, 420)

        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False
        self.listener = None

        self._build_widgets()
        self.assistant = Assistant(settings, confirm=self._confirm, notify=self._notify, on_status=self._status)
        self._log("System", f"Funktionen: {self.assistant.capabilities}")

        if settings.speech_enabled and settings.wake_word_enabled:
            self._start_listener()
        elif settings.speech_enabled:
            self._log("System", "Wake-Word deaktiviert (WAKE_WORD_ENABLED=false) – Eingabe per Text.")
        else:
            self._log("System", "Azure Speech ist nicht konfiguriert – Eingabe nur per Text.")
        self.root.after(100, self._drain_queue)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # --- Aufbau -----------------------------------------------------------
    def _build_widgets(self) -> None:
        top = tk.Frame(self.root)
        top.pack(fill="x", padx=10, pady=(8, 0))
        self.status_var = tk.StringVar(value="Starte …")
        tk.Label(top, textvariable=self.status_var, anchor="w", fg="#555").pack(side="left", fill="x", expand=True)
        self.mic_var = tk.BooleanVar(value=True)
        self.mic_check = tk.Checkbutton(top, text="Mikrofon", variable=self.mic_var, command=self._toggle_mic)
        self.mic_check.pack(side="right")

        self.indicator = tk.Label(self.root, text="●", font=("Segoe UI", 28), fg="#bbb")
        self.indicator.pack(pady=(2, 0))

        self.transcript = scrolledtext.ScrolledText(self.root, wrap="word", state="disabled", font=("Segoe UI", 11))
        self.transcript.pack(fill="both", expand=True, padx=10, pady=8)
        self.transcript.tag_config("Du", foreground="#0a5fb4", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_config(self.name, foreground="#1b7f3b", font=("Segoe UI", 11, "bold"))
        self.transcript.tag_config("System", foreground="#888", font=("Segoe UI", 10, "italic"))

        row = tk.Frame(self.root)
        row.pack(fill="x", padx=10, pady=(0, 10))
        self.entry = tk.Entry(row, font=("Segoe UI", 11))
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda _e: self._send_text())
        tk.Button(row, text="Senden", command=self._send_text).pack(side="left", padx=(6, 0))
        self.entry.focus_set()

    # --- Wake-Word --------------------------------------------------------
    def _start_listener(self) -> None:
        from .audio.wakeword import WakeWordListener

        self.listener = WakeWordListener(
            on_utterance=self._on_utterance,
            on_state=self._on_listener_state,
            model_name=self.settings.wake_word_model,
            threshold=self.settings.wake_word_threshold,
        )
        self._status("Lade Wake-Word-Modell …")
        self.listener.start()

    def _on_listener_state(self, state: str) -> None:
        if state == "wake":
            self._post(self._set_indicator, "#e0442f")
            self._post(self._log, "System", "Wake-Word erkannt.")
            try:
                from .audio.io import play_wav
                from .audio.wakeword import beep_wav

                play_wav(beep_wav())
            except Exception:  # noqa: BLE001
                log.debug("Bestätigungston fehlgeschlagen", exc_info=True)
        elif state == "listening":
            self._post(self._set_indicator, "#3aa655")
        elif state == "processing":
            self._post(self._set_indicator, "#e5a50a")
        elif state.startswith("error:"):
            self._post(self._log, "System", f"Wake-Word-Erkennung nicht verfügbar: {state[6:]}")
            self._post(self._set_indicator, "#bbb")
        text = STATE_TEXT.get(state)
        if text:
            self._status(text.format(name=self.name))

    def _on_utterance(self, wav: bytes) -> None:
        """Läuft im Listener-Thread; Verarbeitung in eigenem Thread, Listener bleibt pausiert bis fertig."""
        self._run_in_background(self._process_audio, wav)

    def _toggle_mic(self) -> None:
        if self.listener is None:
            return
        if self.mic_var.get():
            if not self._busy:
                self.listener.resume()
        else:
            self.listener.pause()
            self._set_indicator("#bbb")
            self._status("Mikrofon aus")

    def _set_indicator(self, color: str) -> None:
        self.indicator.config(fg=color)

    # --- Verarbeitung -----------------------------------------------------
    def _send_text(self) -> None:
        text = self.entry.get().strip()
        if not text or self._busy:
            return
        self.entry.delete(0, "end")
        self._log("Du", text)
        if self.listener is not None:
            self.listener.pause()
        self._run_in_background(self._process_text, text)

    def _run_in_background(self, target, *args) -> None:  # noqa: ANN001
        self._busy = True
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
        self._post(self._log, self.name, answer)
        self._status("Spreche …")
        self.assistant.speak(answer)

    def _done(self) -> None:
        self._busy = False
        if self.listener is not None and self.mic_var.get():
            self.listener.resume()
        else:
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

    def _close(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
