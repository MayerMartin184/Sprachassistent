"""Agent-Kern: Claude mit Werkzeugschleife, Websuche als Server-Werkzeug."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import anthropic

from ..config import Settings
from ..tools.base import ToolRegistry
from .prompts import system_prompt

log = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

MODELS: dict[str, str] = {
    "claude-opus-5": "Claude Opus 5 – höchste Qualität (Standard)",
    "claude-sonnet-5": "Claude Sonnet 5 – schnell, sehr gut",
    "claude-haiku-4-5": "Claude Haiku 4.5 – sehr schnell, einfache Aufgaben",
}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]


def server_tools(model: str) -> list[dict[str, Any]]:
    """Websuche/Web-Fetch passend zur Modellgeneration (Haiku 4.5 kennt nur die Basisvarianten)."""
    if model.startswith("claude-haiku"):
        return [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 8},
            {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 8},
        ]
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
    ]


def request_extras(model: str, effort: str) -> dict[str, Any]:
    """Modellabhängige Parameter: effort/adaptives Denken gibt es ab der 4.6-Generation, nicht auf Haiku 4.5."""
    if model.startswith("claude-haiku"):
        return {}
    if effort not in EFFORTS:
        effort = "medium"
    return {"output_config": {"effort": effort}}


class Agent:
    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        on_status: StatusCallback | None = None,
        client: Any | None = None,
        memory_summary: Callable[[], str] | None = None,
        system_text: str | None = None,
        model: str | None = None,
        effort: str | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry
        self.on_status = on_status or (lambda _msg: None)
        self.client = client or anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.history: list[dict[str, Any]] = []
        self.tz = ZoneInfo(settings.timezone)
        self.memory_summary = memory_summary or (lambda: "")
        self.system_text = system_text
        self.model_override = model
        self.effort_override = effort

    @property
    def model(self) -> str:
        return self.model_override or self.settings.assistant_model

    @property
    def effort(self) -> str:
        return self.effort_override or self.settings.assistant_effort

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.history.clear()

    def _system(self) -> list[dict[str, Any]]:
        now = datetime.now(self.tz)
        weekday = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][now.weekday()]
        text = self.system_text or system_prompt(self.settings.assistant_name)
        blocks = [{"type": "text", "text": text, "cache_control": {"type": "ephemeral"}}]
        memory = self.memory_summary()
        if memory:
            blocks.append({"type": "text", "text": memory})
        blocks.append({"type": "text", "text": f"Aktuell: {weekday}, {now:%d.%m.%Y %H:%M} ({self.tz.key})."})
        return blocks

    def _tools(self) -> list[dict[str, Any]]:
        return self.registry.definitions() + server_tools(self.model)

    def run(self, user_content: str | list[dict[str, Any]]) -> str:
        """Verarbeitet eine Nutzeräußerung (Text oder Inhaltsblöcke, z. B. mit Bild) bis zur endgültigen Antwort."""
        start = len(self.history)
        self.history.append({"role": "user", "content": user_content})
        try:
            return self._loop()
        except anthropic.AuthenticationError:
            del self.history[start:]
            return "Der Claude-API-Schlüssel ist ungültig oder fehlt. Bitte ANTHROPIC_API_KEY prüfen."
        except anthropic.RateLimitError:
            del self.history[start:]
            return "Die Claude-API ist gerade ausgelastet. Bitte in einem Moment erneut versuchen."
        except anthropic.APIStatusError as exc:
            del self.history[start:]
            log.error("API-Fehler %s: %s", exc.status_code, exc.message)
            return f"Die Claude-API hat einen Fehler gemeldet ({exc.status_code})."
        except anthropic.APIConnectionError:
            del self.history[start:]
            return "Keine Verbindung zur Claude-API. Bitte Internetverbindung prüfen."
        except TypeError as exc:
            if "authentication" not in str(exc).lower():
                raise
            del self.history[start:]
            return "Der Claude-API-Schlüssel fehlt. Bitte ANTHROPIC_API_KEY in der Datei .env eintragen."

    def _loop(self) -> str:
        for _ in range(self.settings.max_tool_rounds):
            self.on_status("Denke nach …")
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=self._system(),
                tools=self._tools(),
                messages=self.history,
                **request_extras(self.model, self.effort),
            )
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "Das kann ich leider nicht übernehmen."
            if response.stop_reason == "pause_turn":
                continue  # Server-Werkzeug pausiert; Antwort unverändert zurücksenden

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return self._text(response.content)

            results = []
            for block in tool_uses:
                self.on_status(f"Werkzeug: {block.name}")
                content, is_error = self.registry.execute(block.name, dict(block.input))
                preview = content[:200] if isinstance(content, str) else f"{len(content)} Inhaltsblöcke"
                log.info("Werkzeug %s -> %s%s", block.name, "FEHLER: " if is_error else "", preview)
                result: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id, "content": content}
                if is_error:
                    result["is_error"] = True
                results.append(result)
            self.history.append({"role": "user", "content": results})

        self.history.append({"role": "assistant", "content": "Abgebrochen: zu viele Arbeitsschritte."})
        return "Ich habe die Bearbeitung abgebrochen, weil zu viele Schritte nötig waren. Bitte den Auftrag kleiner fassen."

    def ask(self, model: str, question: str, effort: str = "high") -> str:
        """Einmalige Frage an ein (anderes) Modell ohne Werkzeuge – für Zweitmeinungen und schwere Denkaufgaben."""
        response = self.client.messages.create(
            model=model,
            max_tokens=16000,
            system=f"Du bist ein sorgfältiger Fachexperte. Antworte präzise und auf Deutsch. Aktuell: {datetime.now(self.tz):%d.%m.%Y %H:%M}.",
            messages=[{"role": "user", "content": question}],
            **request_extras(model, effort),
        )
        return self._text(response.content)

    @staticmethod
    def _text(content: list[Any]) -> str:
        parts = [b.text for b in content if getattr(b, "type", None) == "text" and b.text.strip()]
        return "\n".join(parts).strip() or "Erledigt."
