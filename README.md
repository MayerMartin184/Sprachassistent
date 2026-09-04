# Sprachassistent

Sprachgesteuerter Desktop-Assistent (Windows/macOS), der Arbeiten selbstständig übernimmt:
Aufgaben verwalten und abarbeiten, im Web recherchieren, Listen führen, E-Mails lesen, beantworten,
ordnen und ablegen, Kalender prüfen und Termine anlegen, Dateien im Ablageordner ordnen.

- **Denken:** Claude (Anthropic API) mit Werkzeugaufrufen und integrierter Websuche
- **Sprache:** Azure Speech (Spracherkennung und Sprachausgabe, Deutsch)
- **E-Mail/Kalender:** Microsoft 365 über Microsoft Graph
- **Oberfläche:** Push-to-Talk-Fenster (Tkinter) oder Textmodus im Terminal

## Aufbau

```
sprachassistent/
  __main__.py      Einstieg (GUI / --cli)
  app.py           Tkinter-Fenster: Sprechtaste, Verlauf, Bestätigungsdialoge
  assistant.py     Verdrahtung Einstellungen -> Werkzeuge -> Agent -> Sprache
  config.py        Einstellungen aus .env / Umgebungsvariablen
  agent/agent.py   Claude-Werkzeugschleife (Client-Werkzeuge + web_search/web_fetch)
  agent/prompts.py System-Prompt
  audio/io.py      Mikrofonaufnahme, Wiedergabe
  speech/azure.py  Azure Speech REST (STT/TTS)
  tools/tasks.py   Aufgaben (lokal, JSON)
  tools/lists.py   Listen (lokal, JSON)
  tools/files.py   Dateiablage, begrenzt auf DOCUMENTS_ROOT
  tools/m365.py    Mail + Kalender über Graph, Kurz-IDs (m1, m2 ...)
tests/             Unit-Tests ohne API-Aufrufe
```

Ablauf einer Anfrage: Sprechtaste halten -> WAV -> Azure STT -> Text -> Claude-Werkzeugschleife
-> Antworttext -> Azure TTS -> Wiedergabe. Versand von E-Mails, Antworten und Einladungen
verlangt immer eine Bestätigung im Dialog.

## Installation

Voraussetzung: Python 3.10 oder neuer.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS: source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

`sounddevice` benötigt PortAudio; unter Windows und macOS liegt es dem pip-Paket bei.

## Konfiguration (.env)

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `ANTHROPIC_API_KEY` | ja | Claude-API-Schlüssel |
| `ASSISTANT_MODEL` | nein | Standard `claude-opus-5` |
| `ASSISTANT_EFFORT` | nein | `low`…`max`, Standard `medium` |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | für Sprache | Ohne diese Werte läuft die App nur mit Texteingabe |
| `SPEECH_LANGUAGE`, `TTS_VOICE` | nein | Standard `de-DE`, `de-DE-KatjaNeural` |
| `MS_CLIENT_ID`, `MS_TENANT_ID` | für Mail/Kalender | Ohne `MS_CLIENT_ID` sind die Microsoft-Werkzeuge deaktiviert |
| `DOCUMENTS_ROOT` | nein | Ablageordner, Standard `~/Documents`; außerhalb fasst der Assistent nichts an |
| `TIMEZONE` | nein | Standard `Europe/Berlin` |

### Azure Speech einrichten

1. Im Azure-Portal eine Ressource „Speech“ anlegen (z. B. Region `germanywestcentral`).
2. Schlüssel und Region in `.env` eintragen.

### Microsoft 365 einrichten (App-Registrierung)

1. Entra ID (Azure AD) -> App-Registrierungen -> „Neue Registrierung“.
2. Unterstützte Kontotypen: passend zum Konto (Firma: „nur dieses Verzeichnis“, dann `MS_TENANT_ID` = Tenant-ID; privat/gemischt: `common`).
3. Authentifizierung -> „Öffentliche Clientflows zulassen“ auf **Ja** (nötig für den Device-Code-Flow).
4. API-Berechtigungen (Microsoft Graph, delegiert): `User.Read`, `Mail.ReadWrite`, `Mail.Send`, `Calendars.ReadWrite`.
5. Anwendungs-ID (Client) als `MS_CLIENT_ID` eintragen.

Beim ersten Mail-/Kalenderzugriff zeigt die App einen Code und eine URL an. Nach der Anmeldung im
Browser wird das Token in `~/.sprachassistent/ms_token_cache.json` gespeichert.

## Start

```bash
python -m sprachassistent          # Desktop-Fenster
python -m sprachassistent --cli    # Textmodus im Terminal (kein Mikrofon nötig)
python -m sprachassistent -v       # mit ausführlichem Protokoll
```

Bedienung: Sprechtaste oder Leertaste halten, sprechen, loslassen. Alternativ Text eingeben.
Aufnahmen sind auf 60 Sekunden begrenzt (Azure-REST-Erkennung).

Beispiele:
- „Lege eine Aufgabe an: Angebot für Müller bis Freitag, hohe Priorität.“
- „Was steht heute an?“ (Aufgaben und Kalender)
- „Recherchiere die drei größten Anbieter für Photovoltaik-Speicher in Bayern und speichere das als Datei.“
- „Setz Milch und Kaffee auf die Einkaufsliste.“
- „Zeig mir ungelesene Mails von Schmidt.“ -> „Lies m2 vor.“ -> „Antworte, dass ich am Dienstag Zeit habe.“
- „Verschiebe alle Mails von Rechnung@… in den Ordner Buchhaltung.“
- „Räume den Downloads-Ordner auf: PDFs nach Dokumente/PDF, Bilder nach Bilder.“

## Daten

Alles Lokale liegt in `~/.sprachassistent/`: `tasks.json`, `lists.json`, `ms_token_cache.json`.
Der Gesprächsverlauf wird nur im Speicher gehalten und endet mit dem Schließen der App.

## Tests

```bash
pytest
```

## Grenzen der ersten Version

- Push-to-Talk statt Wake-Word; keine globale Hotkey-Erfassung außerhalb des Fensters.
- Microsoft To Do und OneDrive sind nicht angebunden; Aufgaben und Listen liegen lokal.
- Anhänge werden erkannt, aber nicht gelesen oder gesendet.
