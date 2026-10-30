# Masterplan: Mayer E-Concept – Wissen, Ablage, Assistenten

Stand: 30.10.2026 (Rev. B, Ist-Abgleich mit X:) · Autor: Jarvis-Projekt · Für: Martin Mayer (Entscheidung), Team (Ablage/Wissen), Kollege Nexus (Schnittstellen)

Grundlage: die Repos `Sprachassistent` (Jarvis), `ElecTriX-Revit-App` (Nexus/Workboard/MailBridge-Schnittstellen),
`Nexus-Office` (Projektmanager), `Nexus-santier` (Baustellen-App) und der Ist-Stand auf `X:\` (Ebene 1 und 2, gelesen am 30.10.2026).

**Änderungen Rev. B (30.10.2026):** Ordnerstruktur an den Bestand angepasst (Variante B, Abschnitt 3.1), `03_Wissen` heißt `03_Wissen`,
Projektordner-Vorlage = bestehende `000_Ordnerstruktur`, Zeit über TrackingTime, Sicherheitsregel für Zugangsdaten, Synology-Admin-Liste
(Abschnitt 14), Entscheidungen 1 bis 11 getroffen (Abschnitt 13). Nichts in `01_Projekte` wird verschoben oder umbenannt.

---

## 0. Das Ziel in einem Satz

Wenn du nicht da bist, kann jeder (du per Stimme, das Team per Jarvis/Teams) fragen:
*„Wo steht Projekt X? Was fehlt? Was können wir abrechnen? Wie haben wir das letztes Mal gelöst?“* –
und bekommt eine belegte Antwort aus **einer** Ablage, **einer** Wissensbasis und **drei** Programmen,
die sich nicht gegenseitig kopieren.

**Drei Ebenen, feste Hoheit:**

| Ebene | Hoheit (System) | Wer sieht es | Beispiele |
|---|---|---|---|
| **Persönlich** | Jarvis (pro Person) | nur die Person | Mails, Kalender, To Do, Teams, Erinnerungen, Gewohnheiten, Mithör-Protokoll |
| **Projekte (gemeinsam)** | Nexus + ElecTriX + Share `01_Projekte`, `02_sabloane`, `03_Wissen` | ganzes Büro | Anfragen, Aufgaben, Revit-Modell, Pläne, Standards, Lessons Learned |
| **Finanzen (vertraulich)** | Nexus Office + `00_Office` | nur Martin + Buchhaltung | Angebote, Aufträge, Unterschriften, Rechnungen, Ausgaben, Löhne |

Jarvis ist das **Sprachrohr** über alle drei Ebenen – er kopiert keine Daten, er fragt die zuständige Quelle.
Auf Mitarbeiter-PCs ist die Finanz-Ebene technisch gar nicht vorhanden (kein Ordnerzugriff, kein Werkzeug).

---

## 1. Ist-Stand (aus dem Code abgeleitet)

| Bereich | Heute | Lücke |
|---|---|---|
| Projekte/Finanzen | Nexus Office: Kunden, Projekte (`code`, `projekt_nr`, Status `angebot/beauftragt/laufend/fertig`, Beauftragung `nein/email/ja`, LP2/LP3/LP5 je `offen/beauftragt/abgerechnet`), Angebote, Rechnungen (Phasen LP2/LP3/LP5/1.TR/2.TR/Gesamt/Nachtrag, Zahlung `offen/erhalten/teilweise`, Mahnstufen), Nachträge, Unterschriften-Prüfung, Dokumentablage `Dokumente\00_Eingang / 01_Unterschrieben / 02_Nicht unterschrieben`, Scan von `00_Office`, Mail-Eingang `nexus@me-concept.ro` (MailBridge, Angebotsmodus) | Ausgaben/Löhne/Eingangsrechnungen fehlen; Phasenstatus wird von Hand gepflegt; Doppler in `00_Office` |
| Anfragen/Aufgaben | MailBridge liest `tasks@…`  per IMAP → `METools_Tasks_<projekt>.json` (Kategorie, Dringlichkeit, Projektvermutung, Anhänge nach `01_Projekte\<Projekt>\000_Mail-Eingang`), Workboard in Revit, Nexus, Teams-Bot „Asistent“ | nicht alle Postfächer leiten dorthin; keine Rückmeldung „erledigt“ an Absender; keine Wissensableitung |
| Revit | ElecTriX-Pipe `METools.Revit.<user>.<pid>`: `info`, `room_counts`, `find_elements`, `select`, `release_check`, `set_parameters`; Hausstandards `METools_RoomStandards.json`; Plans Out → `<Code>_Planung\JJMMTT\` + `Planliste_JJMMTT.csv`; Kommentare, Aktivitätslog | Projektstand nicht maschinenlesbar zusammengefasst |
| Projektregister | `METools_ProjectRegistry.json`, automatisch aus Ordnern `01_Projekte\JJMM_NN_Kunde_Nr_Name` und `00_Abgeschlossen` | keine Verknüpfung zur Nexus-Office-Projekt-ID  |
| Zeit | ElecTriX TimeTracker (Start/Ende/User je Modell, Heartbeat); Șantier: Einträge mit Minuten, Fahrt, Material, Bons, Berichte mit Unterschrift | Martins eigene Zeit nicht erfasst; keine Auswertung Stunden vs. Angebot |
| Wissen | Hausstandards (Räume), Referenzdokumente in Nexus Office, Memory je PC | **keine zentrale, zweisprachige Wissensbasis**; Lessons Learned nirgends |
| Jarvis | Stimme, M365 (Mail/Kalender/To Do/Teams/Planner), Dateien (PC + NAS), Dokumente, Erinnerungen, Mithören, Gedächtnis | noch kein Zugriff auf Nexus-Daten, Revit-Pipe, Nexus Office, Wissensbasis |

---

## 2. Zielarchitektur

```
                 ┌──────────────────────────────────────────────┐
  Stimme/Text →  │  JARVIS (persönlich, je Person)              │
                 │  Mails · Kalender · To Do · Teams · Erinnern │
                 └──────┬───────────────┬───────────────┬───────┘
                        │ liest/schreibt│ fragt         │ nur Martin/Buchhaltung
                        ▼               ▼               ▼
            ┌───────────────┐  ┌───────────────┐  ┌────────────────────┐
            │ 03_Wissen     │  │ Nexus/ElecTriX│  │ Nexus Office       │
            │ (Brain, DE/RO)│  │ Workboard,    │  │ Angebote, Rechnungen│
            │ Standards,    │  │ Revit-Pipe,   │  │ Ausgaben, Löhne    │
            │ Lessons, ADRs │  │ Projektregister│ │ 00_Office          │
            └───────────────┘  └───────┬───────┘  └────────────────────┘
                                       │
                               ┌───────▼────────┐
                               │ 01_Projekte     │  Revit-Modelle, Pläne, Grundlagen
                               │ (unverändert)   │  PROJEKT.md je Projekt (neu)
                               └────────────────┘
   Eingang:  alle Postfächer ──Outlook-Regel──▶ tasks@ (Projekt) · nexus@ (Angebot/Finanzen) ──MailBridge──▶ Workboard / Office-Eingang
