"""Werkzeug-Registry: Definitionen für die Claude-API und Ausführung der Handler."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[..., str]


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        if tool.name in self._tools:
            raise ValueError(f"Werkzeug doppelt registriert: {tool.name}")
        self._tools[tool.name] = tool

    def register_all(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.to_api() for tool in self._tools.values()]

    def execute(self, name: str, tool_input: dict[str, Any]) -> tuple[str, bool]:
        """Führt ein Werkzeug aus. Rückgabe: (Ergebnistext, is_error)."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Unbekanntes Werkzeug: {name}", True
        try:
            result = tool.handler(**tool_input)
            if not isinstance(result, str):
                result = json.dumps(result, ensure_ascii=False, default=str)
            return result, False
        except TypeError as exc:
            return f"Ungültige Parameter für {name}: {exc}", True
        except Exception as exc:  # noqa: BLE001 - Fehler gehen als Text an das Modell zurück
            log.exception("Werkzeug %s fehlgeschlagen", name)
            return f"Fehler in {name}: {exc}", True


def schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required or [],
        "additionalProperties": False,
    }
