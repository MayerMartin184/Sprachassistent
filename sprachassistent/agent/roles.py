"""Rollen: ein Agent je Aufgabe, mit eigenem Modell, eigener Werkzeugliste und ohne Gesprächsverlauf.

Der Dialog-Agent spricht mit dem Nutzer und gibt Aufträge über `ask_agent` weiter. Jede Rolle läuft als frische
`Agent`-Instanz: kleiner Kontext, eigener Cache (System-Text und Werkzeuge bleiben je Rolle gleich), günstiges
Modell, wo Lesen und Sortieren reicht. Parallel-sichere Rollen dürfen gleichzeitig laufen.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from ..config import Settings
from ..tools.base import Tool, ToolRegistry, schema
from .agent import Agent, request_extras
from .prompts import role_prompt

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Role:
    key: str
    title: str
    model: str  # assistant | worker | expert (Schlüssel in Settings)
    effort: str
    tools: tuple[str, ...]  # Werkzeugnamen oder „prefix*“
    web: bool  # Websuche/Web-Fetch mitgeben
    parallel_safe: bool  # darf gleichzeitig mit anderen Rollen laufen (keine Bestätigungsdialoge, keine Geräte)
    description: str


ROLES: dict[str, Role] = {
    "dialog": Role(
        "dialog", "Dialog", "assistant", "low",
        ("memory_*", "reminder_*", "list_*", "speech_set_language", "ambient_transcript", "screen_capture",
         "webcam_*", "clipboard_*", "app_open", "url_open", "verbrauch_heute", "ask_agent"),
        web=False, parallel_safe=False,
        description="spricht mit dem Nutzer, Gedächtnis, Erinnerungen, Listen",
    ),
    "wissen": Role(
        "wissen", "Wissen", "worker", "low",
        ("files_status", "files_list", "files_search", "files_read", "memory_search"),
        web=False, parallel_safe=True,
        description="Normen, Hausstandards, Prozesse, Lessons Learned, Kundenregeln, „wie haben wir das gelöst“",
    ),
    "projekt": Role(
        "projekt", "Projekt", "assistant", "medium",
        ("files_status", "files_list", "files_search", "files_read", "files_write", "files_mkdir", "memory_search",
         "reminder_set", "todo_add", "task_add"),
        web=False, parallel_safe=True,
        description="Projektstand, PROJEKT.md, Phasen, Pflichtunterlagen, Notizen und Entscheidungen zu einem Projekt",
    ),
    "buero": Role(
        "buero", "Büro", "assistant", "low",
        ("mail_*", "calendar_*", "todo_*", "task_*", "teams_*", "planner_*"),
        web=False, parallel_safe=False,
        description="E-Mail, Kalender, To Do, Teams-Nachrichten, Planner, Besprechungsprotokolle",
    ),
    "dateien": Role(
        "dateien", "Dateien", "worker", "low",
        ("files_*", "create_docx", "create_xlsx", "create_pptx"),
        web=False, parallel_safe=False,
        description="Dateien suchen, lesen, ablegen, ordnen, öffnen; Word, Excel, PowerPoint erzeugen",
    ),
    "recherche": Role(
        "recherche", "Recherche", "assistant", "low",
        ("files_write", "files_mkdir"),
        web=True, parallel_safe=True,
        description="Websuche zu aktuellen Fakten, Anbietern, Preisen, Vorschriften; Ergebnis als Datei",
    ),
    "pruefer": Role(
        "pruefer", "Prüfer", "expert", "high",
        (),
        web=True, parallel_safe=True,
        description="Einwand-Check, Normenabgleich, Rechnen, Varianten mit Folgen, Zweitmeinung",
    ),
    "hintergrund": Role(
        "hintergrund", "Hintergrund", "worker", "low",
        ("todo_add", "todo_list", "task_add", "task_list", "reminder_set", "reminder_list", "memory_save",
         "memory_search", "calendar_events", "files_write", "files_mkdir"),
        web=False, parallel_safe=True,
        description="Erinnerungen und Termine melden, Mithör-Extraktion, Sitzungs-Review",
    ),
}

DELEGATES: tuple[str, ...] = ("wissen", "projekt", "buero", "dateien", "recherche", "pruefer")


def matches(role: Role, tool_name: str) -> bool:
    return any((p.endswith("*") and tool_name.startswith(p[:-1])) or tool_name == p for p in role.tools)


class RoleRunner:
    """Baut je Rolle die Werkzeugliste und führt Aufträge als frischen Agenten aus."""

    def __init__(
        self,
        settings: Settings,
        registry: ToolRegistry,
        client: Any | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> None:
        self.settings = settings
        self.registry = registry  # alle Werkzeuge
        self.on_status = on_status or (lambda _m: None)
        if client is None:
            import anthropic

            client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self.client = client
        self._registries: dict[str, ToolRegistry] = {}

    def invalidate(self) -> None:
        self._registries.clear()

    def registry_for(self, key: str) -> ToolRegistry:
        if key not in self._registries:
            self._registries[key] = self.registry.subset(list(ROLES[key].tools))
        return self._registries[key]

    def model_for(self, key: str) -> str:
        role = ROLES[key]
        return {
            "assistant": self.settings.assistant_model,
            "worker": self.settings.worker_model,
            "expert": self.settings.expert_model,
        }[role.model]

    def agent(self, key: str, system_text: str | None = None, model: str | None = None) -> Agent:
        """Frischer Agent für eine Rolle (ohne Verlauf, ohne Gedächtnis-Block)."""
        role = ROLES[key]
        return Agent(
            self.settings, self.registry_for(key), self.on_status, client=self.client,
            system_text=system_text or role_prompt(key, self.settings.assistant_name),
            model=model or self.model_for(key), effort=role.effort, label=key, web_tools=role.web,
        )

    def run(
        self,
        key: str,
        auftrag: str,
        kontext: str = "",
        system_text: str | None = None,
        model: str | None = None,
        content: list[dict[str, Any]] | None = None,
    ) -> str:
        """Auftrag an eine Rolle. `content` (z. B. mit Bild) ersetzt den Text; `kontext` sind die letzten Runden."""
        role = ROLES[key]
        text = f"Zusammenhang aus dem Gespräch:\n{kontext}\n\nAuftrag: {auftrag}" if kontext else auftrag
        self.on_status(f"{role.title} arbeitet")
        return self.agent(key, system_text, model).run(content if content is not None else text)

    def classify(self, text: str, candidates: list[str]) -> str:
        """Unklare Anfrage einer der Kandidaten-Rollen zuordnen (eine Zeile, günstiges Modell)."""
        options = "\n".join(f"- {k}: {ROLES[k].description}" for k in candidates)
        model = self.settings.worker_model
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=20,
                system=(
                    "Ordne die Anfrage des Nutzers genau einer Rolle zu. Antworte nur mit dem Rollennamen, "
                    "ohne weitere Worte. Passt keine Rolle, antworte: dialog.\nRollen:\n" + options
                ),
                messages=[{"role": "user", "content": text}],
                **request_extras(model, "low"),
            )
        except Exception as exc:  # noqa: BLE001 - dann entscheidet der Dialog
            log.warning("Verteilung fehlgeschlagen: %s", exc)
            return "dialog"
        answer = "".join(getattr(b, "text", "") for b in response.content).strip().lower().strip(".")
        return answer if answer in candidates else "dialog"

    def ask_tool(self, context_provider: Callable[[], str] | None = None) -> Tool:
        """Das Werkzeug, mit dem der Dialog-Agent Aufträge weitergibt."""
        roles = "\n".join(f"- {k}: {ROLES[k].description}" for k in DELEGATES)

        def handler(agent: str, auftrag: str, kontext: str = "") -> str:
            if agent not in DELEGATES:
                return f"Unbekannter Agent: {agent}. Möglich: {', '.join(DELEGATES)}."
            extra = context_provider() if context_provider is not None else ""
            merged = "\n".join(part for part in (extra, kontext) if part)
            return self.run(agent, auftrag, merged)

        return Tool(
            name="ask_agent",
            description=(
                "Gibt einen Auftrag an einen Fachagenten und liefert dessen Ergebnis. Den Auftrag vollständig und "
                "mit allem Zusammenhang formulieren (Projektcode, Namen, Dateien, Ziel). Unabhängige Aufträge in "
                "einer Antwort gleichzeitig aufrufen.\nAgenten:\n" + roles
            ),
            input_schema=schema(
                {
                    "agent": {"type": "string", "enum": list(DELEGATES)},
                    "auftrag": {"type": "string"},
                    "kontext": {"type": "string", "description": "Zusatzinformationen aus dem Gespräch, falls nötig"},
                },
                ["agent", "auftrag"],
            ),
            handler=handler,
            parallel_safe=lambda inp: ROLES.get(str(inp.get("agent", "")), ROLES["dialog"]).parallel_safe,
        )
