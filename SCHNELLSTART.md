# Schnellstart ohne Vorkenntnisse (Windows)

Du brauchst etwa 30 Minuten. Die drei Zugänge (Claude, Azure Speech, Microsoft) kosten teils Geld
bzw. brauchen ein Microsoft-Konto; ohne Azure Speech und Microsoft läuft Jarvis trotzdem, nur per
Texteingabe und ohne Mail/Kalender.

## 1. Code holen

Der Code liegt in deinem GitHub-Repository **MayerMartin184/Sprachassistent** auf dem Branch
`claude/voice-controlled-task-assistant-li2q6c`.

Am einfachsten: In GitHub den Branch oben links auswählen -> grüner Knopf „Code“ -> „Download ZIP“ ->
ZIP entpacken, z. B. nach `C:\Jarvis`.

Alternativ mit Git: `git clone -b claude/voice-controlled-task-assistant-li2q6c https://github.com/MayerMartin184/Sprachassistent.git C:\Jarvis`

## 2. Python installieren

1. https://www.python.org/downloads/ -> „Download Python 3.12“ (oder neuer).
2. Beim Installer **„Add python.exe to PATH“ anhaken**, dann „Install Now“.

## 3. Jarvis installieren (ein Doppelklick)

Im Ordner `C:\Jarvis` die Datei **`Installieren.bat`** doppelklicken. Ein schwarzes Fenster zeigt den
Fortschritt; das dauert einige Minuten. Am Ende liegt auf dem Desktop eine Verknüpfung **„Jarvis“**,
und die Datei `.env` öffnet sich im Editor für Schritt 4.

Falls Windows warnt („Der Computer wurde durch Windows geschützt“): „Weitere Informationen“ und
„Trotzdem ausführen“. Die Datei enthält nur die Befehle aus diesem Abschnitt.

Wer es lieber von Hand macht, Eingabeaufforderung (Windows-Taste, `cmd`, Enter):

```
cd C:\Jarvis
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev,webcam]"
copy .env.example .env
```

## 4. Zugänge anlegen und Schlüssel eintragen

Die Datei `C:\Jarvis\.env` mit dem Editor öffnen (Rechtsklick -> „Öffnen mit“ -> Editor). Dort stehen
Zeilen wie `ANTHROPIC_API_KEY=sk-ant-...`. Du ersetzt jeweils den Teil rechts vom `=` und speicherst.
Menübezeichnungen können sich bei den Anbietern leicht ändern; die Reihenfolge bleibt gleich.

### 4a. Claude-API-Schlüssel (Pflicht, ca. 5 Minuten)

Kosten: Abrechnung nach Nutzung. Für einen normalen Arbeitstag mit einigen Dutzend Aufträgen ist mit
wenigen Euro zu rechnen. Ein Startguthaben von 10 bis 20 Euro reicht zum Ausprobieren.

1. Browser: https://console.anthropic.com öffnen -> „Sign up“ -> mit E-Mail oder Google-Konto registrieren.
2. Nach dem Einloggen links auf **„Billing“** (Abrechnung) -> „Add payment method“ -> Kreditkarte hinterlegen
   -> „Add credits“ -> z. B. 20 US-Dollar aufladen. Optional dort ein monatliches Limit setzen.
3. Links auf **„API Keys“** -> Knopf **„Create Key“** -> Name eingeben, z. B. `Jarvis` -> „Create“.
4. Der Schlüssel beginnt mit `sk-ant-` und wird **nur einmal angezeigt**. Kopieren (Knopf neben dem Text)
   und in `.env` eintragen:
   `ANTHROPIC_API_KEY=sk-ant-hier-dein-Schluessel`
5. Schlüssel nie weitergeben oder in E-Mails schicken. Bei Verlust in der Konsole löschen und neu erstellen.

### 4b. Azure-Konto (Basis für Sprache und Microsoft-Anbindung, ca. 10 Minuten)

Azure ist Microsofts Cloud. Du brauchst es für zwei Dinge: den Sprachdienst (4c) und die
App-Registrierung für To Do/Mail/Kalender (4d). Der Sprachdienst hat einen kostenlosen Tarif
(5 Stunden Spracherkennung und 0,5 Mio. Zeichen Sprachausgabe pro Monat); Kreditkarte wird zur
Identitätsprüfung trotzdem verlangt.

