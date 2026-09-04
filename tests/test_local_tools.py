import pytest

from sprachassistent.tools.base import Tool, ToolRegistry, schema
from sprachassistent.tools.files import FileManager
from sprachassistent.tools.lists import ListManager
from sprachassistent.tools.tasks import TaskManager


def test_registry_executes_and_reports_errors():
    reg = ToolRegistry()
    reg.register(Tool("echo", "gibt zurück", schema({"x": {"type": "string"}}, ["x"]), lambda x: x.upper()))
    reg.register(Tool("boom", "wirft", schema({}), lambda: 1 / 0))
    assert reg.execute("echo", {"x": "hi"}) == ("HI", False)
    assert reg.execute("boom", {})[1] is True
    assert reg.execute("nope", {})[1] is True
    assert reg.execute("echo", {"y": 1})[1] is True  # falsche Parameter
    assert [d["name"] for d in reg.definitions()] == ["echo", "boom"]


def test_tasks_roundtrip(tmp_path):
    tm = TaskManager(tmp_path)
    a = tm.add("Steuer", due="2026-09-30", priority="hoch")
    b = tm.add("Einkaufen")
    assert [t["id"] for t in tm.list()] == [a["id"], b["id"]]
    tm.update(a["id"], done=True)
    assert [t["id"] for t in tm.list()] == [b["id"]]
    assert len(tm.list(include_done=True)) == 2
    assert tm.update(b["id"], delete=True) is None
    assert tm.list(include_done=True) == [a | {"done": True}]
    with pytest.raises(KeyError):
        tm.update(999, done=True)
    with pytest.raises(ValueError):
        tm.add("x", due="30.09.2026")


def test_lists_dedupe_and_remove(tmp_path):
    lm = ListManager(tmp_path)
    assert lm.add("Einkauf", ["Milch", "Brot", "milch "]) == ["Milch", "Brot"]
    assert lm.get("einkauf")["items"] == ["Milch", "Brot"]
    assert lm.remove("Einkauf", ["brot"])["items"] == ["Milch"]
    assert lm.remove("Einkauf") is None
    assert lm.overview() == []
    with pytest.raises(KeyError):
        lm.remove("gibtsnicht")


def test_files_sandbox_and_operations(tmp_path):
    root = tmp_path / "docs"
    fm = FileManager(root)
    fm.write_text("notizen/idee.md", "# Idee")
    assert "Idee" in fm.read_text("notizen/idee.md")
    with pytest.raises(FileExistsError):
        fm.write_text("notizen/idee.md", "x")
    fm.mkdir("Archiv/2026")
    assert "Verschoben" in fm.move("notizen/idee.md", "Archiv/2026")
    assert (root / "Archiv/2026/idee.md").exists()
    assert "idee.md" in fm.search("idee")
    assert "Archiv" in fm.list_dir()
    for bad in ("../ausserhalb.txt", "/etc/passwd", "Archiv/../../x"):
        with pytest.raises(PermissionError):
            fm.resolve(bad)
    with pytest.raises(ValueError):
        (root / "bild.png").write_bytes(b"\x89PNG")
        fm.read_text("bild.png")


def test_update_env_file_replaces_and_appends(tmp_path):
    from sprachassistent.config import update_env_file

    env = tmp_path / ".env"
    env.write_text("# Kommentar\nANTHROPIC_API_KEY=abc\nTTS_VOICE=de-DE-KatjaNeural\n", encoding="utf-8")
    update_env_file(env, {"TTS_VOICE": "de-DE-ConradNeural", "AUDIO_INPUT_DEVICE": "USB PnP"})
    text = env.read_text(encoding="utf-8")
    assert text == "# Kommentar\nANTHROPIC_API_KEY=abc\nTTS_VOICE=de-DE-ConradNeural\nAUDIO_INPUT_DEVICE=USB PnP\n"
