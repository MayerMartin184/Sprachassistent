"""Italienisch-Trainer: Karteikasten, Leitner-Planung, eigene Karten, Italienisch-Modus."""

from datetime import date, timedelta

import pytest

from sprachassistent.tools import italian
from sprachassistent.tools.base import ToolRegistry
from sprachassistent.tools.italian import INTERVALLE, ItalianMode, ItalianTrainer
from sprachassistent.tools.italian_deck import ARTEN, DECK, FELDER, THEMEN


def test_deck_ist_vollstaendig_und_eindeutig():
    ids = [k["id"] for k in DECK]
    assert len(ids) == len(set(ids)), "doppelte Karten-IDs"
    assert len(DECK) >= 150
    for k in DECK:
        assert tuple(k) == FELDER
        for feld in ("id", "it", "de", "ro", "thema"):
            assert k[feld].strip(), f"{k['id']}: Feld {feld} leer"
        assert k["art"] in ARTEN, k["id"]
        assert k["stufe"] in (1, 2, 3), k["id"]
        assert k["id"] == k["id"].lower() and " " not in k["id"], k["id"]
    for thema in ("Begrüßung", "Zahlen", "Zeit", "Essen", "Verben", "Büro", "Grammatik", "Aussprache"):
        assert thema in THEMEN
    assert any(k["art"] == "falscher_freund" for k in DECK)


class Uhr:
    def __init__(self, tag: date) -> None:
        self.tag = tag

    def __call__(self) -> date:
        return self.tag


def test_runde_bewerten_und_wiederholung(tmp_path):
    uhr = Uhr(date(2026, 11, 8))
    t = ItalianTrainer(tmp_path, today=uhr)
    karten, faellig, neu = t.round(5)
    assert (len(karten), faellig, neu) == (5, 0, 5)
    assert all(k["stufe"] == 1 for k in karten)  # Einstieg zuerst

    r = t.grade([(karten[0]["id"], True), (karten[1]["id"], False), ("gibtsnicht", True)])
    assert (r["richtig"], r["falsch"], r["unbekannt"]) == (1, 1, ["gibtsnicht"])
    assert t.progress(karten[0]["id"])["fach"] == 1
    assert t.progress(karten[1]["id"])["fach"] == 0
    assert t.due() == []  # heute nichts mehr fällig
    assert t.stats()["in_arbeit"] == 2 and t.stats()["neu"] == len(DECK) - 2

    uhr.tag += timedelta(days=1)
    faellige = t.due()
    assert [k["id"] for k in faellige] == [karten[0]["id"], karten[1]["id"]]
    runde, f, n = t.round(4)
    assert f == 2 and n == 2 and runde[0]["id"] == karten[0]["id"]  # fällige zuerst
    runde_nur_wdh, f, n = t.round(4, max_neue=0)
    assert (len(runde_nur_wdh), f, n) == (2, 2, 0)

    # richtig durch alle Fächer: Abstände wachsen bis 30 Tage, Fach bleibt bei 5
    cid = karten[0]["id"]
    for erwartet in INTERVALLE[2:] + [INTERVALLE[-1]]:
        t.grade([(cid, True)])
        p = t.progress(cid)
        assert date.fromisoformat(p["faellig"]) == uhr.tag + timedelta(days=erwartet)
        uhr.tag = date.fromisoformat(p["faellig"])
    assert t.progress(cid)["fach"] == 5
    assert t.stats()["gelernt"] == 1
    t.grade([(cid, False)])
    assert t.progress(cid)["fach"] == 0 and t.progress(cid)["faellig"] == (uhr.tag + timedelta(days=1)).isoformat()


def test_thema_filter_und_serie(tmp_path):
    uhr = Uhr(date(2026, 11, 8))
    t = ItalianTrainer(tmp_path, today=uhr)
    karten, _, _ = t.round(3, thema="zahlen")
    assert len(karten) == 3 and all(k["thema"] == "Zahlen" for k in karten)
    t.grade([(k["id"], True) for k in karten])
    assert t.stats()["serie_tage"] == 1
    uhr.tag += timedelta(days=1)
    assert t.stats()["serie_tage"] == 1  # gestern geübt zählt noch
    t.grade([(karten[0]["id"], True)])
    assert t.stats()["serie_tage"] == 2
    uhr.tag += timedelta(days=3)
    assert t.stats()["serie_tage"] == 0
    assert t.stats()["woche_richtig"] == 4


