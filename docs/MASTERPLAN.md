# Masterplan: Mayer E-Concept – Wissen, Ablage, Assistenten

Stand: 29.10.2026 · Autor: Jarvis-Projekt · Für: Martin Mayer (Entscheidung), Team (Ablage/Wissen), Kollege Nexus (Schnittstellen)

Grundlage: die Repos `Sprachassistent` (Jarvis), `ElecTriX-Revit-App` (Nexus/Workboard/MailBridge-Schnittstellen),
`Nexus-Office` (Projektmanager), `Nexus-santier` (Baustellen-App). Auf `X:\` (NAS) hatte ich keinen Zugriff –
alles, was mit **[prüfen]** markiert ist, musst du am Ist-Zustand abgleichen.

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
| **Projekte (gemeinsam)** | Nexus + ElecTriX + Share `01_Projekte`, `02_Wissen` | ganzes Büro | Anfragen, Aufgaben, Revit-Modell, Pläne, Standards, Lessons Learned |
| **Finanzen (vertraulich)** | Nexus Office + `00_Office` | nur Martin + Buchhaltung | Angebote, Aufträge, Unterschriften, Rechnungen, Ausgaben, Löhne |

Jarvis ist das **Sprachrohr** über alle drei Ebenen – er kopiert keine Daten, er fragt die zuständige Quelle.
Auf Mitarbeiter-PCs ist die Finanz-Ebene technisch gar nicht vorhanden (kein Ordnerzugriff, kein Werkzeug).

---

## 1. Ist-Stand (aus dem Code abgeleitet)

| Bereich | Heute | Lücke |
|---|---|---|
| Projekte/Finanzen | Nexus Office: Kunden, Projekte (`code`, `projekt_nr`, Status `angebot/beauftragt/laufend/fertig`, Beauftragung `nein/email/ja`, LP2/LP3/LP5 je `offen/beauftragt/abgerechnet`), Angebote, Rechnungen (Phasen LP2/LP3/LP5/1.TR/2.TR/Gesamt/Nachtrag, Zahlung `offen/erhalten/teilweise`, Mahnstufen), Nachträge, Unterschriften-Prüfung, Dokumentablage `Dokumente\00_Eingang / 01_Unterschrieben / 02_Nicht unterschrieben`, Scan von `00_Office`, Mail-Eingang `nexus@me-concept.ro` (MailBridge, Angebotsmodus) | Ausgaben/Löhne/Eingangsrechnungen fehlen; Phasenstatus wird von Hand gepflegt; Doppler in `00_Office` |
| Anfragen/Aufgaben | MailBridge liest `tasks@…` [prüfen] per IMAP → `METools_Tasks_<projekt>.json` (Kategorie, Dringlichkeit, Projektvermutung, Anhänge nach `01_Projekte\<Projekt>\000_Mail-Eingang`), Workboard in Revit, Nexus, Teams-Bot „Asistent“ | nicht alle Postfächer leiten dorthin; keine Rückmeldung „erledigt“ an Absender; keine Wissensableitung |
| Revit | ElecTriX-Pipe `METools.Revit.<user>.<pid>`: `info`, `room_counts`, `find_elements`, `select`, `release_check`, `set_parameters`; Hausstandards `METools_RoomStandards.json`; Plans Out → `<Code>_Planung\JJMMTT\` + `Planliste_JJMMTT.csv`; Kommentare, Aktivitätslog | Projektstand nicht maschinenlesbar zusammengefasst |
| Projektregister | `METools_ProjectRegistry.json`, automatisch aus Ordnern `01_Projekte\JJMM_NN_Kunde_Nr_Name` und `00_Abgeschlossen` | keine Verknüpfung zur Nexus-Office-Projekt-ID [prüfen] |
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
            │ 02_Wissen     │  │ Nexus/ElecTriX│  │ Nexus Office       │
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

---

## 3. Ordnerstruktur `\\Database\MEC_Database` (X:)

### 3.1 Oberste Ebene (Vorschlag)

| Ordner | Inhalt | Rechte (NTFS-Gruppe) | Änderung |
|---|---|---|---|
| `00_Office` | Firma + Finanzen (siehe 3.2) | **MEC-Office** (Martin, Buchhaltung) | innen aufräumen |
| `01_Projekte` | ein Ordner je Projekt, Revit/Cloud-Referenzen | MEC-Team | **Bestand unverändert**; nur Vorlage für neue Projekte + `PROJEKT.md` ergänzen |
| `02_Wissen` | die Brain-Wissensbasis (3.3) | lesen: MEC-Team; schreiben: Martin + Freigegebene | **neu** |
| `03_Standards` | Revit-Templates, Familien, Shared Parameters, CAD-Layer, Dokumentvorlagen (Word/Excel), Logo | lesen: Team; schreiben: Martin + Revit-Verantwortlicher | neu oder aus Bestand zusammenziehen [prüfen] |
| `04_Kunden_Partner` | je Kunde/Architekt: NDAs, Rahmenverträge, Liefervorgaben (ohne Preise) | Team | neu [prüfen, ob heute in 00_Office] |
| `05_Personal_intern` | Onboarding, Schulungen, Hardware-Liste, Lizenzen (technisch) | Team lesen, Martin schreiben | neu |
| `08_Aplicatii` | Nexus, ElecTriX, METools_*-JSON, Releases | unverändert | – |
| `09_Archiv` | alles Alte, das nicht mehr gebraucht wird, aber nicht gelöscht werden soll; Unterordner nach Jahr | Team lesen | neu – **hierhin wandern die Doppler und Altordner** |

Bestehende Ordner `02…07` [prüfen]: jedem einen Platz oben zuweisen oder nach `09_Archiv\<Jahr>_<alter Name>`.
Nichts löschen, nur verschieben; vorher eine Dateiliste (Jarvis kann sie erstellen) als Nachweis ablegen.

### 3.2 `00_Office` (vertraulich)

```
00_Office\
  00_Eingang\                 alles Neue, das noch nicht einsortiert ist (Scanner, Downloads)
  01_Firma\                   Gründung, Verträge, Versicherungen, Fahrzeuge, Miete, Bank-Stammdaten
  02_Finanzen\
     Eingangsrechnungen\JJJJ\MM\   Lieferanten, Software, Material (Dateiname: JJJJ-MM-TT_Lieferant_Betrag_Projektcode.pdf)
     Ausgangsrechnungen\JJJJ\      = PDF aus Nexus Office (dort "Save PDF"), nur Kopie
     Bank\JJJJ\                    Kontoauszüge/Exports
     Loehne\JJJJ\                  Lohnabrechnungen, Verträge
     Steuerberater\JJJJ\           was an die Kontabilă geht / zurückkommt
     Fixkosten.json                monatliche Fixposten (Löhne, Mieten, Abos) – Jarvis liest sie für die Monatsübersicht
  03_Clienti\Projektmanager\  **bleibt** (Nexus-Office-Datenordner: data\, files\, PDF\, Dokumente\, inbox\)
  04_Angebote_Auftraege\      NUR noch Altbestand → mit "Scan 00_Office" in Projektmanager\Dokumente einsortieren, danach leer/Archiv
  05_Vorlagen_Office\         Briefpapier, Angebots-/Rechnungsvorlagen (fachliche Vorlagen liegen in 03_Standards)
