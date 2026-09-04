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


def test_files_sandbox_and_operations(tmp_path, monkeypatch):
    docs, dl = tmp_path / "docs", tmp_path / "downloads"
    fm = FileManager({"Dokumente": docs, "Downloads": dl}, confirm=lambda _m: True)
    fm.write("Dokumente/notizen/idee.md", "# Idee")
    assert "Idee" in fm.read("Dokumente/notizen/idee.md")
    with pytest.raises(FileExistsError):
        fm.write("Dokumente/notizen/idee.md", "x")
    fm.mkdir("Dokumente/Archiv/2026")
    assert "Verschoben" in fm.move("Dokumente/notizen/idee.md", "Dokumente/Archiv/2026")
    assert (docs / "Archiv/2026/idee.md").exists()
    assert "Kopiert" in fm.copy("Dokumente/Archiv/2026/idee.md", "Downloads/idee_kopie.md")
    assert (dl / "idee_kopie.md").exists()
    assert "idee" in fm.search("idee").lower()
    assert "idee.md" in fm.search("# Idee", "Dokumente", content=True)
    assert "Archiv" in fm.list_dir("Dokumente")
    for bad in ("Dokumente/../ausserhalb.txt", "/etc/passwd", "Fremd/x", ""):
        with pytest.raises((PermissionError, KeyError, ValueError)):
            fm.resolve(bad)
    (docs / "bild.png").write_bytes(b"\x89PNG")
    with pytest.raises(ValueError):
        fm.read("Dokumente/bild.png")
    # Löschen: Bestätigung und Papierkorb (hier: Ersatzordner, da kein send2trash)
    import sys
    monkeypatch.setitem(sys.modules, "send2trash", None)
    monkeypatch.setattr("pathlib.Path.home", classmethod(lambda cls: tmp_path))
    fm.confirm = lambda _m: False
    assert "abgelehnt" in fm.delete("Downloads/idee_kopie.md")
    fm.confirm = lambda _m: True
    assert "Verschoben" in fm.delete("Downloads/idee_kopie.md") and not (dl / "idee_kopie.md").exists()
    with pytest.raises(PermissionError):
        fm.delete("Downloads")


def test_parse_roots():
    from sprachassistent.tools.files import parse_roots
    roots = parse_roots(r"Projekte=D:\Projekte;Server=\\srv\daten; kaputt")
    assert set(roots) == {"Projekte", "Server"}


def test_update_env_file_replaces_and_appends(tmp_path):
    from sprachassistent.config import update_env_file

    env = tmp_path / ".env"
    env.write_text("# Kommentar\nANTHROPIC_API_KEY=abc\nTTS_VOICE=de-DE-KatjaNeural\n", encoding="utf-8")
    update_env_file(env, {"TTS_VOICE": "de-DE-ConradNeural", "AUDIO_INPUT_DEVICE": "USB PnP"})
    text = env.read_text(encoding="utf-8")
    assert text == "# Kommentar\nANTHROPIC_API_KEY=abc\nTTS_VOICE=de-DE-ConradNeural\nAUDIO_INPUT_DEVICE=USB PnP\n"
