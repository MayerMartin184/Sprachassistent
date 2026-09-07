"""Anmeldekette von Microsoft 365 ohne Netzwerk prüfen."""

import pytest

from sprachassistent.tools.m365 import GraphClient


def _client(method: str) -> GraphClient:
    client = object.__new__(GraphClient)
    client.login_method = method
    client.login_hint = "m.mayer@me-concept.de"
    client.broker = True
    client.notify = lambda _m: None
    return client


def test_step_order_per_method():
    names = lambda c: [s.__name__ for s in c._steps()]  # noqa: E731
    assert names(_client("auto")) == ["_by_broker", "_by_browser", "_by_device_code"]
    assert names(_client("windows")) == ["_by_broker", "_by_device_code"]
    assert names(_client("browser")) == ["_by_browser", "_by_device_code"]
    assert names(_client("devicecode")) == ["_by_device_code"]


def test_login_falls_through_to_device_code(monkeypatch):
    client = _client("auto")
    used: list[str] = []

    def broker():
        used.append("broker")
        raise RuntimeError("kein Broker-Paket")

    def browser():
        used.append("browser")
        return {"error": "invalid_grant", "error_description": "Das Kennwort ist nicht korrekt."}

    def device():
        used.append("device")
        return {"access_token": "tok"}

    monkeypatch.setattr(client, "_by_broker", broker)
    monkeypatch.setattr(client, "_by_browser", browser)
    monkeypatch.setattr(client, "_by_device_code", device)
    assert client._login()["access_token"] == "tok"
    assert used == ["broker", "browser", "device"]


def test_login_reports_all_errors_when_nothing_works(monkeypatch):
    client = _client("browser")
    monkeypatch.setattr(client, "_by_browser", lambda: {"error_description": "Kennwort falsch"})
    monkeypatch.setattr(client, "_by_device_code", lambda: {"error_description": "abgelaufen"})
    with pytest.raises(RuntimeError, match="Kennwort falsch"):
        client._login()


def test_broker_step_is_skipped_when_unavailable():
    client = _client("auto")
    client.broker = False
    assert client._by_broker() is None