def test_eigene_karten_und_suche(tmp_path):
    t = ItalianTrainer(tmp_path)
    k = t.add("la bolla di consegna", "der Lieferschein", "avizul de însoțire", "consegna = Lieferung", "Büro", "anders")
    assert k["id"] == "eigen-la-bolla-di-consegna" and k in t.deck()
    assert t.add("La Bolla di Consegna", "x") == k  # kein Doppel
    assert t.add("la birra", "Bier")["id"] == "birra"  # schon im Grunddeck
    k2 = t.add("città", "Stadt", art="unsinn")
    assert k2["id"] == "eigen-citta" and k2["art"] == "anders"
    assert [x["id"] for x in t.search("bere")] and t.search("bere")[0]["id"] == "birra"
    assert any(x["id"] == k["id"] for x in t.search("lieferschein"))
    assert t.search("") == []
    assert "Büro" in t.themen() and t.stats()["eigene"] == 2
    assert k in t.new()
    with pytest.raises(ValueError):
        t.add("", "leer")


class FakeSpeech:
    def __init__(self, preset="katja"):
        self.languages = ["de-DE", "ro-RO"]
        self.voice_preset = preset
        self.voice_override = None


def test_modus_schaltet_und_baut_zurueck():
    sp = FakeSpeech("katja")
    mode = ItalianMode(lambda: sp, lambda: sp)
    assert "an" in mode.on() and mode.active
    assert sp.languages == ["it-IT", "de-DE", "ro-RO"]
    assert sp.voice_override == italian.ITALIENISCHE_STIMME
    assert "bereits" in mode.on()
    assert "aus" in mode.off() and not mode.active
    assert sp.languages == ["de-DE", "ro-RO"] and sp.voice_override is None
    assert "nicht an" in mode.off()

    # mehrsprachige Stimme oder ElevenLabs: Stimme bleibt
    sp2 = FakeSpeech("seraphina")
    ItalianMode(lambda: sp2, lambda: sp2).on()
    assert sp2.voice_override is None and sp2.languages[0] == "it-IT"
    sp3 = FakeSpeech("katja")
    ItalianMode(lambda: sp3, lambda: object()).on()
    assert sp3.voice_override is None

    assert "Textmodus" in ItalianMode(lambda: None, lambda: None).on()


def test_werkzeuge(tmp_path):
    uhr = Uhr(date(2026, 11, 8))
    t = ItalianTrainer(tmp_path, today=uhr)
    sp = FakeSpeech()
    tools = italian.build_tools(t, ItalianMode(lambda: sp, lambda: sp))
    reg = ToolRegistry()
    reg.register_all(tools)
    assert reg.names == ["italienisch_runde", "italienisch_bewerten", "italienisch_merken", "italienisch_suchen", "italienisch_fortschritt", "italienisch_modus"]

    text, err = reg.execute("italienisch_runde", {"anzahl": 3, "thema": "Begrüßung"})
    assert not err and "3 Karten" in text and "[buongiorno]" in text and "verwandt" in text
    assert "Unbekanntes Thema" in reg.execute("italienisch_runde", {"thema": "Quatsch"})[0]
    text, err = reg.execute("italienisch_bewerten", {"ergebnisse": [{"id": "buongiorno", "richtig": True}, {"id": "ciao", "richtig": False}]})
    assert not err and "1 richtig, 1 falsch" in text and "Fach 1" in text
    assert "Lieferschein" in reg.execute("italienisch_merken", {"it": "la bolla di consegna", "de": "der Lieferschein", "ro": "avizul"})[0]
    assert "FALSCHER FREUND" in reg.execute("italienisch_suchen", {"begriff": "birra"})[0]
    assert "Nichts zu" in reg.execute("italienisch_suchen", {"begriff": "xyzxyz"})[0]
    text, err = reg.execute("italienisch_fortschritt", {})
    assert not err and "in Arbeit: 2" in text and "Themen:" in text
    assert "an" in reg.execute("italienisch_modus", {"an": True})[0] and sp.languages[0] == "it-IT"
    assert "aus" in reg.execute("italienisch_modus", {"an": False})[0] and sp.languages[0] == "de-DE"
    assert "Textmodus" in italian.build_tools(t)[-1].handler(an=True)