```

Aufräumregel für die Doppler: **Nexus Office „Scan 00_Office“** (gibt es schon) jede Datei einmal zuordnen → Original bleibt,
Kopie wandert nach `Projektmanager\Dokumente\01/02_…\<Projektcode>\`. Danach die alten Ordner nach `09_Archiv`.
Jarvis-Aufgabe später: Duplikate per Hash finden und melden.

### 3.3 `02_Wissen` – die Brain-Wissensbasis

```
02_Wissen\
  BRAIN.md                    Startseite: Was liegt wo, wie wird geschrieben, die 20 wichtigsten Regeln (DE)
  BRAIN.ro.md                 dieselbe Startseite auf Rumänisch
  _index.json                 maschinenlesbar: Datei · Titel · Thema · Sprache(n) · Projekte · Stichworte · Stand – pflegt Jarvis
  00_Firma\                   Leitbild, Rollen, Prozesse (Angebot → Auftrag → LP → Abrechnung → Abschluss), Checklisten je Phase
  10_Standards\               fachlich: DIN 18015 (Räume → RoomStandards), VDE, Brandschutz, Dokumentationsumfang, Revit-Konventionen,
                              Planinhalte je LP, Benennung von Plänen/Bauteilen
  20_Kunden\<Kunde>.md        je Kunde: Ansprechpartner, Lieferformate, Eigenheiten, "will immer…/nie…"
  30_Projekte\<Code>.md       Steckbrief + Lessons Learned je Projekt (Kopie von 01_Projekte\<Code>\PROJEKT.md beim Abschluss)
  40_Lessons\L-0001_….md      Fehler → Ursache → Regel → wo gilt sie; nach Thema; verlinkt auf Projekt
  50_Entscheidungen\E-0001_….md  Entscheidung · Begründung · Alternativen · Datum · Projekt · wer
  60_Glossar\glossar.md       Fachbegriffe DE ⇄ RO ⇄ EN (für Übersetzung und Suche)
  70_Anleitungen\             Schritt-für-Schritt (ElecTriX, Nexus, Revit-Workflows, Șantier-App)
