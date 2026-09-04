"""Einstieg: `python -m sprachassistent` (Desktop) oder `python -m sprachassistent --cli` (Terminal)."""

from __future__ import annotations

import argparse
import logging
import sys

from .config import load_settings


def run_cli() -> None:
    from .assistant import Assistant

    settings = load_settings()

    def confirm(message: str) -> bool:
        print("\n" + message)
        return input("Bestätigen? [j/N] ").strip().lower() in ("j", "ja", "y", "yes")

    assistant = Assistant(
        settings,
        confirm=confirm,
        notify=lambda msg: print("\n" + msg + "\n"),
        on_status=lambda msg: print(f"  … {msg}", file=sys.stderr),
    )
    print(f"Sprachassistent (Textmodus) – {assistant.capabilities}")
    print("Eingabe mit Enter senden, 'exit' beendet.\n")
    while True:
        try:
            text = input("Du: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in ("exit", "quit", "ende"):
            break
        if text:
            print(f"Assistent: {assistant.handle_text(text)}\n")


def run_gui() -> None:
    from .app import App

    App(load_settings()).run()


def main() -> None:
    parser = argparse.ArgumentParser(prog="sprachassistent", description="Sprachgesteuerter Desktop-Assistent")
    parser.add_argument("--cli", action="store_true", help="Textmodus im Terminal statt Desktop-Fenster")
    parser.add_argument("-v", "--verbose", action="store_true", help="Ausführliche Protokollierung")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.cli:
        run_cli()
    else:
        run_gui()


if __name__ == "__main__":
    main()
