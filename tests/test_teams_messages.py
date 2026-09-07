"""Teams-Nachrichten: Auswahl der Empfänger, Bestätigung und Formatierung – ohne Netzwerk."""

import pytest

from sprachassistent.tools.m365 import M365Tools


class FakeGraph:
    def __init__(self, responses: dict) -> None:
        self.responses = responses
        self.calls: list[tuple] = []

    def request(self, method, path, params=None, json=None, headers=None):  # noqa: ANN001, A002
        self.calls.append((method, path, json))
        # längster passender Pfad gewinnt, damit "/me" nicht "/me/chats" abfängt
        for (m, p), value in sorted(self.responses.items(), key=lambda kv: -len(kv[0][1])):
            if m == method and p in path:
                return value
        return {}


def _tools(responses, confirm=lambda _m: True):
    return M365Tools(FakeGraph(responses), confirm, "Europe/Berlin")


def test_chat_title_prefers_topic_then_partners():
    m = _tools({("GET", "/me"): {"id": "me"}})
    assert m._chat_title({"topic": "Projekt X"}) == "Projekt X"
    chat = {"chatType": "oneOnOne", "members": [{"userId": "me", "displayName": "Ich"}, {"userId": "u2", "displayName": "Anna"}]}
    assert m._chat_title(chat) == "Anna"
    assert m._chat_title({"chatType": "group", "members": []}) == "Gruppenchat"


def test_send_chat_to_person_reuses_existing_chat():
    m = _tools({
        ("GET", "/me"): {"id": "me"},
        ("GET", "/users"): {"value": [{"id": "u2", "displayName": "Anna Schmidt", "mail": "anna@firma.de"}]},
        ("GET", "/me/chats"): {"value": [{"id": "chat-1", "members": [{"userId": "u2"}]}]},
    })
    assert "Anna Schmidt" in m.teams_send_chat("Bis Dienstag!", to="Anna")
    posts = [c for c in m.graph.calls if c[0] == "POST"]
    assert posts and posts[-1][1] == "/chats/chat-1/messages"
    assert posts[-1][2]["body"]["content"] == "Bis Dienstag!"


def test_send_chat_is_not_sent_without_confirmation():
    m = _tools({
        ("GET", "/me"): {"id": "me"},
        ("GET", "/users"): {"value": [{"id": "u2", "displayName": "Anna", "mail": "a@f.de"}]},
        ("GET", "/me/chats"): {"value": [{"id": "chat-1", "members": [{"userId": "u2"}]}]},
    }, confirm=lambda _m: False)
    assert "abgelehnt" in m.teams_send_chat("Text", to="Anna")
    assert not [c for c in m.graph.calls if c[0] == "POST"]


def test_ambiguous_person_asks_back():
    m = _tools({
        ("GET", "/me"): {"id": "me"},
        ("GET", "/users"): {"value": [
            {"id": "1", "displayName": "Anna Schmidt", "mail": "anna.s@f.de"},
            {"id": "2", "displayName": "Anna Weber", "mail": "anna.w@f.de"},
        ]},
    })
    with pytest.raises(KeyError, match="Mehrere Personen"):
        m.teams_send_chat("Hallo", to="Anna")


def test_channel_message_needs_known_team():
    m = _tools({
        ("GET", "/me/joinedTeams"): {"value": [{"id": "team-1", "displayName": "Elektroplanung"}]},
        ("GET", "/channels"): {"value": [{"id": "chan-1", "displayName": "Allgemein"}]},
    })
    assert "tm1" in m.teams_list_teams()
    with pytest.raises(KeyError, match="Unbekannte ID"):
        m.teams_send_channel("ch1", "Text")  # ohne vorheriges Auflisten
    assert "ch1" in m.teams_channels("tm1")
    m._channel_teams.clear()  # Zuordnung Kanal -> Team verloren
    with pytest.raises(KeyError, match="kein Team bekannt"):
        m.teams_send_channel("ch1", "Text")
    m.teams_channels("tm1")
    assert "gepostet" in m.teams_send_channel("ch1", "Kurzinfo", subject="Status")
    posts = [c for c in m.graph.calls if c[0] == "POST"]
    assert posts[-1][1] == "/teams/team-1/channels/chan-1/messages" and posts[-1][2]["subject"] == "Status"


