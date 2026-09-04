"""Einfache JSON-Ablage für Aufgaben und Listen im Datenverzeichnis."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class JsonStore:
    def __init__(self, path: Path, default: Any) -> None:
        self.path = path
        self._default = default

    def load(self) -> Any:
        if not self.path.exists():
            return json.loads(json.dumps(self._default))
        with self.path.open(encoding="utf-8") as fh:
            return json.load(fh)

    def save(self, data: Any) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
        tmp.replace(self.path)
