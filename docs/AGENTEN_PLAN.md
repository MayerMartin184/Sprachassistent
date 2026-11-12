# Agenten-Plan: Jarvis als Team aus Agenten – optimales Ergebnis bei minimalem Verbrauch

Stand: 12.11.2026 (Rev. A) · Für: Martin Mayer (Entscheidung), Kollege Nexus (Schnittstellen) · Ergänzt MASTERPLAN.md Abschnitte 10 bis 12

Ausgangslage aus dem Code (Stand f5d32ed): ein Agent, 54 Werkzeuge, ein Modell für alles, Verlauf wächst den ganzen
Tag ohne Kürzung, Cache nur auf dem System-Text mit 5-Minuten-Laufzeit, Gedächtnis als flache JSON-Liste in jedem Aufruf,
Erinnerungen und Mithör-Modus laufen durch den vollen Agenten. Kein Projektwissen in Dateien, daher liest das Modell bei
jeder Frage neu.

---

## 0. Die drei Zusagen

| Zusage | Woran sie hängt | Wie sie gesichert wird |
|---|---|---|
| **Nichts wird vergessen** | Jede Information hat genau einen Ablageort und wird sofort dort angehängt, nie nur im Gesprächsverlauf gehalten | Schreibpfad (Abschnitt 3): jede Aussage landet in derselben Runde in der Zieldatei, mit Datum und Person. Verlauf darf gekürzt werden, Dateien nie |
| **Keine falschen Informationen** | Jede Antwort über Projekte, Normen, Personen hat eine Quelle mit Stand | Quellenpflicht (Abschnitt 4): Datei + Abschnitt + Stand in jeder Antwort; ohne Quelle keine Behauptung. Wöchentlicher Abgleich meldet Widersprüche zwischen Quellen |
| **Aufgaben gehen an den richtigen Agenten** | Verteilung nach festen Regeln, nicht nach Gefühl | Verteiltabelle (Abschnitt 5): Anfragetyp → Agent → Modell → Werkzeuge → Quellen → Schreibrecht. Nur Unklares entscheidet ein kleines Modell |

---

## 1. Wissen in drei Klassen (Änderungsrate bestimmt die Behandlung)

| Klasse | Beispiele | Ändert sich | Ablage | Lesen | Schreiben |
|---|---|---|---|---|---|
| **Stabil** | DIN 18015, VDE, Brandschutz, Hausstandards, Prozesse, Glossar, Vorlagen | selten, nur mit Ausgabestand | `X:\03_Wissen\10_Standards`, `00_Firma`, `60_Glossar` | über `_index.json`, dann eine Datei, gecacht 1 h | nur Martin; Vorschläge in `_Entwurf\`; nie automatisch aus dem Web |
| **Lebendig** | Projektstand, Phasen, offene Punkte, Kundenregeln, Entscheidungen, Lessons | täglich | `01_Projekte\<Code>\PROJEKT.md` (führend), `008_Entscheidungen\notizen.md`, Registry, Workboard, Nexus Office | immer frisch lesen, nie aus dem Gedächtnis beantworten | nur anhängen (Datum · Wer · Was); Änderungsliste in der Datei |
| **Persönlich** | Gewohnheiten, Absprachen, Personen, Arbeitsweise | laufend | `~\.sprachassistent\gedaechtnis\` (Abschnitt 2) | Kern immer, Rest auf Abruf | Jarvis allein, kurze Bestätigung |

**Regel für Normen (Klasse Stabil):** Kopfzeile jeder Datei enthält `ausgabe:` (z. B. `DIN 18015-2:2021-10`), `quelle:` (Dokument
oder „Normtext liegt nicht vor“), `geprueft_am:`. Liegt der Normtext nicht vor, antwortet jeder Agent mit „nicht geprüft,
Ersatzquelle: …“. Ein Quartals-Agent listet alle Standards mit `geprueft_am` älter als 12 Monate; Martin bestätigt oder ändert.
Web-Recherche zu Normen darf nur nach `_Entwurf\` schreiben, nie nach `10_Standards`.

**Regel für Projekte (Klasse Lebendig):** `PROJEKT.md` trägt `Stand:` in der ersten Zeile. Bei jeder Antwort nennt der Agent
den Stand. Ist er älter als 14 Tage, sagt er das ungefragt („Stand vom 20.10., seitdem keine Notiz“). Widersprüche zwischen
`PROJEKT.md`, Registry, Workboard und Nexus Office werden gemeldet, nicht stillschweigend aufgelöst; der Mensch entscheidet,
der Agent trägt das Ergebnis mit Datum ein.

---

## 2. Persönliches Gedächtnis als Markdown (ersetzt `memory.json`)

```
~\.sprachassistent\gedaechtnis\
  KERN.md            höchstens 1.500 Zeichen, immer im System-Prompt, gecacht: Name, Rolle, Arbeitsweise, 10 feste Regeln
  personen.md        Name · Rolle · Firma · Kontakt · Eigenheiten (eine Zeile je Person)
  gewohnheiten.md    Abläufe, Vorlieben, Formate
  absprachen.md      offene Zusagen mit Datum, erledigte wandern nach tagebuch
  projekte\<Code>.md persönliche Notizen zum Projekt (was NICHT ins gemeinsame PROJEKT.md gehört)
  tagebuch\JJJJ-MM-TT.md   je Runde zwei Zeilen: was gefragt, was getan, was offen
  _index.md          eine Zeile je Datei: Pfad · Titel · Stand · Stichworte (pflegt Jarvis nach jedem Schreiben)
