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


def _agent() -> Agent:
    return Agent(Settings(_env_file=None), ToolRegistry(), client=SimpleNamespace(messages=None))


def _tool_turn() -> list[dict]:
    """Eine Runde mit Werkzeugaufruf: Frage, tool_use, tool_result, Antwort."""
    return [
        {"role": "user", "content": "such mir was"},
        {"role": "assistant", "content": [SimpleNamespace(type="tool_use", id="t1", name="x", input={})]},
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
        {"role": "assistant", "content": [SimpleNamespace(type="text", text="gefunden")]},
    ]


def test_drop_last_exchange_removes_whole_tool_round():
    agent = _agent()
    agent.history = [{"role": "user", "content": "erste"}, {"role": "assistant", "content": "antwort"}] + _tool_turn()
    agent.drop_last_exchange()
    assert [m["content"] for m in agent.history] == ["erste", "antwort"]
    assert not agent._incomplete()  # Verlauf bleibt sendbar


def test_repair_history_cuts_dangling_tool_use():
    agent = _agent()
    agent.history = [
        {"role": "user", "content": "erste"},
        {"role": "assistant", "content": "antwort"},
        {"role": "user", "content": "zweite"},
        {"role": "assistant", "content": [SimpleNamespace(type="tool_use", id="t1", name="x", input={})]},
    ]
    assert agent._incomplete() and agent.repair_history()
    assert [m["content"] for m in agent.history] == ["erste", "antwort"]
    assert not agent.repair_history()  # nichts mehr zu tun


def test_repair_history_handles_trailing_tool_result():
    agent = _agent()
    agent.history = _tool_turn()[:3]  # Antwort fehlt
    assert agent.repair_history() and agent.history == []


def test_ignored_utterance_after_tool_use_keeps_history_sendable():
    """Der Fehler 400: eine verworfene Runde mit Werkzeugaufruf hinterließ einen offenen tool_use."""
    agent = _agent()
    agent.history = [{"role": "user", "content": "erste"}, {"role": "assistant", "content": "antwort"}] + _tool_turn()
    agent.history[-1] = {"role": "assistant", "content": [SimpleNamespace(type="text", text="IGNORE")]}
    agent.drop_last_exchange()
    assert not agent._incomplete()
    assert all(agent._block_type(b) != "tool_use" for m in agent.history if isinstance(m["content"], list) for b in m["content"])


def test_attention_window_only_after_a_question():
    from sprachassistent.webapp import Api

    assert Api._expects_answer("Bis wann soll ich das einplanen?")
    assert not Api._expects_answer("Ich habe die Aufgabe angelegt.")
    assert not Api._expects_answer("Erledigt. Sag Bescheid, wenn noch etwas fehlt.")


def test_recognition_prefers_primary_language_unless_clearly_better():
    from sprachassistent.speech.azure import AzureSpeech

    speech = AzureSpeech("k", "r", languages=["de-DE", "ro-RO"])
    results = {"de-DE": ("Wir müssen das machen", 0.82), "ro-RO": ("Vrem sa facem", 0.80)}
    speech._recognize = lambda _w, lang: results[lang]  # type: ignore[assignment]
    assert speech.transcribe(b"x") == "Wir müssen das machen"  # knapper Vorsprung zählt nicht

    results["ro-RO"] = ("Trebuie sa facem asta maine", 0.97)
    assert speech.transcribe(b"x") == "Trebuie sa facem asta maine"  # deutlich besser gewinnt
    assert speech.last_language == "ro-RO"

    results["de-DE"] = ("", 0.0)  # Deutsch versteht nichts
    results["ro-RO"] = ("Buna ziua", 0.4)
    assert speech.transcribe(b"x") == "Buna ziua"


def test_activity_labels_are_plain_german():
    from sprachassistent.agent.agent import activity

    assert activity("web_search") == "Suche im Web"
    assert activity("planner_add_task") == "Arbeite an den Team-Aufgaben"
    assert activity("files_search") == "Durchsuche deine Dateien"
    assert activity("irgendwas_neues").startswith("Führe")
