"""Verbrauch: Auswertung von verbrauch.jsonl (ein Eintrag je API-Aufruf, geschrieben vom Agenten)."""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from .base import Tool, schema

# US-Dollar je Million Tokens: Eingabe, Cache-Lesen, Cache-Schreiben (1 h), Ausgabe. Stand 03.11.2026.
PRICES: dict[str, tuple[float, float, float, float]] = {
    "claude-opus-5-5": (4.00, 0.20, 8.00, 20.00),
    "claude-sonnet-5-5": (2.00, 0.10, 4.00, 10.00),
    "claude-haiku-5-5": (0.10, 0.01, 0.20, 0.50),
    "claude-opus-5": (5.00, 0.50, 10.00, 25.00),
    "claude-sonnet-5": (2.00, 0.20, 4.00, 10.00),
    "claude-haiku-4-5": (1.00, 0.10, 2.00, 5.00),
}


def _cost(model: str, eingabe: int, cache_lesen: int, cache_schreiben: int, ausgabe: int) -> float | None:
    prices = PRICES.get(model)
    if prices is None:
        return None
    p_in, p_read, p_write, p_out = prices
    return (eingabe * p_in + cache_lesen * p_read + cache_schreiben * p_write + ausgabe * p_out) / 1_000_000


def report(path: Path, day: str | None = None) -> str:
    """Zusammenfassung eines Tages (Standard heute) je Rolle und Modell."""
    day = day or datetime.now().strftime("%Y-%m-%d")
    if not path.exists():
        return "Noch kein Verbrauch protokolliert."
    totals: dict[tuple[str, str], list[int]] = defaultdict(lambda: [0, 0, 0, 0, 0])
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not str(rec.get("zeit", "")).startswith(day):
            continue
        key = (str(rec.get("rolle", "?")), str(rec.get("modell", "?")))
        t = totals[key]
        t[0] += 1
        t[1] += int(rec.get("eingabe", 0))
        t[2] += int(rec.get("cache_lesen", 0))
        t[3] += int(rec.get("cache_schreiben", 0))
        t[4] += int(rec.get("ausgabe", 0))
    if not totals:
        return f"Am {day} wurde nichts protokolliert."
    lines = [f"Verbrauch am {day}:"]
    sum_cost = 0.0
    unknown = False
    calls = 0
    for (rolle, modell), (n, ein, lesen, schreiben, aus) in sorted(totals.items()):
        cost = _cost(modell, ein, lesen, schreiben, aus)
        if cost is None:
            unknown = True
            cost_text = "Preis unbekannt"
        else:
            sum_cost += cost
            cost_text = f"{cost:.3f} USD"
        calls += n
        cached = lesen / (ein + lesen + schreiben) * 100 if (ein + lesen + schreiben) else 0
        lines.append(f"{rolle} ({modell}): {n} Aufrufe, Eingabe {ein + lesen + schreiben} Tokens, davon {cached:.0f} % aus dem Cache, Ausgabe {aus} Tokens, {cost_text}")
    lines.append(f"Gesamt: {calls} Aufrufe, etwa {sum_cost:.2f} USD" + (" (ohne Modelle mit unbekanntem Preis)" if unknown else ""))
    return "\n".join(lines)


def build_tools(path: Path) -> list[Tool]:
    return [
        Tool(
            name="verbrauch_heute",
            description="Zeigt den Token-Verbrauch und die geschätzten Kosten eines Tages je Rolle und Modell (Standard heute).",
            input_schema=schema({"tag": {"type": "string", "description": "JJJJ-MM-TT, Standard heute"}}),
            handler=lambda tag=None: report(path, tag),
            parallel_safe=True,
        ),
    ]