```

Regeln:
1. **Jede Information hat genau einen Ablageort** (Tabelle in Abschnitt 3.4). Nexus Office darf Projektdokumente *verlinken/kopieren* zum schnellen Finden – die Quelle bleibt der Ordner.
2. **Schreiben in gemeinsame Daten nur über die bestehenden Verfahren** (Lock-Datei + atomares Ersetzen wie `SharedJsonStorage` 2.6.4). Jarvis hält sich daran, mit Absender „Jarvis (Name)“.
3. **Unbekannte Felder bleiben erhalten** (JsonExtensionData-Prinzip) – damit Nexus, MailBridge, ElecTriX und Jarvis Versionen mischen können.
4. **Die Wissensbasis ist Text** (Markdown + ein JSON-Index). Keine Datenbank, kein Vendor-Lock, von jedem KI-Werkzeug lesbar, in Git versionierbar.
5. **Zugangsdaten, Keys und Passwörter liegen nie auf X:.** Nur in KeePassXC (Datenbank in `00_Office\01_Firma`, nur Martin) und in lokalen `.env`-Dateien. Jarvis-Werkzeug `ablage_check` sucht vierteljährlich nach Dateinamen wie `Kennwort`, `password`, `API KEY`, `Zugang`, `recovery` und meldet Treffer.

---

## 3. Ordnerstruktur `\\Database\MEC_Database` (X:)

### 3.1 Oberste Ebene (Variante B: Bestand bleibt, zwei Ordner neu)

| Ordner | Inhalt | Rechte (Synology) | Änderung |
|---|---|---|---|
| `00_Office` | Firma + Finanzen (3.2) | nur Martin + Buchhaltung (eigenes Konto) | innen aufräumen, **nicht neu anlegen** |
| `01_Projekte` | ein Ordner je Projekt, Revit-Zentralmodelle | Team | **unverändert**; nur `PROJEKT.md` je Projekt dazu |
| `02_sabloane` | fachliche Vorlagen: Revit, AutoCAD, LV, Word, Excel, Fonts, Dialux, Plot-Checkliste, Leistungsbilanz | Team lesen, Martin + Revit-Verantwortlicher schreiben | **Name bleibt** (Revit-Templates zeigen dorthin); `13_Claude.md` wandert nach `03_Wissen\70_Anleitungen` |
| `03_Wissen` | Brain-Wissensbasis (3.3), angelegt 30.10.2026 | Team lesen, Martin schreiben | **neu**; Inhalt aus `04_Documente` und `Proceduri MEC` zieht hierher |
| `04_Documente` | wird aufgelöst | – | nach Umzug leer, dann löschen |
| `05_Marketing` | Logo, Referenzen, Homepage, Fotos | Team | bleibt |
| `06_Utile` | Werkzeugkiste (LISP, Modellprojekte) | Team | bleibt |
| `07_Scan` | Scanner-Eingang | Scanner schreibt, Martin liest | bleibt; Jarvis sortiert von hier nach `00_Office` oder Projektordner |
| `08_Aplicatii` | Nexus, ElecTriX, MailBridge, `METools_Comments` (führende Registry, Logs, TimeTracker), `Nexus_Hausstandards` | Team | bleibt; Wurzel-Kopie `X:\METools_Comments` nach Klärung mit Kollege löschen |
| `09_Archiv` | Altes, nicht löschen; Unterordner `JJJJ_<alter Name>`; `_Nachweise` mit Dateilisten vor jedem Verschieben | Team lesen | **neu**, angelegt 30.10.2026 |
| `Central` | `Workshare.rvt` (Jan. 2026) | Team | prüfen, ob ein Zentralmodell darauf zeigt; sonst nach `09_Archiv\2026_Central` |
| `Proceduri MEC` | Arbeitsabläufe | Team | nach `03_Wissen\00_Firma\Prozesse` |
| `Site` | Homepage-Quelle | Martin | bleibt, bis Deploy-Pfad geklärt |

Nicht angelegt werden `04_Kunden_Partner` und `05_Personal_intern`: Verträge liegen in `00_Office\01_Firma`, Kundenprofile ohne Preise in `03_Wissen\20_Kunden`, Anleitungen in `03_Wissen\70_Anleitungen`.

**Revit-Regel vor jedem Verschieben:** Jarvis prüft `Revit.ini` und Template-Pfade auf allen vier PCs auf `X:\`-Pfade. Was gefunden wird, bleibt unangetastet. Revit greift nur auf `01_Projekte` zu (und ggf. `02_sabloane`), nie auf `00_Office`.

Nichts löschen, nur verschieben; vorher Dateiliste nach `09_Archiv\_Nachweise\JJJJ-MM-TT_<was>.txt`.

### 3.2 `00_Office` (vertraulich, bestehender Ordner, nur innen aufräumen)

```
00_Office\
  01_documente\               = 01_Firma: Acte Firma, Verträge in/out, Angajați, Kontoauszüge, ANRE, ISO 9001, Leasing (bestehend)
  02_Facturi\
     01 Eingangsrechnungen_Facturi Cheltueli\JJJJ\MM\   (Dateiname: JJJJ-MM-TT_Lieferant_Betrag_Projektcode.pdf)
     02 Ausgangsrechngen_Facturi Incasari\JJJJ\          = PDF aus Nexus Office, nur Kopie
     Ausgaben_JJJJ.xlsx          Ausgabenliste (Entscheidung 3)
     Fixkosten.json              Löhne, Mieten, Abos, stundensatz_intern (Entscheidung 4); Jarvis liest nur
  03_Clienti\
     Projektmanager\            Nexus-Office-Datenordner (data\, files\, PDF\, Dokumente\, inbox\) – der einzige Projektmanager-Pfad (Entscheidung 8)
     01…12_<Kunde>\             Altbestand → mit "Scan 00_Office" in Projektmanager\Dokumente einsortieren, danach nach 09_Archiv
  02_Oferte\, 04_Offene Beauftragungen\   Altbestand → dito
  05_sabloane Word & Excell\   Briefpapier, Angebots-/Rechnungsvorlagen (bleibt)
  01_Management\               PROJEKTMANAGER.html, Projekt-Management*, ZIP = Doppler → 09_Archiv; SC_Mayer_Systemplan.md → 03_Wissen\50_Entscheidungen
  00_Altele\, 10_Temp\, 06_Arhiva Email\   → 09_Archiv
  11_Assistent\                Jarvis-Repo-Kopie, bleibt
