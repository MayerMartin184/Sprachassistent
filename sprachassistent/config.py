"""Zentrale Konfiguration. Werte kommen aus Umgebungsvariablen oder einer .env-Datei."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path.home() / ".sprachassistent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", str(DATA_DIR / ".env")),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Claude
    anthropic_api_key: str | None = None  # None -> SDK-Standardauflösung (ANTHROPIC_API_KEY, ant auth login)
    assistant_model: str = "claude-opus-5"
    assistant_effort: str = "medium"
    max_tool_rounds: int = 30

    # Azure Speech
    azure_speech_key: str | None = None
    azure_speech_region: str | None = None
    speech_language: str = "de-DE"
    tts_voice: str = "de-DE-KatjaNeural"

    # Microsoft 365
    ms_client_id: str | None = None
    ms_tenant_id: str = "common"

    # Wake-Word („Hey Jarvis“, lokal per openWakeWord)
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    assistant_name: str = "Jarvis"

    # Webcam
    webcam_enabled: bool = True
    webcam_index: int = 0

    # Lokales
    documents_root: Path = Path.home() / "Documents"
    data_dir: Path = DATA_DIR
    timezone: str = "Europe/Berlin"

    @field_validator("documents_root", "data_dir", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser()
        return value

    @field_validator("anthropic_api_key", "azure_speech_key", "azure_speech_region", "ms_client_id", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @property
    def speech_enabled(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_region)

    @property
    def m365_enabled(self) -> bool:
        return bool(self.ms_client_id)


def load_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