```

**Schreibregeln (stehen in BRAIN.md):**
- Eine Datei = ein Thema. Kopfzeile immer: `# Titel`, `Stand:`, `Gilt für:`, `Sprache:`.
- Jede Datei beginnt auf Deutsch; Abschnitt `## RO` mit der rumänischen Kurzfassung (Jarvis übersetzt und hält beide Seiten gleich).
- Lessons Learned haben eine Nummer `L-####`, eine Regel in einem Satz und werden bei Projektabschluss **verpflichtend** geschrieben (Abschnitt 7).
- Entscheidungen werden nur mit Begründung abgelegt – „weil der Kunde…“, „weil DIN…“.
- Wer schreiben darf: Martin direkt; Mitarbeiter legen Vorschläge in `_Entwurf\` ab, Jarvis meldet sie Martin zur Freigabe.
- Die KI sucht zuerst in `_index.json`, dann im Text; antwortet mit Quelle (Datei + Abschnitt). Ohne Quelle keine Behauptung.

### 3.4 Projektordner (Vorlage für **neue** Projekte, Bestand bleibt)

```
01_Projekte\JJMM_NN_Kunde_ProjNr_Name\        z. B. 2510_07_PLS_24_19_Am Bungert (Konvention bleibt)
  PROJEKT.md                 Steckbrief (maschinenlesbar, s. Anhang A): Kunde, Ansprechpartner, Phasen, Pflichtunterlagen, Stand
  000_Mail-Eingang\          bestehend – MailBridge legt Anhänge ab
  01_Grundlagen\             Architektenpläne, IFC, Bestand, Baubeschreibung, Brandschutzkonzept, Lastenheft
  02_Planung\                Revit-Modell(e), DWG; **bestehender Name `<Code>_Planung` bleibt, Plans Out schreibt dorthin**
  03_Berechnungen\           Leistungsbilanz, Kurzschluss, Beleuchtung, Kabel
  04_Planversand\            = `<Code>_Planung\JJMMTT\` wie bisher (Plans Out) – kein neuer Ordner, nur hier dokumentiert
  05_Korrespondenz\          Protokolle, Abstimmungen, Besprechungen (JJJJ-MM-TT_Thema.pdf)
  06_Entscheidungen\         kurze Notizen, die später nach 02_Wissen\50_Entscheidungen wandern
  99_Abschluss\              Übergabe, Lessons Learned (Vorlage Anhang B), Schlussstand
```

**Was NICHT in `01_Projekte` liegt:** Angebote, Aufträge, Unterschriften, Rechnungen, Preise, Nachträge mit Beträgen → `00_Office\03_Clienti\Projektmanager`.
Nexus Office zeigt sie beim Projekt an (gibt es schon: Beauftragung, Unterschrift, Dokumente). Im Projektordner darf höchstens ein
`AUFTRAG_vorhanden.txt` liegen (Jarvis legt es an), damit das Team weiß: Auftrag ist da.

### 3.5 Dateinamen