```

Scanner-Eingang ist `X:\07_Scan`, nicht `00_Office\00_Eingang`.

Aufräumregel für die Doppler: **Nexus Office „Scan 00_Office“** jede Datei einmal zuordnen → Original bleibt,
Kopie wandert nach `Projektmanager\Dokumente\01/02_…\<Projektcode>\`. Danach die alten Ordner nach `09_Archiv`.
Jarvis-Werkzeug `ablage_check`: Duplikate per SHA256 aus `MEC_Inventar.csv` finden und melden.

**Zugangsdaten (Stand 30.10.2026, zu erledigen durch Martin):** `CLAUDE CONSOLE API KEY.txt` (Wurzel X:), `github-recovery-codes.txt`,
`Microsoft Edge-Kennwörter*.csv`, `Zugang.txt`, `Zugänge.xlsx` → in KeePassXC, Dateien löschen, API-Key widerrufen und neu erzeugen.

### 3.3 `03_Wissen` – die Brain-Wissensbasis (angelegt 30.10.2026)

```
03_Wissen\
  BRAIN.md                    Startseite: Was liegt wo, wie wird geschrieben, die 20 wichtigsten Regeln (DE)
  BRAIN.ro.md                 dieselbe Startseite auf Rumänisch
  _index.json                 maschinenlesbar: Datei · Titel · Thema · Sprache(n) · Projekte · Stichworte · Stand – pflegt Jarvis
  00_Firma\                   Leitbild, Rollen, Prozesse (Angebot → Auftrag → LP → Abrechnung → Abschluss), Checklisten je Phase
  10_Standards\               fachlich: DIN 18015 (Räume → RoomStandards), VDE, Brandschutz, Dokumentationsumfang, Revit-Konventionen,
                              Planinhalte je LP, Benennung; Unterordner Normen_DE, Normen_RO, Technik (aus 04_Documente);
                              hausstandards.md verweist auf 08_Aplicatii\Nexus_Hausstandards\Hausstandards.md (dort liest Nexus, dort pflegen)
  20_Kunden\<Kunde>.md        je Kunde: Ansprechpartner, Lieferformate, Eigenheiten, "will immer…/nie…"
  30_Projekte\<Code>.md       Steckbrief + Lessons Learned je Projekt (Kopie von 01_Projekte\<Code>\PROJEKT.md beim Abschluss)
  40_Lessons\L-0001_….md      Fehler → Ursache → Regel → wo gilt sie; nach Thema; verlinkt auf Projekt
  50_Entscheidungen\E-0001_….md  Entscheidung · Begründung · Alternativen · Datum · Projekt · wer
  60_Glossar\glossar.md       Fachbegriffe DE ⇄ RO ⇄ EN (für Übersetzung und Suche)
  70_Anleitungen\             Schritt-für-Schritt (ElecTriX, Nexus, Revit-Workflows, Șantier-App); Inhalt aus 02_sabloane\13_Claude.md
  _Entwurf\                   Vorschläge von Mitarbeitern, Freigabe durch Martin
