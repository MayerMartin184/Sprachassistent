"""Rollen, Verteilung, parallele Werkzeuge, Verlaufskürzung, Verbrauchsprotokoll – ohne API-Aufrufe."""

import json
import threading
import time
from types import SimpleNamespace

from sprachassistent.agent import roles as roles_mod
from sprachassistent.agent.agent import Agent, request_extras, server_tools
from sprachassistent.agent.roles import DELEGATES, ROLES, RoleRunner
from sprachassistent.agent.router import Router, rule_matches
from sprachassistent.assistant import Assistant
from sprachassistent.config import Settings
from sprachassistent.tools import verbrauch
from sprachassistent.tools.base import Tool, ToolRegistry, schema


def _text(t):
    return SimpleNamespace(type="text", text=t)


def _tool_use(id_, name, inp):
    return SimpleNamespace(type="tool_use", id=id_, name=name, input=inp)


class FakeMessages:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        response = self.responses.pop(0)
        return response(kwargs) if callable(response) else response


def _settings(tmp_path, **kw):
    return Settings(_env_file=None, data_dir=tmp_path, max_tool_rounds=5, **kw)


def _full_registry():
    reg = ToolRegistry()
    for name in ["mail_list", "mail_send", "calendar_events", "todo_add", "files_list", "files_read", "files_write",
                 "files_delete", "create_docx", "memory_save", "memory_search", "reminder_set", "list_show",
                 "screen_capture", "webcam_capture", "verbrauch_heute"]:
        reg.register(Tool(name, name, schema({}), lambda: "ok"))
    return reg


# --- Verteilung ---------------------------------------------------------------
def test_router_rules_pick_single_role():
    assert rule_matches("Wo steht 2510_07 und was fehlt für LP3?") == ["projekt"]
    assert Router().route("Wie viele Steckdosen je Raum nach DIN 18015?") == "wissen"
    assert Router().route("Antworte Schmidt, dass Dienstag passt") == "buero"
    assert Router().route("Such das Angebot Popescu im NAS") == "dateien"
    assert Router().route("Recherchiere Anbieter für PV-Speicher") == "recherche"
    assert Router().route("Geht das auch ohne EVU-Schreiben?") == "pruefer"


def test_router_leaves_short_and_unmatched_to_dialog():
    assert Router().route("ja") is None
    assert Router().route("mach das") is None
    assert Router().route("Wie spät ist es?") is None
    assert Router().route("Merk dir, dass ich lieber morgens arbeite.") is None


def test_router_asks_classifier_only_when_ambiguous():
    asked = []

    def classify(text, candidates):
        asked.append(candidates)
        return "projekt"

    router = Router(classify)
    assert router.route("Leg eine Aufgabe fürs Projekt 2510_07 an") == "projekt"
    assert asked == [["projekt", "buero"]]
    # Klassifikator außerhalb der Kandidaten -> Dialog entscheidet
    assert Router(lambda t, c: "wissen").route("Leg eine Aufgabe fürs Projekt 2510_07 an") is None
    assert Router().route("Leg eine Aufgabe fürs Projekt 2510_07 an") is None


# --- Rollen und Werkzeuglisten ----------------------------------------------------
def test_roles_get_only_their_tools(tmp_path):
    runner = RoleRunner(_settings(tmp_path), _full_registry(), client=SimpleNamespace(messages=None))
    assert set(runner.registry_for("buero").names) == {"mail_list", "mail_send", "calendar_events", "todo_add"}
    assert set(runner.registry_for("wissen").names) == {"files_list", "files_read", "memory_search"}
    assert runner.registry_for("pruefer").names == []
    assert "files_write" in runner.registry_for("projekt").names and "mail_send" not in runner.registry_for("projekt").names
    assert set(runner.registry_for("dialog").names) == {"memory_save", "memory_search", "reminder_set", "list_show",
                                                        "screen_capture", "webcam_capture", "verbrauch_heute"}
    assert runner.model_for("wissen") == "claude-haiku-5-5"
    assert runner.model_for("pruefer") == "claude-opus-5-5"
    assert runner.model_for("buero") == "claude-sonnet-5-5"


