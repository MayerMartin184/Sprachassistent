"""Italienisch-Trainer: Karteikasten mit Wiederholung nach Leitner, Rumänisch als Brücke.

Der Agent führt die Lektion im Gespräch (fragt ab, korrigiert, erklärt). Dieses Modul liefert ihm die
Karten, merkt sich jedes Ergebnis dauerhaft und plant die Wiederholung: richtig -> nächstes Fach, längeres
Intervall; falsch -> zurück in Fach 0, morgen wieder. Fortschritt liegt in ~/.sprachassistent/italienisch.json.
"""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path
from typing import Callable

from .base import Tool, schema
from .italian_deck import ARTEN, DECK, THEMEN
from .store import JsonStore

INTERVALLE = [0, 1, 3, 7, 14, 30]  # Tage bis zur Wiederholung je Fach 0..5
GELERNT_AB_FACH = 4
ART_LABEL = {"verwandt": "verwandt mit Rumänisch", "anders": "kein rumänisches Gegenstück", "falscher_freund": "FALSCHER FREUND"}
ITALIENISCHE_STIMME = "it-IT-IsabellaMultilingualNeural"


class ItalianTrainer:
    def __init__(self, data_dir: Path, today: Callable[[], date] | None = None) -> None:
        self.store = JsonStore(data_dir / "italienisch.json", {"karten": {}, "eigene": [], "verlauf": []})
        self._today = today or date.today

    # --- Karten ---------------------------------------------------------------
    def deck(self) -> list[dict]:
        return DECK + list(self.store.load()["eigene"])

    def card(self, card_id: str) -> dict | None:
        return next((k for k in self.deck() if k["id"] == card_id), None)

    def themen(self) -> list[str]:
        eigene = [k["thema"] for k in self.store.load()["eigene"]]
        return list(dict.fromkeys(THEMEN + eigene))

    @staticmethod
    def _slug(text: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", text.lower().replace("à", "a").replace("è", "e").replace("é", "e").replace("ì", "i").replace("ò", "o").replace("ù", "u")).strip("-")
        return slug or "wort"

    def add(self, it: str, de: str, ro: str = "", tipp: str = "", thema: str = "Eigene", art: str = "anders") -> dict:
        it, de = it.strip(), de.strip()
        if not it or not de:
            raise ValueError("Italienisch und Deutsch müssen angegeben sein.")
        if art not in ARTEN:
            art = "anders"
        data = self.store.load()
        for karte in data["eigene"] + DECK:
            if karte["it"].lower() == it.lower():
                return karte  # schon im Kasten
        card_id = "eigen-" + self._slug(it)
        ids = {k["id"] for k in DECK} | {k["id"] for k in data["eigene"]}
        n = 2
        while card_id in ids:
            card_id = f"eigen-{self._slug(it)}-{n}"
            n += 1
        karte = {"id": card_id, "it": it, "de": de, "ro": ro.strip(), "art": art, "tipp": tipp.strip(), "thema": thema.strip() or "Eigene", "stufe": 1}
        data["eigene"].append(karte)
        self.store.save(data)
        return karte

    def search(self, query: str, limit: int = 10) -> list[dict]:
        q = query.strip().lower()
        if not q:
            return []
        hits = [k for k in self.deck() if q in k["it"].lower() or q in k["de"].lower() or q in k["ro"].lower()]
        return hits[:limit]

    # --- Planung --------------------------------------------------------------
    def progress(self, card_id: str) -> dict | None:
        return self.store.load()["karten"].get(card_id)

    def due(self, thema: str | None = None) -> list[dict]:
        today = self._today().isoformat()
        karten = self.store.load()["karten"]
        faellig = [(p["faellig"], k) for k in self.deck() if (p := karten.get(k["id"])) and p["faellig"] <= today]
        faellig.sort(key=lambda x: x[0])
        return [k for _, k in faellig if self._thema_passt(k, thema)]

    def new(self, thema: str | None = None) -> list[dict]:
        karten = self.store.load()["karten"]
        neue = [k for k in self.deck() if k["id"] not in karten and self._thema_passt(k, thema)]
        return sorted(neue, key=lambda k: k["stufe"])  # stabil: Reihenfolge im Deck bleibt je Stufe

    @staticmethod
    def _thema_passt(karte: dict, thema: str | None) -> bool:
        return not thema or karte["thema"].lower() == thema.strip().lower()

    def round(self, anzahl: int = 8, thema: str | None = None, max_neue: int | None = None) -> tuple[list[dict], int, int]:
        """Karten für eine Übungsrunde: erst fällige (älteste zuerst), dann neue. Rückgabe (Karten, fällig, neu)."""
        anzahl = max(1, min(int(anzahl), 30))
        faellig = self.due(thema)[:anzahl]
        rest = anzahl - len(faellig)
        if max_neue is not None:
            rest = min(rest, max(0, int(max_neue)))
        neue = self.new(thema)[:rest]
        return faellig + neue, len(faellig), len(neue)

    def grade(self, results: list[tuple[str, bool]]) -> dict:
        """Trägt Ergebnisse ein. Rückgabe: Zusammenfassung mit nächsten Fälligkeiten."""
        data = self.store.load()
        today = self._today()
        richtig = falsch = 0
        unbekannt: list[str] = []
        details: list[str] = []
        ids = {k["id"] for k in self.deck()}
        for card_id, ok in results:
            if card_id not in ids:
                unbekannt.append(card_id)
                continue
            p = data["karten"].get(card_id) or {"fach": 0, "faellig": today.isoformat(), "richtig": 0, "falsch": 0}
            if ok:
                p["fach"] = min(p["fach"] + 1, len(INTERVALLE) - 1)
                p["richtig"] += 1
                richtig += 1
            else:
                p["fach"] = 0
                p["falsch"] += 1
                falsch += 1
            tage = INTERVALLE[p["fach"]] if ok else 1
            p["faellig"] = (today + timedelta(days=tage)).isoformat()
            p["zuletzt"] = today.isoformat()
            data["karten"][card_id] = p
            details.append(f"{card_id}: {'richtig' if ok else 'falsch'} -> Fach {p['fach']}, wieder in {tage} Tag(en)")
        if richtig or falsch:
            tag = next((v for v in data["verlauf"] if v["datum"] == today.isoformat()), None)
            if tag is None:
                tag = {"datum": today.isoformat(), "richtig": 0, "falsch": 0}
                data["verlauf"].append(tag)
            tag["richtig"] += richtig
            tag["falsch"] += falsch
            data["verlauf"] = data["verlauf"][-365:]
        self.store.save(data)
        return {"richtig": richtig, "falsch": falsch, "unbekannt": unbekannt, "details": details}

    def stats(self) -> dict:
        data = self.store.load()
        karten = data["karten"]
        deck = self.deck()
        today = self._today()
        gelernt = sum(1 for p in karten.values() if p["fach"] >= GELERNT_AB_FACH)
        faellig = len(self.due())
        woche = [v for v in data["verlauf"] if v["datum"] >= (today - timedelta(days=6)).isoformat()]
        schwach: dict[str, int] = {}
        for k in deck:
            p = karten.get(k["id"])
            if p and p["falsch"] >= 2 and p["fach"] < GELERNT_AB_FACH:
                schwach[k["thema"]] = schwach.get(k["thema"], 0) + 1
        return {
            "karten_gesamt": len(deck),
            "eigene": len(data["eigene"]),
            "neu": len(deck) - len(karten),
            "in_arbeit": len(karten) - gelernt,
            "gelernt": gelernt,
            "faellig_heute": faellig,
            "serie_tage": self._streak(data["verlauf"], today),
            "woche_richtig": sum(v["richtig"] for v in woche),
            "woche_falsch": sum(v["falsch"] for v in woche),
            "uebungstage_gesamt": len(data["verlauf"]),
            "schwache_themen": sorted(schwach, key=schwach.get, reverse=True)[:3],
        }

    @staticmethod
    def _streak(verlauf: list[dict], today: date) -> int:
        tage = {v["datum"] for v in verlauf}
        tag = today if today.isoformat() in tage else today - timedelta(days=1)
        n = 0
        while tag.isoformat() in tage:
            n += 1
            tag -= timedelta(days=1)
        return n

    # --- Darstellung für das Modell -----------------------------------------
    def format_card(self, karte: dict) -> str:
        p = self.progress(karte["id"])
        status = f"Fach {p['fach']}, {p['richtig']}x richtig, {p['falsch']}x falsch" if p else "neu"
        zeile = f"[{karte['id']}] {karte['it']}  =  {karte['de']}  |  rum.: {karte['ro']}  ({ART_LABEL[karte['art']]}; {status})"
        if karte["tipp"]:
            zeile += f"\n    Tipp: {karte['tipp']}"
        return zeile


class ItalianMode:
    """Lektionsmodus für Stimme und Erkennung: Italienisch zuerst erkennen, italienischfähige Stimme nutzen.

    Rückbau beim Beenden. Ohne Sprachbetrieb (nur Text) passiert nichts.
    """

    def __init__(self, get_speech: Callable[[], object | None], get_tts: Callable[[], object | None]) -> None:
        self._get_speech = get_speech
        self._get_tts = get_tts
        self._saved: tuple[list[str], str | None] | None = None

    @property
    def active(self) -> bool:
        return self._saved is not None

    def on(self) -> str:
        speech = self._get_speech()
        if speech is None:
            return "Textmodus: Es gibt keine Sprachein- und -ausgabe, geübt wird schriftlich."
        if self.active:
            return "Italienisch-Modus ist bereits an."
        languages = list(getattr(speech, "languages", []))
        self._saved = (languages, getattr(speech, "voice_override", None))
        speech.languages = ["it-IT"] + [lang for lang in languages if lang != "it-IT"]
        hinweis = "Erkennung hört zuerst auf Italienisch, Deutsch bleibt möglich."
        if self._get_tts() is speech and not self._voice_is_multilingual(speech):
            speech.voice_override = ITALIENISCHE_STIMME
            hinweis += " Stimme vorübergehend auf eine italienischfähige Stimme gewechselt."
        return "Italienisch-Modus an. " + hinweis

    def off(self) -> str:
        speech = self._get_speech()
        if self._saved is None:
            return "Italienisch-Modus war nicht an."
        languages, override = self._saved
        self._saved = None
        if speech is not None:
            speech.languages = languages or ["de-DE"]
            speech.voice_override = override
        return "Italienisch-Modus aus. Erkennung und Stimme wie zuvor."

    @staticmethod
    def _voice_is_multilingual(speech: object) -> bool:
        voice = getattr(speech, "voice_override", None)
        if not voice:
            try:
                from ..speech.azure import preset

                voice = preset(getattr(speech, "voice_preset", ""))[0]
            except Exception:  # noqa: BLE001
                return True  # unbekanntes Sprachobjekt: nichts verstellen
        return "Multilingual" in voice


def build_tools(trainer: ItalianTrainer, mode: ItalianMode | None = None) -> list[Tool]:
    def runde(anzahl: int = 8, thema: str | None = None, max_neue: int | None = None) -> str:
        if thema and thema.strip().lower() not in (t.lower() for t in trainer.themen()):
            return f"Unbekanntes Thema „{thema}“. Themen: {', '.join(trainer.themen())}."
        karten, faellig, neu = trainer.round(anzahl, thema, max_neue)
        if not karten:
            return "Keine Karten: alles für heute wiederholt und keine neuen Karten mehr" + (f" im Thema {thema}." if thema else ".")
        kopf = f"Runde mit {len(karten)} Karten ({faellig} fällig zur Wiederholung, {neu} neu)" + (f", Thema {thema}" if thema else "") + ":"
        return kopf + "\n" + "\n".join(trainer.format_card(k) for k in karten)

    def bewerten(ergebnisse: list[dict]) -> str:
        paare = [(str(e.get("id", "")), bool(e.get("richtig", False))) for e in ergebnisse]
        r = trainer.grade(paare)
        text = f"Eingetragen: {r['richtig']} richtig, {r['falsch']} falsch."
        if r["details"]:
            text += "\n" + "\n".join(r["details"])
        if r["unbekannt"]:
            text += "\nUnbekannte Karten-IDs: " + ", ".join(r["unbekannt"])
        s = trainer.stats()
        text += f"\nHeute noch fällig: {s['faellig_heute']}. Übungsserie: {s['serie_tage']} Tag(e)."
        return text

    def merken(it: str, de: str, ro: str = "", tipp: str = "", thema: str = "Eigene", art: str = "anders") -> str:
        karte = trainer.add(it, de, ro, tipp, thema, art)
        return "Im Karteikasten:\n" + trainer.format_card(karte)

    def suchen(begriff: str) -> str:
        hits = trainer.search(begriff)
        if not hits:
            return f"Nichts zu „{begriff}“ im Karteikasten. Mit italienisch_merken kannst du es aufnehmen."
        return "\n".join(trainer.format_card(k) for k in hits)

    def fortschritt() -> str:
        s = trainer.stats()
        return (
            f"Karten: {s['karten_gesamt']} (davon {s['eigene']} eigene). Gelernt: {s['gelernt']}, in Arbeit: {s['in_arbeit']}, "
            f"noch nie geübt: {s['neu']}. Heute fällig: {s['faellig_heute']}. Übungsserie: {s['serie_tage']} Tag(e) in Folge, "
            f"insgesamt {s['uebungstage_gesamt']} Übungstage. Letzte 7 Tage: {s['woche_richtig']} richtig, {s['woche_falsch']} falsch."
            + (f" Schwache Themen: {', '.join(s['schwache_themen'])}." if s["schwache_themen"] else "")
            + f"\nThemen: {', '.join(trainer.themen())}."
        )

    def modus(an: bool) -> str:
        if mode is None:
            return "Textmodus: Es gibt keine Sprachein- und -ausgabe, geübt wird schriftlich."
        return mode.on() if an else mode.off()

    ergebnis_schema = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"id": {"type": "string"}, "richtig": {"type": "boolean"}},
            "required": ["id", "richtig"],
        },
        "description": "Pro Karte die ID aus der Runde und ob der Nutzer sie konnte",
    }
    return [
        Tool(
            name="italienisch_runde",
            description=(
                "Holt die Karten für eine Italienisch-Übungsrunde: zuerst fällige Wiederholungen, dann neue Karten. Jede Karte hat "
                "Italienisch, Deutsch, die rumänische Entsprechung (verwandt, anders oder falscher Freund) und einen Tipp. "
                "Die Karten nacheinander im Gespräch abfragen, nicht alle auf einmal vorlesen."
            ),
            input_schema=schema(
                {
                    "anzahl": {"type": "integer", "description": "Karten in dieser Runde, Standard 8 (5 bis 10 passen zu einer kurzen Lektion)"},
                    "thema": {"type": "string", "description": "Nur dieses Thema, z. B. Begrüßung, Grundlagen, Zahlen, Zeit, Essen, Unterwegs, Zuhause, Menschen, Verben, Adjektive, Büro, Grammatik, Aussprache"},
                    "max_neue": {"type": "integer", "description": "Höchstens so viele neue Karten (0 = nur Wiederholung)"},
                },
            ),
            handler=runde,
        ),
        Tool(
            name="italienisch_bewerten",
            description=(
                "Trägt die Ergebnisse der Übungsrunde ein (richtig / falsch je Karten-ID) und plant die Wiederholung: richtig -> längerer "
                "Abstand, falsch -> morgen wieder. Nach jeder Karte oder spätestens am Ende der Runde aufrufen."
            ),
            input_schema=schema({"ergebnisse": ergebnis_schema}, ["ergebnisse"]),
            handler=bewerten,
        ),
        Tool(
            name="italienisch_merken",
            description=(
                "Legt ein neues Wort oder einen Satz in den Karteikasten (z. B. wenn der Nutzer fragt, was etwas auf Italienisch heißt). "
                "Immer die rumänische Entsprechung und einen kurzen Tipp mitgeben, art = verwandt | anders | falscher_freund."
            ),
            input_schema=schema(
                {
                    "it": {"type": "string", "description": "Italienisch, bei Nomen mit Artikel"},
                    "de": {"type": "string", "description": "Deutsch"},
                    "ro": {"type": "string", "description": "Rumänische Entsprechung"},
                    "tipp": {"type": "string", "description": "Merkhilfe, Verwandtschaft oder Warnung vor einem falschen Freund"},
                    "thema": {"type": "string", "description": "Thema, Standard Eigene"},
                    "art": {"type": "string", "enum": list(ARTEN)},
                },
                ["it", "de"],
            ),
            handler=merken,
        ),
        Tool(
            name="italienisch_suchen",
            description="Sucht im Karteikasten nach einem italienischen, deutschen oder rumänischen Wort und zeigt Karte, Verwandtschaft und Lernstand.",
            input_schema=schema({"begriff": {"type": "string"}}, ["begriff"]),
            handler=suchen,
        ),
        Tool(
            name="italienisch_fortschritt",
            description="Lernstand Italienisch: gelernte, laufende und neue Karten, heute fällige Wiederholungen, Übungsserie, schwache Themen, Themenliste.",
            input_schema=schema({}),
            handler=fortschritt,
        ),
        Tool(
            name="italienisch_modus",
            description=(
                "Schaltet den Italienisch-Modus an oder aus: an = Spracherkennung hört zuerst auf Italienisch und die Stimme kann Italienisch "
                "korrekt aussprechen; aus = alles wie zuvor. Zu Beginn jeder Lektion anschalten, am Ende ausschalten."
            ),
            input_schema=schema({"an": {"type": "boolean"}}, ["an"]),
            handler=modus,
        ),
    ]
