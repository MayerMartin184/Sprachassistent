"""Verteilung: Welche Rolle bearbeitet eine Nutzeräußerung?

Stufe 1: feste Regeln (Stichworte, Projektcode) ohne Modellaufruf. Genau eine passende Rolle gewinnt.
Stufe 2: Passen mehrere, entscheidet ein günstiges Modell zwischen den Kandidaten.
Passt keine, bleibt die Äußerung beim Dialog-Agenten, der selbst weitergeben kann.
"""

from __future__ import annotations

import re
from typing import Callable

RULES: list[tuple[str, list[str]]] = [
    ("projekt", [
        r"\b\d{4}_\d{2}\b",  # Projektcode JJMM_NN
        r"\bprojekt(e|s|stand|es)?\b", r"\bproiect", r"\bpflichtunterlagen\b", r"\bleistungsphase", r"\blph?\s?[1-9]\b",
        r"\bbaustelle", r"\bplanversand", r"\bfürs? projekt\b", r"\bprojekt-?notiz",
    ]),
    ("wissen", [
        r"\bdin\b", r"\bvde\b", r"\bnorm(en|text)?\b", r"\bstandards?\b", r"\bhausstandard", r"\blessons?\b",
        r"\bwie haben wir .*(gemacht|gelöst|geloest)\b", r"\bbrandschutz", r"\bglossar\b", r"\bkundenregel",
        r"\bwissensbasis\b", r"\bvorschrift",
    ]),
    ("buero", [
        r"\be-?mails?\b", r"\bpostfach\b", r"\btermin", r"\bkalender\b", r"\bto\s?do\b", r"\baufgabe", r"\bteams\b",
        r"\bplanner\b", r"\bbesprechung", r"\bmeeting", r"\bantworte\b", r"\bschreib(e)? (an|dem|der|ihm|ihr)\b",
        r"\bwas steht (heute|morgen|diese woche) an\b", r"\bchat\b", r"\bungelesen",
    ]),
    ("dateien", [
        r"\bdatei(en)?\b", r"\bordner\b", r"\bnas\b", r"\bpdf\b", r"\bword(-?dokument)?\b", r"\bexcel\b",
        r"\bpowerpoint\b", r"\bpräsentation\b", r"\bdownloads?\b", r"\bdesktop\b", r"\bleg(e)? .* ab\b",
        r"\bräum(e)? .* auf\b", r"\bnetzlaufwerk",
    ]),
    ("recherche", [
        r"\brecherch", r"\bim (netz|internet|web)\b", r"\bgoogle\b", r"\banbieter\b", r"\bpreis(e|vergleich)?\b",
        r"\bnachrichten\b", r"\bnews\b",
    ]),
    ("pruefer", [
        r"\bprüf(e|st|en)?\b", r"\beinw(a|ä)nd", r"\bgeht (das|es) (auch )?ohne\b", r"\bvariante", r"\b(be)?rechne\b",
        r"\bzweitmeinung\b", r"\bkann ich .*(weglassen|streichen)\b", r"\bbewert", r"\bplausib",
    ]),
]

_COMPILED = [(role, [re.compile(p, re.IGNORECASE) for p in patterns]) for role, patterns in RULES]
MIN_WORDS = 3  # „ja“, „mach das“, „danke“ bleiben beim Dialog


def rule_matches(text: str) -> list[str]:
    """Rollen, deren Regeln passen, in Regel-Reihenfolge, ohne Doppelte."""
    found: list[str] = []
    for role, patterns in _COMPILED:
        if any(p.search(text) for p in patterns):
            found.append(role)
    return found


class Router:
    def __init__(self, classify: Callable[[str, list[str]], str] | None = None) -> None:
        self.classify = classify

    def route(self, text: str) -> str | None:
        """Rolle für die Äußerung oder None (Dialog)."""
        if len(text.split()) < MIN_WORDS:
            return None
        matches = rule_matches(text)
        if not matches:
            return None
        if len(matches) == 1:
            return matches[0]
        if self.classify is None:
            return None
        chosen = self.classify(text, matches)
        return chosen if chosen in matches else None
