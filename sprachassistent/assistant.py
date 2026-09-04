"""Verdrahtung: Einstellungen -> Werkzeuge -> Agent -> Sprache."""

from __future__ import annotations

import logging
from typing import Callable

from .agent.agent import Agent
from .config import Settings
from .tools import files, lists, m365, tasks, webcam
from .tools.base import ToolRegistry

log = logging.getLogger(__name__)

Confirm = Callable[[str], bool]
Notify = Callable[[str], None]
Status = Callable[[str], None]


class Assistant:
    def __init__(self, settings: Settings, confirm: Confirm, notify: Notify, on_status: Status) -> None:
        self.settings = settings
        registry = ToolRegistry()
        self.features: list[str] = []

        if settings.m365_enabled:
            graph = m365.GraphClient(
                settings.ms_client_id or "",
                settings.ms_tenant_id,
                settings.data_dir / "ms_token_cache.json",
                notify,
            )
            registry.register_all(m365.build_tools(m365.M365Tools(graph, confirm, settings.timezone)))
            self.features += ["Microsoft To Do", "E-Mail", "Kalender", "Teams-Transkripte"]
        else:
            registry.register_all(tasks.build_tools(tasks.TaskManager(settings.data_dir)))
            self.features.append("Aufgaben (lokal)")

        registry.register_all(lists.build_tools(lists.ListManager(settings.data_dir)))
        registry.register_all(files.build_tools(files.FileManager(settings.documents_root)))
        self.features += ["Listen", "Dateiablage", "Web-Recherche"]

        if settings.webcam_enabled and webcam.available():
            registry.register_all(webcam.build_tools(settings.webcam_index))
            self.features.append("Webcam")

        self.registry = registry
        self.agent = Agent(settings, registry, on_status)

        self.speech = None
        if settings.speech_enabled:
            from .speech.azure import AzureSpeech

            self.speech = AzureSpeech(
                settings.azure_speech_key or "",
                settings.azure_speech_region or "",
                settings.speech_language,
                settings.tts_voice,
            )
            self.features.append(f"Sprache (Wake-Word „Hey {settings.assistant_name}“)" if settings.wake_word_enabled else "Sprache")
        else:
            self.features.append("nur Text")

    @property
    def capabilities(self) -> str:
        return ", ".join(self.features)

    def handle_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        return self.agent.run(text)

    def transcribe(self, wav_bytes: bytes) -> str:
        if self.speech is None:
            raise RuntimeError("Spracherkennung nicht konfiguriert (AZURE_SPEECH_KEY/REGION fehlen).")
        return self.speech.transcribe(wav_bytes)

    def speak(self, text: str) -> str | None:
        """Spricht den Text. Rückgabe: None bei Erfolg, sonst eine Fehlerbeschreibung für den Nutzer."""
        if self.speech is None or not text:
            return None
        from .audio.io import play_wav, resolve_device

        try:
            audio = self.speech.synthesize(text)
        except Exception as exc:  # noqa: BLE001
            log.exception("Sprachsynthese fehlgeschlagen")
            return f"Sprachausgabe (Azure) fehlgeschlagen: {exc}"
        try:
            device = resolve_device(self.settings.audio_output_device, "output")
            play_wav(audio, device)
        except Exception as exc:  # noqa: BLE001
            log.exception("Wiedergabe fehlgeschlagen")
            return f"Wiedergabe fehlgeschlagen: {exc}. Lautsprecher mit AUDIO_OUTPUT_DEVICE in der .env wählen."
        return None
