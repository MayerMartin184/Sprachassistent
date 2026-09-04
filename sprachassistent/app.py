"""Desktop-Fenster im futuristischen Stil: animierte Audio-Wellenlinien, Verlauf, Eingabe, Dialoge.

Farben, Schrift und Logo kommen aus den Einstellungen (BRAND_*), damit die Firmen-CI ohne Codeänderung passt.
"""

from __future__ import annotations

import logging
import math
import queue
import random
import threading
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from tkinter import messagebox

from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)

STATE_TEXT = {
    "idle": "BEREIT",
    "listening": "SAG „HEY {name}“",
    "wake": "ICH HÖRE",
    "processing": "ICH ARBEITE",
    "speaking": "ICH SPRECHE",
}
WAVE_W, WAVE_H = 700, 150


def _mix(c1: str, c2: str, t: float) -> str:
    """Mischt zwei Hex-Farben (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


class App:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.name = settings.assistant_name
        self.root = tk.Tk()
        self.root.title(f"{self.name} – {settings.brand_title}")
        self.root.configure(bg=settings.brand_bg)
        self.root.geometry("900x680")
        self.root.minsize(680, 520)
        icon = Path(__file__).with_name("jarvis.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass

        self.font = settings.brand_font if settings.brand_font in tkfont.families() else "Segoe UI"
        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False
        self._state = "idle"
        self._t = 0.0
        self._amp = 0.05  # geglättete Amplitude 0..1
        self._logo_img = None
        self.listener = None

        self._build_widgets()
        self.assistant = Assistant(settings, confirm=self._confirm, notify=self._notify, on_status=self._status)
        self._log("System", f"Funktionen: {self.assistant.capabilities}")

        if settings.speech_enabled and settings.wake_word_enabled:
            self._start_listener()
        else:
            if settings.speech_enabled:
                self._log("System", "Wake-Word deaktiviert (WAKE_WORD_ENABLED=false) – Eingabe per Text.")
            else:
                self._log("System", "Sprache nicht eingerichtet (AZURE_SPEECH_KEY/REGION fehlen) – Eingabe per Text.")
                self.mic_var.set(False)
                self.mic_check.config(state="disabled")
            self._set_state("idle")
        self.root.after(100, self._drain_queue)
        self.root.after(30, self._animate)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # --- Aufbau -----------------------------------------------------------
    def _build_widgets(self) -> None:
        s, f = self.s, self.font
        head = tk.Frame(self.root, bg=s.brand_bg)
        head.pack(fill="x", padx=28, pady=(18, 0))
        if s.logo_path and Path(s.logo_path).exists():
            try:
                img = tk.PhotoImage(file=str(s.logo_path))
                factor = max(1, math.ceil(img.height() / 44))
                self._logo_img = img.subsample(factor, factor)
                tk.Label(head, image=self._logo_img, bg=s.brand_bg).pack(side="left", padx=(0, 14))
            except tk.TclError:
                log.warning("Logo konnte nicht geladen werden: %s", s.logo_path)
        title = tk.Frame(head, bg=s.brand_bg)
        title.pack(side="left")
        tk.Label(title, text=self.name.upper(), font=(f, 22, "bold"), bg=s.brand_bg, fg=s.brand_text).pack(anchor="w")
        tk.Label(title, text=s.brand_title.upper(), font=(f, 8), bg=s.brand_bg, fg=s.brand_primary).pack(anchor="w")

        self.mic_var = tk.BooleanVar(value=True)
        self.mic_check = tk.Checkbutton(
            head, text="MIKROFON", variable=self.mic_var, command=self._toggle_mic, font=(f, 8),
            bg=s.brand_bg, fg=s.brand_muted, activebackground=s.brand_bg, activeforeground=s.brand_text,
            selectcolor=s.brand_panel, bd=0, highlightthickness=0,
        )
        self.mic_check.pack(side="right")

        # Wellen-Visualisierung
        self.canvas = tk.Canvas(self.root, width=WAVE_W, height=WAVE_H, bg=s.brand_bg, highlightthickness=0)
        self.canvas.pack(pady=(10, 0))
        mid = WAVE_H / 2
        self.canvas.create_line(0, mid, WAVE_W, mid, fill=_mix(s.brand_bg, s.brand_primary, 0.15), width=1)
        self._lines = []
        for spec in self._line_specs():
            self._lines.append(self.canvas.create_line(0, mid, WAVE_W, mid, fill=spec["color"], width=spec["width"], smooth=True))
        self.status_var = tk.StringVar(value="STARTE")
        tk.Label(self.root, textvariable=self.status_var, font=(f, 10, "bold"), bg=s.brand_bg, fg=s.brand_primary).pack(pady=(2, 10))
        tk.Frame(self.root, bg=_mix(s.brand_bg, s.brand_primary, 0.35), height=1).pack(fill="x", padx=28)

        # Eingabe unten (zuerst packen, damit sie immer sichtbar bleibt)
        row = tk.Frame(self.root, bg=s.brand_bg)
        row.pack(side="bottom", fill="x", padx=28, pady=(0, 18))
        self.entry = tk.Entry(
            row, font=(f, 12), bg=s.brand_panel, fg=s.brand_text, insertbackground=s.brand_primary, relief="flat",
            highlightthickness=1, highlightbackground=_mix(s.brand_panel, s.brand_primary, 0.35), highlightcolor=s.brand_primary,
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=9)
        self.entry.bind("<Return>", lambda _e: self._send_text())
        tk.Button(
            row, text="SENDEN", command=self._send_text, font=(f, 10, "bold"), bg=s.brand_primary, fg=s.brand_bg,
            activebackground=s.brand_accent, activeforeground=s.brand_text, relief="flat", padx=18, bd=0,
        ).pack(side="left", padx=(10, 0), ipady=7)

        # Verlauf
        frame = tk.Frame(self.root, bg=s.brand_bg)
        frame.pack(side="top", fill="both", expand=True, padx=28, pady=(12, 12))
        self.transcript = tk.Text(
            frame, wrap="word", state="disabled", font=(f, 11), bg=s.brand_bg, fg=s.brand_text, height=6,
            relief="flat", padx=4, pady=4, spacing1=4, spacing3=10, highlightthickness=0, bd=0, cursor="arrow",
        )
        scroll = tk.Scrollbar(frame, command=self.transcript.yview, bg=s.brand_panel, troughcolor=s.brand_bg, bd=0)
        self.transcript.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.transcript.pack(side="left", fill="both", expand=True)
        self.transcript.tag_config("Du", foreground=s.brand_accent, font=(f, 9, "bold"), spacing1=8)
        self.transcript.tag_config(self.name, foreground=s.brand_primary, font=(f, 9, "bold"), spacing1=8)
        self.transcript.tag_config("System", foreground=s.brand_muted, font=(f, 9, "bold"), spacing1=8)
        self.transcript.tag_config("body", foreground=s.brand_text, font=(f, 11), lmargin1=2, lmargin2=2)
        self.transcript.tag_config("body_system", foreground=s.brand_muted, font=(f, 10), lmargin1=2, lmargin2=2)
        self.entry.focus_set()

    def _line_specs(self) -> list[dict]:
        s = self.s
        return [
            {"color": _mix(s.brand_bg, s.brand_accent, 0.55), "width": 1.5, "freq": 1.6, "speed": 1.1, "phase": 2.1, "gain": 0.7},
            {"color": _mix(s.brand_bg, s.brand_primary, 0.6), "width": 2, "freq": 2.3, "speed": 1.7, "phase": 0.7, "gain": 0.85},
            {"color": s.brand_primary, "width": 2.5, "freq": 3.1, "speed": 2.3, "phase": 0.0, "gain": 1.0},
        ]

    # --- Animation --------------------------------------------------------
    def _target_amp(self) -> float:
        if self._state in ("wake",) and self.listener is not None:
            return 0.15 + 0.85 * self.listener.level
        if self._state == "listening" and self.listener is not None:
            return 0.06 + 0.35 * self.listener.level
        if self._state == "speaking":
            return 0.35 + 0.45 * abs(math.sin(self._t * 3.7) * math.sin(self._t * 1.3)) + random.uniform(-0.05, 0.05)
        if self._state == "processing":
            return 0.18 + 0.08 * math.sin(self._t * 4)
        return 0.06

    def _animate(self) -> None:
        self._t += 0.03
        target = max(0.02, min(1.0, self._target_amp()))
        self._amp += (target - self._amp) * (0.35 if target > self._amp else 0.12)
        mid, n = WAVE_H / 2, 90
        for item, spec in zip(self._lines, self._line_specs()):
            pts = []
            for i in range(n + 1):
                x = i / n
                env = math.sin(math.pi * x) ** 1.5  # Ränder auslaufen lassen
                y = math.sin(x * spec["freq"] * 2 * math.pi + self._t * spec["speed"] * 2 + spec["phase"])
                y *= 0.55 + 0.45 * math.sin(x * 7 + self._t * 0.9 + spec["phase"])
                pts += [x * WAVE_W, mid + y * env * self._amp * spec["gain"] * (WAVE_H / 2 - 6)]
            self.canvas.coords(item, *pts)
        color = {"idle": self.s.brand_muted, "wake": self.s.brand_accent}.get(self._state, self.s.brand_primary)
        self.canvas.itemconfig(self._lines[-1], fill=color)
        self.root.after(30, self._animate)

    def _set_state(self, state: str) -> None:
        self._state = state
        self.status_var.set(STATE_TEXT[state].format(name=self.name.upper()))

    # --- Wake-Word --------------------------------------------------------
    def _start_listener(self) -> None:
        from .audio.wakeword import WakeWordListener

        self.listener = WakeWordListener(
            on_utterance=self._on_utterance, on_state=self._on_listener_state,
            model_name=self.s.wake_word_model, threshold=self.s.wake_word_threshold,
        )
        self.status_var.set("LADE WAKE-WORD-MODELL")
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
        elif state in ("listening", "processing"):
            self._post(self._set_state, state)
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
        self._status("ERKENNE SPRACHE")
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
        text = text.upper().rstrip(" …")
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self._post(self.status_var.set, text)

    def _log(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{who.upper()}\n", who)
        self.transcript.insert("end", text.strip() + "\n", "body_system" if who == "System" else "body")
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