```

**Schreibregeln (stehen in BRAIN.md):**
- Eine Datei = ein Thema. Kopfzeile immer: `# Titel`, `Stand:`, `Gilt für:`, `Sprache:`. YAML-Frontmatter: `title`, `topic`, `status` (entwurf/pruefung/freigegeben), `lang`, `projects`, `tags`, `updated`. Nur `status: freigegeben` wird als Wissen verwendet.
- Jede Datei beginnt auf Deutsch; Abschnitt `## RO` mit der rumänischen Kurzfassung (Jarvis übersetzt und hält beide Seiten gleich).
- Lessons Learned haben eine Nummer `L-####`, eine Regel in einem Satz und werden bei Projektabschluss **verpflichtend** geschrieben (Abschnitt 7).
- Entscheidungen werden nur mit Begründung abgelegt – „weil der Kunde…“, „weil DIN…“.
- Wer schreiben darf: Martin direkt; Mitarbeiter legen Vorschläge in `_Entwurf\` ab, Jarvis meldet sie Martin zur Freigabe.
- Die KI sucht zuerst in `_index.json`, dann im Text; antwortet mit Quelle (Datei + Abschnitt). Ohne Quelle keine Behauptung.

### 3.4 Projektordner (Vorlage = bestehende `01_Projekte\000_Ordnerstruktur`, Bestand bleibt)

```
01_Projekte\JJMM_NN_Kunde_ProjNr_Name\        z. B. 2510_07_PLS_24_19_Am Bungert (Konvention bleibt)
  PROJEKT.md                 NEU: Steckbrief (Anhang A): Kunde, Ansprechpartner, Phasen, Pflichtunterlagen, Stand
  000_Mail-Eingang\          legt MailBridge an
  00_Zentralmodel\           Revit-Zentralmodell (bestehend)
  000_Archiv\                bestehend
  000_Eingang\               Architektenpläne, IFC, Bestand, Baubeschreibung, Brandschutzkonzept (bestehend)
  001_LPH2\  002_LPH3\  003_LPH5\   Planung je Leistungsphase; Plans Out schreibt JJMMTT-Unterordner + Planliste_JJMMTT.csv (bestehend)
  004_Plankopf\  005_Listen\  006_Erschließung\  007_Ausschreibung\   bestehend
  008_Entscheidungen\        NEU: notizen.md, wandert später nach 03_Wissen\50_Entscheidungen
  009_Abschluss\             NEU: Übergabe, LESSONS.md (Anhang B), Schlussstand
