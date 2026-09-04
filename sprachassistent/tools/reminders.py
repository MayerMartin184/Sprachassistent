"""Erinnerungen: Jarvis meldet sich von selbst zur eingestellten Zeit."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .base import Tool, schema
from .store import JsonStore


class Reminders:
    def __init__(self, data_dir: Path, timezone: str) -> None:
        self.store = JsonStore(data_dir / "reminders.json", {"next_id": 1, "items": []})
        self.tz = ZoneInfo(timezone)

    def add(self, when: str, text: str) -> dict:
        dt = datetime.fromisoformat(when)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=self.tz)
        data = self.store.load()
        item = {"id": data["next_id"], "when": dt.isoformat(timespec="minutes"), "text": text.strip(), "done": False}
        data["items"].append(item)
        data["next_id"] += 1
        self.store.save(data)
        return item

    def pending(self) -> list[dict]:
        return sorted((i for i in self.store.load()["items"] if not i["done"]), key=lambda i: i["when"])

    def delete(self, item_id: int) -> bool:
        data = self.store.load()
        before = len(data["items"])
        data["items"] = [i for i in data["items"] if i["id"] != item_id]
        self.store.save(data)
        return len(data["items"]) < before

    def due(self, now: datetime | None = None) -> list[dict]:
        """Fällige Erinnerungen zurückgeben und als erledigt markieren."""
        now = now or datetime.now(self.tz)
        data = self.store.load()
        fired = []
        for item in data["items"]:
            if not item["done"] and datetime.fromisoformat(item["when"]) <= now:
                item["done"] = True
                fired.append(item)
        if fired:
            self.store.save(data)
        return fired

    def format(self, items: list[dict]) -> str:
        if not items:
            return "Keine offenen Erinnerungen."
        return "\n".join(f"#{i['id']} {datetime.fromisoformat(i['when']):%a %d.%m. %H:%M}: {i['text']}" for i in items)


def build_tools(rem: Reminders) -> list[Tool]:
    return [
        Tool(
            name="reminder_set",
            description=(
                "Legt eine Erinnerung an, die Jarvis zur angegebenen Zeit von selbst ausspricht. "
                "when als lokale Zeit YYYY-MM-DDTHH:MM. Für Absprachen mit Termin, Rückrufe, Deadlines."
            ),
            input_schema=schema({"when": {"type": "string"}, "text": {"type": "string"}}, ["when", "text"]),
            handler=lambda when, text: "Erinnerung gesetzt: " + rem.format([rem.add(when, text)]),
        ),
        Tool(
            name="reminder_list",
            description="Zeigt offene Erinnerungen.",
            input_schema=schema({}),
            handler=lambda: rem.format(rem.pending()),
        ),
        Tool(
            name="reminder_delete",
            description="Löscht eine Erinnerung anhand ihrer Nummer.",
            input_schema=schema({"item_id": {"type": "integer"}}, ["item_id"]),
            handler=lambda item_id: "Gelöscht." if rem.delete(item_id) else f"Erinnerung #{item_id} gibt es nicht.",
        ),
    ]