1. https://azure.microsoft.com/de-de/free -> „Kostenlos starten“ -> mit deinem Microsoft-Konto anmelden.
   Hast du ein Firmen-Microsoft-365-Konto, nimm dieses (dann sind To Do/Mail später direkt erreichbar).
2. Telefonnummer und Kreditkarte bestätigen. Es wird nichts abgebucht, solange du im kostenlosen Tarif bleibst.
3. Danach landest du im **Azure-Portal**: https://portal.azure.com

### 4c. Azure Speech anlegen (Spracherkennung und Sprachausgabe)

1. Im Azure-Portal oben in die Suchleiste **„Speech“** tippen -> unter „Marketplace“ den Eintrag
   **„Speech“** (Azure AI Services) wählen -> **„Erstellen“**.
2. Formular ausfüllen:
   - **Abonnement:** dein Abonnement (z. B. „Free Trial“ oder „Azure subscription 1“)
   - **Ressourcengruppe:** „Neu erstellen“ -> Name `jarvis`
   - **Region:** `Germany West Central` (Daten bleiben in Deutschland)
   - **Name:** z. B. `jarvis-speech`
   - **Tarif:** **Free F0** (kostenlos). Wenn F0 ausgegraut ist, gibt es schon eine kostenlose Speech-Ressource
     im Konto; dann `Standard S0` wählen (Abrechnung nach Nutzung, wenige Cent pro Stunde Sprache).
3. **„Überprüfen und erstellen“** -> **„Erstellen“** -> warten (ca. 1 Minute) -> **„Zu Ressource wechseln“**.
4. Links im Menü **„Schlüssel und Endpunkt“** (unter „Ressourcenverwaltung“) öffnen.
5. **„SCHLÜSSEL 1“** kopieren (Symbol rechts daneben) -> in `.env`:
   `AZURE_SPEECH_KEY=hier-der-Schluessel`
6. Darunter steht **„Standort/Region“**, z. B. `germanywestcentral` -> in `.env`:
   `AZURE_SPEECH_REGION=germanywestcentral`
   (Kleingeschrieben, ohne Leerzeichen, genau so wie im Portal angezeigt.)

### 4d. Microsoft 365 anbinden (To Do, Mail, Kalender, Teams-Transkripte)

Damit Jarvis auf dein Postfach zugreifen darf, meldest du ihn bei Microsoft als „App“ an.
Er bekommt dadurch keine Passwörter; du erlaubst den Zugriff einmalig per Anmeldung im Browser.

1. Im Azure-Portal oben suchen: **„Microsoft Entra ID“** -> öffnen.
2. Links **„App-Registrierungen“** -> oben **„Neue Registrierung“**.
3. Formular:
   - **Name:** `Jarvis Sprachassistent`
   - **Unterstützte Kontotypen:**
     - Firmenkonto (Microsoft 365 Business/Enterprise): **„Nur Konten in diesem Organisationsverzeichnis“**
     - Privates Konto (outlook.de, hotmail, live): **„Konten in einem beliebigen Organisationsverzeichnis
       und persönliche Microsoft-Konten“**
   - **Umleitungs-URI:** leer lassen
   -> **„Registrieren“**.
4. Auf der Übersichtsseite der App stehen zwei IDs:
   - **„Anwendungs-ID (Client)“** kopieren -> `.env`: `MS_CLIENT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`
   - Bei Firmenkonto zusätzlich **„Verzeichnis-ID (Mandant)“** kopieren -> `.env`: `MS_TENANT_ID=...`
     Bei privatem Konto bleibt `MS_TENANT_ID=common`.
5. Links **„Authentifizierung“** -> Knopf **„Umleitungs-URI hinzufügen“** (bzw. „Plattform hinzufügen“) ->
   **„Mobile Anwendungen und Desktopanwendungen“** wählen -> Haken bei **`http://localhost`** ->
   **„Konfigurieren“**. Damit kann sich Jarvis über deinen normalen Browser anmelden.
