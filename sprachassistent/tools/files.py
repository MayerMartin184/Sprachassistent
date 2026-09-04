"""Dateiablage: Ordnen, Suchen, Verschieben, Lesen und Schreiben – nur innerhalb des Wurzelordners."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from .base import Tool, schema

TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".yaml", ".yml", ".log", ".ini", ".xml", ".html", ".py"}
MAX_RESULTS = 60


class FileManager:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def resolve(self, relative: str = "") -> Path:
        candidate = Path(relative).expanduser()
        path = (candidate if candidate.is_absolute() else self.root / candidate).resolve()
        if path != self.root and self.root not in path.parents:
            raise PermissionError(f"Pfad liegt außerhalb des erlaubten Ordners {self.root}: {relative}")
        return path

    def rel(self, path: Path) -> str:
        return str(path.relative_to(self.root)) or "."

    def list_dir(self, relative: str = "") -> str:
        path = self.resolve(relative)
        if not path.is_dir():
            raise FileNotFoundError(f"Ordner nicht gefunden: {relative}")
        entries = sorted(path.iterdir(), key=lambda p: (p.is_file(), p.name.lower()))
        if not entries:
            return f"Ordner '{self.rel(path)}' ist leer."
        lines = [f"Inhalt von '{self.rel(path)}':"]
        for entry in entries[:MAX_RESULTS]:
            lines.append(self._describe(entry))
        if len(entries) > MAX_RESULTS:
            lines.append(f"... und {len(entries) - MAX_RESULTS} weitere")
        return "\n".join(lines)

    def search(self, query: str, relative: str = "") -> str:
        base = self.resolve(relative)
        needle = query.lower()
        hits = [p for p in base.rglob("*") if needle in p.name.lower()]
        if not hits:
            return f"Keine Treffer für '{query}' in '{self.rel(base)}'."
        hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        lines = [f"{len(hits)} Treffer für '{query}':"] + [self._describe(p) for p in hits[:MAX_RESULTS]]
        return "\n".join(lines)

    def mkdir(self, relative: str) -> str:
        path = self.resolve(relative)
        path.mkdir(parents=True, exist_ok=True)
        return f"Ordner vorhanden: {self.rel(path)}"

    def move(self, source: str, destination: str) -> str:
        src = self.resolve(source)
        if not src.exists():
            raise FileNotFoundError(f"Quelle nicht gefunden: {source}")
        dst = self.resolve(destination)
        if dst.is_dir():
            dst = dst / src.name
        if dst.exists():
            raise FileExistsError(f"Ziel existiert bereits: {self.rel(dst)}")
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
        return f"Verschoben: {self.rel(src)} -> {self.rel(dst)}"

    def read_text(self, relative: str, max_chars: int = 8000) -> str:
        path = self.resolve(relative)
        if not path.is_file():
            raise FileNotFoundError(f"Datei nicht gefunden: {relative}")
        if path.suffix.lower() not in TEXT_SUFFIXES:
            raise ValueError(f"Kein lesbares Textformat: {path.suffix}")
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > max_chars:
            return text[:max_chars] + f"\n... [gekürzt, {len(text)} Zeichen gesamt]"
        return text

    def write_text(self, relative: str, content: str, overwrite: bool = False) -> str:
        path = self.resolve(relative)
        if path.exists() and not overwrite:
            raise FileExistsError(f"Datei existiert bereits (overwrite=true zum Überschreiben): {relative}")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return f"Gespeichert: {self.rel(path)} ({len(content)} Zeichen)"

    def _describe(self, path: Path) -> str:
        stat = path.stat()
        mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
        if path.is_dir():
            return f"[Ordner] {self.rel(path)}/"
        return f"[Datei]  {self.rel(path)}  ({_human(stat.st_size)}, {mtime})"


def _human(size: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} GB"


def build_tools(fm: FileManager) -> list[Tool]:
    root_hint = f"Alle Pfade sind relativ zum Ablageordner ({fm.root})."
    return [
        Tool(
            name="files_list",
            description=f"Listet den Inhalt eines Ordners. {root_hint}",
            input_schema=schema({"path": {"type": "string", "description": "Relativer Ordnerpfad, leer = Wurzel"}}),
            handler=lambda path="": fm.list_dir(path),
        ),
        Tool(
            name="files_search",
            description=f"Sucht Dateien und Ordner per Namensbestandteil (rekursiv). {root_hint}",
            input_schema=schema(
                {"query": {"type": "string"}, "path": {"type": "string", "description": "Startordner, leer = Wurzel"}},
                ["query"],
            ),
            handler=lambda query, path="": fm.search(query, path),
        ),
        Tool(
            name="files_mkdir",
            description=f"Legt einen Ordner an (inklusive Zwischenordner). {root_hint}",
            input_schema=schema({"path": {"type": "string"}}, ["path"]),
            handler=lambda path: fm.mkdir(path),
        ),
        Tool(
            name="files_move",
            description=(
                "Verschiebt oder benennt eine Datei/einen Ordner um. Ist das Ziel ein Ordner, wird die Datei "
                f"dort abgelegt. Überschreibt nie. {root_hint}"
            ),
            input_schema=schema({"source": {"type": "string"}, "destination": {"type": "string"}}, ["source", "destination"]),
            handler=fm.move,
        ),
        Tool(
            name="files_read",
            description=f"Liest eine Textdatei (txt, md, csv, json ...). {root_hint}",
            input_schema=schema(
                {"path": {"type": "string"}, "max_chars": {"type": "integer", "description": "Standard 8000"}},
                ["path"],
            ),
            handler=lambda path, max_chars=8000: fm.read_text(path, max_chars),
        ),
        Tool(
            name="files_write",
            description=f"Schreibt eine Textdatei, z. B. Notizen, Rechercheergebnisse oder Listen. {root_hint}",
            input_schema=schema(
                {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "overwrite": {"type": "boolean", "description": "Vorhandene Datei überschreiben (Standard: nein)"},
                },
                ["path", "content"],
            ),
            handler=lambda path, content, overwrite=False: fm.write_text(path, content, overwrite),
        ),
    ]
