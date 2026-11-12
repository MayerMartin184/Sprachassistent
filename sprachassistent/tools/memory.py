"""Dauerhaftes Gedächtnis: Absprachen, Gewohnheiten, Personen, Vorlieben – lokal als JSON."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .base import Tool, schema
from .store import JsonStore

CATEGORIES = ("absprache", "gewohnheit", "person", "vorliebe", "projekt", "sonstiges")
MAX_PROMPT_CHARS = 7000
TAGEBUCH_PROMPT_CHARS = 1500  # jüngste Tagebuch-Einträge im System-Prompt (heute und gestern)


class Memory:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonStore(data_dir / "memory.json", {"next_id": 1, "items": []})
        self.tagebuch_dir = data_dir / "tagebuch"

    # --- Tagebuch: Zusammenfassungen abgeschlossener Gesprächsabschnitte ---------------
    def tagebuch(self, text: str) -> Path:
        """Hängt eine Zusammenfassung an das heutige Tagebuch an (eine Datei je Tag, nur anhängen)."""
        self.tagebuch_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        path = self.tagebuch_dir / f"{now:%Y-%m-%d}.md"
        new = not path.exists()
        with path.open("a", encoding="utf-8") as fh:
            if new:
                fh.write(f"# Tagebuch {now:%d.%m.%Y}\n")
            fh.write(f"\n## {now:%H:%M}\n{text.strip()}\n")
        return path

    def tagebuch_recent(self, max_chars: int = TAGEBUCH_PROMPT_CHARS) -> str:
        """Die jüngsten Einträge von heute und gestern, von hinten gekürzt."""
        if not self.tagebuch_dir.exists():
            return ""
        files = sorted(self.tagebuch_dir.glob("*.md"))[-2:]
        text = "\n".join(p.read_text(encoding="utf-8") for p in files).strip()
        if len(text) > max_chars:
            text = "…" + text[-max_chars:]
        return text

    def save(self, text: str, category: str = "sonstiges") -> dict:
        if category not in CATEGORIES:
            category = "sonstiges"
        data = self.store.load()
        text = " ".join(text.split())
        for item in data["items"]:
            if item["text"].lower() == text.lower():
                return item  # schon bekannt
        item = {"id": data["next_id"], "category": category, "text": text, "created": datetime.now().strftime("%Y-%m-%d")}
        data["items"].append(item)
        data["next_id"] += 1
        self.store.save(data)
        return item

    def search(self, query: str = "") -> list[dict]:
        items = self.store.load()["items"]
        if not query:
            return items
        words = [w for w in query.lower().split() if len(w) > 2]
        return [i for i in items if any(w in i["text"].lower() or w in i["category"] for w in words)]

    def forget(self, item_id: int) -> bool:
        data = self.store.load()
        before = len(data["items"])
        data["items"] = [i for i in data["items"] if i["id"] != item_id]
        self.store.save(data)
        return len(data["items"]) < before

    def summary(self) -> str:
        """Kompakter Text für den System-Prompt (je Gespräch eingefroren): Gedächtnis plus jüngstes Tagebuch."""
        items = sorted(self.store.load()["items"], key=lambda i: i["id"], reverse=True)
        parts: list[str] = []
        if items:
            lines = []
            total = 0
            for i in items:
                line = f"- [{i['category']}, {i['created']}] {i['text']} (#{i['id']})"
                total += len(line)
                if total > MAX_PROMPT_CHARS:
                    lines.append(f"- … {len(items) - len(lines)} ältere Einträge (memory_search)")
                    break
                lines.append(line)
            parts.append("Gedächtnis über den Nutzer:\n" + "\n".join(lines))
        recent = self.tagebuch_recent()
        if recent:
            parts.append("Tagebuch (Zusammenfassungen der letzten Gespräche):\n" + recent)
        return "\n\n".join(parts)

    @staticmethod
    def format(items: list[dict]) -> str:
        if not items:
            return "Nichts gefunden."
        return "\n".join(f"#{i['id']} [{i['category']}] {i['text']} ({i['created']})" for i in items)


def build_tools(memory: Memory) -> list[Tool]:
    return [
        Tool(
            name="memory_save",
            description=(
                "Merkt sich dauerhaft eine Information über den Nutzer: Absprachen (mit wem, was, bis wann), "
                "Gewohnheiten und Abläufe, Personen, Vorlieben, Projekte. Kurz und konkret formulieren."
            ),
            input_schema=schema(
                {"text": {"type": "string"}, "category": {"type": "string", "enum": list(CATEGORIES)}},
                ["text"],
            ),
            handler=lambda text, category="sonstiges": "Gemerkt: " + Memory.format([memory.save(text, category)]),
        ),
        Tool(
            name="memory_search",
            description="Durchsucht das Gedächtnis (leer = alles anzeigen).",
            input_schema=schema({"query": {"type": "string"}}),
            handler=lambda query="": Memory.format(memory.search(query)),
        ),
        Tool(
            name="memory_forget",
            description="Löscht einen Gedächtniseintrag anhand seiner Nummer.",
            input_schema=schema({"item_id": {"type": "integer"}}, ["item_id"]),
            handler=lambda item_id: "Vergessen." if memory.forget(item_id) else f"Eintrag #{item_id} gibt es nicht.",
        ),
    ]
