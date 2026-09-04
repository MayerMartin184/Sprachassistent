"""Fenster mit eingebetteter Web-Ansicht (pywebview): HTML/CSS-Oberfläche im Mayer-E-Concept-Stil.

Die Seite fragt Python alle 70 ms nach Zustand, Mikrofonpegel und neuen Nachrichten (poll) und ruft
send/set_mic/open_settings auf. Bestätigungen laufen über den nativen Dialog des Fensters.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import threading
from pathlib import Path
from typing import Any

import webview

from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)
UI_FILE = Path(__file__).with_name("ui") / "index.html"


class Api:
    """Von JavaScript aufrufbare Schnittstelle (window.pywebview.api)."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self.window: webview.Window | None = None
        self._lock = threading.Lock()
        self._messages: list[dict[str, str]] = []
        self._state = "idle"
        self._status: str | None = None
        self._busy = False
        self._mic_on = True
        self.listener = None
        self.assistant: Assistant | None = None

    # --- Start ------------------------------------------------------------
    def start(self) -> None:
        """Wird nach dem Öffnen des Fensters im Hintergrund aufgerufen."""
        try:
            self.assistant = Assistant(self.s, confirm=self._confirm, notify=self._notify, on_status=self._set_status)
        except Exception as exc:  # noqa: BLE001
            log.exception("Assistent konnte nicht starten")
            self._push("System", f"Start fehlgeschlagen: {exc}")
            return
        self._push("System", f"Funktionen: {self.assistant.capabilities}")
        if self.s.speech_enabled and self.s.wake_word_enabled:
            self._start_listener()
        else:
            self._mic_on = False
            if self.s.speech_enabled:
                self._push("System", "Wake-Word deaktiviert (WAKE_WORD_ENABLED=false) – Eingabe per Text.")
            else:
                self._push("System", "Sprache nicht eingerichtet – Eingabe per Text.\n" + self.s.speech_diagnosis())
            self._set_state("idle")

    def _start_listener(self) -> None:
        from .audio.io import resolve_device
        from .audio.wakeword import WakeWordListener

        device = None
        try:
            device = resolve_device(self.s.audio_input_device, "input")
        except Exception as exc:  # noqa: BLE001
            self._push("System", f"Mikrofon-Auswahl: {exc} – Windows-Standard wird verwendet.")
        self.listener = WakeWordListener(
            on_utterance=self._on_utterance, on_state=self._on_listener_state,
            model_name=self.s.wake_word_model, threshold=self.s.wake_word_threshold, device=device,
            end_silence_ms=self.s.speech_end_silence_ms, vad_threshold=self.s.vad_threshold,
            attention_ms=self.s.attention_seconds * 1000,
        )
        self._state, self._status = "loading", None
        self.listener.start()

    # --- Einstellungen (Dialog im Fenster) -------------------------------------
    def get_settings(self) -> dict[str, Any]:
        inputs: list[dict[str, Any]] = []
        outputs: list[dict[str, Any]] = []
        try:
            from .audio.io import list_devices

            inputs = [{"id": i, "name": n, "default": d} for i, n, d in list_devices("input")]
            outputs = [{"id": i, "name": n, "default": d} for i, n, d in list_devices("output")]
        except Exception as exc:  # noqa: BLE001
            log.warning("Geräteliste nicht verfügbar: %s", exc)
        from .speech.azure import VOICE_PRESETS

        s = self.s
        return {
            "inputs": inputs, "outputs": outputs,
            "voices": [{"id": k, "name": n} for k, n, *_ in VOICE_PRESETS],
            "tts_preset": s.tts_preset, "attention_seconds": s.attention_seconds,
            "languages": s.language_list,
            "audio_input_device": s.audio_input_device or "", "audio_output_device": s.audio_output_device or "",
            "wake_word_threshold": s.wake_word_threshold, "speech_end_silence_ms": s.speech_end_silence_ms,
            "vad_threshold": s.vad_threshold, "tts_voice": s.tts_voice, "assistant_name": s.assistant_name,
            "speech_enabled": s.speech_enabled, "env_file": str(s.env_file_in_use() or Path(".env").resolve()),
        }

    def save_settings(self, values: dict[str, Any]) -> str:
        """Schreibt die Werte in die .env und übernimmt sie sofort."""
        from .config import update_env_file

        s = self.s
        mapping = {
            "audio_input_device": ("AUDIO_INPUT_DEVICE", str), "audio_output_device": ("AUDIO_OUTPUT_DEVICE", str),
            "wake_word_threshold": ("WAKE_WORD_THRESHOLD", float), "speech_end_silence_ms": ("SPEECH_END_SILENCE_MS", int),
            "vad_threshold": ("VAD_THRESHOLD", float), "tts_preset": ("TTS_PRESET", str),
            "attention_seconds": ("ATTENTION_SECONDS", int), "speech_languages": ("SPEECH_LANGUAGES", str),
        }
        env_values: dict[str, str] = {}
        for field, (env_key, cast) in mapping.items():
            if field not in values:
                continue
            raw = values[field]
            value = cast(raw) if raw not in ("", None) else ("" if cast is str else None)
            if value is None:
                continue
            setattr(s, field, value if value != "" else None)
            env_values[env_key] = str(value)
        env_path = s.env_file_in_use() or Path(".env").resolve()
        update_env_file(Path(env_path), env_values)

        if self.assistant is not None and self.assistant.speech is not None:
            self.assistant.speech.voice_preset = s.tts_preset
            self.assistant.speech.languages = s.language_list
        if self.listener is not None:
            self.listener.threshold = s.wake_word_threshold
            self.listener.end_silence_ms = s.speech_end_silence_ms
            self.listener.vad_threshold = s.vad_threshold
            self.listener.attention_ms = s.attention_seconds * 1000
            try:
                from .audio.io import resolve_device

                device = resolve_device(s.audio_input_device, "input")
                if device != self.listener.device:
                    self.listener.restart(device)
            except Exception as exc:  # noqa: BLE001
                return f"Gespeichert, aber Mikrofon nicht gefunden: {exc}"
        return "Gespeichert und übernommen."

    # --- Vom Browser aufgerufen ----------------------------------------------
    def config(self) -> dict[str, Any]:
        s = self.s
        logo = None
        if s.logo_path and Path(s.logo_path).exists():
            suffix = Path(s.logo_path).suffix.lower().lstrip(".") or "png"
            data = base64.b64encode(Path(s.logo_path).read_bytes()).decode()
            logo = f"data:image/{'svg+xml' if suffix == 'svg' else suffix};base64,{data}"
        return {
            "name": s.assistant_name,
            "title": s.brand_title,
            "logo": logo,
            "colors": {
                "bg": s.brand_bg, "panel": s.brand_panel, "grid": s.brand_grid, "line": s.brand_line,
                "primary": s.brand_primary, "accent": s.brand_accent, "text": s.brand_text, "muted": s.brand_muted,
            },
        }

    def poll(self) -> dict[str, Any]:
        with self._lock:
            messages, self._messages = self._messages, []
            status, self._status = self._status, None
        level = self.listener.level if self.listener is not None else 0.0
        return {
            "state": self._state,
            "status": status,
            "level": round(level, 3),
            "score": round(self.listener.score, 2) if self.listener is not None else None,
            "threshold": self.s.wake_word_threshold,
            "messages": messages,
            "busy": self._busy,
            "mic": {"enabled": self.listener is not None, "on": self._mic_on},
        }

    def send(self, text: str) -> None:
        text = (text or "").strip()
        if not text or self._busy or self.assistant is None:
            return
        self._push("Du", text)
        if self.listener is not None:
            self.listener.pause()
        self._set_state("processing")
        self._run(self._process_text, text)

    def set_mic(self, on: bool) -> None:
        self._mic_on = bool(on)
        if self.listener is None:
            return
        if self._mic_on:
            if not self._busy:
                self.listener.resume()
        else:
            self.listener.pause()
            self._set_state("idle")

    def open_settings(self) -> None:
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
        self._push("System", f"Einstellungen geöffnet: {env}. Nach dem Speichern Jarvis neu starten.")

    # --- Verarbeitung -----------------------------------------------------
    def _run(self, target, *args) -> None:  # noqa: ANN001
        self._busy = True

        def guarded() -> None:
            try:
                target(*args)
            except Exception as exc:  # noqa: BLE001
                log.exception("Verarbeitung fehlgeschlagen")
                self._push("System", f"Fehler: {exc}")
            finally:
                self._busy = False
                if self.listener is not None and self._mic_on:
                    self.listener.resume(attentive=self.s.attention_seconds > 0)
                else:
                    self._set_state("idle")

        threading.Thread(target=guarded, daemon=True).start()

    def _process_text(self, text: str) -> None:
        assert self.assistant is not None
        answer = self.assistant.handle_text(text)
        self._push(self.s.assistant_name, answer)
        self._set_state("speaking")
        error = self.assistant.speak(answer)
        if error:
            self._push("System", error)

    def _process_audio(self, wavs: list[bytes]) -> None:
        assert self.assistant is not None
        self._set_status("Erkenne Sprache")
        text = self.assistant.transcribe(wavs)
        if not text:
            self._push("System", "Nichts verstanden.")
            return
        self._push("Du", text)
        self._process_text(text)

    def _on_utterance(self, wavs: list[bytes]) -> None:
        self._run(self._process_audio, wavs)

    def _on_listener_state(self, state: str) -> None:
        if state == "wake":
            self._set_state("wake")
            try:
                from .audio.io import play_wav, resolve_device
                from .audio.wakeword import beep_wav

                play_wav(beep_wav(), resolve_device(self.s.audio_output_device, "output"))
            except Exception as exc:  # noqa: BLE001
                self._push("System", f"Bestätigungston fehlgeschlagen: {exc}")
        elif state in ("listening", "processing", "attentive"):
            self._set_state(state)
        elif state == "cancel":
            self._push("System", "Ich habe nichts gehört. Bitte direkt nach dem Ton sprechen.")
        elif state.startswith("error:"):
            self._push("System", f"Wake-Word-Erkennung nicht verfügbar: {state[6:]}")
            self.listener = None
            self._mic_on = False
            self._set_state("idle")

    # --- Helfer ------------------------------------------------------------
    def _push(self, who: str, text: str) -> None:
        with self._lock:
            self._messages.append({"who": who, "text": text})

    def _set_state(self, state: str) -> None:
        self._state = state

    def _set_status(self, text: str) -> None:
        with self._lock:
            self._status = text.rstrip(" …")

    def _confirm(self, message: str) -> bool:
        if self.window is None:
            return False
        return bool(self.window.create_confirmation_dialog("Bestätigung", message))

    def _notify(self, message: str) -> None:
        self._push("System", message)


def run(settings: Settings) -> None:
    api = Api(settings)
    window = webview.create_window(
        f"{settings.assistant_name} – {settings.brand_title}",
        url=UI_FILE.as_uri(),
        js_api=api,
        width=1000,
        height=760,
        min_size=(760, 560),
        background_color=settings.brand_bg,
        text_select=True,
    )
    api.window = window

    def on_closed() -> None:
        if api.listener is not None:
            api.listener.stop()

    window.events.closed += on_closed
    webview.start(api.start, private_mode=False)
