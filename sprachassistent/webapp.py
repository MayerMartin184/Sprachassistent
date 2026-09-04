"""Backend der Oberfläche: Zustand, Nachrichten, Einstellungen, proaktive Meldungen.

Läuft als eigener Prozess (server.py) getrennt vom Fenster, damit lange Schritte (Kamera, Modelle, KI)
das Fenster nie einfrieren. Die Seite fragt regelmäßig poll() ab; Bestätigungen werden als Frage in die
Oberfläche gestellt und dort beantwortet.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .assistant import Assistant
from .config import Settings

log = logging.getLogger(__name__)
UI_FILE = Path(__file__).with_name("ui") / "index.html"


class Api:
    """Von der Oberfläche aufrufbare Schnittstelle (über server.py als JSON-Endpunkte)."""

    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._lock = threading.Lock()
        self._confirm_request: dict[str, str] | None = None
        self._confirm_answers: dict[str, bool] = {}
        self._confirm_event = threading.Event()
        self.last_poll = time.time()
        self._messages: list[dict[str, str]] = []
        self._state = "idle"
        self._status: str | None = None
        self._busy = False
        self._mic_on = True
        self.listener = None
        self.assistant: Assistant | None = None
        self.presence = None
        self.ambient = None
        self._announced_events: set[str] = set()
        self._announce_lock = threading.Lock()

    # --- Start ------------------------------------------------------------
    def start(self) -> None:
        """Wird nach dem Öffnen des Fensters im Hintergrund aufgerufen."""
        snapshot = None
        if self.presence is not None:
            self.presence.start()
            snapshot = self.presence.snapshot_jpeg
        try:
            self.assistant = Assistant(self.s, confirm=self._confirm, notify=self._notify, on_status=self._set_status, snapshot_provider=snapshot)
        except Exception as exc:  # noqa: BLE001
            log.exception("Assistent konnte nicht starten")
            self._push("System", f"Start fehlgeschlagen: {exc}")
            return
        self._push("System", f"Funktionen: {self.assistant.capabilities}" + (", Präsenz" if self.presence else ""))
        if self.s.speech_enabled:
            from .ambient import AmbientRecorder

            self.ambient = AmbientRecorder(self.s, self.assistant, notify=self._push, announce=self._announce)
            self.ambient.enabled = self.s.ambient_listening
            self.assistant.register_ambient(self.ambient)
        threading.Thread(target=self._scheduler, name="scheduler", daemon=True).start()
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
            on_ambient=lambda wavs: self.ambient.submit(wavs) if self.ambient is not None else None,
        )
        self.listener.ambient = self.s.ambient_listening
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
        speech = self.assistant.speech if self.assistant is not None else None
        voices = []
        for k, n, voice, *_ in VOICE_PRESETS:
            label = n
            if speech is not None:
                used, replaced = speech.resolve_voice(voice)
                if replaced:
                    label += f"  [in deiner Region nicht verfügbar, Ersatz: {used.split('-')[-1].replace('Neural', '')}]"
            voices.append({"id": k, "name": label})
        return {
            "inputs": inputs, "outputs": outputs,
            "voices": voices,
            "tts_preset": s.tts_preset, "attention_seconds": s.attention_seconds,
            "presence_enabled": s.presence_enabled, "presence_cooldown_min": s.presence_cooldown_min,
            "presence_available": self.presence is not None,
            "ambient_extract_minutes": s.ambient_extract_minutes,
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
            "presence_enabled": ("PRESENCE_ENABLED", bool), "presence_cooldown_min": ("PRESENCE_COOLDOWN_MIN", int),
            "ambient_extract_minutes": ("AMBIENT_EXTRACT_MINUTES", int),
        }
        env_values: dict[str, str] = {}
        for field, (env_key, cast) in mapping.items():
            if field not in values:
                continue
            raw = values[field]
            if cast is bool:
                value = bool(raw)
            else:
                value = cast(raw) if raw not in ("", None) else ("" if cast is str else None)
            if value is None:
                continue
            setattr(s, field, value if value != "" else None)
            env_values[env_key] = str(value).lower() if cast is bool else str(value)
        env_path = s.env_file_in_use() or Path(".env").resolve()
        update_env_file(Path(env_path), env_values)

        if self.assistant is not None and self.assistant.speech is not None:
            self.assistant.speech.voice_preset = s.tts_preset
            self.assistant.speech.languages = s.language_list
        if self.presence is not None:
            self.presence.logic.cooldown_s = s.presence_cooldown_min * 60
            if not s.presence_enabled:
                self.presence.stop()
                self.presence = None
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

    def setup_m365(self) -> str:
        """Richtet die Microsoft-App automatisch ein (Administrator-Anmeldung per Gerätecode)."""
        from pathlib import Path as _Path

        from .config import update_env_file
        from .tools.m365_setup import M365Setup

        self._push("System", "Microsoft-Einrichtung gestartet …")
        try:
            result = M365Setup(self.s.ms_tenant_id, lambda msg: self._push("System", msg)).run(self.s.ms_client_id)
        except Exception as exc:  # noqa: BLE001
            log.exception("Microsoft-Einrichtung fehlgeschlagen")
            self._push("System", f"Microsoft-Einrichtung fehlgeschlagen: {exc}")
            return f"Fehlgeschlagen: {exc}"
        env_path = self.s.env_file_in_use() or _Path(".env").resolve()
        update_env_file(_Path(env_path), {"MS_CLIENT_ID": result["client_id"], "MS_TENANT_ID": result["tenant_id"] or self.s.ms_tenant_id})
        cache = self.s.data_dir / "ms_token_cache.json"
        if cache.exists():
            cache.unlink()  # alte Anmeldung passt nicht mehr zu den neuen Berechtigungen
        what = "neu angelegt" if result["created"] else "korrigiert"
        msg = (f"Microsoft-App {what}: Umleitungsadresse, Berechtigungen und Administrator-Zustimmung gesetzt. "
               f"MS_CLIENT_ID={result['client_id']} in die .env geschrieben. Bitte Jarvis neu starten; "
               "beim ersten Kalender- oder Mail-Zugriff öffnet sich dann die normale Anmeldung im Browser.")
        self._push("System", msg)
        return msg

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
        try:
            return self._poll()
        except Exception as exc:  # noqa: BLE001 - die Oberfläche darf nie hängen bleiben
            log.warning("poll: %s", exc)
            return {"state": self._state, "status": None, "level": 0, "messages": [], "busy": self._busy}

    def _poll(self) -> dict[str, Any]:
        self.last_poll = time.time()
        with self._lock:
            messages, self._messages = self._messages, []
            status, self._status = self._status, None
            confirm = dict(self._confirm_request) if self._confirm_request else None
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
            "ambient": {"available": self.ambient is not None, "on": bool(self.ambient and self.ambient.enabled)},
            "confirm": confirm,
        }

    def set_ambient(self, on: bool) -> None:
        from .config import update_env_file

        on = bool(on)
        self.s.ambient_listening = on
        if self.ambient is not None:
            self.ambient.enabled = on
        if self.listener is not None:
            self.listener.ambient = on
        env_path = self.s.env_file_in_use() or Path(".env").resolve()
        update_env_file(Path(env_path), {"AMBIENT_LISTENING": "true" if on else "false"})
        self._push("System", "Mithören eingeschaltet: Gespräche werden mitgeschrieben und auf Zusagen, Aufgaben und Termine geprüft."
                   if on else "Mithören ausgeschaltet.")

    def answer_confirm(self, request_id: str, ok: bool) -> None:
        with self._lock:
            if self._confirm_request and self._confirm_request["id"] == request_id:
                self._confirm_answers[request_id] = bool(ok)
                self._confirm_request = None
        self._confirm_event.set()

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

    # --- Proaktiv: Erinnerungen, Termine, Präsenz ---------------------------------
    def _scheduler(self) -> None:
        """Prüft alle 20 s fällige Erinnerungen und alle 60 s anstehende Termine."""
        last_calendar = 0.0
        while True:
            try:
                assert self.assistant is not None
                for item in self.assistant.reminders.due():
                    self._announce(f"Erinnerung, die der Nutzer gesetzt hat: „{item['text']}“ (fällig jetzt).")
                if (
                    self.assistant.m365 is not None and self.assistant.graph is not None
                    and self.assistant.graph.has_account() and time.time() - last_calendar >= 60
                ):
                    last_calendar = time.time()
                    for ev in self.assistant.m365.calendar_upcoming(self.s.calendar_lead_minutes):
                        key = f"cal:{ev['id']}"
                        if key in self._announced_events:
                            continue
                        self._announced_events.add(key)
                        minutes = max(1, int((ev["start"] - datetime.now(ev["start"].tzinfo)).total_seconds() // 60))
                        where = f", Ort: {ev['location']}" if ev.get("location") else (" (Teams)" if ev.get("online") else "")
                        self._announce(f"In {minutes} Minuten beginnt der Termin „{ev['subject']}“{where}.")
            except Exception as exc:  # noqa: BLE001
                log.warning("Scheduler: %s", exc)
            time.sleep(20)

    def _on_presence_event(self, kind: str, description: str, jpeg: bytes | None) -> None:
        self._announce(description, jpeg)

    def _announce(self, description: str, jpeg: bytes | None = None) -> None:
        """Lässt den Agenten eine kurze Meldung formulieren und spricht sie, sobald nichts anderes läuft."""
        if self.assistant is None:
            return
        with self._announce_lock:
            deadline = time.time() + 120
            while self._busy and time.time() < deadline:
                time.sleep(0.5)
            if self._busy:
                return
            self._busy = True
            try:
                if self.listener is not None:
                    self.listener.pause()
                self._set_state("processing")
                text = self.assistant.handle_event(description, jpeg)
                self._push(self.s.assistant_name, text)
                self._set_state("speaking")
                error = self.assistant.speak(text)
                if error:
                    self._push("System", error)
            except Exception as exc:  # noqa: BLE001
                log.exception("Proaktive Meldung fehlgeschlagen")
                self._push("System", f"Meldung fehlgeschlagen: {exc}")
            finally:
                self._busy = False
                if self.listener is not None and self._mic_on:
                    self.listener.resume(attentive=self.s.attention_seconds > 0)
                else:
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
        """Stellt die Frage in der Oberfläche und wartet (max. 3 Minuten) auf die Antwort."""
        request_id = uuid.uuid4().hex
        with self._lock:
            self._confirm_request = {"id": request_id, "message": message}
            self._confirm_event.clear()
        deadline = time.time() + 180
        while time.time() < deadline:
            self._confirm_event.wait(timeout=1)
            with self._lock:
                if request_id in self._confirm_answers:
                    return self._confirm_answers.pop(request_id)
        with self._lock:
            if self._confirm_request and self._confirm_request["id"] == request_id:
                self._confirm_request = None
        return False

    def shutdown(self) -> None:
        if self.listener is not None:
            self.listener.stop()
        if self.presence is not None:
            self.presence.stop()

    def _notify(self, message: str) -> None:
        self._push("System", message)


def _preload(settings: Settings):  # noqa: ANN202
    """Schwere Importe, Modelle und die Kamera vor dem Fenster laden – sonst blockiert der Start das Fenster
    („reagiert nicht“). Rückgabe: vorbereitete Präsenz-Überwachung oder None."""
    presence = None
    import importlib

    for name in ("anthropic", "msal", "numpy", "sounddevice"):
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - fehlende Audio-Bibliothek meldet später der Listener
            log.warning("Vorladen von %s fehlgeschlagen: %s", name, exc)

    if settings.webcam_enabled:
        try:
            import cv2  # noqa: F401

            if settings.presence_enabled:
                from .presence import PresenceWatcher

                watcher = PresenceWatcher(
                    settings.webcam_index, lambda *_: None,
                    absence_min=settings.presence_absence_min, cooldown_min=settings.presence_cooldown_min,
                )
                if watcher.open():
                    presence = watcher
        except ImportError:
            pass
        except Exception as exc:  # noqa: BLE001
            log.warning("Kamera nicht vorbereitet: %s", exc)
    if settings.speech_enabled and settings.wake_word_enabled:
        try:
            from .audio.wakeword import preload_models

            preload_models(settings.wake_word_model)
        except Exception as exc:  # noqa: BLE001 - Fehler zeigt später der Listener im Verlauf
            log.warning("Wake-Word-Modelle nicht vorgeladen: %s", exc)
    return presence


def create_backend(settings: Settings) -> Api:
    """Bereitet das Backend vor (Importe, Modelle, Kamera) und liefert die Schnittstelle."""
    presence = _preload(settings)
    api = Api(settings)
    if presence is not None:
        presence.on_event = api._on_presence_event
        api.presence = presence
    return api
