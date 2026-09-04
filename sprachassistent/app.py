"""Desktop-Fenster: pulsierender Zustandskreis, Verlauf, Texteingabe, Mikrofon-Schalter, Bestätigungsdialoge."""

from __future__ import annotations

import logging
import math
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox

from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)

BG = "#12141a"
PANEL = "#1b1e27"
FG = "#e6e8ee"
MUTED = "#8b91a1"
COLORS = {
    "idle": "#4a4f5c",
    "listening": "#3aa655",
    "wake": "#e0442f",
    "processing": "#e5a50a",
    "speaking": "#3d8bfd",
}
STATE_TEXT = {
    "idle": "Mikrofon aus – Text eingeben",
    "listening": "Sag „Hey {name}“",
    "wake": "Ich höre …",
    "processing": "Ich arbeite …",
    "speaking": "Ich spreche …",
}
FONT = "Segoe UI"


class App:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.name = settings.assistant_name
        self.root = tk.Tk()
        self.root.title(self.name)
        self.root.configure(bg=BG)
        self.root.geometry("820x640")
        self.root.minsize(600, 460)
        icon = Path(__file__).with_name("jarvis.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False
        self._state = "idle"
        self._phase = 0.0
        self.listener = None

        self._build_widgets()
        self.assistant = Assistant(settings, confirm=self._confirm, notify=self._notify, on_status=self._status)
        self._log("System", f"Funktionen: {self.assistant.capabilities}")

        if settings.speech_enabled and settings.wake_word_enabled:
            self._start_listener()
        elif settings.speech_enabled:
            self._log("System", "Wake-Word deaktiviert (WAKE_WORD_ENABLED=false) – Eingabe per Text.")
        else:
            self._log("System", "Sprache nicht eingerichtet (AZURE_SPEECH_KEY/REGION fehlen) – Eingabe per Text.")
            self.mic_check.config(state="disabled")
        self.root.after(100, self._drain_queue)
        self.root.after(40, self._animate)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # --- Aufbau -----------------------------------------------------------
    def _build_widgets(self) -> None:
        head = tk.Frame(self.root, bg=BG)
        head.pack(fill="x", padx=18, pady=(14, 0))
        tk.Label(head, text=self.name, font=(FONT, 20, "bold"), bg=BG, fg=FG).pack(side="left")
        self.mic_var = tk.BooleanVar(value=True)
        self.mic_check = tk.Checkbutton(
            head, text="Mikrofon", variable=self.mic_var, command=self._toggle_mic,
            bg=BG, fg=FG, activebackground=BG, activeforeground=FG, selectcolor=PANEL, font=(FONT, 10),
        )
        self.mic_check.pack(side="right")

        self.canvas = tk.Canvas(self.root, width=160, height=160, bg=BG, highlightthickness=0)
        self.canvas.pack(pady=(6, 0))
        self._halo = self.canvas.create_oval(30, 30, 130, 130, fill="", outline=COLORS["idle"], width=2)
        self._orb = self.canvas.create_oval(50, 50, 110, 110, fill=COLORS["idle"], outline="")

        self.status_var = tk.StringVar(value="Starte …")
        tk.Label(self.root, textvariable=self.status_var, font=(FONT, 12), bg=BG, fg=MUTED).pack(pady=(0, 8))

        frame = tk.Frame(self.root, bg=PANEL, bd=0, highlightthickness=0)
        frame.pack(fill="both", expand=True, padx=18, pady=(0, 10))
        self.transcript = tk.Text(
            frame, wrap="word", state="disabled", font=(FONT, 11), bg=PANEL, fg=FG,
            insertbackground=FG, relief="flat", padx=12, pady=10, spacing3=6,
        )
        scroll = tk.Scrollbar(frame, command=self.transcript.yview)
        self.transcript.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.transcript.pack(side="left", fill="both", expand=True)
        self.transcript.tag_config("Du", foreground="#7fb4ff", font=(FONT, 11, "bold"))
        self.transcript.tag_config(self.name, foreground="#6fd38a", font=(FONT, 11, "bold"))
        self.transcript.tag_config("System", foreground=MUTED, font=(FONT, 10, "italic"))

        row = tk.Frame(self.root, bg=BG)
        row.pack(fill="x", padx=18, pady=(0, 16))
        self.entry = tk.Entry(
            row, font=(FONT, 12), bg=PANEL, fg=FG, insertbackground=FG, relief="flat", highlightthickness=1,
            highlightbackground="#2a2e3a", highlightcolor="#3d8bfd",
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda _e: self._send_text())
        tk.Button(
            row, text="Senden", command=self._send_text, font=(FONT, 11, "bold"), bg="#3d8bfd", fg="white",
            activebackground="#2f6fd0", activeforeground="white", relief="flat", padx=16,
        ).pack(side="left", padx=(8, 0), ipady=6)
        self.entry.focus_set()

    # --- Zustandskreis ----------------------------------------------------
    def _set_state(self, state: str) -> None:
        self._state = state
        text = STATE_TEXT.get(state)
        if text:
            self.status_var.set(text.format(name=self.name))

    def _animate(self) -> None:
        speed = {"idle": 0.0, "listening": 0.05, "wake": 0.18, "processing": 0.12, "speaking": 0.10}[self._state]
        self._phase += speed
        pulse = (math.sin(self._phase) + 1) / 2  # 0..1
        r = 30 + 6 * pulse
        hr = 42 + 14 * pulse
        color = COLORS[self._state]
        self.canvas.coords(self._orb, 80 - r, 80 - r, 80 + r, 80 + r)
        self.canvas.coords(self._halo, 80 - hr, 80 - hr, 80 + hr, 80 + hr)
        self.canvas.itemconfig(self._orb, fill=color)
        self.canvas.itemconfig(self._halo, outline=color)
        self.root.after(40, self._animate)

    # --- Wake-Word --------------------------------------------------------
    def _start_listener(self) -> None:
        from .audio.wakeword import WakeWordListener

        self.listener = WakeWordListener(
            on_utterance=self._on_utterance,
            on_state=self._on_listener_state,
            model_name=self.settings.wake_word_model,
            threshold=self.settings.wake_word_threshold,
        )
        self.status_var.set("Lade Wake-Word-Modell …")
        self.listener.start()

    def _on_listener_state(self, state: str) -> None:
        if state == "wake":
            self._post(self._set_state, "wake")
            try:
                from .audio.io import play_wav
                from .audio.wakeword import beep_wav

                play_wav(beep_wav())
            except Exception:  # noqa: BLE001
                log.debug("Bestätigungston fehlgeschlagen", exc_info=True)
        elif state == "listening":
            self._post(self._set_state, "listening")
        elif state == "processing":
            self._post(self._set_state, "processing")
        elif state.startswith("error:"):
            self._post(self._log, "System", f"Wake-Word-Erkennung nicht verfügbar: {state[6:]}")
            self._post(self._set_state, "idle")

    def _on_utterance(self, wav: bytes) -> None:
        self._run_in_background(self._process_audio, wav)

    def _toggle_mic(self) -> None:
        if self.listener is None:
            return
        if self.mic_var.get():
            if not self._busy:
                self.listener.resume()
        else:
            self.listener.pause()
            self._set_state("idle")

    # --- Verarbeitung -----------------------------------------------------
    def _send_text(self) -> None:
        text = self.entry.get().strip()
        if not text or self._busy:
            return
        self.entry.delete(0, "end")
        self._log("Du", text)
        if self.listener is not None:
            self.listener.pause()
        self._set_state("processing")
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
        self._post(self._set_state, "speaking")
        self.assistant.speak(answer)

    def _done(self) -> None:
        self._busy = False
        if self.listener is not None and self.mic_var.get():
            self.listener.resume()
        else:
            self._set_state("idle")
            self.status_var.set("Bereit – Text eingeben")

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
