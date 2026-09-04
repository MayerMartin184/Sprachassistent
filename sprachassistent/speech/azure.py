"""Spracherkennung und Sprachausgabe über die Azure-Speech-REST-API.

Bewusst ohne das native Azure-SDK: nur HTTP-Aufrufe, 16-kHz-Mono-PCM-WAV rein, WAV raus.
Grenze der REST-Erkennung: Aufnahmen bis 60 Sekunden.
"""

from __future__ import annotations

import re
from xml.sax.saxutils import escape

import requests

OUTPUT_FORMAT = "riff-16khz-16bit-mono-pcm"

# Stimmen-Palette: (Schlüssel, Anzeigename, Azure-Stimme, Tonhöhe, Tempo, Stil oder None, Effektkette)
# Mehrsprachige Stimmen ("Multilingual") sprechen Deutsch, Rumänisch und Englisch mit derselben Stimme.
# Die Effektkette (speech/effects.py) läuft lokal auf dem Ton und macht aus normalen Stimmen Filmcharaktere.
VOICE_PRESETS: list[tuple] = [
    # --- natürliche Stimmen ---
    ("seraphina", "Seraphina – weiblich, natürlich, mehrsprachig", "de-DE-SeraphinaMultilingualNeural", "0%", "0%", None, []),
    ("florian", "Florian – männlich, natürlich, mehrsprachig", "de-DE-FlorianMultilingualNeural", "0%", "0%", None, []),
    ("katja", "Katja – weiblich, klar", "de-DE-KatjaNeural", "0%", "0%", None, []),
    ("conrad", "Conrad – männlich, ruhig", "de-DE-ConradNeural", "0%", "0%", None, []),
    ("amala", "Amala – weiblich, warm", "de-DE-AmalaNeural", "0%", "0%", None, []),
    ("christoph", "Christoph – männlich, sachlich", "de-DE-ChristophNeural", "0%", "0%", None, []),
    ("louisa", "Louisa – weiblich, jung", "de-DE-LouisaNeural", "0%", "0%", None, []),
    ("killian", "Killian – männlich, jung", "de-DE-KillianNeural", "0%", "0%", None, []),
    ("tanja", "Tanja – weiblich, freundlich", "de-DE-TanjaNeural", "0%", "0%", None, []),
    ("ralf", "Ralf – männlich, kräftig", "de-DE-RalfNeural", "0%", "0%", None, []),
    ("alina_ro", "Alina – rumänisch, weiblich", "ro-RO-AlinaNeural", "0%", "0%", None, []),
    ("emil_ro", "Emil – rumänisch, männlich", "ro-RO-EmilNeural", "0%", "0%", None, []),
    ("ava_en", "Ava – englisch, weiblich, mehrsprachig", "en-US-AvaMultilingualNeural", "0%", "0%", None, []),
    ("andrew_en", "Andrew – englisch, männlich, mehrsprachig", "en-US-AndrewMultilingualNeural", "0%", "0%", None, []),
    # --- Filmcharaktere (Effektkette) ---
    ("bordcomputer", "★ Bordcomputer – ruhig, kalt, leicht metallisch (KI im Raumschiff)", "de-DE-FlorianMultilingualNeural", "-6%", "-10%", None,
     [("flanger", 0.3, 1.5, 0.35), ("reverb", 0.3, 0.18)]),
    ("maskenlord", "★ Dunkler Maskenlord – tief, atmend, bedrohlich", "de-DE-ConradNeural", "-28%", "-14%", None,
     [("layer", -12, 0.5), ("lowpass", 1900), ("distortion", 1.7), ("reverb", 0.4, 0.25)]),
    ("daemon", "★ Dämon – mehrere Kehlen, verzerrt, hallend", "de-DE-ConradNeural", "-35%", "-10%", None,
     [("layer", -12, 0.8), ("layer", -7, 0.45), ("layer", 4, 0.2), ("distortion", 3.0), ("reverb", 1.4, 0.45)]),
    ("monster", "★ Monster – gewaltig, knurrend, sehr tief", "de-DE-RalfNeural", "-42%", "-18%", None,
     [("layer", -12, 0.9), ("layer", -24, 0.4), ("distortion", 2.8), ("lowpass", 2400), ("reverb", 0.9, 0.35)]),
    ("hoehlentroll", "★ Höhlentroll – dumpf, langsam, riesig", "de-DE-RalfNeural", "-32%", "-26%", None,
     [("layer", -12, 0.7), ("lowpass", 1500), ("distortion", 1.5), ("reverb", 1.1, 0.4)]),
    ("kampfroboter", "★ Kampfroboter – hart, metallisch, abgehackt", "de-DE-ChristophNeural", "-5%", "+4%", None,
     [("ring_mod", 42, 0.9), ("bitcrush", 6, 1), ("distortion", 1.4), ("lowpass", 4200)]),
    ("cyborg", "★ Cyborg – halb Mensch, halb Maschine", "de-DE-FlorianMultilingualNeural", "-15%", "-6%", None,
     [("layer", -12, 0.35), ("ring_mod", 30, 0.35), ("flanger", 0.8, 2.0, 0.4), ("distortion", 1.3)]),
    ("alien", "★ Alien – fremdartig, schwebend", "de-DE-KillianNeural", "+8%", "-4%", None,
     [("ring_mod", 110, 0.7), ("flanger", 1.2, 4.0, 0.5), ("reverb", 0.6, 0.35)]),
    ("geist", "★ Geist – flüsternd, verhallt, unheimlich", "de-DE-AmalaNeural", "+4%", "-16%", None,
     [("layer", 7, 0.5), ("layer", -5, 0.3), ("flanger", 1.5, 5.0, 0.5), ("tremolo", 5.5, 0.4), ("reverb", 2.2, 0.6)]),
    ("riese", "★ Riese – donnernd, gutmütig, mit Halle", "de-DE-FlorianMultilingualNeural", "-26%", "-12%", None,
     [("layer", -12, 0.5), ("reverb", 2.6, 0.55)]),
    ("zauberer", "★ Alter Zauberer – weise, getragen, Echo", "de-DE-ConradNeural", "-10%", "-16%", None,
     [("reverb", 1.0, 0.35)]),
    ("nachtheld", "★ Maskierter Nachtheld – heiseres Knurren", "de-DE-ChristophNeural", "-30%", "-8%", None,
     [("distortion", 2.4), ("lowpass", 2100), ("highpass", 120)]),
    ("hexe", "★ Hexe – hoch, krächzend, kichernd", "de-DE-ElkeNeural", "+38%", "-6%", None,
     [("layer", 12, 0.3), ("distortion", 1.4), ("tremolo", 7, 0.25), ("reverb", 0.5, 0.25)]),
    ("funker", "★ Funker / Pilot – Funkgerät mit Rauschen", "de-DE-KatjaNeural", "0%", "+4%", None,
     [("highpass", 350), ("lowpass", 3000), ("distortion", 2.2), ("noise", 0.012)]),
    ("achtbit", "★ 8-Bit-Roboter – Spielautomat", "de-DE-ChristophNeural", "+10%", "+6%", None,
     [("bitcrush", 4, 2), ("lowpass", 3500)]),
    ("kind", "★ Kind – hoch und flink", "de-DE-LouisaNeural", "+35%", "+10%", None, []),
    ("chipmunk", "★ Streifenhörnchen – sehr hoch, schnell", "de-DE-LouisaNeural", "+48%", "+18%", None, [("layer", 12, 0.4)]),
    ("erzaehler", "★ Erzähler – tief und getragen", "de-DE-ConradNeural", "-12%", "-12%", None, [("reverb", 0.5, 0.2)]),
    ("ansagerin", "★ Ansagerin – schnell und präzise", "de-DE-KatjaNeural", "+4%", "+18%", None, []),
]


