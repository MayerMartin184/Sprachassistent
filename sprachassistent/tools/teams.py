"""Hilfsfunktionen für Teams-Transkripte (WebVTT -> 'Sprecher: Text')."""

from __future__ import annotations

import re

_TIMING = re.compile(r"^\d{2}:\d{2}(:\d{2})?\.\d{3}\s+-->\s+")
_VOICE = re.compile(r"<v\s+([^>]+)>(.*?)</v>", re.S)
_TAGS = re.compile(r"<[^>]+>")


def parse_vtt(vtt: str) -> str:
    """Wandelt WebVTT in fortlaufenden Text um und fasst aufeinanderfolgende Aussagen eines Sprechers zusammen."""
    lines: list[tuple[str, str]] = []
    for raw in vtt.splitlines():
        line = raw.strip()
        if not line or line == "WEBVTT" or _TIMING.match(line) or line.isdigit() or "-->" in line:
            continue
        if line.startswith(("NOTE", "STYLE", "REGION")):
            continue
        match = _VOICE.search(line)
        if match:
            speaker, text = match.group(1).strip(), match.group(2)
        else:
            speaker, text = "", line
        text = " ".join(_TAGS.sub("", text).split())
        if not text:
            continue
        if lines and lines[-1][0] == speaker:
            lines[-1] = (speaker, lines[-1][1] + " " + text)
        else:
            lines.append((speaker, text))
    return "\n".join(f"{s}: {t}" if s else t for s, t in lines)