```

Bestehende Projekte bekommen nur `PROJEKT.md`, `008_Entscheidungen` und `009_Abschluss` dazu. Nichts wird verschoben oder umbenannt (Entscheidung 6).

### 3.5 Dateinamen

- Dokumente: `JJJJ-MM-TT_Thema_Absender.pdf` (Datum zuerst → sortiert sich von selbst)
- Pläne: wie Plans Out (`{nummer}_{index}_{name}`), Planliste bleibt CSV
- Eingangsrechnungen: `JJJJ-MM-TT_Lieferant_Betrag_Projektcode.pdf` (ohne Projekt: `_ALLG`)
- Keine Leerzeichen am Anfang, keine Umlaute in Ordnernamen neuer Projekte (Revit-Referenzen); Bestand mit Umlauten bleibt

---

## 4. Eingang: Mails und Aufgaben

**Zwei Postfächer, zwei Welten:**

| Postfach | Zweck | Verarbeitung | Sichtbar für |
|---|---|---|---|
| `tasks@me-concept.ro` (Shared Mailbox, Entscheidung 1) | alles, was mit Projektarbeit zu tun hat (Anfragen, Änderungen, Fragen, Termine, Planlieferungen) | MailBridge → `METools_Tasks_<projekt>.json` + Anhänge → `000_Mail-Eingang` → Workboard/Nexus/Teams | Team |
| `nexus@me-concept.ro` | Angebotsanfragen, Lieferantenangebote, Rechnungen, Verträge | MailBridge Angebotsmodus → Nexus Office Eingang | Martin, Buchhaltung |

**Postfach:** Shared Mailbox `tasks@me-concept.ro` im selben Tenant wie die Mitarbeiterpostfächer (0 € bis 50 GB). Zugriff MailBridge: Entra-App mit `IMAP.AccessAsApp`, `New-ServicePrincipal` + `Add-MailboxPermission` nur auf tasks@, bestehender MailKit-Code mit XOAUTH2. Erster Schritt: `Get-AcceptedDomain` prüfen, ob `me-concept.ro` und `me-concept.de` im selben Tenant liegen. EWS ab 10/2026 abgeschaltet, nicht verwenden.

**Mail-Regeln (du richtest sie ein, Jarvis kann sie dir vorlesen/prüfen):**
1. Serverseitig als Exchange-Transportregel (nicht Outlook-Regel): *Bcc an `tasks@`*, wenn Absenderdomain = Kunde/Architekt (Liste aus `METools_ProjectRegistry.json` → `CustomerDomains`) **und** Betreff nicht „Angebot/Rechnung/Ofertă/Factură“. **Voraussetzung:** `CustomerDomains` ist heute bei allen 36 Projekten leer; Jarvis schlägt sie je Projekt aus `000_Mail-Eingang` und Keywords vor, Martin bestätigt (Phase 1c).
2. *Weiterleiten an `nexus@`*, wenn Betreff/Anhang „Angebot, Rechnung, Auftrag, Ofertă, Factură, Comandă“.
3. Alles andere bleibt bei dir – Jarvis triagiert es persönlich (Mail-Tools gibt es schon).

**Erweiterung MailBridge (Absprache Kollege):** Kategorie `finance` nie in die Team-Tasks schreiben, sondern nach `nexus@`-Eingang umleiten;
Kategorie `deadline` mit `DueDate` → Jarvis legt für den Zuständigen eine Erinnerung an.

**Erledigt-Rückmeldung:** Wenn eine Aufgabe im Workboard `done` wird, schreibt Jarvis (des Zuständigen) auf Wunsch eine kurze Antwort an den Absender.

**Wissensableitung:** Jarvis fasst jede Woche neue Anfragen je Projekt zusammen und schlägt vor, was ins `PROJEKT.md` (Besonderheiten) oder in `20_Kunden` gehört.

---

## 5. Projekt-Lebenszyklus, Status und Abrechnung

### 5.1 Phasen und „fertig“ heißt

| Phase | Status Nexus Office | Fertig, wenn (Nachweis im Ordner) | Dann |
|---|---|---|---|
| Anfrage | – (Eingang) | Kunde, Umfang, Termin bekannt | Angebot in Nexus Office |
| Angebot | Projekt `angebot`, Angebot `versendet` | PDF versendet | Nachfassen nach 10 Tagen (Jarvis erinnert) |
| Auftrag | `beauftragt`, Beauftragung `email/ja` | signierte Beauftragung in `Dokumente\01_Unterschrieben` | Projektordner aus Vorlage, `PROJEKT.md`, Registry-Eintrag |
| LP1/LP2 | lp2 `beauftragt` → `abgerechnet` | Vorplanung versendet (`_Planung\JJMMTT` + Planliste), Pflichtunterlagen vorhanden | **Rechnung LP2** |
| LP3 | lp3 … | Entwurfsplanung versendet, Release-Check ohne offene Punkte, Leistungsbilanz abgelegt | **Rechnung LP3** |
| LP5 | lp5 … | Ausführungsplanung versendet, Release-Check grün, Revisionsstand dokumentiert | **Rechnung LP5 / Gesamt** |
| Nachtrag | Nachtrag `approved` | Zusatzleistung erbracht | Rechnung `Nachtrag` |
| Abschluss | Projekt `fertig` | Lessons Learned geschrieben, Ordner nach `00_Abgeschlossen` (bleibt in `01_Projekte`) | Zahlungseingang überwachen |

### 5.2 Pflichtunterlagen je Projekt (Jarvis prüft und mahnt)

Baubeschreibung · Brandschutzkonzept · aktuelle Architektenpläne/IFC · Raumbuch/Nutzung · Leistungsbilanz · Versorgungskonzept ·
Hausanschluss/EVU-Schreiben · Auftrag (Hinweisdatei) · Freigabeprotokolle. Liste je Projekttyp in `03_Wissen\00_Firma\Checklisten`
und je Projekt in `PROJEKT.md` abgehakt. Fehlt etwas → Jarvis sagt es beim Projektstand **ungefragt**.

### 5.3 Der „Projektstand“ (eine Antwort aus fünf Quellen)

Jarvis-Werkzeug `projektstand(<Code>)` liefert:
1. Nexus Office: Status, Beauftragung, LP-Status, offene/überfällige Rechnungen, Nachträge *(nur Martin)*
2. Ordner: letzter Planversand (Datum, Anzahl Pläne), fehlende Pflichtunterlagen aus `PROJEKT.md`
3. Workboard: offene Anfragen/Aufgaben, wer, seit wann, fällig
4. Revit (Pipe): `release_check` – Geräte ohne Raum/Stromkreis, Höhe 0, Duplikate
5. Zeit: Stunden TimeTracker/Șantier je Phase *(Vergleich mit Angebot nur Martin)*

Antwort immer: **Stand · Fehlt · Nächster Schritt · Abrechenbar?**

### 5.4 Abrechnungsradar (monatlich, nur Martin)

Am 1. und 15. jedes Monats:
- „Abrechenbar jetzt“: LP-Status `beauftragt` **und** Planversand vorhanden **und** keine Rechnung dieser Phase
- „Diesen Monat fertig machen“: Phasen mit Planversand-Termin ≤ Monatsende oder Release-Check < 5 offene Punkte
- „Überfällig“: Rechnungen > Fälligkeit (Mahnstufe aus Nexus Office)
- „Nachfassen“: Angebote `versendet` > 10 Tage
Ergebnis als gesprochene Zusammenfassung + Liste in To Do (`Abrechnung Monat JJJJ-MM`).

---

## 6. Finanzen: Ausgaben, Löhne, Kennzahlen (nur Martin/Buchhaltung)

1. **Eingangsrechnungen**: landen in `X:\07_Scan` oder per Mail in `nexus@`. Jarvis liest sie (PDF/Foto), schlägt vor:
   Lieferant · Datum · Betrag · MwSt · Kategorie (Material/Software/Fahrzeug/Miete/Sonstiges) · Projektcode · Zahlziel → Ablage
   nach `02_Facturi\01 Eingangsrechnungen_Facturi Cheltueli\JJJJ\MM\` **und** Zeile in `Ausgaben_JJJJ.xlsx` (Entscheidung 3; Nexus-Office-Liste erst, wenn Finanzrechte im Programm trennbar sind).
2. **Fixkosten** (`Fixkosten.json`): Löhne, Sozialabgaben, Miete, Abos – einmal gepflegt, monatlich fortgeschrieben.
3. **Baustellenkosten**: Șantier-Bons (`receipts`) je Projekt aus der Cloud → Materialkosten je Projekt.
4. **Monatsabschluss (Jarvis, am 3. des Folgemonats)**: Umsatz (Rechnungen `erhalten`), offene Forderungen, Ausgaben nach Kategorie,
   Fixkosten, Stunden × interner Satz je Projekt → **Projektmarge** (Angebot − Stunden − Material). Als Excel in `02_Finanzen\Berichte\JJJJ-MM.xlsx`.
5. **Steuerberater**: einmal monatlich Ordner `Steuerberater\JJJJ\MM` mit allen Belegen (Jarvis sammelt, du prüfst, dann senden).

Was Jarvis nie allein tut: Rechnungen erstellen/versenden, Preise ändern, Zahlungen buchen. Immer Vorschlag → dein Ja.

---

## 7. Wissen erzeugen: Lessons Learned und Entscheidungen

**Der Prozess, damit nichts verloren geht:**
1. **Während des Projekts**: Jeder Fehler/Erkenntnis wird in 1 Satz per Stimme festgehalten („Jarvis, merk dir fürs Projekt: …“)
   → `008_Entscheidungen\notizen.md` im Projektordner, mit Datum, Person.
2. **Bei Planversand**: Jarvis fragt: „Gab es bei dieser Phase etwas, das das Team beim nächsten Mal wissen muss?“ (max. 3 Fragen).
3. **Bei Abschluss (Pflicht, 15 Minuten)**: Jarvis führt das Interview (Anhang B): Was lief anders als geplant? Was hat Zeit gekostet?
   Was würde ich dem Mitarbeiter sagen, der das nächste Mal so ein Projekt macht? Welche Kundenregel gilt künftig?
   → `009_Abschluss\LESSONS.md` → kopiert nach `03_Wissen\30_Projekte\<Code>.md`, Regeln einzeln nach `40_Lessons\L-####`, Kundenregeln nach `20_Kunden`.
