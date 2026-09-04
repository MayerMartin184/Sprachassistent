import time
from types import SimpleNamespace

from sprachassistent import ambient as amb
from sprachassistent.config import Settings


class FakeAgent:
    calls = []

    def __init__(self, reply):
        self.reply = reply

    def run(self, content):
        FakeAgent.calls.append(content)
        return self.reply


def _recorder(tmp_path, monkeypatch, reply="Angelegt: To-Do „Angebot Popescu bis Dienstag“."):
    settings = Settings(_env_file=None, data_dir=tmp_path, ambient_extract_minutes=0)
    assistant = SimpleNamespace(transcribe=lambda wavs: "wir schicken Popescu das Angebot bis Dienstag", registry=None, memory=None)
    notes = []
    rec = amb.AmbientRecorder(settings, assistant, notify=lambda who, text: notes.append((who, text)))
    monkeypatch.setattr(rec, "_agent", lambda prompt: FakeAgent(reply))
    return rec, notes


def test_disabled_recorder_ignores_audio(tmp_path, monkeypatch):
    rec, notes = _recorder(tmp_path, monkeypatch)
    rec.submit([b"wav"])
    time.sleep(0.3)
    assert not rec.today_file().exists() and notes == []


def test_enabled_recorder_writes_transcript_and_extracts(tmp_path, monkeypatch):
    rec, notes = _recorder(tmp_path, monkeypatch)
    rec.enabled = True
    rec.submit([b"wav"])
    deadline = time.time() + 3
    while not rec.today_file().exists() and time.time() < deadline:
        time.sleep(0.05)
    assert "Popescu" in rec.today_file().read_text(encoding="utf-8")
    rec._maybe_extract()
    assert notes and notes[-1][0] == "Mithören" and "Angebot" in notes[-1][1]
    assert "Popescu" in FakeAgent.calls[-1]
    assert "Popescu" in rec.transcript_today()


def test_nothing_new_is_silent(tmp_path, monkeypatch):
    rec, notes = _recorder(tmp_path, monkeypatch, reply="Nichts Neues.")
    rec.enabled = True
    rec.submit([b"wav"])
    deadline = time.time() + 3
    while not rec._buffer and time.time() < deadline:
        time.sleep(0.05)
    rec._maybe_extract()
    assert notes == []