6. Links **„API-Berechtigungen“** -> **„Berechtigung hinzufügen“** -> **„Microsoft Graph“** ->
   **„Delegierte Berechtigungen“** -> im Suchfeld nacheinander suchen und jeweils anhaken:
   - `User.Read` (ist meist schon da)
   - `Mail.ReadWrite`
   - `Mail.Send`
   - `Calendars.ReadWrite`
   - `Tasks.ReadWrite`
   - `OnlineMeetings.Read`
   - `OnlineMeetingTranscript.Read.All`
   -> unten **„Berechtigungen hinzufügen“**.
7. Nur Firmenkonto: Oben den Knopf **„Administratorzustimmung für <Firma> erteilen“** klicken, falls du
   Administrator bist. Sonst diese Seite deiner IT zeigen; besonders `OnlineMeetingTranscript.Read.All`
   braucht fast immer die Zustimmung eines Administrators. Ohne Zustimmung funktionieren To Do, Mail und
   Kalender meist trotzdem, nur die Teams-Transkripte nicht.

**Erste Anmeldung:** Beim ersten Auftrag an Jarvis, der Mail/To Do/Kalender betrifft, öffnet sich dein
Browser mit der Microsoft-Anmeldung. Konto wählen, Berechtigungen bestätigen, fertig. Danach merkt sich
Jarvis die Anmeldung. Öffnet sich kein Browser, zeigt Jarvis stattdessen einen Code für
https://microsoft.com/devicelogin an.

### 4e. Kontrolle: So sollte `.env` aussehen (Beispiel)

```
ANTHROPIC_API_KEY=sk-ant-api03-Abc...
ASSISTANT_MODEL=claude-opus-5
ASSISTANT_EFFORT=medium
AZURE_SPEECH_KEY=1a2b3c4d5e6f...
AZURE_SPEECH_REGION=germanywestcentral
SPEECH_LANGUAGE=de-DE
TTS_VOICE=de-DE-KatjaNeural
WAKE_WORD_ENABLED=true
WAKE_WORD_MODEL=hey_jarvis
WAKE_WORD_THRESHOLD=0.5
ASSISTANT_NAME=Jarvis
WEBCAM_ENABLED=true
WEBCAM_INDEX=0
MS_CLIENT_ID=11111111-2222-3333-4444-555555555555
MS_TENANT_ID=common
DOCUMENTS_ROOT=~/Documents
TIMEZONE=Europe/Berlin
```

## 5. Starten

Doppelklick auf **„Jarvis“** auf dem Desktop (oder auf `Jarvis.bat` im Ordner). Es öffnet sich das
Jarvis-Fenster ohne schwarze Konsole.

Der Kreis in der Mitte zeigt den Zustand: **grün** wartet auf „Hey Jarvis“, **rot** nimmt auf,
**gelb** arbeitet, **blau** spricht, **grau** Mikrofon aus. Unten kannst du jederzeit auch tippen.
Beim ersten Mail- oder To-Do-Zugriff erscheint ein Code zum Anmelden bei Microsoft.

Fehlt der Claude-Schlüssel, erscheint beim Start ein Hinweisfenster statt des Programms.
Fehlermeldungen landen in `%USERPROFILE%\.sprachassistent\jarvis.log`.

## Wenn etwas nicht geht

- **„Der Claude-API-Schlüssel fehlt“**: `.env` liegt nicht direkt in `C:\Jarvis`, wurde nicht gespeichert, oder der Schlüssel steht nicht rechts vom `=`. Die Datei darf auch `.env.txt` heißen.
- **Kein Ton / kein Mikrofon**: In den Windows-Einstellungen unter Datenschutz den Mikrofonzugriff für Desktop-Apps erlauben.
- **Wake-Word reagiert nicht**: `WAKE_WORD_THRESHOLD=0.4` in `.env` eintragen; „Hey Jarvis“ englisch aussprechen („Dschárwis“).
- **Wake-Word löst zu oft aus**: `WAKE_WORD_THRESHOLD=0.65`.
- **Microsoft-Fehler 403**: Berechtigung fehlt oder braucht Admin-Zustimmung; Datei `%USERPROFILE%\.sprachassistent\ms_token_cache.json` löschen und neu anmelden.
- Mehr Details: `python -m sprachassistent -v`
