# Jarvis – Sprachassistent

Sprachgesteuerter Desktop-Assistent (Windows/macOS). „Hey Jarvis“ sagen, Auftrag sprechen, fertig.
Er übernimmt Arbeiten selbstständig, denkt mit und gibt Ratschläge:

- **Aufgaben** in Microsoft To Do anlegen, verfolgen, erledigen (mit Rückfrage bei fehlenden Angaben)
- **Recherche** im Web, Ergebnisse als Datei ablegen
- **Listen** (Einkauf, Ideen, Packliste …)
- **E-Mail**: lesen, beantworten, ordnen, ablegen (Versand immer mit Bestätigung)
- **Kalender**: Termine anzeigen und anlegen
- **Teams-Besprechungen**: Transkript laden, kurz zusammenfassen, offene Punkte als To-Do anlegen
- **Dateiablage**: suchen, verschieben, Ordner anlegen, Notizen schreiben (nur im Ablageordner)
- **Webcam**: auf Zuruf ein Bild aufnehmen und dazu beraten („Jarvis, schau dir das Dokument an“)

Technik: Claude (Anthropic API) als Agent mit Werkzeugen und integrierter Websuche, openWakeWord
für „Hey Jarvis“ (lokal, CPU), Azure Speech für Spracherkennung und Sprachausgabe, Microsoft Graph für
To Do, Mail, Kalender und Teams.

**Neu hier?** Siehe [SCHNELLSTART.md](SCHNELLSTART.md) für eine Schritt-für-Schritt-Anleitung ohne Vorkenntnisse.

## Aufbau

```
sprachassistent/
  __main__.py        Einstieg (Fenster / --cli)
  app.py             Fenster: pulsierender Zustandskreis, Verlauf, Texteingabe, Mikrofon-Schalter
Installieren.bat     Windows: Einrichtung per Doppelklick + Desktop-Verknüpfung
Jarvis.bat           Windows: Start ohne Konsolenfenster
Aktualisieren.bat    Windows: neueste Version von GitHub holen, .env bleibt erhalten
  assistant.py       Verdrahtung Einstellungen -> Werkzeuge -> Agent -> Sprache
  config.py          Einstellungen aus .env / Umgebungsvariablen
  agent/agent.py     Claude-Werkzeugschleife (eigene Werkzeuge + web_search/web_fetch)
  agent/prompts.py   Persona und Arbeitsregeln
  audio/io.py        Aufnahme/Wiedergabe (16 kHz mono)
  audio/wakeword.py  „Hey Jarvis“-Erkennung, Aufnahme bis zur Sprechpause
  speech/azure.py    Azure Speech REST (STT/TTS)
  tools/m365.py      To Do, Mail, Kalender, Teams-Transkripte über Graph (Kurz-IDs t1/m1/mt1)
  tools/teams.py     WebVTT-Transkript -> „Sprecher: Text“
  tools/webcam.py    Schnappschuss als Bild für Claude
  tools/files.py     Dateiablage, begrenzt auf DOCUMENTS_ROOT
  tools/lists.py     Listen (lokal)
  tools/tasks.py     Aufgaben lokal (nur ohne Microsoft 365)
tests/               Unit-Tests ohne API-Aufrufe
```

Ablauf: Mikrofon hört dauerhaft lokal auf „Hey Jarvis“ -> Bestätigungston -> Aufnahme bis ca. 1,2 s
Pause -> Azure STT -> Claude-Werkzeugschleife -> Antwort -> Azure TTS. Während Jarvis spricht oder
arbeitet, ist das Wake-Word stumm geschaltet. Der Mikrofon-Schalter im Fenster schaltet das Zuhören ab.

## Installation

Voraussetzung: Python 3.10 oder neuer.

**Windows, ohne Kommandozeile:** `Installieren.bat` doppelklicken (richtet alles ein und legt eine
Desktop-Verknüpfung an), danach `Jarvis.bat` bzw. die Verknüpfung „Jarvis“ zum Starten.

