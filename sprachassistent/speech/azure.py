"""Spracherkennung und Sprachausgabe über die Azure-Speech-REST-API.

Bewusst ohne das native Azure-SDK: nur HTTP-Aufrufe, 16-kHz-Mono-PCM-WAV rein, WAV raus.
Grenze der REST-Erkennung: Aufnahmen bis 60 Sekunden.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

import requests

OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"


class AzureSpeech:
    def __init__(self, key: str, region: str, language: str = "de-DE", voice: str = "de-DE-KatjaNeural") -> None:
        self.key = key
        self.region = region
        self.language = language
        self.voice = voice

    def transcribe(self, wav_bytes: bytes) -> str:
        url = f"https://{self.region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        resp = requests.post(
            url,
            params={"language": self.language, "format": "simple", "profanity": "raw"},
            headers={
                "Ocp-Apim-Subscription-Key": self.key,
                "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
                "Accept": "application/json",
            },
            data=wav_bytes,
            timeout=60,
        )
        resp.raise_for_status()
        data = resp.json()
        status = data.get("RecognitionStatus")
        if status == "Success":
            return data.get("DisplayText", "").strip()
        if status in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout"):
            return ""
        raise RuntimeError(f"Spracherkennung fehlgeschlagen: {status}")

    def synthesize(self, text: str) -> bytes:
        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        ssml = (
            f'<speak version="1.0" xml:lang="{self.language}">'
            f'<voice name="{self.voice}">{escape(clean_for_speech(text))}</voice></speak>'
        )
        resp = requests.post(
            url,
            headers={
                "Ocp-Apim-Subscription-Key": self.key,
                "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
                "User-Agent": "sprachassistent",
            },
            data=ssml.encode("utf-8"),
            timeout=60,
        )
        if resp.status_code >= 400:
            hint = {401: "Schlüssel ungültig", 403: "Schlüssel/Region passen nicht zusammen oder Kontingent erschöpft",
                    400: "Stimme oder Sprache unbekannt (TTS_VOICE prüfen)", 429: "zu viele Anfragen"}.get(resp.status_code, "")
            raise RuntimeError(f"HTTP {resp.status_code} {hint}: {resp.text[:200]}")
        return resp.content


_MARKDOWN = re.compile(r"[*_`#>]+|\[([^\]]+)\]\([^)]+\)")


def clean_for_speech(text: str, max_chars: int = 1500) -> str:
    """Entfernt Markdown-Zeichen und kürzt sehr lange Texte für die Sprachausgabe."""
    cleaned = _MARKDOWN.sub(lambda m: m.group(1) or "", text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) > max_chars:
        cut = cleaned[:max_chars]
        cut = cut[: cut.rfind(".") + 1] if "." in cut else cut
        cleaned = cut + " Den vollständigen Text findest du im Fenster."
    return cleaned