- Dokumente: `JJJJ-MM-TT_Thema_Absender.pdf` (Datum zuerst → sortiert sich von selbst)
- Pläne: wie Plans Out (`{nummer}_{index}_{name}`), Planliste bleibt CSV
- Eingangsrechnungen: `JJJJ-MM-TT_Lieferant_Betrag_Projektcode.pdf` (ohne Projekt: `_ALLG`)
- Keine Leerzeichen am Anfang, keine Umlaute in Ordnernamen neuer Projekte (Revit-Cloud-Referenzen) [prüfen, wie bisher]

---

## 4. Eingang: Mails und Aufgaben

**Zwei Postfächer, zwei Welten:**

| Postfach | Zweck | Verarbeitung | Sichtbar für |
|---|---|---|---|
| `tasks@…` [prüfen Adresse] | alles, was mit Projektarbeit zu tun hat (Anfragen, Änderungen, Fragen, Termine, Planlieferungen) | MailBridge → `METools_Tasks_<projekt>.json` + Anhänge → `000_Mail-Eingang` → Workboard/Nexus/Teams | Team |
| `nexus@me-concept.ro` | Angebotsanfragen, Lieferantenangebote, Rechnungen, Verträge | MailBridge Angebotsmodus → Nexus Office Eingang | Martin, Buchhaltung |

**Outlook-Regeln (du richtest sie ein, Jarvis kann sie dir vorlesen/prüfen):**
1. In jedem deiner Postfächer: *Weiterleiten als Kopie an `tasks@`*, wenn Absenderdomain = Kunde/Architekt (Liste aus `METools_ProjectRegistry.json` → `CustomerDomains`) **und** Betreff nicht „Angebot/Rechnung/Ofertă/Factură“.
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
| Abschluss | Projekt `fertig` | Lessons Learned geschrieben, Ordner nach `00_Abgeschlossen` | Zahlungseingang überwachen |

### 5.2 Pflichtunterlagen je Projekt (Jarvis prüft und mahnt)

Baubeschreibung · Brandschutzkonzept · aktuelle Architektenpläne/IFC · Raumbuch/Nutzung · Leistungsbilanz · Versorgungskonzept ·
Hausanschluss/EVU-Schreiben · Auftrag (Hinweisdatei) · Freigabeprotokolle. Liste je Projekttyp in `02_Wissen\00_Firma\Checklisten`
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

1. **Eingangsrechnungen**: landen in `00_Office\00_Eingang` oder per Mail in `nexus@`. Jarvis liest sie (PDF/Foto), schlägt vor:
   Lieferant · Datum · Betrag · MwSt · Kategorie (Material/Software/Fahrzeug/Miete/Sonstiges) · Projektcode · Zahlziel → Ablage
   nach `02_Finanzen\Eingangsrechnungen\JJJJ\MM\` **und** Zeile in `Ausgaben_JJJJ.xlsx` (oder, mit Kollegen abgestimmt, neue Nexus-Office-Liste `ausgaben`).
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
   → `06_Entscheidungen\notizen.md` im Projektordner, mit Datum, Person.
2. **Bei Planversand**: Jarvis fragt: „Gab es bei dieser Phase etwas, das das Team beim nächsten Mal wissen muss?“ (max. 3 Fragen).
3. **Bei Abschluss (Pflicht, 15 Minuten)**: Jarvis führt das Interview (Anhang B): Was lief anders als geplant? Was hat Zeit gekostet?
   Was würde ich dem Mitarbeiter sagen, der das nächste Mal so ein Projekt macht? Welche Kundenregel gilt künftig?
   → `99_Abschluss\LESSONS.md` → kopiert nach `02_Wissen\30_Projekte\<Code>.md`, Regeln einzeln nach `40_Lessons\L-####`, Kundenregeln nach `20_Kunden`.
4. **Rückkopplung**: Beim Anlegen eines neuen Projekts liest Jarvis `20_Kunden\<Kunde>.md` + die letzten 5 Lessons des Projekttyps vor.
   Beim Release-Check ergänzt er die Hausstandards um „Lessons“-Regeln (z. B. „bei PLS immer Steckdose neben Fenster prüfen“).
5. **Vierteljährlich**: Jarvis listet Lessons ohne Zuordnung zu einem Standard → du entscheidest, was in `10_Standards` übernommen wird.

Mehrsprachig: Interview auf Deutsch (du) oder Rumänisch (Team); Ablage Deutsch + `## RO`-Kurzfassung automatisch.