def test_role_agent_has_no_history_small_toolset_and_own_cache(tmp_path):
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("Stand: LP3. Quelle: PROJEKT.md")])])
    runner = RoleRunner(_settings(tmp_path), _full_registry(), client=SimpleNamespace(messages=fake))
    answer = runner.run("projekt", "Stand 2510_07", kontext="Nutzer: Hallo")
    assert answer.startswith("Stand: LP3")
    call = fake.calls[0]
    assert call["model"] == "claude-sonnet-5-5" and call["output_config"] == {"effort": "medium"}
    assert not any(t.get("type", "").startswith("web_search") for t in call["tools"])  # Projekt ohne Websuche
    assert len(call["system"]) == 1 and "Projekt-Agent" in call["system"][0]["text"]
    assert "Zusammenhang aus dem Gespräch" in call["messages"][0]["content"][1]["text"]


def test_ask_agent_tool_delegates_and_knows_parallel_safety(tmp_path):
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("DIN 18015: 3 Steckdosen.")])])
    runner = RoleRunner(_settings(tmp_path), _full_registry(), client=SimpleNamespace(messages=fake))
    tool = runner.ask_tool(lambda: "Nutzer: vorher")
    assert tool.handler(agent="wissen", auftrag="Steckdosen je Raum") == "DIN 18015: 3 Steckdosen."
    assert fake.calls[0]["model"] == "claude-haiku-5-5"
    assert tool.is_parallel_safe({"agent": "wissen"}) and tool.is_parallel_safe({"agent": "pruefer"})
    assert not tool.is_parallel_safe({"agent": "buero"}) and not tool.is_parallel_safe({"agent": "unbekannt"})
    assert "Unbekannter Agent" in tool.handler(agent="chef", auftrag="x")
    assert set(DELEGATES) <= set(ROLES)


# --- Parallele Werkzeuge ------------------------------------------------------------
def _slow_tool(name, parallel_safe=None):
    def handler():
        time.sleep(0.15)
        return name

    return Tool(name, name, schema({}), handler, parallel_safe=parallel_safe)


def test_read_only_tools_run_concurrently(tmp_path):
    reg = ToolRegistry()
    reg.register_all([_slow_tool("files_list"), _slow_tool("mail_search"), _slow_tool("files_write")])
    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[_tool_use("a", "files_list", {}), _tool_use("b", "mail_search", {})]),
        SimpleNamespace(stop_reason="end_turn", content=[_text("ok")]),
        SimpleNamespace(stop_reason="tool_use", content=[_tool_use("c", "files_list", {}), _tool_use("d", "files_write", {})]),
        SimpleNamespace(stop_reason="end_turn", content=[_text("ok")]),
    ]
    fake = FakeMessages(responses)
    agent = Agent(_settings(tmp_path), reg, client=SimpleNamespace(messages=fake))
    start = time.monotonic()
    agent.run("lies")
    assert time.monotonic() - start < 0.27  # zwei lesende Werkzeuge gleichzeitig
    results = fake.calls[1]["messages"][-1]["content"]
    assert [r["tool_use_id"] for r in results] == ["a", "b"] and [r["content"] for r in results] == ["files_list", "mail_search"]
    start = time.monotonic()
    agent.run("schreib")
    assert time.monotonic() - start >= 0.3  # schreibendes Werkzeug dabei: nacheinander


