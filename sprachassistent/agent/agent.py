"""Agent-Kern: Claude mit Werkzeugschleife, Websuche als Server-Werkzeug.

Sparsam mit Tokens und mit den aktuellen Modellen verträglich:
- System-Text und Werkzeugliste sind je Gespräch eingefroren und eine Stunde gecacht; das Datum steht in der
  Nutzeräußerung, nicht im System-Text (ein veränderter System-Text würde den Cache und die Denkblöcke entwerten).
- Der Verlauf wird nur angehängt, nie in der Mitte geändert. Wird er zu groß oder war lange Pause, fasst ein
  günstiges Modell ihn zusammen; die Zusammenfassung geht ins Tagebuch und ersetzt den Verlauf.
- Lesende Werkzeuge laufen gleichzeitig.
- Jeder Aufruf protokolliert seinen Verbrauch in verbrauch.jsonl.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Any, Callable
from zoneinfo import ZoneInfo

import anthropic

from ..config import Settings
from ..tools.base import ToolRegistry
from .prompts import SUMMARY_PROMPT, system_prompt

log = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

# Klartext für die Statuszeile: was gerade läuft
TOOL_ACTIVITY: list[tuple[str, str]] = [
    ("web_search", "Suche im Web"), ("web_fetch", "Lese eine Webseite"),
    ("mail_send", "Bereite den Mailversand vor"), ("mail_reply", "Bereite die Antwort vor"), ("mail_", "Sehe die Mails durch"),
    ("calendar_", "Sehe den Kalender durch"),
    ("todo_", "Arbeite in Microsoft To Do"), ("planner_", "Arbeite an den Team-Aufgaben"),
    ("teams_chat", "Sehe die Teams-Chats durch"), ("teams_send", "Bereite die Teams-Nachricht vor"),
    ("teams_transcript", "Lade das Besprechungsprotokoll"), ("teams_", "Sehe Teams durch"),
    ("files_search", "Durchsuche deine Dateien"), ("files_read", "Lese eine Datei"), ("files_write", "Schreibe eine Datei"),
    ("files_", "Arbeite mit Dateien"),
    ("create_docx", "Erstelle ein Word-Dokument"), ("create_xlsx", "Erstelle eine Excel-Tabelle"),
    ("create_pptx", "Erstelle eine Präsentation"),
    ("memory_", "Sehe im Gedächtnis nach"), ("reminder_", "Arbeite an den Erinnerungen"),
    ("list_", "Arbeite an deinen Listen"), ("task_", "Arbeite an den Aufgaben"),
    ("screen_capture", "Sehe auf deinen Bildschirm"), ("webcam_", "Sehe durch die Kamera"),
    ("app_open", "Starte ein Programm"), ("url_open", "Öffne eine Webseite"), ("clipboard_", "Nutze die Zwischenablage"),
    ("ask_agent", "Gebe den Auftrag weiter"), ("ask_model", "Hole eine zweite Meinung"),
    ("ambient_", "Sehe ins Gesprächsprotokoll"), ("verbrauch_", "Rechne den Verbrauch zusammen"),
]


def activity(tool_name: str) -> str:
    for prefix, text in TOOL_ACTIVITY:
        if tool_name.startswith(prefix):
            return text
    return f"Führe {tool_name} aus"


MODELS: dict[str, str] = {
    "claude-sonnet-5-5": "Claude Sonnet 5.5 – schnell, sehr gut (Standard für den Dialog)",
    "claude-opus-5-5": "Claude Opus 5.5 – höchste Qualität (Prüfer)",
    "claude-haiku-5-5": "Claude Haiku 5.5 – sehr schnell, günstig (Arbeiter)",
}
EFFORTS = ["low", "medium", "high", "xhigh", "max"]

# System-Text und Werkzeuge ändern sich je Gespräch nicht: eine Stunde cachen. Der Verlauf ändert sich je Runde:
# Standardlaufzeit reicht, der Breakpoint wandert mit der letzten Nachricht mit.
CACHE_LONG: dict[str, str] = {"type": "ephemeral", "ttl": "1h"}
CACHE_SHORT: dict[str, str] = {"type": "ephemeral"}
CHARS_PER_TOKEN = 3.5  # grobe Schätzung für deutschen Text und JSON


def _legacy_haiku(model: str) -> bool:
    """Haiku 4.5 kennt weder effort noch die neuen Websuche-Varianten."""
    return model.startswith("claude-haiku-4")


def server_tools(model: str) -> list[dict[str, Any]]:
    """Websuche/Web-Fetch passend zur Modellgeneration."""
    if _legacy_haiku(model):
        return [
            {"type": "web_search_20250305", "name": "web_search", "max_uses": 8},
            {"type": "web_fetch_20250910", "name": "web_fetch", "max_uses": 8},
        ]
    return [
        {"type": "web_search_20260209", "name": "web_search", "max_uses": 8},
        {"type": "web_fetch_20260209", "name": "web_fetch", "max_uses": 8},
    ]


def request_extras(model: str, effort: str) -> dict[str, Any]:
    """Modellabhängige Parameter: effort gibt es auf allen aktuellen Modellen, nicht auf Haiku 4.5."""
    if _legacy_haiku(model):
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
        label: str = "dialog",
        web_tools: bool = True,
        on_compact: Callable[[str], None] | None = None,
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
        self.label = label  # Rolle, für das Verbrauchsprotokoll
        self.web_tools = web_tools
        self.on_compact = on_compact  # bekommt die Zusammenfassung, z. B. für das Tagebuch
        self._lock = threading.RLock()
        self._session_system: list[dict[str, Any]] | None = None  # eingefroren je Gespräch
        self._session_model: str | None = None
        self._last_run: float | None = None
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
        with self._lock:
            self.history.clear()
            self._container_id = None
            self._session_system = None
            self._session_model = None

    @staticmethod
    def _block_type(block: Any) -> str | None:
        return block.get("type") if isinstance(block, dict) else getattr(block, "type", None)

    @staticmethod
    def _block_text(block: Any) -> str:
        if isinstance(block, dict):
            return str(block.get("text") or "")
        return str(getattr(block, "text", "") or "")

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
        with self._lock:
            starts = self._turn_starts()
            if starts:
                del self.history[starts[-1] :]
            else:
                self.history.clear()

    # --- Anfrage zusammenbauen ----------------------------------------------------
    def _stamp(self) -> str:
        now = datetime.now(self.tz)
        weekday = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"][now.weekday()]
        return f"[Aktuell: {weekday}, {now:%d.%m.%Y %H:%M} ({self.tz.key})]"

    def _user_message(self, content: str | list[dict[str, Any]]) -> dict[str, Any]:
        """Nutzeräußerung mit Zeitstempel als erstem Block. Der Stempel bleibt im Verlauf (nur anhängen)."""
        stamp = {"type": "text", "text": self._stamp()}
        blocks = [stamp, {"type": "text", "text": content}] if isinstance(content, str) else [stamp, *content]
        return {"role": "user", "content": blocks}

    def _system(self) -> list[dict[str, Any]]:
        """System-Blöcke, je Gespräch eingefroren (sonst verfällt der Cache und die Denkblöcke werden ungültig)."""
        if self._session_system is None:
            text = self.system_text or system_prompt(self.settings.assistant_name)
            blocks = [{"type": "text", "text": text, "cache_control": dict(CACHE_LONG)}]
            memory = self.memory_summary()
            if memory:
                blocks.append({"type": "text", "text": memory, "cache_control": dict(CACHE_LONG)})
            self._session_system = blocks
            self._session_model = self.model
        return self._session_system

    def _tools(self) -> list[dict[str, Any]]:
        tools = self.registry.definitions()
        if self.web_tools:
            tools += server_tools(self.model)
        return tools

    def _messages_for_request(self) -> list[dict[str, Any]]:
        """Verlauf mit Cache-Breakpoint auf der letzten Nutzer-Nachricht; der Verlauf selbst bleibt unverändert."""
        messages = list(self.history)
        if not messages or messages[-1]["role"] != "user":
            return messages
        content = messages[-1]["content"]
        blocks = [{"type": "text", "text": content}] if isinstance(content, str) else list(content)
        if blocks and isinstance(blocks[-1], dict):
            blocks[-1] = {**blocks[-1], "cache_control": dict(CACHE_SHORT)}
            messages[-1] = {"role": "user", "content": blocks}
        return messages

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

    # --- Verbrauch -------------------------------------------------------------------
    def _log_usage(self, response: Any, model: str) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        record = {
            "zeit": datetime.now(self.tz).isoformat(timespec="seconds"),
            "rolle": self.label,
            "modell": model,
            "eingabe": getattr(usage, "input_tokens", 0) or 0,
            "cache_lesen": getattr(usage, "cache_read_input_tokens", 0) or 0,
            "cache_schreiben": getattr(usage, "cache_creation_input_tokens", 0) or 0,
            "ausgabe": getattr(usage, "output_tokens", 0) or 0,
        }
        try:
            path = self.settings.data_dir / "verbrauch.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as exc:
            log.warning("Verbrauch nicht protokolliert: %s", exc)

    # --- Verlauf klein halten ----------------------------------------------------------
    def estimated_tokens(self) -> int:
        total = 0
        for message in self.history:
            content = message["content"]
            if isinstance(content, str):
                total += len(content)
                continue
            for block in content:
                kind = self._block_type(block)
                if kind in ("text", "thinking"):
                    total += len(self._block_text(block))
                elif kind == "tool_use":
                    inp = block.get("input") if isinstance(block, dict) else getattr(block, "input", None)
                    total += len(json.dumps(inp, ensure_ascii=False, default=str)) if inp else 0
                elif kind == "tool_result":
                    inner = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                    total += len(inner) if isinstance(inner, str) else len(json.dumps(inner, default=str))
                else:
                    total += 200  # Bilder und Sonstiges: Pauschale
        return int(total / CHARS_PER_TOKEN)

    def _transcript(self, max_chars: int = 60000) -> str:
        """Verlauf als Klartext für die Zusammenfassung."""
        lines: list[str] = []
        for message in self.history:
            content = message["content"]
            who = "Nutzer" if message["role"] == "user" else "Assistent"
            if isinstance(content, str):
                lines.append(f"{who}: {content}")
                continue
            for block in content:
                kind = self._block_type(block)
                if kind == "text":
                    text = self._block_text(block)
                    if text and not text.startswith("[Aktuell:"):
                        lines.append(f"{who}: {text}")
                elif kind == "tool_use":
                    name = block.get("name") if isinstance(block, dict) else getattr(block, "name", "?")
                    inp = block.get("input") if isinstance(block, dict) else getattr(block, "input", {})
                    lines.append(f"Werkzeug {name}({json.dumps(inp, ensure_ascii=False, default=str)[:200]})")
                elif kind == "tool_result":
                    inner = block.get("content") if isinstance(block, dict) else getattr(block, "content", "")
                    text = inner if isinstance(inner, str) else "(Inhaltsblöcke)"
                    lines.append(f"Ergebnis: {text[:300]}")
        text = "\n".join(lines)
        return text[-max_chars:]

    def _summarize(self) -> str:
        transcript = self._transcript()
        if not transcript.strip():
            return ""
        model = self.settings.worker_model
        try:
            response = self.client.messages.create(
                model=model,
                max_tokens=2000,
                system=SUMMARY_PROMPT,
                messages=[{"role": "user", "content": transcript}],
                **request_extras(model, "low"),
            )
            self._log_usage(response, model)
            return self._text(response.content)
        except Exception as exc:  # noqa: BLE001 - Zusammenfassung ist Komfort, kein Muss
            log.warning("Zusammenfassung fehlgeschlagen: %s", exc)
            return ""

    def _compact(self, reason: str) -> None:
        """Verlauf zu einer Zusammenfassung eindampfen und ein neues Gespräch beginnen."""
        self.repair_history()
        summary = self._summarize() if self._turn_starts() else ""
        self.history.clear()
        self._container_id = None
        self._session_system = None
        if summary:
            stamp = datetime.now(self.tz).strftime("%d.%m.%Y %H:%M")
            self.history.append({"role": "user", "content": [{"type": "text", "text": f"[Zusammenfassung der bisherigen Unterhaltung, Stand {stamp}]\n{summary}"}]})
            self.history.append({"role": "assistant", "content": [{"type": "text", "text": "Verstanden."}]})
            if self.on_compact is not None:
                try:
                    self.on_compact(summary)
                except Exception:  # noqa: BLE001
                    log.exception("Tagebuch nicht geschrieben")
        log.info("Verlauf zusammengefasst (%s)", reason)

    def _maybe_compact(self) -> None:
        if not self.history:
            return
        if self._session_model and self.model != self._session_model:
            self._compact("Modellwechsel")
        elif self._last_run is not None and time.monotonic() - self._last_run > self.settings.history_idle_minutes * 60:
            self._compact("Pause")
        elif self.estimated_tokens() > self.settings.history_compact_tokens:
            self._compact("Umfang")

    def flush(self) -> None:
        """Beim Beenden: Verlauf ins Tagebuch sichern."""
        with self._lock:
            if self._turn_starts():
                self._compact("Ende")

    def note_exchange(self, user_text: str, answer: str) -> None:
        """Eine Runde, die eine andere Rolle beantwortet hat, als Klartext in den Verlauf übernehmen."""
        with self._lock:
            self._maybe_compact()
            self.history.append(self._user_message(user_text))
            self.history.append({"role": "assistant", "content": [{"type": "text", "text": answer}]})
            self._last_run = time.monotonic()

    def recent_context(self, turns: int = 2, max_chars: int = 1500) -> str:
        """Die letzten Runden als Klartext, damit eine Rolle ohne Verlauf den Zusammenhang kennt."""
        lines: list[str] = []
        for message in self.history:
            content = message["content"]
            blocks = [{"type": "text", "text": content}] if isinstance(content, str) else content
            for block in blocks:
                if self._block_type(block) != "text":
                    continue
                text = self._block_text(block).strip()
                if not text or text.startswith("[Aktuell:"):
                    continue
                who = "Nutzer" if message["role"] == "user" else "Assistent"
                lines.append(f"{who}: {text}")
        if not lines:
            return ""
        return "\n".join(lines[-2 * turns :])[-max_chars:]

    # --- Ausführung ---------------------------------------------------------------
    def run(self, user_content: str | list[dict[str, Any]], _retry: bool = False) -> str:
        """Verarbeitet eine Nutzeräußerung (Text oder Inhaltsblöcke, z. B. mit Bild) bis zur endgültigen Antwort."""
        with self._lock:
            if not _retry:
                self._maybe_compact()
            start = len(self.history)
            self.history.append(self._user_message(user_content))
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
                message = str(exc.message).lower()
                if not _retry and "container" in message:
                    # Container abgelaufen oder unbekannt: ohne ihn und mit bereinigtem Verlauf noch einmal versuchen
                    log.warning("Container verworfen und Anfrage wiederholt: %s", exc.message)
                    self._container_id, self._container_expires = None, None
                    return self.run(user_content, _retry=True)
                if not _retry and ("thinking" in message or "signature" in message):
                    # Denkblöcke passen nicht mehr zum Gespräch: einmalig ohne sie weitermachen
                    log.warning("Denkblöcke verworfen und Anfrage wiederholt: %s", exc.message)
                    self._strip_thinking()
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
            finally:
                self._last_run = time.monotonic()

    def _strip_thinking(self) -> None:
        for message in self.history:
            content = message["content"]
            if isinstance(content, list):
                message["content"] = [b for b in content if self._block_type(b) not in ("thinking", "redacted_thinking")]

    def _loop(self) -> str:
        for _ in range(self.settings.max_tool_rounds):
            self.on_status("Denke nach")
            model = self.model
            extras = request_extras(model, self.effort)
            if self._usable_container():
                extras["container"] = self._container_id
            response = self.client.messages.create(
                model=model,
                max_tokens=16000,
                system=self._system(),
                tools=self._tools(),
                messages=self._messages_for_request(),
                **extras,
            )
            self._log_usage(response, model)
            self._remember_container(response)
            self.history.append({"role": "assistant", "content": response.content})

            if response.stop_reason == "refusal":
                return "Das kann ich leider nicht übernehmen."
            if response.stop_reason == "pause_turn":
                continue  # Server-Werkzeug pausiert; Antwort unverändert zurücksenden

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
                return self._text(response.content)
            self.history.append({"role": "user", "content": self._execute(tool_uses)})

        self.history.append({"role": "assistant", "content": "Abgebrochen: zu viele Arbeitsschritte."})
        return "Ich habe die Bearbeitung abgebrochen, weil zu viele Schritte nötig waren. Bitte den Auftrag kleiner fassen."

    def _execute(self, tool_uses: list[Any]) -> list[dict[str, Any]]:
        """Werkzeuge ausführen; nur lesende (parallel-sichere) gleichzeitig. Ergebnisse in Aufrufreihenfolge."""
        jobs = [(block.name, dict(block.input)) for block in tool_uses]
        parallel = (
            self.settings.parallel_tools and len(jobs) > 1
            and all(self.registry.parallel_safe(name, inp) for name, inp in jobs)
        )
        if parallel:
            self.on_status(f"{len(jobs)} Schritte gleichzeitig")
            with ThreadPoolExecutor(max_workers=min(len(jobs), 6), thread_name_prefix="werkzeug") as pool:
                outputs = list(pool.map(lambda job: self.registry.execute(*job), jobs))
        else:
            outputs = []
            for name, inp in jobs:
                self.on_status(activity(name))
                outputs.append(self.registry.execute(name, inp))

        results = []
        for block, (content, is_error) in zip(tool_uses, outputs):
            preview = content[:200] if isinstance(content, str) else f"{len(content)} Inhaltsblöcke"
            log.info("Werkzeug %s -> %s%s", block.name, "FEHLER: " if is_error else "", preview)
            result: dict[str, Any] = {"type": "tool_result", "tool_use_id": block.id, "content": content}
            if is_error:
                result["is_error"] = True
            results.append(result)
        return results

    def ask(self, model: str, question: str, effort: str = "high") -> str:
        """Einmalige Frage an ein (anderes) Modell ohne Werkzeuge – für Zweitmeinungen und schwere Denkaufgaben."""
        response = self.client.messages.create(
            model=model,
            max_tokens=16000,
            system=f"Du bist ein sorgfältiger Fachexperte. Antworte präzise und auf Deutsch. Aktuell: {datetime.now(self.tz):%d.%m.%Y %H:%M}.",
            messages=[{"role": "user", "content": question}],
            **request_extras(model, effort),
        )
        self._log_usage(response, model)
        return self._text(response.content)

    @staticmethod
    def _text(content: list[Any]) -> str:
        parts = [b.text for b in content if getattr(b, "type", None) == "text" and b.text.strip()]
        return "\n".join(parts).strip() or "Erledigt."