---

## 8. Zeit: wo bleibt die Zeit?

| Wer | Erfassung | Auswertung |
|---|---|---|
| Mitarbeiter Revit | ElecTriX TimeTracker (automatisch je Modell) | Stunden je Projekt/Woche, Jarvis liest `TimeTracker`-JSON [prüfen Pfad] |
| Monteure | Șantier-Einträge (Minuten, Fahrt, Material) | je Projekt aus Supabase (`records`) |
| **Martin** | **automatisch durch Jarvis**: aktives Revit-Modell (Pipe `info` → Dokumenttitel → Projektcode), Fenstertitel (Outlook/Office: Projektcode im Betreff/Pfad), Kalendertermine (Projektcode im Titel), Mithör-Protokoll (Projektname genannt) → Zeitblöcke ≥ 10 min je Projekt; Tagesende: „Stimmt das so?“ – 1 Korrektur, fertig | gleiche Auswertung |

Regel: Jeder Termin, jede Mail, jede Datei trägt den **Projektcode** (`JJMM_NN`) – das ist der Schlüssel, über den alles zusammenfindet.

---

## 9. Rollen und Rechte

| Rolle | Ordner | Programme | Jarvis-Werkzeuge |
|---|---|---|---|
| Martin | alles | alle | alle (inkl. Nexus Office, Finanzen, Abrechnungsradar) |
| Buchhaltung (Frau) | `00_Office` | Nexus Office | eigener Jarvis: Office-Lesen, Eingangsrechnungen, Monatsabschluss |
| Planer (Mitarbeiter) | `01_Projekte`, `02_Wissen` (lesen), `03_Standards`, `08_Aplicatii` | Revit+ElecTriX, Nexus, Teams | Wissen, Projektstand (ohne Finanzen), Workboard, Revit-Pipe, eigene Mails/Kalender |
| Monteure | – | Șantier-App | Wissen (RO) über Teams-Bot/Nexus |

Technisch: NTFS-Gruppen `MEC-Office`, `MEC-Team`; Jarvis prüft beim Start, welche Ordner erreichbar sind, und aktiviert nur passende Werkzeuge.
Entscheidungsstufen (Abschnitt 11) werden pro Werkzeug in der Jarvis-Konfiguration eingestellt: `nur lesen` / `vorschlagen` / `nach Ja ausführen` / `allein`.

---

## 10. Jarvis: Werkzeuge und Routinen

### 10.1 Neue Werkzeuge (Reihenfolge = Umsetzung)