# --- Verlauf: eingefrorener System-Text, Zusammenfassung, Tagebuch --------------------------------
def test_system_block_is_frozen_per_conversation(tmp_path):
    memory = ["Gedächtnis: A"]
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("1")]),
                         SimpleNamespace(stop_reason="end_turn", content=[_text("2")])])
    agent = Agent(_settings(tmp_path), ToolRegistry(), client=SimpleNamespace(messages=fake), memory_summary=lambda: memory[0])
    agent.run("eins")
    memory[0] = "Gedächtnis: B"  # memory_save mitten im Gespräch
    agent.run("zwei")
    assert fake.calls[0]["system"] == fake.calls[1]["system"]
    assert fake.calls[1]["system"][1]["text"] == "Gedächtnis: A" and fake.calls[1]["system"][1]["cache_control"]["ttl"] == "1h"
    assert "Aktuell:" not in json.dumps(fake.calls[1]["system"])  # Datum steht in der Nutzeräußerung


def test_long_or_idle_history_is_summarized_into_diary(tmp_path):
    diary = []
    summary_calls = []

    def summarizer(kwargs):
        summary_calls.append(kwargs)
        return SimpleNamespace(stop_reason="end_turn", content=[_text("Nutzer fragte nach 2510_07; Brandschutz offen.")])

    fake = FakeMessages([
        SimpleNamespace(stop_reason="end_turn", content=[_text("Antwort eins " * 2000)]),
        summarizer,
        SimpleNamespace(stop_reason="end_turn", content=[_text("Antwort zwei")]),
    ])
    settings = _settings(tmp_path, history_compact_tokens=3000)
    agent = Agent(settings, ToolRegistry(), client=SimpleNamespace(messages=fake), on_compact=diary.append)
    agent.run("Wo steht 2510_07?")
    assert agent.estimated_tokens() > 3000
    agent.run("Und jetzt?")
    assert summary_calls and summary_calls[0]["model"] == "claude-haiku-5-5" and "tools" not in summary_calls[0]
    assert "2510_07" in summary_calls[0]["messages"][0]["content"]
    assert diary == ["Nutzer fragte nach 2510_07; Brandschutz offen."]
    messages = fake.calls[-1]["messages"]
    assert messages[0]["content"][0]["text"].startswith("[Zusammenfassung der bisherigen Unterhaltung")
    assert messages[1] == {"role": "assistant", "content": [{"type": "text", "text": "Verstanden."}]}
    assert messages[2]["content"][1]["text"] == "Und jetzt?" and len(messages) == 3

    # Pause: ebenfalls zusammenfassen
    fake.responses += [summarizer, SimpleNamespace(stop_reason="end_turn", content=[_text("drei")])]
    agent._last_run -= settings.history_idle_minutes * 60 + 1
    agent.run("Weiter")
    assert len(summary_calls) == 2 and len(fake.calls[-1]["messages"]) == 3


def test_flush_writes_diary_and_summary_failure_is_harmless(tmp_path):
    diary = []
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("ok")]),
                         lambda kw: (_ for _ in ()).throw(RuntimeError("API weg"))])
    agent = Agent(_settings(tmp_path), ToolRegistry(), client=SimpleNamespace(messages=fake), on_compact=diary.append)
    agent.run("hallo")
    agent.flush()
    assert diary == [] and agent.history == []  # keine Zusammenfassung, aber sauberer Neustart


def test_note_exchange_and_recent_context(tmp_path):
    agent = Agent(_settings(tmp_path), ToolRegistry(), client=SimpleNamespace(messages=None))
    agent.note_exchange("Wo steht Am Bungert?", "LP3, Brandschutz fehlt.")
    assert [m["role"] for m in agent.history] == ["user", "assistant"]
    assert agent.recent_context() == "Nutzer: Wo steht Am Bungert?\nAssistent: LP3, Brandschutz fehlt."


def test_memory_diary_roundtrip(tmp_path):
    from sprachassistent.tools.memory import Memory

    m = Memory(tmp_path)
    assert m.tagebuch_recent() == ""
    path = m.tagebuch("Erste Zusammenfassung.")
    m.tagebuch("Zweite Zusammenfassung.")
    assert path.read_text(encoding="utf-8").count("## ") == 2
    assert "Zweite Zusammenfassung." in m.summary() and "Tagebuch" in m.summary()