4. **Rückkopplung**: Beim Anlegen eines neuen Projekts liest Jarvis `20_Kunden\<Kunde>.md` + die letzten 5 Lessons des Projekttyps vor.
   Beim Release-Check ergänzt er die Hausstandards um „Lessons“-Regeln (z. B. „bei PLS immer Steckdose neben Fenster prüfen“).
5. **Vierteljährlich**: Jarvis listet Lessons ohne Zuordnung zu einem Standard → du entscheidest, was in `10_Standards` übernommen wird.

Mehrsprachig: Interview auf Deutsch (du) oder Rumänisch (Team); Ablage Deutsch + `## RO`-Kurzfassung automatisch.

---

## 8. Zeit: wo bleibt die Zeit?

| Wer | Erfassung | Auswertung |
|---|---|---|
| Mitarbeiter Revit | ElecTriX TimeTracker (automatisch je Modell) + TrackingTime laut `Procedura de lucru - Planner + TrackingTime` | Jarvis liest `X:\08_Aplicatii\METools_Comments\METools_TimeTracker_<pid>.jsonl` und TrackingTime-MCP |
| Monteure | Șantier-Einträge (Minuten, Fahrt, Material) | je Projekt aus Supabase (`records`) |
| **Martin** | **TrackingTime ist führend** (Autotrack läuft bereits). Jarvis liest per TrackingTime-MCP; Tagesende: nur Lücken > 30 min nachfragen, 1 Korrektur, fertig. Kein Fenstertitel-Tracking | gleiche Auswertung; Vergleich Stunden zu Angebot nur Martin |

Regel: Jeder Termin, jede Mail, jede Datei trägt den **Projektcode** (`JJMM_NN`) – das ist der Schlüssel, über den alles zusammenfindet.

---

## 9. Rollen und Rechte

| Rolle | Ordner | Programme | Jarvis-Werkzeuge |
|---|---|---|---|
| Martin | alles | alle | alle (inkl. Nexus Office, Finanzen, Abrechnungsradar) |
| Buchhaltung (Frau, eigenes Synology-Konto) | `00_Office` | Nexus Office | eigener Jarvis: Office-Lesen, Eingangsrechnungen, Monatsabschluss |
| Planer (Raul / r.orban, Ioan Chindea, Stefan Picu / s.picu) | `01_Projekte`, `02_sabloane`, `03_Wissen` (lesen), `05_Marketing`, `06_Utile`, `08_Aplicatii` | Revit+ElecTriX, Nexus, Teams | Wissen, Projektstand (ohne Finanzen), Workboard, Revit-Pipe, eigene Mails/Kalender |
| Monteure | – | Șantier-App | Wissen (RO) über Teams-Bot/Nexus |

Technisch: Synology-Rechte sind vergeben (`00_Office` nur Martin, Rest alle); Admin-Prüfliste in Abschnitt 14. Jarvis prüft beim Start, welche Ordner erreichbar sind, und aktiviert nur passende Werkzeuge.
Entscheidungsstufen (Abschnitt 11) werden pro Werkzeug in der Jarvis-Konfiguration eingestellt: `nur lesen` / `vorschlagen` / `nach Ja ausführen` / `allein`.

---

## 10. Jarvis: Werkzeuge und Routinen

### 10.1 Neue Werkzeuge (Reihenfolge = Umsetzung)

| # | Werkzeug | Quelle | Schreibt? |
|---|---|---|---|
| 1 | `wissen_suchen`, `wissen_lesen`, `wissen_ablegen` (Entwurf/Freigabe) | `03_Wissen` + `_index.json` | ja, mit Regeln |
| 2 | `projekt_liste`, `projekt_steckbrief` | Registry + `PROJEKT.md` | Steckbrief ja |
| 3 | `workboard_liste`, `workboard_anlegen/zuweisen/erledigen` | `METools_Tasks_*.json` | ja, Lock-Verfahren |
| 4 | `revit_info/raeume/elemente/zeigen/freigabecheck` | ElecTriX-Pipe | nein (`select` nur Anzeige) |
| 5 | `projektstand` | kombiniert 1–4 (+ 6 bei Martin) | nein |
| 6 | `office_uebersicht/liste/datensatz/ueberfaellig` | Nexus-Office-Datenordner (nur wenn erreichbar) | nein; später Phase/LP-Status setzen nach Ja |
| 7 | `abrechnungsradar` | 5 + 6 | To-Do-Liste |
| 8 | `beleg_erfassen` | PDF/Foto → Ausgabenliste | ja, nach Ja |
| 9 | `zeit_heute/zeit_projekt` | TrackingTime-MCP, ergänzt um Pipe `info` | Zeitblöcke, nach Bestätigung |
| 10 | `lessons_interview` | Stimme | Markdown in Projekt + Wissen |
| 11 | `revit_parameter_setzen` | Pipe `set_parameters` | nach Vorlesen + Ja |
| 12 | `ablage_check` | `MEC_Inventar.csv` (SHA256), Dateinamen, Wurzel von X: | nein; Bericht: Duplikate, Zugangsdaten, Streudateien, Registry-Doppler |

### 10.2 Proaktive Routinen

| Wann | Was | Für wen |
|---|---|---|
| täglich 07:30 | Morgenbriefing: Termine, neue Workboard-Anfragen je Projekt, fällige Aufgaben, 1 Lesson zum heutigen Projekt | jeder |
| stündlich | Mail-Triage: neue Mails in Projekt/Finanz/Privat einordnen, Weiterleitung prüfen | jeder |
| täglich 17:30 | Tagesabschluss: Zeitblöcke bestätigen, offene Notizen ins Projekt, Erinnerungen für morgen | jeder |
| Freitag 15:00 | Wochenstand je laufendem Projekt (Stand · Fehlt · Nächster Schritt) | Martin, Team-Lead |
| 1. und 15. | Abrechnungsradar | Martin |
| 3. des Monats | Monatsabschluss (Ausgaben, Umsatz, Forderungen, Margen) | Martin, Buchhaltung |
| bei Projektabschluss | Lessons-Interview, Ordner nach `00_Abgeschlossen`, Wissen aktualisiert | Martin/Projektleiter |
| vierteljährlich | Standards-Review aus Lessons; Duplikat-/Ablage-Check | Martin |