**Manuell:**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate   macOS: source .venv/bin/activate
pip install -e ".[dev,webcam]"
cp .env.example .env
```

Beim ersten Start lädt openWakeWord die Modelldateien (wenige MB) herunter.

## Konfiguration (.env)

| Variable | Pflicht | Bedeutung |
|---|---|---|
| `ANTHROPIC_API_KEY` | ja | Claude-API-Schlüssel |
| `ASSISTANT_MODEL`, `ASSISTANT_EFFORT` | nein | Standard `claude-opus-5`, `medium` |
| `AZURE_SPEECH_KEY`, `AZURE_SPEECH_REGION` | für Sprache | Ohne diese Werte nur Texteingabe |
| `SPEECH_LANGUAGE`, `TTS_VOICE` | nein | Standard `de-DE`, `de-DE-KatjaNeural` |
| `WAKE_WORD_ENABLED`, `WAKE_WORD_MODEL`, `WAKE_WORD_THRESHOLD` | nein | Standard `true`, `hey_jarvis`, `0.5` |
| `ASSISTANT_NAME` | nein | Anredename, Standard `Jarvis` |
| `WEBCAM_ENABLED`, `WEBCAM_INDEX` | nein | Standard `true`, `0` |
| `BRAND_BG`, `BRAND_PANEL`, `BRAND_PRIMARY`, `BRAND_ACCENT`, `BRAND_TEXT`, `BRAND_MUTED` | nein | Hex-Farben der Oberfläche (Firmen-CI) |
| `BRAND_FONT`, `BRAND_TITLE`, `LOGO_PATH` | nein | Schriftart, Untertitel im Kopf, PNG-Logo |
| `MS_CLIENT_ID`, `MS_TENANT_ID` | für Microsoft 365 | Ohne `MS_CLIENT_ID` laufen Aufgaben lokal, Mail/Kalender/Teams sind aus |
| `DOCUMENTS_ROOT` | nein | Ablageordner, Standard `~/Documents` |
| `TIMEZONE` | nein | Standard `Europe/Berlin` |

### Azure Speech einrichten

1. Azure-Portal -> Ressource „Speech“ anlegen (z. B. Region `germanywestcentral`).
2. Schlüssel und Region in `.env` eintragen.

### Microsoft 365 einrichten (App-Registrierung)

1. Entra ID (Azure AD) -> App-Registrierungen -> „Neue Registrierung“.
2. Kontotypen: Firma -> „nur dieses Verzeichnis“ (dann `MS_TENANT_ID` = Tenant-ID); privat/gemischt -> `common`.
3. Authentifizierung -> „Plattform hinzufügen“ -> „Mobile Anwendungen und Desktopanwendungen“ -> `http://localhost` anhaken (Browser-Anmeldung).
4. API-Berechtigungen (Microsoft Graph, delegiert): `User.Read`, `Mail.ReadWrite`, `Mail.Send`,
   `Calendars.ReadWrite`, `Tasks.ReadWrite`, `OnlineMeetings.Read`, `OnlineMeetingTranscript.Read.All`.
   Für `OnlineMeetingTranscript.Read.All` ist in Firmen-Tenants meist eine Administrator-Zustimmung nötig.
5. Anwendungs-ID (Client) als `MS_CLIENT_ID` eintragen.

Beim ersten Zugriff öffnet sich der Browser zur Microsoft-Anmeldung (Ausweichweg: Gerätecode). Danach liegt das
Token in `~/.sprachassistent/ms_token_cache.json`. Nach Änderung der Berechtigungen diese Datei löschen
und neu anmelden.

### Teams-Transkripte

Voraussetzung: Die Transkription war in der Besprechung eingeschaltet (in Teams „Transkription starten“,
oder per Besprechungsrichtlinie automatisch). Abrufbar sind Besprechungen aus dem eigenen Kalender.

## Start

```bash
python -m sprachassistent          # Fenster mit Wake-Word
python -m sprachassistent --cli    # Textmodus im Terminal (kein Mikrofon nötig)
python -m sprachassistent -v       # ausführliches Protokoll
```

Beispiele:
- „Hey Jarvis, leg eine Aufgabe an: Angebot für Müller bis Freitag, wichtig.“
- „Hey Jarvis, was steht heute an?“ (To Do und Kalender)
- „Hey Jarvis, fass die Teams-Besprechung von heute Morgen zusammen. Was muss ich noch erledigen?“
- „Hey Jarvis, recherchiere Anbieter für Photovoltaik-Speicher in Bayern und speichere das als Datei.“
- „Hey Jarvis, zeig mir ungelesene Mails von Schmidt.“ -> „Lies m2 vor.“ -> „Antworte, dass Dienstag passt.“
- „Hey Jarvis, schau dir das Dokument an, das ich in die Kamera halte. Was fehlt darin?“
- „Hey Jarvis, wie würdest du meine Woche priorisieren?“

## Daten und Datenschutz

- Wake-Word-Erkennung läuft komplett lokal; erst nach „Hey Jarvis“ geht Audio an Azure.
- Lokale Daten in `~/.sprachassistent/`: `lists.json`, `tasks.json` (nur ohne Microsoft 365), `ms_token_cache.json`.
- Webcam-Bilder werden nur auf Aufforderung aufgenommen und an die Claude-API gesendet, nicht gespeichert.
- Der Gesprächsverlauf wird nur im Speicher gehalten und endet mit dem Schließen der App.

## Tests

```bash
pytest
```

## Grenzen dieser Version

- Erkennung des Wake-Words ist auf „Hey Jarvis“ (englisch ausgesprochen) trainiert; ein eigener Name braucht ein eigenes openWakeWord-Modell.
- Aufnahmen sind auf 30 Sekunden pro Äußerung begrenzt.
- Anhänge werden erkannt, aber nicht gelesen oder gesendet. OneDrive ist nicht angebunden.
