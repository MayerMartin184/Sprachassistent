"""Aufgabenverwaltung (lokal, JSON)."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .base import Tool, schema
from .store import JsonStore

PRIORITIES = ("hoch", "mittel", "niedrig")


class TaskManager:
    def __init__(self, data_dir: Path) -> None:
        self.store = JsonStore(data_dir / "tasks.json", {"next_id": 1, "tasks": []})

    # --- Kernfunktionen -------------------------------------------------
    def add(self, title: str, due: str | None = None, priority: str = "mittel", notes: str = "") -> dict:
        if priority not in PRIORITIES:
            raise ValueError(f"Priorität muss eine von {PRIORITIES} sein")
        if due:
            date.fromisoformat(due)  # validiert YYYY-MM-DD
        data = self.store.load()
        task = {
            "id": data["next_id"],
            "title": title.strip(),
            "due": due,
            "priority": priority,
            "notes": notes.strip(),
            "done": False,
            "created": datetime.now().isoformat(timespec="seconds"),
        }
        data["tasks"].append(task)
        data["next_id"] += 1
        self.store.save(data)
        return task

    def list(self, include_done: bool = False) -> list[dict]:
        tasks = self.store.load()["tasks"]
        if not include_done:
            tasks = [t for t in tasks if not t["done"]]
        order = {p: i for i, p in enumerate(PRIORITIES)}
        return sorted(tasks, key=lambda t: (t["due"] or "9999-12-31", order[t["priority"]], t["id"]))

    def update(
        self,
        task_id: int,
        done: bool | None = None,
        title: str | None = None,
        due: str | None = None,
        priority: str | None = None,
        notes: str | None = None,
        delete: bool = False,
    ) -> dict | None:
        data = self.store.load()
        for i, task in enumerate(data["tasks"]):
            if task["id"] != task_id:
                continue
            if delete:
                data["tasks"].pop(i)
                self.store.save(data)
                return None
            if done is not None:
                task["done"] = done
            if title is not None:
                task["title"] = title.strip()
            if due is not None:
                if due:
                    date.fromisoformat(due)
                task["due"] = due or None
            if priority is not None:
                if priority not in PRIORITIES:
                    raise ValueError(f"Priorität muss eine von {PRIORITIES} sein")
                task["priority"] = priority
            if notes is not None:
                task["notes"] = notes.strip()
            self.store.save(data)
            return task
        raise KeyError(f"Aufgabe {task_id} nicht gefunden")

    # --- Formatierung ---------------------------------------------------
    @staticmethod
    def format(tasks: list[dict]) -> str:
        if not tasks:
            return "Keine Aufgaben."
        lines = []
        for t in tasks:
            mark = "[x]" if t["done"] else "[ ]"
            due = f" fällig {t['due']}" if t["due"] else ""
            notes = f" – {t['notes']}" if t["notes"] else ""
            lines.append(f"{mark} #{t['id']} ({t['priority']}){due}: {t['title']}{notes}")
        return "\n".join(lines)


def build_tools(manager: TaskManager) -> list[Tool]:
    return [
        Tool(
            name="task_add",
            description="Legt eine neue Aufgabe in der Aufgabenliste des Nutzers an.",
            input_schema=schema(
                {
                    "title": {"type": "string", "description": "Kurzer Aufgabentitel"},
                    "due": {"type": "string", "description": "Fälligkeitsdatum YYYY-MM-DD (optional)"},
                    "priority": {"type": "string", "enum": list(PRIORITIES), "description": "Standard: mittel"},
                    "notes": {"type": "string", "description": "Zusätzliche Details (optional)"},
                },
                ["title"],
            ),
            handler=lambda **kw: "Aufgabe angelegt:\n" + TaskManager.format([manager.add(**kw)]),
        ),
        Tool(
            name="task_list",
            description="Zeigt die offenen Aufgaben, sortiert nach Fälligkeit und Priorität.",
            input_schema=schema(
                {"include_done": {"type": "boolean", "description": "Auch erledigte Aufgaben anzeigen"}}
            ),
            handler=lambda include_done=False: TaskManager.format(manager.list(include_done)),
        ),
        Tool(
            name="task_update",
            description=(
                "Ändert eine Aufgabe: als erledigt markieren (done=true), Titel/Fälligkeit/Priorität/Notizen "
                "anpassen oder löschen (delete=true). Die id stammt aus task_list."
            ),
            input_schema=schema(
                {
                    "task_id": {"type": "integer"},
                    "done": {"type": "boolean"},
                    "title": {"type": "string"},
                    "due": {"type": "string", "description": "YYYY-MM-DD, leerer String entfernt die Fälligkeit"},
                    "priority": {"type": "string", "enum": list(PRIORITIES)},
                    "notes": {"type": "string"},
                    "delete": {"type": "boolean"},
                },
                ["task_id"],
            ),
            handler=lambda **kw: _format_update(manager.update(**kw)),
        ),
    ]


def _format_update(task: dict | None) -> str:
    if task is None:
        return "Aufgabe gelöscht."
    return "Aufgabe aktualisiert:\n" + TaskManager.format([task])
