"""Werkzeugschleife des Agenten mit einem Fake-Client (keine API-Aufrufe)."""

from types import SimpleNamespace

from sprachassistent.agent.agent import Agent
from sprachassistent.config import Settings
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
        return self.responses.pop(0)


def _agent(responses, registry):
    client = SimpleNamespace(messages=FakeMessages(responses))
    settings = Settings(_env_file=None, max_tool_rounds=5, assistant_effort="medium")
    agent = Agent(settings, registry, client=client)
    return agent, client.messages


def test_tool_round_trip_and_history():
    reg = ToolRegistry()
    reg.register(Tool("add", "addiert", schema({"a": {"type": "integer"}, "b": {"type": "integer"}}, ["a", "b"]), lambda a, b: str(a + b)))
    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[_text("Ich rechne."), _tool_use("t1", "add", {"a": 2, "b": 3})]),
        SimpleNamespace(stop_reason="end_turn", content=[_text("Das Ergebnis ist 5.")]),
    ]
    agent, fake = _agent(responses, reg)
    assert agent.run("Was ist 2 plus 3?") == "Das Ergebnis ist 5."
    assert len(fake.calls) == 2
    second = fake.calls[1]["messages"]
    assert second[-1] == {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "5"}]}
    assert fake.calls[0]["output_config"] == {"effort": "medium"}
    assert any(t.get("type", "").startswith("web_search") for t in fake.calls[0]["tools"])
    assert fake.calls[0]["system"][0]["cache_control"] == {"type": "ephemeral"}
    # Verlauf: user, assistant(tool_use), user(result), assistant(final)
    assert [m["role"] for m in agent.history] == ["user", "assistant", "user", "assistant"]


def test_tool_error_is_flagged():
    reg = ToolRegistry()
    reg.register(Tool("fail", "scheitert", schema({}), lambda: (_ for _ in ()).throw(RuntimeError("kaputt"))))
    responses = [
        SimpleNamespace(stop_reason="tool_use", content=[_tool_use("t1", "fail", {})]),
        SimpleNamespace(stop_reason="end_turn", content=[_text("Leider ging das nicht.")]),
    ]
    agent, fake = _agent(responses, reg)
    agent.run("mach")
    result = fake.calls[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "kaputt" in result["content"]


def test_pause_turn_resends_and_round_limit():
    reg = ToolRegistry()
    responses = [
        SimpleNamespace(stop_reason="pause_turn", content=[SimpleNamespace(type="server_tool_use", id="s1", name="web_search", input={})]),
        SimpleNamespace(stop_reason="end_turn", content=[_text("Fertig.")]),
    ]
    agent, fake = _agent(responses, reg)
    assert agent.run("suche") == "Fertig."
    assert fake.calls[1]["messages"][-1]["role"] == "assistant"

    endless = [SimpleNamespace(stop_reason="tool_use", content=[_tool_use(f"t{i}", "x", {})]) for i in range(5)]
    reg.register(Tool("x", "nix", schema({}), lambda: "ok"))
    agent, _ = _agent(endless, reg)
    assert "abgebrochen" in agent.run("endlos").lower()
