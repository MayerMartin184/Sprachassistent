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
        # Websuche und Web-Fetch laufen serverseitig in einem Container. Wird ein Zug pausiert, muss dessen
        # Kennung bei der Fortsetzung mitgeschickt werden, sonst lehnt die API mit 400 ab.
        self._container_id: str | None = None
        self._container_expires: Any = None

    @property
    def model(self) -> str:
        return self.model_override or self.settings.assistant_model

    @property
    def effort(self) -> str:
        return self.effort_override or self.settings.assistant_effort

    # ------------------------------------------------------------------
    def reset(self) -> None:
        self.history.clear()
        self._container_id = None

    @staticmethod
    def _block_type(block: Any) -> str | None:
        return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

    def _turn_starts(self) -> list[int]:
        """Positionen echter Nutzer-Runden. Werkzeug-Ergebnisse haben zwar die Rolle „user“, sind aber keine."""
        starts = []
        for i, message in enumerate(self.history):
            if message["role"] != "user":
                continue
            content = message["content"]
            if isinstance(content, str):
                starts.append(i)
                continue
            first = content[0] if content else None
            if self._block_type(first) != "tool_result":
                starts.append(i)
        return starts

    def _incomplete(self) -> bool:
        """Endet der Verlauf mitten in einer Runde? Dann lehnt die API die nächste Anfrage ab."""
        if not self.history:
            return False
        last = self.history[-1]
        if last["role"] != "assistant":
            return True  # offene Nutzeräußerung oder Werkzeug-Ergebnis ohne Antwort
        content = last["content"]
        if isinstance(content, str):
            return False
        return any(self._block_type(b) in ("tool_use", "server_tool_use") for b in content)

    def repair_history(self) -> bool:
        """Angebrochene Runden abschneiden, bis der Verlauf wieder sendbar ist. True, wenn etwas entfernt wurde."""
        changed = False
        while self.history and self._incomplete():
            starts = self._turn_starts()
            if starts:
                del self.history[starts[-1] :]
            else:
                self.history.clear()
            changed = True
        return changed

    def drop_last_exchange(self) -> None:
        """Letzte Runde (Nutzeräußerung samt Antwort und Werkzeugaufrufen) vollständig verwerfen."""
        starts = self._turn_starts()
        if starts:
            del self.history[starts[-1] :]
        else:
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

    def _usable_container(self) -> bool:
        if not self._container_id:
            return False
        expires = self._container_expires
        if expires is None:
            return True
        try:
            return datetime.now(self.tz) < expires.astimezone(self.tz)
        except (AttributeError, TypeError, ValueError):
            return True

    def _remember_container(self, response: Any) -> None:
        container = getattr(response, "container", None)
        container_id = getattr(container, "id", None)
        if container_id:
            self._container_id = container_id
            self._container_expires = getattr(container, "expires_at", None)

    def _tools(self) -> list[dict[str, Any]]:
        return self.registry.definitions() + server_tools(self.model)

    def run(self, user_content: str | list[dict[str, Any]], _retry: bool = False) -> str:
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
            self.repair_history()
            return "Die Claude-API ist gerade ausgelastet. Bitte in einem Moment erneut versuchen."
        except anthropic.BadRequestError as exc:
            del self.history[start:]
            self.repair_history()
            if not _retry and "container" in str(exc.message).lower():
                # Container abgelaufen oder unbekannt: ohne ihn und mit bereinigtem Verlauf noch einmal versuchen
                log.warning("Container verworfen und Anfrage wiederholt: %s", exc.message)
                self._container_id, self._container_expires = None, None
                return self.run(user_content, _retry=True)
            log.error("API-Fehler 400: %s", exc.message)
            detail = " ".join(str(exc.message).split())[:200]
            return f"Die Claude-API hat die Anfrage abgelehnt: {detail}"
        except anthropic.APIStatusError as exc:
            del self.history[start:]
            repaired = self.repair_history()
            log.error("API-Fehler %s: %s", exc.status_code, exc.message)
            detail = " ".join(str(exc.message).split())[:200]
            if repaired:
                return "Der Gesprächsverlauf war beschädigt und wurde bereinigt. Bitte sag den letzten Satz noch einmal."
            return f"Die Claude-API hat einen Fehler gemeldet ({exc.status_code}): {detail}"
        except anthropic.APIConnectionError:
            del self.history[start:]
            self.repair_history()
            return "Keine Verbindung zur Claude-API. Bitte Internetverbindung prüfen."
        except TypeError as exc:
            if "authentication" not in str(exc).lower():
                raise
            del self.history[start:]
            return "Der Claude-API-Schlüssel fehlt. Bitte ANTHROPIC_API_KEY in der Datei .env eintragen."

    def _loop(self) -> str:
        for _ in range(self.settings.max_tool_rounds):
            self.on_status("Denke nach …")
            extras = request_extras(self.model, self.effort)
            if self._usable_container():
                extras["container"] = self._container_id
            response = self.client.messages.create(
                model=self.model,
                max_tokens=16000,
                system=self._system(),
                tools=self._tools(),
                messages=self.history,
                **extras,
            )
            self._remember_container(response)
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
