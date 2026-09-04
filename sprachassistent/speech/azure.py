"""Spracherkennung und Sprachausgabe über die Azure-Speech-REST-API.

Bewusst ohne das native Azure-SDK: nur HTTP-Aufrufe, 16-kHz-Mono-PCM-WAV rein, WAV raus.
Grenze der REST-Erkennung: Aufnahmen bis 60 Sekunden.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

import requests

OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"

# Stimmen-Palette: (Schlüssel, Anzeigename, Azure-Stimme, Tonhöhe, Tempo, Stil oder None)
# Mehrsprachige Stimmen ("Multilingual") sprechen Deutsch, Rumänisch und Englisch mit derselben Stimme.
VOICE_PRESETS: list[tuple[str, str, str, str, str, str | None]] = [
    ("seraphina", "Seraphina – weiblich, natürlich, mehrsprachig", "de-DE-SeraphinaMultilingualNeural", "0%", "0%", None),
    ("florian", "Florian – männlich, natürlich, mehrsprachig", "de-DE-FlorianMultilingualNeural", "0%", "0%", None),
    ("katja", "Katja – weiblich, klar", "de-DE-KatjaNeural", "0%", "0%", None),
    ("conrad", "Conrad – männlich, ruhig", "de-DE-ConradNeural", "0%", "0%", None),
    ("amala", "Amala – weiblich, warm", "de-DE-AmalaNeural", "0%", "0%", None),
    ("christoph", "Christoph – männlich, sachlich", "de-DE-ChristophNeural", "0%", "0%", None),
    ("louisa", "Louisa – weiblich, jung", "de-DE-LouisaNeural", "0%", "0%", None),
    ("killian", "Killian – männlich, jung", "de-DE-KillianNeural", "0%", "0%", None),
    ("tanja", "Tanja – weiblich, freundlich", "de-DE-TanjaNeural", "0%", "0%", None),
    ("ralf", "Ralf – männlich, kräftig", "de-DE-RalfNeural", "0%", "0%", None),
    ("erzaehler", "Erzähler – tief und getragen", "de-DE-ConradNeural", "-12%", "-12%", None),
    ("ansagerin", "Ansagerin – schnell und präzise", "de-DE-KatjaNeural", "+4%", "+18%", None),
    ("monster", "Monster – sehr tief und langsam", "de-DE-RalfNeural", "-45%", "-18%", None),
    ("roboter", "Roboter – metallisch und flach", "de-DE-ChristophNeural", "+25%", "+8%", None),
    ("kind", "Kind – hoch und flink", "de-DE-LouisaNeural", "+35%", "+10%", None),
    ("riese", "Riese – tief, aber freundlich", "de-DE-FlorianMultilingualNeural", "-30%", "-8%", None),
    ("hexe", "Hexe – hoch und krächzend", "de-DE-ElkeNeural", "+40%", "-6%", None),
    ("alina_ro", "Alina – rumänisch, weiblich", "ro-RO-AlinaNeural", "0%", "0%", None),
    ("emil_ro", "Emil – rumänisch, männlich", "ro-RO-EmilNeural", "0%", "0%", None),
    ("ava_en", "Ava – englisch, weiblich, mehrsprachig", "en-US-AvaMultilingualNeural", "0%", "0%", None),
    ("andrew_en", "Andrew – englisch, männlich, mehrsprachig", "en-US-AndrewMultilingualNeural", "0%", "0%", None),
]


def preset(key: str) -> tuple[str, str, str, str | None]:
    """Liefert (Stimme, Tonhöhe, Tempo, Stil) zu einem Palettenschlüssel; unbekannt -> Seraphina."""
    for k, _name, voice, pitch, rate, style in VOICE_PRESETS:
        if k == key:
            return voice, pitch, rate, style
    return VOICE_PRESETS[0][2:6]


class AzureSpeech:
    def __init__(
        self,
        key: str,
        region: str,
        languages: list[str] | None = None,
        voice_preset: str = "seraphina",
        voice: str | None = None,
    ) -> None:
        self.key = key
        self.region = region
        self.languages = languages or ["de-DE"]
        self.voice_preset = voice_preset
        self.voice_override = voice  # explizite Azure-Stimme (TTS_VOICE) überstimmt die Palette
        self.last_language = self.languages[0]

    # --- Erkennung ----------------------------------------------------------
    def _recognize(self, wav_bytes: bytes, language: str) -> tuple[str, float]:
        url = f"https://{self.region}.stt.speech.microsoft.com/speech/recognition/conversation/cognitiveservices/v1"
        resp = requests.post(
            url,
            params={"language": language, "format": "detailed", "profanity": "raw"},
            headers={
                "Ocp-Apim-Subscription-Key": self.key,
                "Content-Type": "audio/wav; codecs=audio/pcm; samplerate=16000",
                "Accept": "application/json",
            },
            data=wav_bytes,
            timeout=60,
        )
        if resp.status_code >= 400:
            hint = {401: "Schlüssel ungültig", 403: "Schlüssel/Region passen nicht zusammen"}.get(resp.status_code, "")
            raise RuntimeError(f"Spracherkennung HTTP {resp.status_code} {hint}: {resp.text[:200]}")
        data = resp.json()
        status = data.get("RecognitionStatus")
        if status == "Success":
            best = max(data.get("NBest") or [{}], key=lambda n: n.get("Confidence", 0))
            return (best.get("Display") or data.get("DisplayText") or "").strip(), float(best.get("Confidence", 0))
        if status in ("NoMatch", "InitialSilenceTimeout", "BabbleTimeout"):
            return "", 0.0
        raise RuntimeError(f"Spracherkennung fehlgeschlagen: {status}")

    def transcribe(self, wav_bytes: bytes) -> str:
        """Erkennt in allen konfigurierten Sprachen parallel und nimmt das sicherste Ergebnis."""
        if len(self.languages) == 1:
            text, _ = self._recognize(wav_bytes, self.languages[0])
            return text
        from concurrent.futures import ThreadPoolExecutor

        with ThreadPoolExecutor(max_workers=len(self.languages)) as pool:
            results = list(pool.map(lambda lang: (lang, *self._recognize(wav_bytes, lang)), self.languages))
        lang, text, _conf = max(results, key=lambda r: r[2])
        if text:
            self.last_language = lang
        return text

    # --- Ausgabe ------------------------------------------------------------
    def synthesize(self, text: str) -> bytes:
        url = f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/v1"
        voice, pitch, rate, style = preset(self.voice_preset)
        if self.voice_override:
            voice = self.voice_override
        lang = voice[:5]
        body = escape(clean_for_speech(text))
        if pitch != "0%" or rate != "0%":
            body = f'<prosody pitch="{pitch}" rate="{rate}">{body}</prosody>'
        if style:
            body = f'<mstts:express-as style="{style}">{body}</mstts:express-as>'
        ssml = (
            f'<speak version="1.0" xmlns="http://www.w3.org/2001/10/synthesis" '
            f'xmlns:mstts="https://www.w3.org/2001/mstts" xml:lang="{lang}">'
            f'<voice name="{voice}">{body}</voice></speak>'
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