---

## 11. Der „Klon“: Jarvis für das Team und Nexus als Projekt-Gehirn

- **Mitarbeiter-Jarvis** = dieselbe Software, eigener Microsoft-Login, eigene Keys, Werkzeuge 1–5 + 9 + 10, nie 6–8.
  Sprache automatisch (DE/RO), Wissensbasis liefert beide.
- **Nexus (Revit)** bleibt das Projekt-Gehirn in Revit und Teams; Jarvis gibt ihm nichts Neues, sondern nutzt dieselben Dateien.
  Vorschlag an den Kollegen: Nexus liest `03_Wissen\_index.json` ebenfalls → gleiche Antworten in beiden Systemen.
- **Entscheidungsstufen** je Werkzeug (konfigurierbar, Start konservativ):
  - `allein`: lesen, suchen, zusammenfassen, erinnern, Zeit vorschlagen
  - `nach Ja`: Workboard schreiben, Wissen ablegen, Parameter in Revit setzen, Antwortmail an Kunden
  - `nie`: Angebote, Preise, Rechnungen, Löschen außerhalb Papierkorb
- **Wenn Martin fehlt**: Team fragt seinen Jarvis oder Nexus → Antworten kommen aus Wissen + Projektstand mit Quelle.
  Was „nach Ja“ bräuchte, landet als Vorschlag in Martins To Do mit Begründung – er entscheidet per Stimme von unterwegs.

---

## 12. Umsetzungsplan

| Phase | Inhalt | Aufwand | Voraussetzung |
|---|---|---|---|
| **0 Stabil** (jetzt) | Jarvis im Alltag zuverlässig (Update, Einstellungen, ElevenLabs) | 1 Woche Nutzung | – |
| **1a Sicherheit** | Zugangsdaten von X: in KeePassXC, API-Key tauschen, Synology-Admin-Liste (Abschnitt 14) | 2 h Martin, 1 h Admin | – |
| **1b Struktur** | ✅ `03_Wissen`, `09_Archiv`, BRAIN.md, Glossar, `Hausstandards.md` angelegt (30.10.). Offen: `MEC_Inventar.csv` erstellen, Doppler-Bericht, `04_Documente` + `Proceduri MEC` umziehen, Office-Doppler nach Archiv, Revit-Pfadcheck vorher | 1 Tag | Inventar |
| **1c Daten** | `CustomerDomains` für 36 Projekte, erste 10 Standards + 5 Kundenprofile (Jarvis schlägt vor, Martin bestätigt per Stimme) | 3 h Martin | 1b |
| **2 Wissen in Jarvis** | Werkzeuge 1–2, `_index.json`, DE/RO-Antworten, `PROJEKT.md` für laufende Projekte anlegen (Jarvis fragt je Projekt 5 Dinge) | 3–4 Tage | Phase 1 |
| **3 Eingang** | Shared Mailbox tasks@, Transportregel, IMAP-OAuth2 für MailBridge, Kategorie `finance` → `nexus@`, Werkzeug 3 | 2 Tage + Absprache Kollege | Tenant-Prüfung, Kollege |
| **4 Projektstand** | Werkzeuge 4–5 (Revit-Pipe, kombinierte Antwort), Pflichtunterlagen-Check, Wochenstand | 4–5 Tage | Phase 2–3 |
| **5 Finanzen (nur Martin)** | Werkzeuge 6–7, Abrechnungsradar, Office-Dokumente über „Scan 00_Office“ bereinigen, Altordner nach Archiv | 3 Tage + Aufräumen | Office-Datenordner |
| **6 Ausgaben** | Werkzeug 8, Fixkosten, Monatsabschluss-Excel, Steuerberater-Ordner | 3 Tage | Phase 5, Entscheidung Excel vs. Nexus-Office-Liste |
| **7 Zeit** | Werkzeug 9 aus TrackingTime-MCP, Tagesabschluss, Stunden je Projekt | 1 Tag | Phase 4 |
| **8 Lessons** | Werkzeug 10, Abschluss-Ritual, Rückkopplung in Standards | 2 Tage | Phase 2 |
| **9 Team** | Jarvis-Installer für Mitarbeiter, Rollenprofile, Entscheidungsstufen, Nexus liest Wissensindex | 3 Tage + Kollege | Phasen 2–4 stabil |
| **10 Hintergrund** | Agenten je Projekt (Mails + Workboard + Revit beobachten, melden statt fragen), Revit schreiben (11) | offen | alles davor |

Reihenfolge-Prinzip: erst **lesen**, dann **vorschlagen**, zuletzt **schreiben**. Jede Phase ist für sich nützlich.

---

## 13. Entscheidungen (getroffen 30.10.2026)