| # | Werkzeug | Quelle | Schreibt? |
|---|---|---|---|
| 1 | `wissen_suchen`, `wissen_lesen`, `wissen_ablegen` (Entwurf/Freigabe) | `02_Wissen` + `_index.json` | ja, mit Regeln |
| 2 | `projekt_liste`, `projekt_steckbrief` | Registry + `PROJEKT.md` | Steckbrief ja |
| 3 | `workboard_liste`, `workboard_anlegen/zuweisen/erledigen` | `METools_Tasks_*.json` | ja, Lock-Verfahren |
| 4 | `revit_info/raeume/elemente/zeigen/freigabecheck` | ElecTriX-Pipe | nein (`select` nur Anzeige) |
| 5 | `projektstand` | kombiniert 1–4 (+ 6 bei Martin) | nein |
| 6 | `office_uebersicht/liste/datensatz/ueberfaellig` | Nexus-Office-Datenordner (nur wenn erreichbar) | nein; später Phase/LP-Status setzen nach Ja |
| 7 | `abrechnungsradar` | 5 + 6 | To-Do-Liste |
| 8 | `beleg_erfassen` | PDF/Foto → Ausgabenliste | ja, nach Ja |
| 9 | `zeit_heute/zeit_projekt` | Pipe `info`, Fenstertitel, Kalender | Zeitblöcke, nach Bestätigung |
| 10 | `lessons_interview` | Stimme | Markdown in Projekt + Wissen |
| 11 | `revit_parameter_setzen` | Pipe `set_parameters` | nach Vorlesen + Ja |

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
  Vorschlag an den Kollegen: Nexus liest `02_Wissen\_index.json` ebenfalls → gleiche Antworten in beiden Systemen.
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
| **1 Struktur** | Ordner 02/03/04/05/09 anlegen, NTFS-Gruppen, BRAIN.md + Vorlagen, erste 10 Standards + 5 Kundenprofile schreiben (Jarvis hilft beim Diktieren) | 2–3 Tage Martin, 1 Tag Umsetzung | NAS-Zugriff, Gruppen |
| **2 Wissen in Jarvis** | Werkzeuge 1–2, `_index.json`, DE/RO-Antworten, `PROJEKT.md` für laufende Projekte anlegen (Jarvis fragt je Projekt 5 Dinge) | 3–4 Tage | Phase 1 |
| **3 Eingang** | Outlook-Regeln, MailBridge-Kategorie `finance` → `nexus@`, Werkzeug 3 (Workboard lesen, dann schreiben) | 2 Tage + Absprache Kollege | tasks@-Adresse, Kollege |
| **4 Projektstand** | Werkzeuge 4–5 (Revit-Pipe, kombinierte Antwort), Pflichtunterlagen-Check, Wochenstand | 4–5 Tage | Phase 2–3 |
| **5 Finanzen (nur Martin)** | Werkzeuge 6–7, Abrechnungsradar, Office-Dokumente über „Scan 00_Office“ bereinigen, Altordner nach Archiv | 3 Tage + Aufräumen | Office-Datenordner |
| **6 Ausgaben** | Werkzeug 8, Fixkosten, Monatsabschluss-Excel, Steuerberater-Ordner | 3 Tage | Phase 5, Entscheidung Excel vs. Nexus-Office-Liste |
| **7 Zeit** | Werkzeug 9, Tagesabschluss, Auswertung Stunden je Projekt | 3 Tage | Phase 4 |
| **8 Lessons** | Werkzeug 10, Abschluss-Ritual, Rückkopplung in Standards | 2 Tage | Phase 2 |
| **9 Team** | Jarvis-Installer für Mitarbeiter, Rollenprofile, Entscheidungsstufen, Nexus liest Wissensindex | 3 Tage + Kollege | Phasen 2–4 stabil |
| **10 Hintergrund** | Agenten je Projekt (Mails + Workboard + Revit beobachten, melden statt fragen), Revit schreiben (11) | offen | alles davor |

Reihenfolge-Prinzip: erst **lesen**, dann **vorschlagen**, zuletzt **schreiben**. Jede Phase ist für sich nützlich.

---

## 13. Entscheidungen, die nur du treffen kannst

1. Adresse des Tasks-Postfachs und welche Postfächer weiterleiten sollen.
2. Bestehende Ordner `02…07` auf X: – zuordnen oder archivieren (ich brauche eine Liste der obersten zwei Ebenen).
3. Ausgaben: eigene Excel (`Ausgaben_JJJJ.xlsx`) **oder** neue Liste in Nexus Office (dann Kollege einbinden).
4. Interner Stundensatz für Margenberechnung (nur für dich sichtbar).
5. Wer außer dir Wissen freigeben darf (Teamleiter?).
6. Ob `PROJEKT.md` auch in bestehende Projektordner darf (nur eine neue Datei, keine Verschiebung – Revit-Referenzen bleiben unberührt).
7. Entscheidungsstufen zum Start (Vorschlag: alles „nach Ja“, Lesen „allein“).

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

Ablage: `99_Abschluss\LESSONS.md` → `02_Wissen\30_Projekte\<Code>.md` + `40_Lessons\` + `20_Kunden\` (Jarvis trennt und übersetzt).

## Anhang C – `_index.json` (Beispiel)

```json
[
  {"file": "10_Standards/steckdosen_je_raum.md", "title": "Steckdosen je Raum (DIN 18015-2)", "topic": "standard",
   "lang": ["de","ro"], "projects": [], "tags": ["steckdose","raum","din18015"], "updated": "2026-10-29"},
  {"file": "40_Lessons/L-0001_brandschutz_frueh_anfragen.md", "title": "Brandschutzkonzept vor LP3 anfordern", "topic": "lesson",
   "lang": ["de","ro"], "projects": ["2510_07"], "tags": ["brandschutz","lp3","unterlagen"], "updated": "2026-10-29"}
]
```
