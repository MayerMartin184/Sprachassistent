"""Automatische Einrichtung der Microsoft-App-Registrierung über Microsoft Graph.

Der Nutzer meldet sich einmal als Administrator an (Gerätecode über Microsofts eigene
„Microsoft Graph Command Line Tools“-App). Danach wird die Jarvis-App angelegt oder korrigiert:
Umleitungsadresse http://localhost, öffentlicher Client, Graph-Berechtigungen, Administrator-Zustimmung.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Callable

import msal
import requests

from .m365 import GRAPH, SCOPES

log = logging.getLogger(__name__)

# Microsofts eigene, in jedem Tenant vorhandene Verwaltungs-App (wie PowerShell "Connect-MgGraph")
GRAPH_CLI_CLIENT_ID = "14d82eec-204b-4c2f-b7e8-296a70dab67e"
GRAPH_APP_ID = "00000003-0000-0000-c000-000000000000"
SETUP_SCOPES = ["Application.ReadWrite.All", "DelegatedPermissionGrant.ReadWrite.All", "Directory.Read.All"]
APP_NAME = "Jarvis Sprachassistent"
REDIRECT = "http://localhost"
BROKER_REDIRECT = "ms-appx-web://Microsoft.AAD.BrokerPlugin/{client_id}"  # Anmeldung über das Windows-Konto


class M365Setup:
    def __init__(self, tenant_id: str, notify: Callable[[str], None]) -> None:
        tenant = tenant_id if tenant_id and tenant_id != "common" else "organizations"
        self.app = msal.PublicClientApplication(GRAPH_CLI_CLIENT_ID, authority=f"https://login.microsoftonline.com/{tenant}")
        self.notify = notify
        self.token: str | None = None

    # --- Anmeldung ----------------------------------------------------------------
    def login(self) -> None:
        flow = self.app.initiate_device_flow(scopes=SETUP_SCOPES)
        if "user_code" not in flow:
            raise RuntimeError(f"Anmeldung nicht möglich: {flow.get('error_description', flow)}")
        self.notify(
            "Einrichtung: Bitte im Browser https://microsoft.com/devicelogin öffnen und diesen Code eingeben: "
            f"{flow['user_code']}  – mit deinem Administrator-Konto anmelden und den Berechtigungen zustimmen."
        )
        result = self.app.acquire_token_by_device_flow(flow)
        if "access_token" not in result:
            raise RuntimeError(f"Anmeldung fehlgeschlagen: {result.get('error_description', result)}")
        self.token = result["access_token"]

    def _req(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        resp = requests.request(method, f"{GRAPH}{path}", headers=headers, timeout=30, **kwargs)
        if resp.status_code >= 400:
            try:
                detail = resp.json().get("error", {}).get("message", resp.text)
            except ValueError:
                detail = resp.text
            raise RuntimeError(f"Graph {method} {path} -> {resp.status_code}: {detail}")
        return resp.json() if resp.content else {}

    # --- Schritte ------------------------------------------------------------------
    def graph_service_principal(self) -> dict[str, Any]:
        data = self._req("GET", "/servicePrincipals", params={"$filter": f"appId eq '{GRAPH_APP_ID}'"})
        if not data.get("value"):
            raise RuntimeError("Microsoft-Graph-Dienstprinzipal nicht gefunden.")
        return data["value"][0]

    def scope_ids(self, graph_sp: dict[str, Any]) -> dict[str, str]:
        by_value = {s["value"]: s["id"] for s in graph_sp.get("oauth2PermissionScopes", [])}
        missing = [s for s in SCOPES if s not in by_value]
        if missing:
            raise RuntimeError(f"Berechtigungen unbekannt: {missing}")
        return {s: by_value[s] for s in SCOPES}

    def find_app(self, client_id: str | None) -> dict[str, Any] | None:
        if client_id:
            data = self._req("GET", "/applications", params={"$filter": f"appId eq '{client_id}'"})
            if data.get("value"):
                return data["value"][0]
        data = self._req("GET", "/applications", params={"$filter": f"displayName eq '{APP_NAME}'", "$orderby": "createdDateTime"})
        return data["value"][0] if data.get("value") else None

    def desired_body(self, scope_ids: dict[str, str]) -> dict[str, Any]:
        return {
            "displayName": APP_NAME,
            "signInAudience": "AzureADMyOrg",
            "isFallbackPublicClient": True,
            "publicClient": {"redirectUris": [REDIRECT]},  # Broker-Adresse folgt, sobald die appId bekannt ist
            "requiredResourceAccess": [
                {"resourceAppId": GRAPH_APP_ID, "resourceAccess": [{"id": sid, "type": "Scope"} for sid in scope_ids.values()]}
            ],
        }

    def ensure_app(self, client_id: str | None, scope_ids: dict[str, str]) -> tuple[dict[str, Any], bool]:
        body = self.desired_body(scope_ids)
        app = self.find_app(client_id)
        if app is None:
            app = self._req("POST", "/applications", json=body)
            time.sleep(3)  # Verzeichnis braucht einen Moment
            self._ensure_redirects(app["id"], app["appId"], set())
            return app, True
        patch = {k: v for k, v in body.items() if k not in ("displayName", "publicClient")}
        self._req("PATCH", f"/applications/{app['id']}", json=patch)
        self._ensure_redirects(app["id"], app["appId"], set(app.get("publicClient", {}).get("redirectUris", [])))
        return app, False

    def _ensure_redirects(self, object_id: str, app_id: str, existing: set[str]) -> None:
        """http://localhost (Browser) und die Broker-Adresse (Windows-Konto) eintragen, Vorhandenes behalten."""
        wanted = existing | {REDIRECT, BROKER_REDIRECT.format(client_id=app_id)}
        self._req("PATCH", f"/applications/{object_id}", json={"publicClient": {"redirectUris": sorted(wanted)}})

    def ensure_service_principal(self, app_id: str) -> dict[str, Any]:
        data = self._req("GET", "/servicePrincipals", params={"$filter": f"appId eq '{app_id}'"})
        if data.get("value"):
            return data["value"][0]
        for attempt in range(5):
            try:
                return self._req("POST", "/servicePrincipals", json={"appId": app_id})
            except RuntimeError as exc:
                if attempt == 4:
                    raise
                log.info("Dienstprinzipal noch nicht anlegbar (%s), erneuter Versuch …", exc)
                time.sleep(3)
        raise RuntimeError("Dienstprinzipal konnte nicht angelegt werden.")

    def grant_admin_consent(self, sp_id: str, graph_sp_id: str) -> None:
        scope = " ".join(SCOPES)
        data = self._req(
            "GET", "/oauth2PermissionGrants",
            params={"$filter": f"clientId eq '{sp_id}' and resourceId eq '{graph_sp_id}' and consentType eq 'AllPrincipals'"},
        )
        if data.get("value"):
            self._req("PATCH", f"/oauth2PermissionGrants/{data['value'][0]['id']}", json={"scope": scope})
        else:
            self._req("POST", "/oauth2PermissionGrants",
                      json={"clientId": sp_id, "consentType": "AllPrincipals", "resourceId": graph_sp_id, "scope": scope})

    # --- Gesamtablauf -----------------------------------------------------------------
    def run(self, client_id: str | None) -> dict[str, Any]:
        self.login()
        graph_sp = self.graph_service_principal()
        ids = self.scope_ids(graph_sp)
        app, created = self.ensure_app(client_id, ids)
        sp = self.ensure_service_principal(app["appId"])
        self.grant_admin_consent(sp["id"], graph_sp["id"])
        tenant = self._req("GET", "/organization").get("value", [{}])[0].get("id")
        return {"client_id": app["appId"], "tenant_id": tenant, "created": created}
