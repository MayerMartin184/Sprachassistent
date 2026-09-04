"""Einstieg: `python -m sprachassistent` (Fenster) oder `python -m sprachassistent --cli` (Terminal)."""

from __future__ import annotations

import argparse
import logging
import sys
from logging.handlers import RotatingFileHandler

from .config import ConfigError, check_required, load_settings


def run_cli() -> None:
    from .assistant import Assistant

    settings = load_settings()
    check_required(settings)

    def confirm(message: str) -> bool:
        print("\n" + message)
        return input("Bestätigen? [j/N] ").strip().lower() in ("j", "ja", "y", "yes")

    assistant = Assistant(
        settings,
        confirm=confirm,
        notify=lambda msg: print("\n" + msg + "\n"),
        on_status=lambda msg: print(f"  … {msg}", file=sys.stderr),
    )
    print(f"{settings.assistant_name} (Textmodus) – {assistant.capabilities}")
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
            print(f"{settings.assistant_name}: {assistant.handle_text(text)}\n")


def run_setup_m365() -> None:
    """Microsoft-App im Terminal einrichten (Alternative zum Knopf im Fenster)."""
    from pathlib import Path

    from .config import update_env_file
    from .tools.m365_setup import M365Setup

    settings = load_settings()
    result = M365Setup(settings.ms_tenant_id, lambda msg: print("\n" + msg + "\n")).run(settings.ms_client_id)
    env_path = settings.env_file_in_use() or Path(".env").resolve()
    update_env_file(Path(env_path), {"MS_CLIENT_ID": result["client_id"], "MS_TENANT_ID": result["tenant_id"] or settings.ms_tenant_id})
    print(f"Fertig. MS_CLIENT_ID={result['client_id']} ({'neu' if result['created'] else 'korrigiert'}). Jarvis neu starten.")


def run_backend(port: int) -> None:
    """Backend-Prozess (wird vom Fenster gestartet)."""
    from .server import serve

    settings = load_settings()
    _log_to_file(settings.data_dir / "jarvis.log")
    try:
        check_required(settings)
    except ConfigError as exc:
        logging.error("%s", exc)
        sys.exit(2)
    serve(settings, port)


def run_gui(use_tk: bool = False) -> None:
    import tkinter as tk
    from tkinter import messagebox

    settings = load_settings()
    _log_to_file(settings.data_dir / "jarvis.log")
    try:
        check_required(settings)
        if not use_tk:
            try:
                from . import window
            except ImportError:
                window = None  # type: ignore[assignment]
                logging.warning("pywebview nicht verfügbar – klassisches Fenster")
            if window is not None:
                window.run(settings)
                return
        from .app import App

        App(settings).run()
    except ConfigError as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Jarvis – Einrichtung unvollständig", str(exc))
        sys.exit(1)
    except Exception as exc:  # noqa: BLE001 - ohne Konsole muss der Fehler sichtbar werden
        logging.exception("Start fehlgeschlagen")
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Jarvis – Fehler", f"{exc}\n\nDetails stehen in {settings.data_dir / 'jarvis.log'}")
        sys.exit(1)


def _log_to_file(path) -> None:  # noqa: ANN001
    handler = RotatingFileHandler(path, maxBytes=2_000_000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    logging.getLogger().setLevel(logging.INFO)


def main() -> None:
    parser = argparse.ArgumentParser(prog="sprachassistent", description="Sprachgesteuerter Desktop-Assistent")
    parser.add_argument("--cli", action="store_true", help="Textmodus im Terminal statt Fenster")
    parser.add_argument("--tk", action="store_true", help="Klassisches Tkinter-Fenster statt Web-Ansicht")
    parser.add_argument("--backend", action="store_true", help="Nur Backend-Prozess (intern, vom Fenster gestartet)")
    parser.add_argument("--setup-m365", action="store_true", help="Microsoft-App-Registrierung automatisch einrichten")
    parser.add_argument("--port", type=int, default=0, help="Port des Backends (intern)")
    parser.add_argument("-v", "--verbose", action="store_true", help="Ausführliche Protokollierung")
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.setup_m365:
        run_setup_m365()
    elif args.backend:
        run_backend(args.port)
    elif args.cli:
        try:
            run_cli()
        except ConfigError as exc:
            print(f"\n{exc}", file=sys.stderr)
            sys.exit(1)
    else:
        run_gui(use_tk=args.tk)


if __name__ == "__main__":
    main()