```

- `memory_search` liest zuerst `_index.md` und liefert nur Treffer-Zeilen; erst `memory_read` holt eine Datei.
- `memory_save` hängt an die passende Datei an und aktualisiert `_index.md`. Nie überschreiben.
- Beim Start liest Jarvis `KERN.md` und die letzten 20 Zeilen des heutigen und gestrigen Tagebuchs. Mehr nicht.
- Bestehende `memory.json` wird einmalig in diese Dateien übertragen (Werkzeug `memory_migrate`, einmal, mit Bericht).

---

## 3. Der Schreibpfad: so geht nichts verloren

1. Jede Aussage des Nutzers, die eine Tatsache enthält („Kunde will 6 Steckdosen“, „Brandschutz kommt Freitag“), wird **in derselben Runde** geschrieben, bevor Jarvis antwortet. Ziel nach Tabelle in Abschnitt 1. Jarvis bestätigt mit Datei und Zeile („Notiert in PROJEKT.md 2510_07, Notizen“).
2. Werkzeug-Ergebnisse, die Wissen enthalten (Transkript-Zusammenfassung, Recherche, Review), werden als Datei gespeichert, nicht nur gesprochen. Der Verlauf enthält danach nur den Pfad.
3. Nach jeder Runde: zwei Zeilen ins Tagebuch. Nach 30 Minuten Pause oder ab 40.000 Tokens Verlauf: ältere Runden werden zu einem Absatz zusammengefasst, der Absatz steht im Tagebuch **und** ersetzt die alten Runden im Verlauf. Nichts geht verloren, der Verlauf bleibt klein.
4. Beim Beenden der App: offene Runde abschließen, Tagebuch schreiben. Beim nächsten Start weiß Jarvis, wo er war.
5. Jeden Freitag 15:00 (Abgleich-Agent): für jedes laufende Projekt `PROJEKT.md` gegen Registry, Workboard, Planversand-Ordner und Nexus Office prüfen. Ergebnis als Liste „Widersprüche · Fehlende Pflichtunterlagen · Stand älter als 14 Tage“ in To Do und als Datei `03_Wissen\_Entwurf\abgleich_JJJJ-MM-TT.md`.

---

## 4. Quellenpflicht und Antwortform

- Antworten über Projekte, Normen, Personen, Zahlen: immer mit Quelle „(PROJEKT.md 2510_07, Stand 2026-11-10)“ oder „(10_Standards/steckdosen_je_raum.md, DIN 18015-2:2021-10)“.
- Ohne Quelle: „Dazu habe ich nichts Belegtes“ statt einer Vermutung.
- Zwei Quellen widersprechen sich: beide nennen, nicht entscheiden.
- Gesprochene Antwort bleibt kurz; Quelle steht im Fenster-Text, gesprochen nur „Stand vom zehnten November“.

---

## 5. Agenten und Verteilung

### 5.1 Die Rollen

| Agent | Modell · Effort | Werkzeuge (Anzahl) | Verlauf | Darf schreiben | Aufgabe |
|---|---|---|---|---|---|
| **Dialog** (Jarvis selbst) | Sonnet 5.5 · low | Sprache, Gedächtnis, Erinnerungen, Listen, `ask_agent` (12) | ja, gekürzt | Gedächtnis, Tagebuch | spricht mit dem Nutzer, verteilt, fasst Ergebnisse in einen Satz |
| **Wissen** | Haiku 5.5 · low | `wissen_index`, `wissen_lesen`, `files_read` (3) | nein | nein | findet Standard, Lesson, Kundenregel; liefert Auszug mit Quelle und Stand |
| **Projekt** | Sonnet 5.5 · medium | `projekt_steckbrief`, `projekt_notiz`, Registry, Workboard, `files_list/search/read` (8) | nein | `PROJEKT.md`, `notizen.md`, Workboard nach Ja | Projektstand, Pflichtunterlagen, Notizen, Änderungsliste |
| **Büro** | Sonnet 5.5 · low | Mail, Kalender, To Do, Teams, Planner (26) | nein | Versand nach Ja | alles Microsoft 365 |
| **Dateien** | Haiku 5.5 · low | `files_*`, `create_docx/xlsx/pptx` (13) | nein | Dateien | suchen, ordnen, erstellen, lesen und zusammenfassen |
| **Prüfer** | Opus 5.5 · high | keine, nur Text + Wissens-Auszüge | nein | nein | Einwand-Check, Normen-Abgleich, Rechnen, Entscheidung mit Varianten (Planungsregeln 1 bis 3 des Nutzers) |
| **Hintergrund** | Haiku 5.5 · low | `todo_add`, `reminder_set`, `calendar_list` (3) | nein | To Do, Erinnerungen | Erinnerungen formulieren, Termine melden, Mithör-Extraktion |
| **Abgleich** (geplant, Freitag) | Sonnet 5.5 · medium | Projekt + Wissen lesend (8) | nein | `_Entwurf\abgleich_*.md`, To Do | Abschnitt 3 Punkt 5 |
| **Ablage** (geplant, nachts) | Haiku 5.5 · low | `files_list`, `wissen_index_bauen` (2) | nein | `_index.json`, `_index.md` | Index aus Dateidaten neu bauen, wenn sich Dateien geändert haben; Streudateien und Zugangsdaten melden |

Technisch: jeder Agent ist eine `Agent`-Instanz mit eigenem System-Text, eigener Werkzeugliste (`ToolRegistry` nur mit seinen
Werkzeugen) und eigenem Modell. Dialog ruft sie über ein Werkzeug `ask_agent(agent, auftrag, kontext)` und bekommt nur das
Ergebnis zurück, nie den Weg. Das bestehende `ask_model` wird zu `ask_agent("pruefer", …)`.

### 5.2 Verteiltabelle (erst Regel, dann Modell)

Stufe 1, Regel ohne Modell (im Code, `router.py`): Stichworte und Muster aus der Erkennung.

| Anfrage enthält | Agent | Beispiel |
|---|---|---|
| Projektcode `JJMM_NN`, „Projekt“, „Stand“, „fehlt“, „Pflichtunterlagen“, „Notiz fürs Projekt“ | Projekt | „Wo steht 2510_07?“ |
| „DIN“, „VDE“, „Norm“, „Standard“, „wie haben wir das letztes Mal“, „Lesson“, „Kunde X will immer“ | Wissen | „Wie viele Steckdosen im Schlafzimmer?“ |
| „Mail“, „Termin“, „Kalender“, „To Do“, „Teams“, „Planner“, Name einer Person + „schreib“ | Büro | „Antworte Schmidt, dass Dienstag passt“ |
| „Datei“, „Ordner“, „such“, „leg ab“, „erstell ein Word/Excel“, „NAS“ | Dateien | „Such das Angebot Popescu“ |
| „prüf“, „Einwand“, „geht das ohne“, „Variante“, „rechne“, „Zweitmeinung“ | Prüfer (mit Wissens-Auszügen als Kontext) | „Kann ich die Leistungsbilanz ohne EVU-Schreiben abgeben?“ |
| Systemereignis, Mithör-Ausschnitt | Hintergrund | Erinnerung fällig |
| kein Treffer oder zwei Treffer | Stufe 2 | |

Stufe 2, Haiku 5.5 ohne Werkzeuge, eine Antwortzeile: `{"agent": "...", "auftrag": "..."}`. Kostet wenige hundert Tokens.
Bleibt es unklar, fragt Dialog den Nutzer mit einer gebündelten Rückfrage.

Mehrere Agenten in einer Anfrage („Stand von 2510_07 und schreib dem Architekten“): Dialog ruft nacheinander Projekt, dann
Büro mit dem Ergebnis von Projekt als Kontext. Parallel nur, wenn die Aufträge unabhängig sind.

### 5.3 Schreibrechte (Entscheidung 7 des Masterplans bleibt)

| Stufe | Was | Wer |
|---|---|---|
| allein | lesen, suchen, zusammenfassen, Gedächtnis, Tagebuch, Erinnerungen, Index bauen | alle lesenden Agenten, Hintergrund, Ablage |
| nach Ja | `PROJEKT.md`-Notizen, Workboard, Mail- und Teams-Versand, Wissen nach `_Entwurf\`, Dateien verschieben | Projekt, Büro, Dateien |
| nie | `10_Standards` ändern, Finanzen, Löschen außerhalb Papierkorb, Angebote, Preise | niemand ohne Martin |

---

## 6. Kontext-Haushalt je Anfrage (Zielwerte, Entwurf)

| Block | Heute | Ziel | Maßnahme |
|---|---|---|---|
| Werkzeug-Definitionen | 54 Werkzeuge in jedem Aufruf | 3 bis 26 je Agent | Werkzeugliste je Rolle |
| System-Prompt | ein Text für alles, Cache 5 min | je Rolle kurz, Cache 1 h | `cache_control` mit `ttl: 1h` |
| Gedächtnis | 7.000 Zeichen, ungecacht | `KERN.md` ≤ 1.500 Zeichen, eigener Cache-Breakpoint | Abschnitt 2 |
| Verlauf | ganzer Tag, ungecacht | letzte 6 Runden + Tagebuch-Absatz, Breakpoint auf letzter Nachricht | Abschnitt 3 Punkt 3 |
| Werkzeug-Ergebnisse | bleiben voll im Verlauf | nach 2 Runden auf eine Zeile gekürzt (Pfad oder Kurzfassung) | Kürzung in `agent.py` |
| Hintergrund-Meldungen | voller Agent mit Verlauf | Haiku, 3 Werkzeuge, kein Verlauf | Rolle Hintergrund |
| Mithör-Extraktion | neuer Agent mit 54 Werkzeugen alle 3 min | Rolle Hintergrund, Cache geteilt | gleicher System-Text wie Hintergrund |
| Schwere Fragen | Opus 5 `ask_model` | Opus 5.5 nur über Prüfer, mit Auszügen statt ganzen Dateien | Rolle Prüfer |

Messung: jeder API-Aufruf schreibt `usage` (Eingabe, Cache-Lesen, Cache-Schreiben, Ausgabe, Modell, Agent) nach
`~\.sprachassistent\verbrauch.jsonl`. Jarvis beantwortet „Was hast du heute verbraucht?“ daraus. Erst damit lassen sich die
Zielwerte prüfen; die Tabelle ist ein Entwurf, keine Messung.

---

## 7. Modelle

| Rolle | Modell | Grund |
|---|---|---|
| Dialog, Projekt, Büro, Abgleich | `claude-sonnet-5-5` | schnell für Sprache, Werkzeuge zuverlässig, 2 $/10 $ je Mio. Tokens |
| Wissen, Dateien, Hintergrund, Ablage, Router | `claude-haiku-5-5` | Lesen und Sortieren, 0,10 $/0,50 $ |
| Prüfer | `claude-opus-5-5` · high | Fachprüfung, Rechnen, Einwände, 4 $/20 $ |

Umstellungspunkte im Code: `MODELS` in `agent/agent.py`, Standard in `config.py` und `.env.example`, `server_tools()` (Haiku 5.5
nutzt die aktuellen Websuche-Varianten, die Haiku-4.5-Sonderfälle entfallen), `request_extras()` (Effort gilt auf allen drei).
Opus 5.5 und Sonnet 5.5 lehnen erzwungene Werkzeugwahl ab; der Code nutzt sie nicht.

---

## 8. Hintergrund-Routinen (aus Masterplan 10.2, mit Agent und Kosten)

| Wann | Agent | Was | Verbrauch |
|---|---|---|---|
| alle 20 s (Scheduler) | Hintergrund | fällige Erinnerung, Termin in 10 min: ein Satz | nur bei Ereignis, Haiku ohne Verlauf |
| alle 3 min bei Mithören | Hintergrund | Aufgaben, Zusagen, Termine aus Gesprächsausschnitt | Haiku, gecachter System-Text |
| täglich 07:30 | Projekt + Büro | Morgenbriefing: Termine, neue Workboard-Anfragen, fällige Aufgaben, eine Lesson zum Tagesprojekt | eine Sonnet-Runde |
| täglich 17:30 | Dialog | Tagesabschluss: Tagebuch, offene Notizen in `PROJEKT.md`, Erinnerungen für morgen | eine Sonnet-Runde |
| nachts 02:00 | Ablage | `_index.json` und `_index.md` neu bauen, wenn Dateien geändert; Streudateien melden | Haiku, nur bei Änderungen |
| Freitag 15:00 | Abgleich | Abschnitt 3 Punkt 5 | eine Sonnet-Runde je Projekt |
| 1. und 15. | Projekt (nur Martin) | Abrechnungsradar (Masterplan 5.4) | eine Sonnet-Runde |
| vierteljährlich | Wissen | Standards mit `geprueft_am` älter als 12 Monate; Lessons ohne Standard | Haiku-Liste, Martin entscheidet |

Alle Routinen schreiben ihr Ergebnis in eine Datei oder in To Do, nie nur in den Verlauf.

---

## 9. Umsetzung in Stufen (jede für sich nützlich)

| Stufe | Inhalt | Dateien im Repo | Voraussetzung | Aufwand |
|---|---|---|---|---|
| **1 Cache** | `ttl: 1h` auf System-Text, Breakpoint auf letzter Nachricht, eigener Breakpoint auf Gedächtnis-Block | `agent/agent.py` | keine | 1 h |
| **2 Verlauf** | Werkzeug-Ergebnisse nach 2 Runden kürzen; Zusammenfassung ab 40.000 Tokens oder 30 min Pause; Tagebuch; `usage`-Protokoll | `agent/agent.py`, `tools/memory.py`, `webapp.py` | 1 | 1 Tag |
| **3 Rollen** | `ToolRegistry` je Rolle, `Agent` je Rolle, `ask_agent`, Hintergrund und Mithören auf Haiku ohne Verlauf | neu `agent/roles.py`, `assistant.py`, `ambient.py`, `webapp.py` | 2 | 2 Tage |
| **4 Router** | Regeltabelle 5.2 im Code, Haiku-Fallback, Rückfrage | neu `agent/router.py`, `assistant.py` | 3 | 1 Tag |
| **5 Modelle** | Opus 5.5, Sonnet 5.5, Haiku 5.5; Tests der Werkzeugschleife | `agent/agent.py`, `config.py`, `.env.example`, `tests/` | keine | 0,5 Tag |
| **6 Gedächtnis-MD** | Abschnitt 2 inkl. Migration aus `memory.json` | `tools/memory.py`, `tests/` | 2 | 1 Tag |
| **7 Wissen auf X:** | `wissen_index`, `wissen_lesen`, `wissen_ablegen` (nach `_Entwurf\`), `projekt_steckbrief`, `projekt_notiz` | neu `tools/wissen.py`, `tools/projekt.py` | `03_Wissen\_index.json` und erste `PROJEKT.md` vorhanden | 3 Tage |
| **8 Routinen** | Morgenbriefing, Tagesabschluss, Ablage nachts, Abgleich Freitag | `webapp.py` (Scheduler), neu `routinen.py` | 3, 7 | 2 Tage |
| **9 Prüfer** | Einwand-Check mit Planungsregeln als fester System-Text, Varianten-Antwort | `agent/roles.py` | 3, 7 | 0,5 Tag |

Reihenfolge-Prinzip: erst Verbrauch senken (1 bis 5), dann Wissen sichern (6 bis 7), dann Hintergrund (8 bis 9).
Stufen 1, 2 und 5 ändern das Verhalten für den Nutzer nicht und können sofort umgesetzt werden.

---

## 10. Wie eine Anfrage später läuft (Beispiel)

„Hey Jarvis, wo steht Am Bungert und was fehlt noch für LP3?“

1. Router Stufe 1: „steht“, „fehlt“, Projektname → Projekt. Kein Modellaufruf.
2. Dialog ruft `ask_agent("projekt", "Stand und fehlende Pflichtunterlagen LP3 für 2510_07")`.
3. Projekt (Sonnet, 8 Werkzeuge, kein Verlauf): liest `PROJEKT.md` (Stand 2026-11-10), Registry, Workboard. Antwort an Dialog: „Stand: LP3 beauftragt, Versand geplant 15.11. Fehlt: Brandschutzkonzept (angefragt 10.10.), EVU-Schreiben. Offen im Workboard: 2 Anfragen seit 4.11. Quelle: PROJEKT.md 2510_07, Stand 2026-11-10.“
4. Dialog spricht: „Am Bungert ist in LP3, Versand am fünfzehnten geplant. Es fehlen Brandschutzkonzept und EVU-Schreiben, das Brandschutzkonzept ist seit dem zehnten Oktober angefragt. Stand vom zehnten November.“ Im Fenster steht die Quelle.
5. Tagebuch: „11:42 Projektstand 2510_07 abgefragt; Brandschutz seit 10.10. offen.“
6. Verbrauch: Dialog eine Runde mit 12 Werkzeugen und gecachtem Verlauf, Projekt eine Runde mit 8 Werkzeugen. Kein Opus, kein NAS-Scan, keine 54 Werkzeuge.

Nutzer: „Merk dir, der Brandschutz kommt am Freitag.“
Router: „merk dir“ + Projektkontext → Projekt. `projekt_notiz("2510_07", "2026-11-12 · Martin · Brandschutzkonzept zugesagt für Freitag 14.11.")`
hängt an `PROJEKT.md` an, `reminder_set` für Freitag 09:00. Dialog: „Notiert im Projekt, ich erinnere Freitag früh.“

---

## 11. Einwände, Annahmen, nicht geprüft

**Einwände**
- Kollege Nexus: Agenten schreiben in `PROJEKT.md`, Nexus liest sie nicht → beide lesen dieselbe Datei und `_index.json` (Masterplan 11); Absprache nötig, bevor Stufe 7 schreibt.
- Nutzer: mehr Agenten heißt mehr Latenz bei Sprache → Dialog antwortet sofort mit „Ich schaue nach“, Rollen laufen parallel, wo unabhängig; Haiku-Rollen antworten in Sekunden.
- Bauleiter/Team: Wissen auf X: ist nur so gut wie die Pflege → Freitags-Abgleich und Quartals-Check sind Pflichtroutinen, Ergebnisse landen in Martins To Do.
- Architekt (Software): Verlauf kürzen kann Zusammenhang kosten → Tagebuch-Absatz ersetzt die Runden, Dateien bleiben vollständig; im Zweifel liest Dialog das Tagebuch nach.
- Betrieb: Scheduled Routinen laufen nur, wenn die App läuft → für Nacht- und Freitagsroutinen muss der PC an sein oder die Routine läuft beim nächsten Start nach (Datum in `routinen_status.json`).

**Annahmen**
- Nutzung über den Tag mit Pausen über 5 Minuten (deshalb Cache 1 h).
- `03_Wissen` und `09_Archiv` existieren auf X: (laut Masterplan 1b erledigt), `_index.json` noch leer.
- Modellpreise laut Anthropic-Preisliste Stand 03.11.2026.
- Mitarbeiter-Jarvis bekommt dieselben Rollen ohne Büro-Finanzen und ohne Schreibrecht in `10_Standards`.

**Nicht geprüft**
- Tatsächlicher Token-Verbrauch heute (kein Protokoll vorhanden; Stufe 2 liefert es).
- Ob die Werkzeugschleife mit Sonnet 5.5 und Haiku 5.5 in allen 54 Werkzeugen identisch läuft (Tests in Stufe 5).
- Inhalt und Stand der Ordner auf X: (kein Zugriff aus dieser Sitzung).
