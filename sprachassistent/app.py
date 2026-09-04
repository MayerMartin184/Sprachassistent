"""Desktop-Fenster im Mayer-E-Concept-Stil: Raster, Leiterbahnen, animierte Audio-Wellenlinien, Verlauf, Eingabe.

Farben und Schriften kommen aus den Einstellungen (BRAND_*), damit sich das Design ohne Codeänderung anpassen lässt.
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
HERO_H = 300  # Höhe des oberen Bereichs (Kopf + Wellen + Status)
GRID = 44


def _mix(c1: str, c2: str, t: float) -> str:
    """Mischt zwei Hex-Farben (t=0 -> c1, t=1 -> c2)."""
    a = [int(c1[i : i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def _spaced(text: str) -> str:
    """Tk kennt keine Laufweite; gesperrte Schrift wird über schmale Leerzeichen nachgebildet."""
    return " ".join(text)


class App:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.name = settings.assistant_name
        self.root = tk.Tk()
        self.root.title(f"{self.name} – {settings.brand_title}")
        self.root.configure(bg=settings.brand_bg)
        self.root.geometry("960x720")
        self.root.minsize(720, 560)
        icon = Path(__file__).with_name("jarvis.ico")
        if icon.exists():
            try:
                self.root.iconbitmap(str(icon))
            except tk.TclError:
                pass

        families = set(tkfont.families())
        self.font = settings.brand_font if settings.brand_font in families else "Segoe UI"
        self.mono = settings.brand_mono if settings.brand_mono in families else "Courier New"
        self._ui_queue: queue.Queue = queue.Queue()
        self._busy = False
        self._state = "idle"
        self._t = 0.0
        self._amp = 0.05
        self._logo_img = None
        self._dots: list[int] = []
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
                self._log("System", "Sprache nicht eingerichtet – Eingabe per Text.\n" + settings.speech_diagnosis())
                self.mic_var.set(False)
                self.mic_check.config(state="disabled")
            self._set_state("idle")
        self.root.after(100, self._drain_queue)
        self.root.after(30, self._animate)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    # --- Aufbau -----------------------------------------------------------
    def _build_widgets(self) -> None:
        s, f, m = self.s, self.font, self.mono

        # Oberer Bereich: eine Zeichenfläche mit Raster, Leiterbahnen, Logo, Wellen, Status
        self.hero = tk.Canvas(self.root, height=HERO_H, bg=s.brand_bg, highlightthickness=0)
        self.hero.pack(fill="x")
        self.hero.bind("<Configure>", lambda _e: self._draw_static())

        self.mic_var = tk.BooleanVar(value=True)
        self.mic_check = tk.Checkbutton(
            self.hero, text=_spaced("MIKROFON"), variable=self.mic_var, command=self._toggle_mic, font=(m, 8),
            bg=s.brand_bg, fg=s.brand_muted, activebackground=s.brand_bg, activeforeground=s.brand_text,
            selectcolor=s.brand_panel, bd=0, highlightthickness=0,
        )
        self.settings_btn = tk.Button(
            self.hero, text=_spaced("EINSTELLUNGEN"), command=self._open_settings, font=(m, 8), bg=s.brand_bg,
            fg=s.brand_muted, activebackground=s.brand_bg, activeforeground=s.brand_text, relief="flat", bd=0,
            cursor="hand2", highlightthickness=0,
        )
        self.status_var = tk.StringVar(value=_spaced("STARTE"))

        # Trennlinie
        tk.Frame(self.root, bg=s.brand_line, height=1).pack(fill="x", padx=36)

        # Eingabe unten (zuerst packen, damit sie immer sichtbar bleibt)
        row = tk.Frame(self.root, bg=s.brand_bg)
        row.pack(side="bottom", fill="x", padx=36, pady=(0, 22))
        box = tk.Frame(row, bg=s.brand_line, padx=1, pady=1)
        box.pack(side="left", fill="x", expand=True)
        self.entry = tk.Entry(
            box, font=(f, 12), bg=s.brand_panel, fg=s.brand_text, insertbackground=s.brand_primary, relief="flat",
            highlightthickness=0, bd=0,
        )
        self.entry.pack(fill="x", ipady=10, padx=12)
        self.entry.bind("<Return>", lambda _e: self._send_text())
        self.entry.bind("<FocusIn>", lambda _e: box.configure(bg=s.brand_primary))
        self.entry.bind("<FocusOut>", lambda _e: box.configure(bg=s.brand_line))
        tk.Button(
            row, text=_spaced("SENDEN") + "  →", command=self._send_text, font=(m, 10, "bold"), bg=s.brand_primary,
            fg=s.brand_bg, activebackground=s.brand_accent, activeforeground=s.brand_bg, relief="flat", padx=22, bd=0,
            cursor="hand2",
        ).pack(side="left", padx=(12, 0), ipady=9)

        # Verlauf
        frame = tk.Frame(self.root, bg=s.brand_bg)
        frame.pack(side="top", fill="both", expand=True, padx=36, pady=(16, 16))
        self.transcript = tk.Text(
            frame, wrap="word", state="disabled", font=(f, 11), bg=s.brand_bg, fg=s.brand_text, height=6,
            relief="flat", padx=2, pady=2, spacing1=2, spacing3=12, highlightthickness=0, bd=0, cursor="arrow",
        )
        scroll = tk.Scrollbar(frame, command=self.transcript.yview, bg=s.brand_panel, troughcolor=s.brand_bg, bd=0, width=8)
        self.transcript.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.transcript.pack(side="left", fill="both", expand=True)
        self.transcript.tag_config("Du", foreground=s.brand_primary, font=(m, 8, "bold"), spacing1=10)
        self.transcript.tag_config(self.name, foreground=s.brand_primary, font=(m, 8, "bold"), spacing1=10)
        self.transcript.tag_config("System", foreground=s.brand_muted, font=(m, 8, "bold"), spacing1=10)
        self.transcript.tag_config("body", foreground=s.brand_text, font=(f, 11), lmargin1=2, lmargin2=2)
        self.transcript.tag_config("body_system", foreground=s.brand_muted, font=(f, 10), lmargin1=2, lmargin2=2)
        self.entry.focus_set()

    def _draw_static(self) -> None:
        """Zeichnet Raster, Leiterbahnen, Logo, Titel; wird bei Größenänderung neu aufgebaut."""
        c, s = self.hero, self.s
        w = max(c.winfo_width(), 400)
        c.delete("all")
        self._dots = []

        for x in range(0, w, GRID):
            c.create_line(x, 0, x, HERO_H, fill=s.brand_grid)
        for y in range(0, HERO_H, GRID):
            c.create_line(0, y, w, y, fill=s.brand_grid)

        # Leiterbahnen links und rechts, wie auf der Website
        def trace(points: list[tuple[float, float]]) -> None:
            flat = [v for pt in points for v in pt]
            c.create_line(*flat, fill=s.brand_line, width=1.5)
            x, y = points[-1]
            c.create_rectangle(x - 3, y - 3, x + 3, y + 3, outline=s.brand_line, fill=s.brand_bg)
            x0, y0 = points[0]
            self._dots.append(c.create_oval(x0 - 3, y0 - 3, x0 + 3, y0 + 3, fill=s.brand_primary, outline=""))

        trace([(40, 120), (40, 180), (120, 180), (120, 250)])
        trace([(0, 70), (90, 70), (90, 110)])
        trace([(w - 40, 130), (w - 40, 200), (w - 130, 200), (w - 130, 260)])
        trace([(w, 80), (w - 100, 80), (w - 100, 110)])

        # Logo: PNG oder gezeichnete Raute mit Blitz
        if s.logo_path and Path(s.logo_path).exists():
            try:
                img = tk.PhotoImage(file=str(s.logo_path))
                factor = max(1, math.ceil(img.height() / 48))
                self._logo_img = img.subsample(factor, factor)
                c.create_image(36, 46, image=self._logo_img, anchor="w")
            except tk.TclError:
                log.warning("Logo konnte nicht geladen werden: %s", s.logo_path)
        else:
            cx, cy, r = 58, 50, 22
            c.create_polygon(cx, cy - r, cx + r, cy, cx, cy + r, cx - r, cy, outline=s.brand_primary, fill=s.brand_panel, width=2)
            c.create_line(cx + 6, cy - 11, cx - 5, cy + 1, cx + 3, cy + 1, cx - 6, cy + 12, fill=s.brand_primary, width=3, joinstyle="miter")

        c.create_text(96, 38, text=_spaced(self.name.upper()), anchor="w", fill=s.brand_text, font=(self.font, 20, "bold"))
        c.create_text(96, 64, text=_spaced(s.brand_title.upper()), anchor="w", fill=s.brand_primary, font=(self.mono, 8))
        c.create_window(w - 36, 46, window=self.mic_check, anchor="e")
        c.create_window(w - 150, 46, window=self.settings_btn, anchor="e")

        # Wellen: Mittellinie und drei Linien
        self._wave_x0, self._wave_x1, self._wave_mid = 120, w - 120, 178
        c.create_line(self._wave_x0, self._wave_mid, self._wave_x1, self._wave_mid, fill=s.brand_line, dash=(2, 6))
        self._lines = [
            c.create_line(0, 0, 0, 0, fill=spec["color"], width=spec["width"], smooth=True) for spec in self._line_specs()
        ]
        # Status mit Strich davor, wie „—— ELECTRICAL ENGINEERING“
        c.create_line(w / 2 - 150, 262, w / 2 - 118, 262, fill=s.brand_primary)
        c.create_text(w / 2 - 108, 262, textvariable=self.status_var, anchor="w", fill=s.brand_primary, font=(self.mono, 9, "bold"))

    def _line_specs(self) -> list[dict]:
        s = self.s
        return [
            {"color": _mix(s.brand_bg, s.brand_accent, 0.5), "width": 1.5, "freq": 1.6, "speed": 1.1, "phase": 2.1, "gain": 0.7},
            {"color": s.brand_accent, "width": 2, "freq": 2.3, "speed": 1.7, "phase": 0.7, "gain": 0.85},
            {"color": s.brand_primary, "width": 2.5, "freq": 3.1, "speed": 2.3, "phase": 0.0, "gain": 1.0},
        ]

    # --- Animation --------------------------------------------------------
    def _target_amp(self) -> float:
        if self._state == "wake" and self.listener is not None:
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
        if not hasattr(self, "_lines"):
            self.root.after(30, self._animate)
            return
        target = max(0.02, min(1.0, self._target_amp()))
        self._amp += (target - self._amp) * (0.35 if target > self._amp else 0.12)
        x0, x1, mid = self._wave_x0, self._wave_x1, self._wave_mid
        width, height, n = x1 - x0, 60, 90
        for item, spec in zip(self._lines, self._line_specs()):
            pts = []
            for i in range(n + 1):
                x = i / n
                env = math.sin(math.pi * x) ** 1.5
                y = math.sin(x * spec["freq"] * 2 * math.pi + self._t * spec["speed"] * 2 + spec["phase"])
                y *= 0.55 + 0.45 * math.sin(x * 7 + self._t * 0.9 + spec["phase"])
                pts += [x0 + x * width, mid + y * env * self._amp * spec["gain"] * height]
            self.hero.coords(item, *pts)
        color = {"idle": self.s.brand_muted, "wake": self.s.brand_text}.get(self._state, self.s.brand_primary)
        self.hero.itemconfig(self._lines[-1], fill=color)
        # Leuchtpunkte der Leiterbahnen pulsieren leicht
        glow = _mix(self.s.brand_accent, self.s.brand_primary, (math.sin(self._t * 2) + 1) / 2)
        for dot in self._dots:
            self.hero.itemconfig(dot, fill=glow)
        self.root.after(30, self._animate)

    def _set_state(self, state: str) -> None:
        self._state = state
        self.status_var.set(_spaced(STATE_TEXT[state].format(name=self.name.upper())))

    # --- Wake-Word --------------------------------------------------------
    def _start_listener(self) -> None:
        from .audio.wakeword import WakeWordListener

        self.listener = WakeWordListener(
            on_utterance=self._on_utterance, on_state=self._on_listener_state,
            model_name=self.s.wake_word_model, threshold=self.s.wake_word_threshold,
        )
        self.status_var.set(_spaced("LADE WAKE-WORD-MODELL"))
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
        error = self.assistant.speak(answer)
        if error:
            self._post(self._log, "System", error)

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
        text = _spaced(text.upper().rstrip(" …"))
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self._post(self.status_var.set, text)

    def _log(self, who: str, text: str) -> None:
        self.transcript.config(state="normal")
        self.transcript.insert("end", f"{_spaced(who.upper())}\n", who)
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

    def _open_settings(self) -> None:
        """Öffnet die .env im Standard-Editor; legt sie aus der Vorlage an, falls sie fehlt."""
        import os
        import shutil

        env = self.s.env_file_in_use()
        if env is None:
            env = Path(".env").resolve()
            example = Path(".env.example")
            if example.exists():
                shutil.copy(example, env)
            else:
                env.write_text("ANTHROPIC_API_KEY=\n", encoding="utf-8")
        try:
            os.startfile(str(env))  # type: ignore[attr-defined]  # Windows
        except AttributeError:
            import subprocess

            subprocess.Popen(["open" if os.uname().sysname == "Darwin" else "xdg-open", str(env)])
        self._log("System", f"Einstellungen geöffnet: {env}. Nach dem Speichern Jarvis neu starten.")

    def _close(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()
