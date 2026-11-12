"""Werkzeug-Registry: Definitionen für die Claude-API und Ausführung der Handler."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[..., Any]
ToolResult = str | list[dict[str, Any]]

# Werkzeuge, die nur lesen, dürfen gleichzeitig laufen. Erkennung am Namen; Ausnahmen setzen `parallel_safe` selbst.
_READ_ONLY_MARKERS = (
    "_list", "_search", "_read", "_show", "_status", "_events", "_folders", "_chats", "_meetings",
    "_transcript", "_plans", "_buckets", "_tasks", "_lists", "_channels", "_get", "_teams",
)


def read_only_name(name: str) -> bool:
    return any(marker in name for marker in _READ_ONLY_MARKERS)


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    handler: Handler
    # True/False: fest. Callable: entscheidet anhand der Eingabe. None: nach Namen (nur lesende Werkzeuge).
    parallel_safe: bool | Callable[[dict[str, Any]], bool] | None = None

    def to_api(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }

    def is_parallel_safe(self, tool_input: dict[str, Any]) -> bool:
        if callable(self.parallel_safe):
            try:
                return bool(self.parallel_safe(tool_input))
            except Exception:  # noqa: BLE001
                return False
        if self.parallel_safe is None:
            return read_only_name(self.name)
        return self.parallel_safe


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

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    @property
    def names(self) -> list[str]:
        return list(self._tools)

    def subset(self, patterns: list[str]) -> ToolRegistry:
        """Neue Registry mit den Werkzeugen, deren Name genau passt oder mit einem `prefix*` beginnt."""
        sub = ToolRegistry()
        for name, tool in self._tools.items():
            for pattern in patterns:
                if (pattern.endswith("*") and name.startswith(pattern[:-1])) or name == pattern:
                    sub.register(tool)
                    break
        return sub

    def definitions(self) -> list[dict[str, Any]]:
        return [tool.to_api() for tool in self._tools.values()]

    def parallel_safe(self, name: str, tool_input: dict[str, Any]) -> bool:
        tool = self._tools.get(name)
        return tool is not None and tool.is_parallel_safe(tool_input)

    def execute(self, name: str, tool_input: dict[str, Any]) -> tuple[ToolResult, bool]:
        """Führt ein Werkzeug aus. Rückgabe: (Ergebnis als Text oder Inhaltsblöcke, is_error)."""
        tool = self._tools.get(name)
        if tool is None:
            return f"Unbekanntes Werkzeug: {name}", True
        try:
            result = tool.handler(**tool_input)
            if isinstance(result, list):
                return result, False
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
