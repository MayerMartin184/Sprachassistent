"""Sprachausgabe über ElevenLabs: echte Charakterstimmen statt nachbearbeiteter Standardstimmen.

Die Spracherkennung bleibt bei Azure; hier geht es nur um die Stimme. Geliefert wird 16-kHz-Mono-PCM,
das direkt in eine WAV-Datei verpackt wird – dasselbe Format wie bei Azure, damit die Wiedergabe gleich bleibt.
"""

from __future__ import annotations

import logging
from typing import Any

import requests

from ..audio.io import SAMPLE_RATE, pcm_to_wav
from .azure import clean_for_speech

log = logging.getLogger(__name__)

BASE = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_multilingual_v2"  # spricht Deutsch, Rumänisch und Englisch
OUTPUT_FORMAT = f"pcm_{SAMPLE_RATE}"

ERRORS = {
    401: "Der ElevenLabs-Schlüssel ist ungültig.",
    403: "Der ElevenLabs-Schlüssel darf diese Stimme nicht verwenden.",
    404: "Die eingestellte Stimme gibt es in deinem ElevenLabs-Konto nicht.",
    422: "ElevenLabs hat die Anfrage abgelehnt (Text oder Einstellungen ungültig).",
    429: "ElevenLabs-Kontingent erschöpft oder zu viele Anfragen.",
}


class ElevenLabsSpeech:
    def __init__(
        self,
        api_key: str,
        voice_id: str,
        model: str = DEFAULT_MODEL,
        stability: float = 0.4,
        similarity: float = 0.75,
        style: float = 0.0,
    ) -> None:
        self.api_key = api_key
        self.voice_id = voice_id
        self.model = model or DEFAULT_MODEL
        self.stability = stability
        self.similarity = similarity
        self.style = style
        self._voices: list[dict[str, str]] | None = None

    @property
    def configured(self) -> bool:
        return bool(self.api_key and self.voice_id)

    def _headers(self) -> dict[str, str]:
        return {"xi-api-key": self.api_key}

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            return requests.request(method, f"{BASE}{path}", headers=headers, **kwargs)
        except requests.RequestException as exc:
            raise RuntimeError(f"ElevenLabs ist nicht erreichbar (Internetverbindung oder Firewall): {exc}") from exc

    def _fail(self, response: Any, what: str) -> RuntimeError:
        hint = ERRORS.get(response.status_code, "")
        detail = " ".join(str(response.text)[:200].split())
        return RuntimeError(f"{what}: HTTP {response.status_code} {hint} {detail}".strip())

    # --- Stimmen ---------------------------------------------------------------
    def voices(self, refresh: bool = False) -> list[dict[str, str]]:
        """Stimmen des Kontos: eigene, gestaltete und die aus der Bibliothek."""
        if self._voices is not None and not refresh:
            return self._voices
        if not self.api_key:
            return []
        response = self._request("GET", "/voices", timeout=30)
        if response.status_code >= 400:
            raise self._fail(response, "Stimmen konnten nicht geladen werden")
        voices = []
        for voice in response.json().get("voices", []):
            labels = voice.get("labels") or {}
            traits = ", ".join(str(v) for v in labels.values() if v)
            voices.append({
                "id": voice.get("voice_id", ""),
                "name": voice.get("name", "?") + (f" – {traits}" if traits else ""),
            })
        self._voices = [v for v in voices if v["id"]]
        return self._voices

    # --- Ausgabe ---------------------------------------------------------------
    def synthesize(self, text: str) -> bytes:
        if not self.configured:
            raise RuntimeError("ElevenLabs ist nicht vollständig eingerichtet (Schlüssel oder Stimme fehlt).")
        response = self._request(
            "POST",
            f"/text-to-speech/{self.voice_id}",
            headers={"Content-Type": "application/json", "Accept": "audio/pcm"},
            params={"output_format": OUTPUT_FORMAT},
            json={
                "text": clean_for_speech(text),
                "model_id": self.model,
                "voice_settings": {
                    "stability": self.stability,
                    "similarity_boost": self.similarity,
                    "style": self.style,
                    "use_speaker_boost": True,
                },
            },
            timeout=120,
        )
        if response.status_code >= 400:
            raise self._fail(response, "Sprachausgabe fehlgeschlagen")
        return pcm_to_wav(response.content, SAMPLE_RATE)
