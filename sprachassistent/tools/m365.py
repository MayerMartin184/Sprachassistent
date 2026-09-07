"""Microsoft 365 über Microsoft Graph: E-Mail und Kalender.

Anmeldung per Device-Code-Flow (msal), Token-Cache im Datenverzeichnis.
Graph-IDs sind sehr lang; sie werden pro Sitzung auf Kurz-IDs (m1, m2, ...) abgebildet,
damit das Modell (und der Nutzer) bequem darauf verweisen kann.
"""

from __future__ import annotations

import logging
import sys
from datetime import datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

import msal
import requests

from .base import Tool, schema
from .teams import parse_vtt

log = logging.getLogger(__name__)

GRAPH = "https://graph.microsoft.com/v1.0"
SCOPES = [
    "User.Read",
    "Mail.ReadWrite",
    "Mail.Send",
    "Calendars.ReadWrite",
    "Tasks.ReadWrite",
    "OnlineMeetings.Read",
    "OnlineMeetingTranscript.Read.All",
]
MAIL_FIELDS = "id,subject,from,toRecipients,receivedDateTime,isRead,flag,bodyPreview,hasAttachments"
_SUCCESS_HTML = (
    "<html><body style='font-family:sans-serif;text-align:center;margin-top:15%'>"
    "<h2>Anmeldung erfolgreich</h2><p>Du kannst dieses Fenster schließen und zu Jarvis zurückkehren.</p>"
    "</body></html>"
)

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
    """Anmeldung bei Microsoft mit drei Wegen, in dieser Reihenfolge:

    1. Windows-Konto (Broker): nutzt die Anmeldung des Rechners, meist ohne Kennworteingabe.
    2. Browser: öffnet den Standardbrowser; besteht dort schon eine Microsoft-Sitzung, geht es ohne Kennwort.
    3. Gerätecode: Code in einem beliebigen Browser eingeben – auch in dem, in dem man schon angemeldet ist.
    """

    def __init__(
        self,
        client_id: str,
        tenant_id: str,
        cache_path: Path,
        notify: Notify,
        login_method: str = "auto",
        login_hint: str | None = None,
    ) -> None:
        self.cache_path = cache_path
        self.notify = notify
        self.login_method = (login_method or "auto").lower()
        self.login_hint = login_hint or None
        self._cache = msal.SerializableTokenCache()
        if cache_path.exists():
            self._cache.deserialize(cache_path.read_text(encoding="utf-8"))
        authority = f"https://login.microsoftonline.com/{tenant_id}"
        broker = sys.platform == "win32" and self.login_method in ("auto", "windows")
        try:
            self._app = msal.PublicClientApplication(
                client_id, authority=authority, token_cache=self._cache, enable_broker_on_windows=broker
            )
            self.broker = broker
        except Exception as exc:  # noqa: BLE001 - ohne Broker-Paket weiter ohne Windows-Anmeldung
            log.info("Windows-Anmeldung nicht verfügbar (%s) – Browser/Gerätecode", exc)
            self._app = msal.PublicClientApplication(client_id, authority=authority, token_cache=self._cache)
            self.broker = False

    def _save_cache(self) -> None:
        if self._cache.has_state_changed:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            self.cache_path.write_text(self._cache.serialize(), encoding="utf-8")

    def has_account(self) -> bool:
        return bool(self._app.get_accounts())

    def account_name(self) -> str | None:
        accounts = self._app.get_accounts()
        return accounts[0].get("username") if accounts else None

    def sign_out(self) -> str:
        for account in self._app.get_accounts():
            self._app.remove_account(account)
        self._save_cache()
        if self.cache_path.exists():
            self.cache_path.unlink()
        return "Microsoft-Anmeldung entfernt."

    def token(self) -> str:
        result = None
        accounts = self._app.get_accounts()
        if accounts:
            result = self._app.acquire_token_silent(SCOPES, account=accounts[0])
        if not result:
            result = self._login()
        if "access_token" not in result:
            raise RuntimeError(f"Microsoft-Anmeldung fehlgeschlagen: {result.get('error_description', result)}")
        self._save_cache()
        return result["access_token"]

    def login(self) -> str:
        """Anmeldung ausdrücklich starten (Knopf in den Einstellungen)."""
        self._login()
        self._save_cache()
        name = self.account_name()
        return f"Angemeldet als {name}." if name else "Anmeldung abgeschlossen."

    # --- Anmeldewege ---------------------------------------------------------------
    def _login(self) -> dict[str, Any]:
        errors: list[str] = []
        for step in self._steps():
            try:
                result = step()
            except Exception as exc:  # noqa: BLE001 - nächster Weg wird versucht
                log.info("Anmeldeweg fehlgeschlagen: %s", exc)
                errors.append(str(exc))
                continue
            if result and "access_token" in result:
                return result
            if result:
                detail = result.get("error_description") or result.get("error") or str(result)
                log.info("Anmeldeweg ohne Token: %s", detail)
                errors.append(str(detail).splitlines()[0])
        raise RuntimeError("Anmeldung nicht möglich. " + " | ".join(errors[-3:]))

    def _steps(self) -> list[Any]:
        if self.login_method == "devicecode":
            return [self._by_device_code]
        if self.login_method == "browser":
            return [self._by_browser, self._by_device_code]
        if self.login_method == "windows":
            return [self._by_broker, self._by_device_code]
        return [self._by_broker, self._by_browser, self._by_device_code]

    def _by_broker(self) -> dict[str, Any] | None:
        if not self.broker:
            return None
        self.notify("Anmeldung über das Windows-Konto – bitte im Windows-Fenster bestätigen.")
        return self._app.acquire_token_interactive(
            SCOPES,
            login_hint=self.login_hint,
            parent_window_handle=msal.PublicClientApplication.CONSOLE_WINDOW_HANDLE,
            timeout=180,
        )

    def _by_browser(self) -> dict[str, Any]:
        self.notify("Bitte im Browser bei Microsoft anmelden. Das Fenster öffnet sich gleich.")
        return self._app.acquire_token_interactive(
            SCOPES, login_hint=self.login_hint, timeout=300, success_template=_SUCCESS_HTML
        )

    def _by_device_code(self) -> dict[str, Any]:
        flow = self._app.initiate_device_flow(scopes=SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Gerätecode nicht möglich: {flow.get('error_description', flow)}")
        self.notify(
            "Anmeldung per Code: Öffne https://microsoft.com/devicelogin am besten in dem Browser, in dem du schon "
            f"bei Microsoft angemeldet bist, und gib diesen Code ein: {flow['user_code']}"
        )
        return self._app.acquire_token_by_device_flow(flow)

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
        self._ids: dict[str, dict[str, str]] = {}
        self._reverse: dict[str, dict[str, str]] = {}
        self._folder_cache: dict[str, str] = {}
        self._task_lists: dict[str, str] = {}
        self._meeting_urls: dict[str, str] = {}

    # --- Kurz-IDs -------------------------------------------------------
    def _short(self, graph_id: str, prefix: str = "m") -> str:
        ids = self._ids.setdefault(prefix, {})
        reverse = self._reverse.setdefault(prefix, {})
        if graph_id in reverse:
            return reverse[graph_id]
        short = f"{prefix}{len(ids) + 1}"
        ids[short] = graph_id
        reverse[graph_id] = short
        return short

    def _long(self, short: str, prefix: str = "m", hint: str = "mail_search") -> str:
        try:
            return self._ids.get(prefix, {})[short]
        except KeyError:
            raise KeyError(f"Unbekannte ID '{short}'. Erst {hint} verwenden.") from None

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
            self._ids["m"][message_id] = moved["id"]
            self._reverse["m"][moved["id"]] = message_id
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

    def calendar_upcoming(self, minutes: int) -> list[dict[str, Any]]:
        """Termine, die in den nächsten `minutes` Minuten beginnen (für proaktive Hinweise)."""
        now = datetime.now(self.tz)
        data = self.graph.request(
            "GET",
            "/me/calendarView",
            params={
                "startDateTime": now.isoformat(),
                "endDateTime": (now + timedelta(minutes=minutes)).isoformat(),
                "$orderby": "start/dateTime",
                "$top": 10,
                "$select": "id,subject,start,location,isAllDay,onlineMeeting",
            },
            headers={"Prefer": f'outlook.timezone="{self.tz.key}"'},
        )
        result = []
        for e in data.get("value", []):
            if e.get("isAllDay"):
                continue
            start = datetime.fromisoformat(e["start"]["dateTime"][:19]).replace(tzinfo=self.tz)
            if start >= now:
                result.append({"id": e["id"], "subject": e.get("subject"), "start": start,
                               "location": e.get("location", {}).get("displayName"), "online": bool(e.get("onlineMeeting"))})
        return result

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

    # --- Microsoft To Do --------------------------------------------------
    def _todo_lists(self) -> list[dict[str, Any]]:
        return self.graph.request("GET", "/me/todo/lists", params={"$top": 50}).get("value", [])

    def _todo_list_id(self, name: str | None, create: bool = False) -> tuple[str, str]:
        lists = self._todo_lists()
        if not name:
            default = next((l for l in lists if l.get("wellknownListName") == "defaultList"), lists[0] if lists else None)
            if default is None:
                raise RuntimeError("Keine To-Do-Liste gefunden.")
            return default["id"], default["displayName"]
        key = name.strip().lower()
        for l in lists:
            if l["displayName"].lower() == key:
                return l["id"], l["displayName"]
        if not create:
            raise KeyError(f"To-Do-Liste '{name}' nicht gefunden. Vorhandene: " + ", ".join(l["displayName"] for l in lists))
        created = self.graph.request("POST", "/me/todo/lists", json={"displayName": name.strip()})
        return created["id"], created["displayName"]

    def _fmt_todo(self, t: dict[str, Any], list_name: str) -> str:
        due = t.get("dueDateTime", {}).get("dateTime")
        due_txt = f" fällig {datetime.fromisoformat(due[:19]):%d.%m.%Y}" if due else ""
        imp = {"high": "hoch", "normal": "mittel", "low": "niedrig"}.get(t.get("importance", "normal"), "mittel")
        mark = "[x]" if t.get("status") == "completed" else "[ ]"
        body = " ".join((t.get("body", {}).get("content") or "").split())[:120]
        body_txt = f" – {body}" if body else ""
        return f"{mark} {self._short(t['id'], 't')} ({imp}){due_txt}: {t.get('title')}{body_txt}  [Liste: {list_name}]"

    def todo_lists(self) -> str:
        lists = self._todo_lists()
        return "To-Do-Listen:\n" + "\n".join(f"- {l['displayName']}" + (" (Standard)" if l.get("wellknownListName") == "defaultList" else "") for l in lists)

    def todo_list(self, list_name: str | None = None, include_completed: bool = False) -> str:
        list_id, name = self._todo_list_id(list_name)
        params: dict[str, Any] = {"$top": 100, "$orderby": "createdDateTime desc"}
        if not include_completed:
            params["$filter"] = "status ne 'completed'"
        tasks = self.graph.request("GET", f"/me/todo/lists/{list_id}/tasks", params=params).get("value", [])
        if not tasks:
            return f"Keine offenen Aufgaben in '{name}'."
        tasks.sort(key=lambda t: t.get("dueDateTime", {}).get("dateTime") or "9999")
        for t in tasks:
            self._task_lists[self._short(t["id"], "t")] = list_id
        return f"{len(tasks)} Aufgaben in '{name}':\n" + "\n".join(self._fmt_todo(t, name) for t in tasks)

    def todo_add(
        self,
        title: str,
        due: str | None = None,
        importance: str = "normal",
        notes: str | None = None,
        list_name: str | None = None,
        reminder: str | None = None,
    ) -> str:
        if importance not in ("low", "normal", "high"):
            raise ValueError("importance muss low, normal oder high sein")
        list_id, name = self._todo_list_id(list_name, create=True)
        task: dict[str, Any] = {"title": title.strip(), "importance": importance}
        if due:
            task["dueDateTime"] = {"dateTime": f"{due}T00:00:00", "timeZone": self.tz.key}
        if reminder:
            task["reminderDateTime"] = {"dateTime": reminder, "timeZone": self.tz.key}
            task["isReminderOn"] = True
        if notes:
            task["body"] = {"content": notes, "contentType": "text"}
        created = self.graph.request("POST", f"/me/todo/lists/{list_id}/tasks", json=task)
        self._task_lists[self._short(created["id"], "t")] = list_id
        return "In Microsoft To Do angelegt:\n" + self._fmt_todo(created, name)

    def todo_update(self, task_id: str, completed: bool | None = None, title: str | None = None, due: str | None = None, delete: bool = False) -> str:
        graph_id = self._long(task_id, "t", "todo_list")
        list_id = self._task_lists.get(task_id)
        if list_id is None:
            raise KeyError(f"Liste zu Aufgabe {task_id} unbekannt. Erst todo_list aufrufen.")
        path = f"/me/todo/lists/{list_id}/tasks/{graph_id}"
        if delete:
            self.graph.request("DELETE", path)
            return f"Aufgabe {task_id} gelöscht."
        patch: dict[str, Any] = {}
        if completed is not None:
            patch["status"] = "completed" if completed else "notStarted"
        if title:
            patch["title"] = title.strip()
        if due is not None:
            patch["dueDateTime"] = {"dateTime": f"{due}T00:00:00", "timeZone": self.tz.key} if due else None
        if not patch:
            return "Nichts zu ändern."
        updated = self.graph.request("PATCH", path, json=patch)
        return "Aktualisiert:\n" + self._fmt_todo(updated, "")

    # --- Teams-Besprechungen -----------------------------------------------
    def teams_meetings(self, days_back: int = 7) -> str:
        end = datetime.now(self.tz)
        start = end - timedelta(days=max(1, min(days_back, 60)))
        data = self.graph.request(
            "GET",
            "/me/calendarView",
            params={
                "startDateTime": start.isoformat(),
                "endDateTime": end.isoformat(),
                "$orderby": "start/dateTime desc",
                "$top": 50,
                "$select": "subject,start,end,isOnlineMeeting,onlineMeeting,organizer",
            },
            headers={"Prefer": f'outlook.timezone="{self.tz.key}"'},
        )
        meetings = [e for e in data.get("value", []) if e.get("isOnlineMeeting") and e.get("onlineMeeting", {}).get("joinUrl")]
        if not meetings:
            return f"Keine Teams-Besprechungen in den letzten {days_back} Tagen."
        lines = [f"Teams-Besprechungen der letzten {days_back} Tage (ID | Zeit | Thema):"]
        for e in meetings:
            short = self._short(e["onlineMeeting"]["joinUrl"], "mt")
            self._meeting_urls[short] = e["onlineMeeting"]["joinUrl"]
            s = datetime.fromisoformat(e["start"]["dateTime"][:19])
            lines.append(f"{short} | {s:%a %d.%m. %H:%M} | {e.get('subject')}")
        return "\n".join(lines)

    def teams_transcript(self, meeting_id: str, max_chars: int = 150_000) -> str:
        join_url = self._long(meeting_id, "mt", "teams_meetings")
        found = self.graph.request("GET", "/me/onlineMeetings", params={"$filter": f"JoinWebUrl eq '{join_url}'"}).get("value", [])
        if not found:
            return "Besprechung in Teams nicht gefunden (nur eigene oder als Teilnehmer besuchte Besprechungen sind abrufbar)."
        online_id = found[0]["id"]
        transcripts = self.graph.request("GET", f"/me/onlineMeetings/{online_id}/transcripts").get("value", [])
        if not transcripts:
            return "Für diese Besprechung liegt kein Transkript vor. Die Transkription muss in Teams während der Sitzung eingeschaltet sein."
        transcripts.sort(key=lambda t: t.get("createdDateTime", ""), reverse=True)
        token = self.graph.token()
        resp = requests.get(
            f"{GRAPH}/me/onlineMeetings/{online_id}/transcripts/{transcripts[0]['id']}/content",
            params={"$format": "text/vtt"},
            headers={"Authorization": f"Bearer {token}"},
            timeout=120,
        )
        if resp.status_code >= 400:
            raise RuntimeError(f"Transkript konnte nicht geladen werden ({resp.status_code}): {resp.text[:300]}")
        text = parse_vtt(resp.text)
        if len(text) > max_chars:
            text = text[:max_chars] + f"\n... [gekürzt, {len(text)} Zeichen gesamt]"
        return f"Transkript ({len(text)} Zeichen):\n{text}"


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
        Tool(
            name="todo_lists",
            description="Zeigt die Listen in Microsoft To Do.",
            input_schema=schema({}),
            handler=m.todo_lists,
        ),
        Tool(
            name="todo_list",
            description="Zeigt Aufgaben aus Microsoft To Do (Standardliste oder benannte Liste) mit Kurz-IDs (t1, t2 ...).",
            input_schema=schema({"list_name": {"type": "string"}, "include_completed": {"type": "boolean"}}),
            handler=m.todo_list,
        ),
        Tool(
            name="todo_add",
            description=(
                "Legt eine Aufgabe in Microsoft To Do an. Fehlende Listen werden angelegt. "
                "due als YYYY-MM-DD, reminder als lokale Zeit YYYY-MM-DDTHH:MM:SS."
            ),
            input_schema=schema(
                {
                    "title": {"type": "string"},
                    "due": {"type": "string"},
                    "importance": {"type": "string", "enum": ["low", "normal", "high"]},
                    "notes": {"type": "string"},
                    "list_name": {"type": "string", "description": "Leer = Standardliste 'Aufgaben'"},
                    "reminder": {"type": "string"},
                },
                ["title"],
            ),
            handler=m.todo_add,
        ),
        Tool(
            name="todo_update",
            description="Erledigt (completed=true), ändert oder löscht eine To-Do-Aufgabe anhand ihrer Kurz-ID aus todo_list/todo_add.",
            input_schema=schema(
                {
                    "task_id": {"type": "string"},
                    "completed": {"type": "boolean"},
                    "title": {"type": "string"},
                    "due": {"type": "string", "description": "YYYY-MM-DD, leer entfernt die Fälligkeit"},
                    "delete": {"type": "boolean"},
                },
                ["task_id"],
            ),
            handler=m.todo_update,
        ),
        Tool(
            name="teams_meetings",
            description="Listet vergangene Teams-Besprechungen aus dem Kalender mit Kurz-IDs (mt1, mt2 ...).",
            input_schema=schema({"days_back": {"type": "integer", "description": "Standard 7, max 60"}}),
            handler=m.teams_meetings,
        ),
        Tool(
            name="teams_transcript",
            description=(
                "Lädt das Transkript einer Teams-Besprechung als Text (Sprecher: Aussage). Danach zusammenfassen: "
                "Ergebnisse, Entscheidungen, offene Punkte des Nutzers."
            ),
            input_schema=schema({"meeting_id": {"type": "string"}, "max_chars": {"type": "integer"}}, ["meeting_id"]),
            handler=m.teams_transcript,
        ),
    ]
