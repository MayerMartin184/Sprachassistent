"""Microsoft 365 über Microsoft Graph: E-Mail und Kalender.

Anmeldung per Device-Code-Flow (msal), Token-Cache im Datenverzeichnis.
Graph-IDs sind sehr lang; sie werden pro Sitzung auf Kurz-IDs (m1, m2, ...) abgebildet,
damit das Modell (und der Nutzer) bequem darauf verweisen kann.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import msal
import requests

from .base import Tool, schema

log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = ["User.Read", "Mail.ReadWrite", "Mail.Send", "Calendars.ReadWrite"]
MAIL_FIELDS = "id,subject,from,toRecipients,receivedDateTime,isRead,flag,bodyPreview,hasAttachments"

Confirm = Callable[[str], bool]
Notify = Callable[[str], None]


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag in ("script", "style"):
            self._skip += 1
        elif tag in ("p", "br", "div", "li", "tr", "h1", "h2", "h3"):
            self._chunks.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style") and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip:
            self._chunks.append(data)

    def text(self) -> str:
        raw = "".join(self._chunks)
        lines = [" ".join(line.split()) for line in raw.splitlines()]
        return "\n".join(line for line in lines if line)


def html_to_text(html: str) -> str:
    parser = _TextExtractor()
    parser.feed(html)
    return parser.text()


class GraphClient:
    def __init__(self, client_id: str, tenant_id: str, cache_path: Path, notify: Notify) -> None:
        self.cache_path = cache_path
        self.notify = notify
        self._cache = msal.SerializableTokenCache()
        if cache_path.exists():
            self._cache.deserialize(cache_path.read_text(encoding="utf-8"))
        self._app = msal.PublicClientApplication(
            client_id,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
            token_cache=self._cache,
        )

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def token(self) -> str:
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result:
            flow = self._app.initiate_device_flow(scopes=SCOPES)
            if "user_code" not in flow:
                raise RuntimeError(f"Device-Flow konnte nicht gestartet werden: {flow.get('error_description', flow)}")
            self.notify(flow["message"])
            result = self._app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Microsoft-Anmeldung fehlgeschlagen: {result.get('error_description', result)}")
        self._save_cache()
        return result["access_token"]

    def request(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        hdrs = {"Authorization": f"Bearer {self.token()}"}
        if headers:
            hdrs.update(headers)
        resp = requests.request(method, f"{GRAPH}{path}", params=params, json=json, headers=hdrs, timeout=30)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise RuntimeError(f"Graph {method} {path} -> {resp.status_code}: {detail}")
        if resp.status_code == 204 or not resp.content:
            return {}
        return resp.json()


class M365Tools:
    def __init__(self, graph: GraphClient, confirm: Confirm, timezone: str) -> None:
        self.graph = graph
        self.confirm = confirm
        self.tz = ZoneInfo(timezone)
        self._ids: dict[str, str] = {}
        self._reverse: dict[str, str] = {}
        self._folder_cache: dict[str, str] = {}

    # --- Kurz-IDs -------------------------------------------------------
    def _short(self, graph_id: str) -> str:
        if graph_id in self._reverse:
            return self._reverse[graph_id]
        short = f"m{len(self._ids) + 1}"
        self._ids[short] = graph_id
        self._reverse[graph_id] = short
        return short

    def _long(self, short: str) -> str:
        try:
            return self._ids[short]
        except KeyError:
            raise KeyError(f"Unbekannte Nachrichten-ID '{short}'. Erst mail_search verwenden.") from None

    # --- Mail -----------------------------------------------------------
    def _fmt_mail(self, m: dict[str, Any]) -> str:
        sender = m.get("from", {}).get("emailAddress", {})
        who = sender.get("name") or sender.get("address") or "unbekannt"
        received = self._local(m.get("receivedDateTime"))
        flags = []
        if not m.get("isRead", True):
            flags.append("ungelesen")
        if m.get("flag", {}).get("flagStatus") == "flagged":
            flags.append("markiert")
        if m.get("hasAttachments"):
            flags.append("Anhang")
        flag_txt = f" [{', '.join(flags)}]" if flags else ""
        preview = " ".join((m.get("bodyPreview") or "").split())[:160]
        return f"{self._short(m['id'])} | {received} | {who} | {m.get('subject') or '(kein Betreff)'}{flag_txt}\n    {preview}"

    def _local(self, iso: str | None) -> str:
        if not iso:
            return "?"
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00")).astimezone(self.tz)
        return dt.strftime("%d.%m.%Y %H:%M")

    def mail_search(self, query: str | None = None, folder: str = "inbox", unread_only: bool = False, top: int = 10) -> str:
        top = max(1, min(top, 25))
        params: dict[str, Any] = {"$select": MAIL_FIELDS, "$top": top}
        if query:
            params["$search"] = f'"{query}"'  # $search erlaubt kein $orderby/$filter
        else:
            params["$orderby"] = "receivedDateTime desc"
            if unread_only:
                params["$filter"] = "isRead eq false"
        folder_id = self._folder_id(folder)
        data = self.graph.request("GET", f"/me/mailFolders/{folder_id}/messages", params=params)
        mails = data.get("value", [])
        if query and unread_only:
            mails = [m for m in mails if not m.get("isRead", True)]
        if not mails:
            return "Keine passenden E-Mails gefunden."
        return f"{len(mails)} E-Mails (ID | Empfangen | Von | Betreff):\n" + "\n".join(self._fmt_mail(m) for m in mails)

    def mail_read(self, message_id: str, max_chars: int = 6000) -> str:
        m = self.graph.request(
            "GET",
            f"/me/messages/{self._long(message_id)}",
            params={"$select": "subject,from,toRecipients,ccRecipients,receivedDateTime,body,hasAttachments"},
        )
        body = m.get("body", {})
        text = html_to_text(body.get("content", "")) if body.get("contentType") == "html" else body.get("content", "")
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [gekürzt, {len(text)} Zeichen gesamt]"
        to = ", ".join(r["emailAddress"].get("address", "") for r in m.get("toRecipients", []))
        cc = ", ".join(r["emailAddress"].get("address", "") for r in m.get("ccRecipients", []))
        sender = m.get("from", {}).get("emailAddress", {})
        head = [
            f"Von: {sender.get('name', '')} <{sender.get('address', '')}>",
            f"An: {to}",
        ]
        if cc:
            head.append(f"CC: {cc}")
        head += [f"Empfangen: {self._local(m.get('receivedDateTime'))}", f"Betreff: {m.get('subject')}"]
        if m.get("hasAttachments"):
            head.append("Anhänge: ja")
        return "\n".join(head) + "\n\n" + text

    def mail_send(self, to: list[str], subject: str, body: str, cc: list[str] | None = None) -> str:
        summary = f"E-Mail senden?\nAn: {', '.join(to)}\n" + (f"CC: {', '.join(cc)}\n" if cc else "") + f"Betreff: {subject}\n\n{body}"
        if not self.confirm(summary):
            return "Der Nutzer hat den Versand abgelehnt. Nicht gesendet."
        message = {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to],
        }
        if cc:
            message["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc]
        self.graph.request("POST", "/me/sendMail", json={"message": message, "saveToSentItems": True})
        return f"E-Mail an {', '.join(to)} gesendet."

    def mail_reply(self, message_id: str, body: str, reply_all: bool = False) -> str:
        if not self.confirm(f"Antwort auf Nachricht {message_id} senden ({'an alle' if reply_all else 'an Absender'})?\n\n{body}"):
            return "Der Nutzer hat den Versand abgelehnt. Nicht gesendet."
        action = "replyAll" if reply_all else "reply"
        self.graph.request("POST", f"/me/messages/{self._long(message_id)}/{action}", json={"comment": body})
        return "Antwort gesendet."

    def mail_folders(self) -> str:
        data = self.graph.request("GET", "/me/mailFolders", params={"$top": 100, "$select": "id,displayName,unreadItemCount,totalItemCount"})
        folders = data.get("value", [])
        self._folder_cache.update({f["displayName"].lower(): f["id"] for f in folders})
        return "Ordner:\n" + "\n".join(f"- {f['displayName']} ({f['unreadItemCount']} ungelesen / {f['totalItemCount']})" for f in folders)

    def _folder_id(self, name: str, create: bool = False) -> str:
        key = name.strip().lower()
        well_known = {"inbox": "inbox", "posteingang": "inbox", "gesendet": "sentitems", "sentitems": "sentitems",
                      "entwürfe": "drafts", "drafts": "drafts", "archiv": "archive", "archive": "archive",
                      "gelöscht": "deleteditems", "papierkorb": "deleteditems", "junk": "junkemail"}
        if key in well_known:
            return well_known[key]
        if key not in self._folder_cache:
            self.mail_folders()
        if key not in self._folder_cache:
            if not create:
                raise KeyError(f"Ordner '{name}' nicht gefunden. Vorhandene Ordner mit mail_folders prüfen.")
            created = self.graph.request("POST", "/me/mailFolders", json={"displayName": name.strip()})
            self._folder_cache[key] = created["id"]
        return self._folder_cache[key]

    def mail_move(self, message_id: str, destination_folder: str, create_if_missing: bool = True) -> str:
        dest = self._folder_id(destination_folder, create=create_if_missing)
        moved = self.graph.request("POST", f"/me/messages/{self._long(message_id)}/move", json={"destinationId": dest})
        if moved.get("id"):
            self._ids[message_id] = moved["id"]
            self._reverse[moved["id"]] = message_id
        return f"Nachricht {message_id} nach '{destination_folder}' verschoben."

    def mail_mark(self, message_id: str, read: bool | None = None, flagged: bool | None = None) -> str:
        patch: dict[str, Any] = {}
        if read is not None:
            patch["isRead"] = read
        if flagged is not None:
            patch["flag"] = {"flagStatus": "flagged" if flagged else "notFlagged"}
        if not patch:
            return "Nichts zu ändern."
        self.graph.request("PATCH", f"/me/messages/{self._long(message_id)}", json=patch)
        return f"Nachricht {message_id} aktualisiert: {patch}"

    # --- Kalender -------------------------------------------------------
    def calendar_events(self, days_ahead: int = 7, start_date: str | None = None) -> str:
        start = datetime.fromisoformat(start_date).replace(tzinfo=self.tz) if start_date else datetime.now(self.tz).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=max(1, min(days_ahead, 60)))
        data = self.graph.request(
            "GET",
            "/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime",
                "$top": 50,
                "$select": "subject,start,end,location,isAllDay,organizer,attendees",
            },
            headers={"Prefer": f'outlook.timezone="{self.tz.key}"'},
        )
        events = data.get("value", [])
        if not events:
            return f"Keine Termine zwischen {start:%d.%m.%Y} und {end:%d.%m.%Y}."
        lines = [f"Termine {start:%d.%m.%Y} bis {end:%d.%m.%Y}:"]
        for e in events:
            s = datetime.fromisoformat(e["start"]["dateTime"][:19])
            en = datetime.fromisoformat(e["end"]["dateTime"][:19])
            when = f"{s:%a %d.%m.} ganztägig" if e.get("isAllDay") else f"{s:%a %d.%m. %H:%M}-{en:%H:%M}"
            loc = e.get("location", {}).get("displayName")
            lines.append(f"- {when}: {e.get('subject')}" + (f" @ {loc}" if loc else ""))
        return "\n".join(lines)

    def calendar_create_event(
        self,
        subject: str,
        start: str,
        end: str,
        attendees: list[str] | None = None,
        location: str | None = None,
        body: str | None = None,
    ) -> str:
        if attendees and not self.confirm(
            f"Termin '{subject}' ({start} bis {end}) anlegen und Einladungen an {', '.join(attendees)} senden?"
        ):
            return "Der Nutzer hat das Anlegen abgelehnt."
        event: dict[str, Any] = {
            "subject": subject,
            "start": {"dateTime": start, "timeZone": self.tz.key},
            "end": {"dateTime": end, "timeZone": self.tz.key},
        }
        if location:
            event["location"] = {"displayName": location}
        if body:
            event["body"] = {"contentType": "Text", "content": body}
        if attendees:
            event["attendees"] = [{"emailAddress": {"address": a}, "type": "required"} for a in attendees]
        created = self.graph.request("POST", "/me/events", json=event)
        return f"Termin angelegt: {created.get('subject')} am {start}."


def build_tools(m: M365Tools) -> list[Tool]:
    return [
        Tool(
            name="mail_search",
            description=(
                "Sucht/listet E-Mails. Ohne query: neueste Nachrichten des Ordners. Mit query: Volltextsuche "
                "(Absender, Betreff, Inhalt). Liefert Kurz-IDs (m1, m2 ...) für weitere Werkzeuge."
            ),
            input_schema=schema(
                {
                    "query": {"type": "string", "description": "Suchbegriff (optional)"},
                    "folder": {"type": "string", "description": "Ordnername, Standard 'inbox'"},
                    "unread_only": {"type": "boolean"},
                    "top": {"type": "integer", "description": "Anzahl, Standard 10, max 25"},
                }
            ),
            handler=m.mail_search,
        ),
        Tool(
            name="mail_read",
            description="Liest den vollständigen Text einer E-Mail anhand ihrer Kurz-ID.",
            input_schema=schema({"message_id": {"type": "string"}, "max_chars": {"type": "integer"}}, ["message_id"]),
            handler=m.mail_read,
        ),
        Tool(
            name="mail_send",
            description="Sendet eine neue E-Mail. Der Nutzer muss den Versand in einem Dialog bestätigen.",
            input_schema=schema(
                {
                    "to": {"type": "array", "items": {"type": "string"}, "description": "Empfängeradressen"},
                    "subject": {"type": "string"},
                    "body": {"type": "string", "description": "Reiner Text"},
                    "cc": {"type": "array", "items": {"type": "string"}},
                },
                ["to", "subject", "body"],
            ),
            handler=m.mail_send,
        ),
        Tool(
            name="mail_reply",
            description="Antwortet auf eine E-Mail (Kurz-ID). Der Nutzer muss den Versand bestätigen.",
            input_schema=schema(
                {"message_id": {"type": "string"}, "body": {"type": "string"}, "reply_all": {"type": "boolean"}},
                ["message_id", "body"],
            ),
            handler=m.mail_reply,
        ),
        Tool(
            name="mail_folders",
            description="Listet die E-Mail-Ordner mit Anzahl ungelesener Nachrichten.",
            input_schema=schema({}),
            handler=m.mail_folders,
        ),
        Tool(
            name="mail_move",
            description="Verschiebt eine E-Mail in einen Ordner (zum Ablegen/Ordnen). Fehlende Ordner werden angelegt.",
            input_schema=schema(
                {
                    "message_id": {"type": "string"},
                    "destination_folder": {"type": "string"},
                    "create_if_missing": {"type": "boolean", "description": "Standard true"},
                },
                ["message_id", "destination_folder"],
            ),
            handler=m.mail_move,
        ),
        Tool(
            name="mail_mark",
            description="Markiert eine E-Mail als gelesen/ungelesen oder setzt/entfernt die Kennzeichnung.",
            input_schema=schema(
                {"message_id": {"type": "string"}, "read": {"type": "boolean"}, "flagged": {"type": "boolean"}},
                ["message_id"],
            ),
            handler=m.mail_mark,
        ),
        Tool(
            name="calendar_events",
            description="Zeigt Kalendertermine ab heute (oder ab start_date) für die nächsten Tage.",
            input_schema=schema(
                {
                    "days_ahead": {"type": "integer", "description": "Standard 7, max 60"},
                    "start_date": {"type": "string", "description": "YYYY-MM-DD (optional)"},
                }
            ),
            handler=m.calendar_events,
        ),
        Tool(
            name="calendar_create_event",
            description="Legt einen Kalendertermin an. Mit Teilnehmern werden Einladungen versendet (Bestätigung nötig).",
            input_schema=schema(
                {
                    "subject": {"type": "string"},
                    "start": {"type": "string", "description": "Lokale Zeit YYYY-MM-DDTHH:MM:SS"},
                    "end": {"type": "string", "description": "Lokale Zeit YYYY-MM-DDTHH:MM:SS"},
                    "attendees": {"type": "array", "items": {"type": "string"}},
                    "location": {"type": "string"},
                    "body": {"type": "string"},
                },
                ["subject", "start", "end"],
            ),
            handler=m.calendar_create_event,
        ),
    ]