| Nr. | Frage | Entscheidung |
|---|---|---|
| 1 | Tasks-Postfach | `tasks@me-concept.ro` als Shared Mailbox; Weiterleitung aus Martins Postfach und den drei Planer-Postfächern per Transportregel |
| 2 | Bestand `02…07` | Variante B (Abschnitt 3.1): bleibt, nur `03_Wissen` und `09_Archiv` neu, `00_Office` wird nicht neu angelegt |
| 3 | Ausgaben | `Ausgaben_JJJJ.xlsx` in `02_Facturi`; Nexus-Office-Liste später |
| 4 | Interner Stundensatz | Martin trägt `stundensatz_intern` in `Fixkosten.json` ein; Jarvis liest nur |
| 5 | Wissen freigeben | nur Martin; nach 3 Monaten prüfen, ob ein Planer Standards freigeben darf |
| 6 | `PROJEKT.md` in bestehende Ordner | ja, nur neue Dateien, nichts verschieben |
| 7 | Entscheidungsstufen | Lesen „allein“, alles andere „nach Ja“, Finanzen „nie“ |
| 8 | Projektmanager-Pfad | `00_Office\03_Clienti\Projektmanager`; Kopien in `01_Management` nach `09_Archiv` |
| 9 | Registry-Pfad | `08_Aplicatii\METools_Comments` führend; Wurzel-Kopie nach Bestätigung des Kollegen löschen |
| 10 | Passwörter | KeePassXC (kostenlos), Datenbank in `00_Office\01_Firma`; kein Bezahl-Passwortmanager |
| 11 | Sprache neuer Ordner | neue Ordner deutsch, bestehende rumänische Namen bleiben; Wissen DE mit `## RO` |

---

## 14. Synology: Prüfliste für den Admin (Rumänisch, zum Weiterleiten)

Rechte sind vergeben (`00_Office` nur Martin, alles andere alle). Zu prüfen bleibt, ob die Sperre wasserdicht ist und ob die NAS von außen angreifbar ist.

```
Solicitare: verificare NAS Synology, share „MEC_Database“ (X:). Nu muta și nu redenumi niciun folder, Revit are căi fixe.

1. Control Panel > Shared Folder > MEC_Database > Edit > Permissions: bifează „Enable advanced share permissions”.
2. Tab Advanced: bifează „Hide folders and files from users without permissions”.
3. File Station > MEC_Database > 00_Office > Properties > Permission: doar Martin (și contul contabilitate) Read/Write; ceilalți fără drepturi. Verifică cu Permission Inspector pentru un cont de angajat.
4. Creează utilizator `contabilitate` cu acces Read/Write numai la 00_Office. Nu se folosește contul lui Martin în comun.
5. Test de pe un PC de angajat: \\Database\MEC_Database\00_Office în Explorer → trebuie „Access denied”. Captură de ecran.
6. Control Panel > File Services > SMB > Advanced: „Enable Transfer Log” pentru Delete și Rename.
7. Snapshot Replication: snapshot zilnic MEC_Database, 30 zile; DSM ≥ 7.2: Immutable snapshots 7 zile.
8. Recycle Bin pe share: activat, „Restrict access to administrators only”.
9. Securitate externă: QuickConnect și port forwarding doar dacă sunt necesare; dacă nu, dezactivate. Fără DSM (5000/5001), SMB (445) sau RDP expuse pe internet. Acces de la distanță numai prin VPN (Synology VPN Server sau Tailscale).
10. Control Panel > Security: Firewall activ (numai LAN + VPN), Auto Block activ, 2FA obligatoriu pentru conturile admin, contul „admin” implicit dezactivat, DSM la zi.
11. Raport: versiune DSM, ce porturi sunt deschise spre internet, rezultatul testului de la pct. 5.
```

---

## Anhang A – `PROJEKT.md` (Vorlage)

```markdown
# 2510_07_PLS_24_19_Am Bungert
Stand: 2026-10-29 · Status: laufend · Projektleiter: Martin · Sprache Kunde: DE
Kunde: PLS · Ansprechpartner: … (Mail, Tel) · Architekt: …
Nexus-Office-ID: … · Registry-ID: dir_2510_07_PLS_24_19_Am Bungert
## Phasen
- LP2: abgerechnet (Versand 2026-06-12)
- LP3: beauftragt – Versand geplant 2026-11-15
- LP5: offen
## Ordner
Zentralmodell: 00_Zentralmodel · Grundlagen: 000_Eingang · Planung: 001_LPH2, 002_LPH3, 003_LPH5
## Pflichtunterlagen
- [x] Baubeschreibung  - [x] Architektenpläne 2026-09-30  - [ ] Brandschutzkonzept (fehlt, angefragt 2026-10-10)
- [x] Leistungsbilanz  - [ ] EVU-Schreiben
## Besonderheiten / Kundenregeln
- Kunde will DWG + PDF, Planliste als Excel
## Offene Punkte
- …
## Notizen (Datum · Wer · Text)
- 2026-10-20 · Martin · Steckdosen Küche nach Kundenwunsch 6 statt 4
```

## Anhang B – Lessons-Learned-Interview (Jarvis stellt die Fragen, 15 min)

1. Was lief anders als geplant – und warum?
2. Was hat am meisten Zeit gekostet, das nicht im Angebot war?
3. Welche Regel soll beim nächsten Projekt dieses Typs/Kunden gelten? (ein Satz, wird `L-####`)
4. Welche Entscheidung würdest du anders treffen? Begründung.
5. Was muss der Mitarbeiter wissen, der das nächste Mal so ein Projekt übernimmt?
6. Gab es etwas, das die Hausstandards (DIN/Räume/Dokumentation) ändern sollte?

Ablage: `009_Abschluss\LESSONS.md` → `03_Wissen\30_Projekte\<Code>.md` + `40_Lessons\` + `20_Kunden\` (Jarvis trennt und übersetzt).

## Anhang C – `_index.json` (Beispiel)

```json
[
  {"file": "10_Standards/steckdosen_je_raum.md", "title": "Steckdosen je Raum (DIN 18015-2)", "topic": "standard",
   "lang": ["de","ro"], "projects": [], "tags": ["steckdose","raum","din18015"], "updated": "2026-10-29"},
  {"file": "40_Lessons/L-0001_brandschutz_frueh_anfragen.md", "title": "Brandschutzkonzept vor LP3 anfordern", "topic": "lesson",
   "lang": ["de","ro"], "projects": ["2510_07"], "tags": ["brandschutz","lp3","unterlagen"], "updated": "2026-10-29"}
]
```
