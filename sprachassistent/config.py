"""Zentrale Konfiguration. Werte kommen aus Umgebungsvariablen oder einer .env-Datei."""

from __future__ import annotations

from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DATA_DIR = Path.home() / ".sprachassistent"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        # Reihenfolge = Priorität (spätere überschreiben frühere). .env.example wird mitgelesen, weil Nutzer ihre
        # Schlüssel oft dort eintragen; .env.txt, weil der Windows-Editor gern ".txt" anhängt.
        env_file=(".env.example", ".env", ".env.txt", str(DATA_DIR / ".env")),
        env_file_encoding="utf-8",
        env_ignore_empty=True,  # leere Zeile (KEY=) überschreibt keinen Wert aus einer anderen Datei
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

    # Audio
    audio_input_device: str | None = None  # Name (Teilstring) oder Nummer des Mikrofons; leer = Windows-Standard

    # Wake-Word („Hey Jarvis“, lokal per openWakeWord)
    wake_word_enabled: bool = True
    wake_word_model: str = "hey_jarvis"
    wake_word_threshold: float = 0.5
    assistant_name: str = "Jarvis"

    # Design (Hex-Farben; Standard = Mayer E-Concept: dunkles Petrol, Raster, hellcyanfarbene Akzente)
    brand_bg: str = "#0c171b"
    brand_panel: str = "#122126"
    brand_grid: str = "#16262c"
    brand_line: str = "#2f5a63"
    brand_primary: str = "#a7e3ea"
    brand_accent: str = "#5fb3bf"
    brand_text: str = "#f2f7f8"
    brand_muted: str = "#8fa4ab"
    brand_font: str = "Segoe UI"
    brand_mono: str = "Consolas"
    brand_title: str = "Mayer E-Concept · Assistant"
    logo_path: Path | None = None  # PNG, wird oben links angezeigt (sonst gezeichnetes Rautenzeichen)

    # Webcam
    webcam_enabled: bool = True
    webcam_index: int = 0

    # Lokales
    documents_root: Path = Path.home() / "Documents"
    data_dir: Path = DATA_DIR
    timezone: str = "Europe/Berlin"

    @field_validator("documents_root", "data_dir", "logo_path", mode="before")
    @classmethod
    def _expand(cls, value: object) -> object:
        if isinstance(value, str):
            return Path(value).expanduser() if value.strip() else None
        return value

    @field_validator("anthropic_api_key", "azure_speech_key", "azure_speech_region", "ms_client_id", "audio_input_device", mode="before")
    @classmethod
    def _empty_to_none(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    @field_validator("azure_speech_region", mode="after")
    @classmethod
    def _normalize_region(cls, value: str | None) -> str | None:
        # "Germany West Central" / "(Europe) Germany West Central" -> "germanywestcentral"
        if value is None:
            return None
        cleaned = value.split(")")[-1].strip().lower().replace(" ", "")
        return cleaned or None

    def missing_speech_values(self) -> list[str]:
        missing = []
        if not self.azure_speech_key:
            missing.append("AZURE_SPEECH_KEY")
        if not self.azure_speech_region:
            missing.append("AZURE_SPEECH_REGION")
        return missing

    @staticmethod
    def env_file_in_use() -> Path | None:
        for candidate in (Path(".env"), Path(".env.txt"), DATA_DIR / ".env", Path(".env.example")):
            if candidate.exists():
                return candidate.resolve()
        return None

    @staticmethod
    def speech_diagnosis() -> str:
        """Zeigt pro Datei, was in den Azure-Zeilen steht (Schlüssel maskiert) – zum Finden von Tippfehlern."""
        wanted = ("AZURE_SPEECH_KEY", "AZURE_SPEECH_REGION")
        lines_out: list[str] = []
        for candidate in (Path(".env"), Path(".env.txt"), Path(".env.example"), DATA_DIR / ".env"):
            if not candidate.exists():
                continue
            found: dict[str, str] = {}
            for raw in candidate.read_text(encoding="utf-8", errors="replace").splitlines():
                line = raw.strip()
                if "=" not in line:
                    continue
                key, _, value = line.partition("=")
                key, value = key.strip().lstrip("#").strip().upper(), value.strip().strip("\"'")
                if key in wanted:
                    shown = "(leer)" if not value else (value[:4] + "…" + value[-3:] + f" ({len(value)} Zeichen)" if key.endswith("KEY") else value)
                    if raw.lstrip().startswith("#"):
                        shown += "  <- Zeile ist mit # auskommentiert"
                    found[key] = shown
            lines_out.append(f"{candidate.resolve()}:")
            for key in wanted:
                lines_out.append(f"   {key} = {found.get(key, '(Zeile fehlt)')}")
        if not lines_out:
            return "Keine .env-Datei gefunden."
        return "\n".join(lines_out) + "\nErwartet: AZURE_SPEECH_KEY = 32 Zeichen, AZURE_SPEECH_REGION = germanywestcentral"

    @property
    def speech_enabled(self) -> bool:
        return bool(self.azure_speech_key and self.azure_speech_region)

    @property
    def m365_enabled(self) -> bool:
        return bool(self.ms_client_id)


class ConfigError(RuntimeError):
    """Fehlende oder ungültige Konfiguration, verständlich für den Nutzer formuliert."""


def load_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings


def check_required(settings: Settings) -> None:
    import os

    key = settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN")
    if not key or key.startswith("sk-ant-...") or "hier" in key.lower():
        raise ConfigError(
            "Der Claude-API-Schlüssel fehlt.\n\n"
            f"Bitte die Datei .env im Programmordner ({Path.cwd()}) öffnen und in der Zeile\n"
            "ANTHROPIC_API_KEY=... deinen Schlüssel eintragen.\n\n"
            "Hinweis: Die Datei muss genau .env heißen (auch .env.txt wird akzeptiert)."
        )