def test_planner_add_task_with_due_bucket_and_assignment():
    m = _tools({
        ("GET", "/me"): {"id": "me"},
        ("GET", "/me/joinedTeams"): {"value": [{"id": "group-1", "displayName": "Elektroplanung"}]},
        ("GET", "/groups/group-1/planner/plans"): {"value": [{"id": "plan-1", "title": "Projekte"}]},
        ("GET", "/planner/plans/plan-1/buckets"): {"value": [{"id": "bucket-1", "name": "Diese Woche"}]},
        ("GET", "/users"): {"value": [{"id": "u2", "displayName": "Anna Schmidt", "mail": "anna@f.de"}]},
        ("POST", "/planner/tasks"): {"id": "task-1", "title": "Angebot prüfen"},
        ("GET", "/planner/tasks/task-1/details"): {"@odata.etag": 'W/"1"'},
    })
    m.teams_list_teams()
    assert "p1" in m.planner_plans("tm1")
    msg = m.planner_add_task("p1", "Angebot prüfen", due="2026-09-11", bucket="Diese Woche", assign_to="Anna", notes="Details")
    post = [c for c in m.graph.calls if c[0] == "POST" and c[1] == "/planner/tasks"][0][2]
    assert post["planId"] == "plan-1" and post["bucketId"] == "bucket-1"
    assert post["dueDateTime"].startswith("2026-09-11") and post["dueDateTime"].endswith("Z")
    assert "u2" in post["assignments"] and "Anna Schmidt" in msg
    assert any(c[0] == "PATCH" and c[1].endswith("/details") for c in m.graph.calls)


def test_planner_task_needs_confirmation_for_assignment():
    m = _tools({
        ("GET", "/me/joinedTeams"): {"value": [{"id": "group-1", "displayName": "T"}]},
        ("GET", "/groups/group-1/planner/plans"): {"value": [{"id": "plan-1", "title": "P"}]},
        ("GET", "/users"): {"value": [{"id": "u2", "displayName": "Anna", "mail": "a@f.de"}]},
    }, confirm=lambda _m: False)
    m.teams_list_teams(); m.planner_plans("tm1")
    assert "abgelehnt" in m.planner_add_task("p1", "Aufgabe", assign_to="Anna")
    assert not [c for c in m.graph.calls if c[0] == "POST" and c[1] == "/planner/tasks"]


def test_planner_missing_plan_explains_next_step():
    m = _tools({
        ("GET", "/me/joinedTeams"): {"value": [{"id": "group-1", "displayName": "T"}]},
        ("GET", "/groups/group-1/planner/plans"): {"value": []},
    })
    m.teams_list_teams()
    assert "Reiter" in m.planner_plans("tm1")


def test_planner_update_uses_etag():
    m = _tools({
        ("GET", "/me/joinedTeams"): {"value": [{"id": "g", "displayName": "T"}]},
        ("GET", "/groups/g/planner/plans"): {"value": [{"id": "plan-1", "title": "P"}]},
        ("GET", "/planner/plans/plan-1/tasks"): {"value": [{"id": "task-9", "title": "Offen", "percentComplete": 0}]},
        ("GET", "/planner/tasks/task-9"): {"@odata.etag": 'W/"7"'},
    })
    m.teams_list_teams(); m.planner_plans("tm1")
    assert "pt1" in m.planner_tasks("p1")
    assert "aktualisiert" in m.planner_update_task("pt1", completed=True)
    patch = [c for c in m.graph.calls if c[0] == "PATCH"][0]
    assert patch[1] == "/planner/tasks/task-9" and patch[2] == {"percentComplete": 100}