# Ersatz, falls eine Stimme in der Azure-Region nicht verfügbar ist (gleiches Geschlecht, gleiche Sprache)
VOICE_FALLBACKS = {
    "de-DE-FlorianMultilingualNeural": "de-DE-ConradNeural",
    "de-DE-SeraphinaMultilingualNeural": "de-DE-KatjaNeural",
    "en-US-AndrewMultilingualNeural": "en-US-GuyNeural",
    "en-US-AvaMultilingualNeural": "en-US-JennyNeural",
    "de-DE-ElkeNeural": "de-DE-KatjaNeural",
    "de-DE-KillianNeural": "de-DE-ConradNeural",
    "de-DE-LouisaNeural": "de-DE-AmalaNeural",
    "de-DE-TanjaNeural": "de-DE-KatjaNeural",
    "de-DE-RalfNeural": "de-DE-ConradNeural",
    "de-DE-ChristophNeural": "de-DE-ConradNeural",
    "de-DE-AmalaNeural": "de-DE-KatjaNeural",
}


def preset(key: str) -> tuple[str, str, str, str | None, list]:
    """Liefert (Stimme, Tonhöhe, Tempo, Stil, Effektkette) zu einem Palettenschlüssel; unbekannt -> Seraphina."""
    for k, _name, voice, pitch, rate, style, fx in VOICE_PRESETS:
        if k == key:
            return voice, pitch, rate, style, fx
    return VOICE_PRESETS[0][2:7]


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
        self._voices: set[str] | None = None  # in der Region verfügbare Stimmen (einmal abgefragt)

    def available_voices(self) -> set[str]:
        """Stimmen, die es in dieser Azure-Region gibt. Leer, wenn die Abfrage scheitert (dann keine Prüfung)."""
        if self._voices is None:
            try:
                resp = requests.get(
                    f"https://{self.region}.tts.speech.microsoft.com/cognitiveservices/voices/list",
                    headers={"Ocp-Apim-Subscription-Key": self.key},
                    timeout=20,
                )
                resp.raise_for_status()
                self._voices = {v["ShortName"] for v in resp.json()}
            except Exception:  # noqa: BLE001
                self._voices = set()
        return self._voices

    def resolve_voice(self, voice: str) -> tuple[str, bool]:
        """(tatsächlich genutzte Stimme, war Ersatz nötig)."""
        voices = self.available_voices()
        if not voices or voice in voices:
            return voice, False
        fallback = VOICE_FALLBACKS.get(voice)
        if fallback and fallback in voices:
            return fallback, True
        # letzte Rettung: irgendeine Stimme derselben Sprache und Endung "Neural"
        same_lang = sorted(v for v in voices if v.startswith(voice[:5]))
        return (same_lang[0] if same_lang else voice), True

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
        voice, pitch, rate, style, fx = preset(self.voice_preset)
        if self.voice_override:
            voice = self.voice_override
        voice, _ = self.resolve_voice(voice)
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
        if fx:
            from .effects import process_wav

            return process_wav(resp.content, fx)
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
