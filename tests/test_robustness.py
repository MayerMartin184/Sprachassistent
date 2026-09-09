"""Verhalten bei Störungen: Mikrofon-Neustart, Dazwischenreden, Nachfrage-Fenster ohne Wake-Word."""

import threading
from types import SimpleNamespace

from sprachassistent.agent.agent import Agent
from sprachassistent.assistant import Assistant
from sprachassistent.audio.wakeword import WakeWordListener
from sprachassistent.config import Settings
from sprachassistent.tools.base import ToolRegistry


class _FastStop(threading.Event):
    """Wartezeiten im Test überspringen."""

    def wait(self, timeout=None):  # noqa: ANN001
        return super().wait(0)


def test_microphone_session_restarts_after_device_error(monkeypatch):
    import sys
    import types

    monkeypatch.setitem(sys.modules, "sounddevice", types.ModuleType("sounddevice"))  # keine Audio-Hardware im Test
    states: list[str] = []
    listener = WakeWordListener(on_utterance=lambda _w: None, on_state=states.append)
    listener._stop = _FastStop()
    listener._load_models = lambda: (None, None)  # type: ignore[assignment]
    attempts: list[int] = []

    def session(*_args):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("Gerät nicht verfügbar")
        listener._stop.set()

    listener._session = session  # type: ignore[assignment]
    listener._run()
    assert len(attempts) == 3 and listener.restarts == 2
    assert [s for s in states if s.startswith("restart:")]


def test_microphone_health_reports_silence():
    listener = WakeWordListener(on_utterance=lambda _w: None, on_state=lambda _s: None)
    assert listener.health() == (True, 0.0)  # noch nie gelaufen
    listener.last_frame_at = 1.0  # lange her
    healthy, idle = listener.health()
    assert not healthy and idle > 10
    listener.pause()
    assert listener.health()[0]  # pausiert ist in Ordnung


def _assistant_with(reply: str) -> Assistant:
    assistant = object.__new__(Assistant)
    assistant.agent = SimpleNamespace(run=lambda _t: reply, drop_last_exchange=lambda: dropped.append(1))
    return assistant


dropped: list[int] = []


def test_unaddressed_speech_is_ignored():
    dropped.clear()
    assistant = _assistant_with("IGNORE")
    assert assistant.handle_text("… und dann sagte er zu mir", addressed=False) == ""
    assert dropped == [1]  # Verlauf bleibt sauber


def test_unaddressed_speech_still_answers_when_meant():
    dropped.clear()
    assistant = _assistant_with("Klar, ich lege das an.")
    assert assistant.handle_text("leg das bitte als Aufgabe an", addressed=False).startswith("Klar")
    assert dropped == []


def test_addressed_speech_is_passed_through_unchanged():
    seen: list[str] = []
    assistant = object.__new__(Assistant)
    assistant.agent = SimpleNamespace(run=lambda t: seen.append(t) or "ok")
    assert assistant.handle_text("Wie spät ist es?") == "ok"
    assert seen == ["Wie spät ist es?"]  # ohne Zusatzhinweis


def test_agent_drops_last_exchange():
    agent = Agent(Settings(_env_file=None), ToolRegistry(), client=SimpleNamespace(messages=None))
    agent.history = [
        {"role": "user", "content": "erste Frage"},
        {"role": "assistant", "content": "erste Antwort"},
        {"role": "user", "content": "Nebengespräch"},
        {"role": "assistant", "content": "IGNORE"},
    ]
    agent.drop_last_exchange()
    assert [m["content"] for m in agent.history] == ["erste Frage", "erste Antwort"]
