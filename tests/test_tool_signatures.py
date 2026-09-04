"""Jeder Schema-Parameter muss vom Handler akzeptiert werden, jeder Pflichtparameter existieren."""

import inspect

from sprachassistent.tools import files, lists, m365, tasks


def _check(tools):
    for tool in tools:
        sig = inspect.signature(tool.handler)
        params = sig.parameters
        accepts_kwargs = any(p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values())
        for name in tool.input_schema["properties"]:
            assert accepts_kwargs or name in params, f"{tool.name}: Handler kennt '{name}' nicht"
        for name, p in params.items():
            if p.default is inspect.Parameter.empty and p.kind is not inspect.Parameter.VAR_KEYWORD:
                assert name in tool.input_schema["required"], f"{tool.name}: '{name}' ist nicht required"


def test_local_tool_signatures(tmp_path):
    _check(tasks.build_tools(tasks.TaskManager(tmp_path)))
    _check(lists.build_tools(lists.ListManager(tmp_path)))
    _check(files.build_tools(files.FileManager({"Dokumente": tmp_path})))
    from sprachassistent.tools import computer, memory, reminders
    _check(computer.build_tools())
    _check(memory.build_tools(memory.Memory(tmp_path)))
    _check(reminders.build_tools(reminders.Reminders(tmp_path, "Europe/Berlin")))


def test_m365_tool_signatures():
    dummy = m365.M365Tools(graph=None, confirm=lambda _m: False, timezone="Europe/Berlin")
    _check(m365.build_tools(dummy))


def test_html_to_text():
    html = "<html><style>x{}</style><body><p>Hallo <b>Welt</b></p><div>Zeile 2</div></body></html>"
    assert m365.html_to_text(html) == "Hallo Welt\nZeile 2"


def test_webcam_tool_signature():
    from sprachassistent.tools import webcam

    _check(webcam.build_tools(0))


def test_registry_passes_content_blocks_through():
    from sprachassistent.tools.base import Tool, ToolRegistry, schema

    blocks = [{"type": "text", "text": "hi"}]
    reg = ToolRegistry()
    reg.register(Tool("img", "liefert Blöcke", schema({}), lambda: blocks))
    assert reg.execute("img", {}) == (blocks, False)
