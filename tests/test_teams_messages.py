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
