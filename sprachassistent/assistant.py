"""Verdrahtung: Einstellungen -> Werkzeuge -> Agent -> Sprache."""

from __future__ import annotations

import logging
from typing import Callable

from .agent.agent import Agent
from .config import Settings
from .tools import files, lists, m365, memory, reminders, tasks, webcam
from .tools.base import ToolRegistry

log = logging.getLogger(__name__)

Confirm = Callable[[str], bool]
Notify = Callable[[str], None]
Status = Callable[[str], None]


class Assistant:
    def __init__(
        self, settings: Settings, confirm: Confirm, notify: Notify, on_status: Status, snapshot_provider=None  # noqa: ANN001
    ) -> None:
        self.settings = settings
        registry = ToolRegistry()
        self.features: list[str] = []
        self.m365: m365.M365Tools | None = None
        self.graph: m365.GraphClient | None = None

        if settings.m365_enabled:
            graph = m365.GraphClient(
                settings.ms_client_id or "",
                settings.ms_tenant_id,
                settings.data_dir / "ms_token_cache.json",
                notify,
            )
            self.graph = graph
            self.m365 = m365.M365Tools(graph, confirm, settings.timezone)
            registry.register_all(m365.build_tools(self.m365))
            self.features += ["Microsoft To Do", "E-Mail", "Kalender", "Teams-Transkripte"]
        else:
            registry.register_all(tasks.build_tools(tasks.TaskManager(settings.data_dir)))
            self.features.append("Aufgaben (lokal)")

        registry.register_all(lists.build_tools(lists.ListManager(settings.data_dir)))
        registry.register_all(files.build_tools(files.FileManager(settings.documents_root)))
        self.memory = memory.Memory(settings.data_dir)
        registry.register_all(memory.build_tools(self.memory))
        self.reminders = reminders.Reminders(settings.data_dir, settings.timezone)
        registry.register_all(reminders.build_tools(self.reminders))
        self.features += ["Listen", "Dateiablage", "Web-Recherche", "Gedächtnis", "Erinnerungen"]

        if settings.webcam_enabled and webcam.available():
            registry.register_all(webcam.build_tools(settings.webcam_index, snapshot_provider))
            self.features.append("Webcam")

        self.registry = registry
        self.agent = Agent(settings, registry, on_status, memory_summary=self.memory.summary)

        self.speech = None
        if settings.speech_enabled:
            from .speech.azure import AzureSpeech

            self.speech = AzureSpeech(
                settings.azure_speech_key or "",
                settings.azure_speech_region or "",
                languages=settings.language_list,
                voice_preset=settings.tts_preset,
                voice=settings.tts_voice,
            )
            self.features.append(f"Sprache (Wake-Word „Hey {settings.assistant_name}“)" if settings.wake_word_enabled else "Sprache")
        else:
            self.features.append("nur Text")

    def register_ambient(self, recorder) -> None:  # noqa: ANN001
        """Werkzeug, mit dem der Agent das heutige Gesprächsprotokoll lesen kann."""
        from .tools.base import Tool, schema

        self.registry.register(Tool(
            name="ambient_transcript",
            description=(
                "Liest das heutige Gesprächsprotokoll des Mithör-Modus (was der Nutzer heute in Gesprächen und Sitzungen "
                "gesagt und zugesagt hat). Für Fragen wie „Was habe ich heute zugesagt?“ oder „Worum ging es im Gespräch mit X?“."
            ),
            input_schema=schema({"max_chars": {"type": "integer", "description": "Standard 20000"}}),
            handler=lambda max_chars=20000: recorder.transcript_today(max_chars),
        ))

    @property
    def capabilities(self) -> str:
        return ", ".join(self.features)

    def handle_text(self, text: str) -> str:
        text = text.strip()
        if not text:
            return ""
        return self.agent.run(text)

    def handle_event(self, description: str, jpeg: bytes | None = None) -> str:
        """Proaktives Ereignis (Erinnerung, Termin, Präsenz) durch den Agenten formulieren lassen."""
        import base64

        content: list[dict] = []
        if jpeg:
            content.append({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": base64.b64encode(jpeg).decode()}})
        content.append({"type": "text", "text": f"[Systemereignis, nicht vom Nutzer gesprochen] {description} Formuliere die gesprochene Meldung an den Nutzer, ein bis zwei Sätze."})
        return self.agent.run(content)

    def transcribe(self, wavs: list[bytes] | bytes) -> str:
        """Transkribiert ein oder mehrere Teilstücke und fügt die Texte zusammen."""
        if self.speech is None:
            raise RuntimeError("Spracherkennung nicht konfiguriert (AZURE_SPEECH_KEY/REGION fehlen).")
        if isinstance(wavs, bytes):
            wavs = [wavs]
        parts = [self.speech.transcribe(w) for w in wavs]
        return " ".join(p for p in parts if p).strip()

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