# --- Assistant: direkte Verteilung -----------------------------------------------------
def test_assistant_dispatches_clear_requests_directly_to_role():
    seen = []
    assistant = object.__new__(Assistant)
    assistant.router = Router()
    assistant.runner = SimpleNamespace(run=lambda role, text, kontext="": seen.append((role, text, kontext)) or "Stand LP3.")
    assistant.agent = SimpleNamespace(run=lambda t: "dialog", recent_context=lambda: "Nutzer: hi",
                                      note_exchange=lambda t, a: seen.append(("note", t, a)))
    assert assistant.handle_text("Wo steht 2510_07?") == "Stand LP3."
    assert seen == [("projekt", "Wo steht 2510_07?", "Nutzer: hi"), ("note", "Wo steht 2510_07?", "Stand LP3.")]
    assert assistant.handle_text("danke") == "dialog"


def test_handle_event_uses_background_role_with_image():
    seen = []
    assistant = object.__new__(Assistant)
    assistant.runner = SimpleNamespace(run=lambda role, text, content=None: seen.append((role, content)) or "Hallo zurück!")
    assert assistant.handle_event("Nutzer ist zurück.", jpeg=b"\xff\xd8") == "Hallo zurück!"
    role, content = seen[0]
    assert role == "hintergrund" and content[0]["type"] == "image" and "Systemereignis" in content[1]["text"]


# --- Modelle und Verbrauch ------------------------------------------------------------------
def test_current_models_get_effort_and_new_web_tools():
    for model in ("claude-sonnet-5-5", "claude-haiku-5-5", "claude-opus-5-5"):
        assert request_extras(model, "low") == {"output_config": {"effort": "low"}}
        assert server_tools(model)[0]["type"] == "web_search_20260209"
    assert Settings(_env_file=None).assistant_model == "claude-sonnet-5-5"
    assert Settings(_env_file=None).ambient_model_effective == "claude-haiku-5-5"


def test_usage_is_logged_and_reported(tmp_path):
    usage = SimpleNamespace(input_tokens=1000, cache_read_input_tokens=9000, cache_creation_input_tokens=0, output_tokens=200)
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("ok")], usage=usage)])
    agent = Agent(_settings(tmp_path), ToolRegistry(), client=SimpleNamespace(messages=fake), label="dialog")
    agent.run("hi")
    path = tmp_path / "verbrauch.jsonl"
    record = json.loads(path.read_text(encoding="utf-8").splitlines()[0])
    assert record["rolle"] == "dialog" and record["modell"] == "claude-sonnet-5-5" and record["cache_lesen"] == 9000
    text = verbrauch.report(path)
    assert "dialog (claude-sonnet-5-5): 1 Aufrufe" in text and "90 % aus dem Cache" in text and "USD" in text
    assert verbrauch.report(tmp_path / "fehlt.jsonl").startswith("Noch kein")


def test_registry_subset_and_parallel_heuristic():
    reg = _full_registry()
    assert reg.subset(["mail_*", "todo_add"]).names == ["mail_list", "mail_send", "todo_add"]
    assert reg.parallel_safe("mail_list", {}) and reg.parallel_safe("files_read", {})
    assert not reg.parallel_safe("mail_send", {}) and not reg.parallel_safe("files_write", {}) and not reg.parallel_safe("nix", {})
    assert roles_mod.matches(ROLES["dialog"], "webcam_capture") and not roles_mod.matches(ROLES["dialog"], "mail_send")


def test_thread_safety_of_agent_lock(tmp_path):
    """Zwei Aufrufe gleichzeitig dürfen den Verlauf nicht vermischen."""
    fake = FakeMessages([SimpleNamespace(stop_reason="end_turn", content=[_text("a")]),
                         SimpleNamespace(stop_reason="end_turn", content=[_text("b")])])
    agent = Agent(_settings(tmp_path), ToolRegistry(), client=SimpleNamespace(messages=fake))
    threads = [threading.Thread(target=agent.run, args=(t,)) for t in ("eins", "zwei")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert [m["role"] for m in agent.history] == ["user", "assistant", "user", "assistant"]
