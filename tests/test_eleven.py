"""ElevenLabs-Sprachausgabe ohne Netzwerk: Anfrageform, Fehlermeldungen, Rückfall auf Azure."""

import io
import wave
from types import SimpleNamespace

import pytest

from sprachassistent.speech import eleven
from sprachassistent.speech.eleven import ElevenLabsSpeech


class FakeResponse:
    def __init__(self, status=200, content=b"", data=None, text=""):
        self.status_code = status
        self.content = content
        self._data = data or {}
        self.text = text

    def json(self):
        return self._data


def test_synthesize_builds_request_and_wraps_pcm(monkeypatch):
    calls = {}
    pcm = (b"\x01\x00" * 1600)  # 0,1 s Ton

    def fake_request(method, url, headers=None, params=None, json=None, timeout=None):  # noqa: A002, ANN001
        calls.update(method=method, url=url, headers=headers, params=params, json=json)
        return FakeResponse(content=pcm)

    monkeypatch.setattr(eleven.requests, "request", fake_request)
    speech = ElevenLabsSpeech("sk_test", "voice-42", stability=0.3)
    wav = speech.synthesize("**Hallo** Martin")

    assert calls["method"] == "POST" and calls["url"].endswith("/text-to-speech/voice-42")
    assert calls["headers"]["xi-api-key"] == "sk_test"
    assert calls["params"]["output_format"] == "pcm_16000"
    assert calls["json"]["text"] == "Hallo Martin"  # Markdown entfernt
    assert calls["json"]["model_id"] == "eleven_multilingual_v2"
    assert calls["json"]["voice_settings"]["stability"] == 0.3
    with wave.open(io.BytesIO(wav)) as wf:
        assert wf.getframerate() == 16000 and wf.getnchannels() == 1 and wf.getnframes() == 1600


def test_error_codes_are_explained(monkeypatch):
    monkeypatch.setattr(eleven.requests, "request", lambda *a, **k: FakeResponse(401, text="unauthorized"))
    with pytest.raises(RuntimeError, match="Schlüssel ist ungültig"):
        ElevenLabsSpeech("falsch", "v1").synthesize("Test")

    monkeypatch.setattr(eleven.requests, "request", lambda *a, **k: FakeResponse(404, text="voice not found"))
    with pytest.raises(RuntimeError, match="Stimme gibt es"):
        ElevenLabsSpeech("k", "unbekannt").synthesize("Test")


def test_voices_are_listed_with_traits(monkeypatch):
    data = {"voices": [
        {"voice_id": "v1", "name": "Rachel", "labels": {"accent": "british", "age": "young"}},
        {"voice_id": "v2", "name": "Dunkler Lord", "labels": {}},
        {"name": "ohne id"},
    ]}
    monkeypatch.setattr(eleven.requests, "request", lambda *a, **k: FakeResponse(data=data))
    voices = ElevenLabsSpeech("k", "v1").voices()
    assert [v["id"] for v in voices] == ["v1", "v2"]
    assert "british" in voices[0]["name"] and voices[1]["name"] == "Dunkler Lord"


def test_not_configured_is_reported():
    with pytest.raises(RuntimeError, match="nicht vollständig eingerichtet"):
        ElevenLabsSpeech("k", "").synthesize("Test")


def test_speak_falls_back_to_azure_with_note(monkeypatch):
    from sprachassistent.assistant import Assistant

    assistant = object.__new__(Assistant)
    assistant.settings = SimpleNamespace(audio_output_device=None)
    assistant._stop_speaking = __import__("threading").Event()
    assistant.speech = SimpleNamespace(synthesize=lambda _t: b"AZURE")
    assistant.tts = SimpleNamespace(synthesize=lambda _t: (_ for _ in ()).throw(RuntimeError("HTTP 429 Kontingent")))
    played = []
    assistant._play_interruptible = lambda audio, device: played.append(audio)  # type: ignore[assignment]

    note = assistant.speak("Guten Morgen")
    assert played == [b"AZURE"] and "429" in note and "Azure-Stimme" in note


def test_network_failure_is_explained(monkeypatch):
    def boom(*_a, **_k):
        raise eleven.requests.RequestException("Verbindung abgelehnt")

    monkeypatch.setattr(eleven.requests, "request", boom)
    with pytest.raises(RuntimeError, match="nicht erreichbar"):
        ElevenLabsSpeech("k", "v1").synthesize("Test")
