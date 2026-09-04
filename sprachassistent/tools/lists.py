"""Benannte Listen (Einkauf, Ideen, Packliste ...) – lokal als JSON."""

from __future__ import annotations

from pathlib import Path

from .base import Tool, schema
from .store import JsonStore


class ListManager:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonStore(data_dir / "lists.json", {})

    @staticmethod
    def _key(name: str) -> str:
        return name.strip().lower()

    def add(self, name: str, items: list[str]) -> list[str]:
        data = self.store.load()
        key = self._key(name)
        entry = data.setdefault(key, {"name": name.strip(), "items": []})
        for item in items:
            item = item.strip()
            if item and item.lower() not in (x.lower() for x in entry["items"]):
                entry["items"].append(item)
        self.store.save(data)
        return entry["items"]

    def get(self, name: str) -> dict | None:
        return self.store.load().get(self._key(name))

    def overview(self) -> list[dict]:
        return list(self.store.load().values())

    def remove(self, name: str, items: list[str] | None = None) -> dict | None:
        data = self.store.load()
        key = self._key(name)
        if key not in data:
            raise KeyError(f"Liste '{name}' nicht gefunden")
        if not items:
            data.pop(key)
            self.store.save(data)
            return None
        wanted = {i.strip().lower() for i in items}
        data[key]["items"] = [x for x in data[key]["items"] if x.lower() not in wanted]
        self.store.save(data)
        return data[key]

    @staticmethod
    def format(entry: dict) -> str:
        if not entry["items"]:
            return f"Liste '{entry['name']}' ist leer."
        return f"Liste '{entry['name']}':\n" + "\n".join(f"- {x}" for x in entry["items"])


def build_tools(manager: ListManager) -> list[Tool]:
    def show(name: str | None = None) -> str:
        if name:
            entry = manager.get(name)
            return ListManager.format(entry) if entry else f"Liste '{name}' existiert nicht."
        lists = manager.overview()
        if not lists:
            return "Es gibt noch keine Listen."
        return "Vorhandene Listen:\n" + "\n".join(f"- {e['name']} ({len(e['items'])} Einträge)" for e in lists)

    def remove(name: str, items: list[str] | None = None) -> str:
        entry = manager.remove(name, items)
        return f"Liste '{name}' gelöscht." if entry is None else ListManager.format(entry)

    return [
        Tool(
            name="list_add",
            description="Fügt Einträge zu einer benannten Liste hinzu (z. B. Einkaufsliste). Legt die Liste bei Bedarf an.",
            input_schema=schema(
                {
                    "name": {"type": "string", "description": "Name der Liste"},
                    "items": {"type": "array", "items": {"type": "string"}, "description": "Einträge"},
                },
                ["name", "items"],
            ),
            handler=lambda name, items: ListManager.format({"name": name, "items": manager.add(name, items)}),
        ),
        Tool(
            name="list_show",
            description="Zeigt eine Liste oder – ohne Name – die Übersicht aller Listen.",
            input_schema=schema({"name": {"type": "string"}}),
            handler=show,
        ),
        Tool(
            name="list_remove",
            description="Entfernt Einträge aus einer Liste oder löscht die ganze Liste, wenn keine Einträge angegeben sind.",
            input_schema=schema(
                {"name": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
                ["name"],
            ),
            handler=remove,
        ),
    ]
