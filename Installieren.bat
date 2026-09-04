@echo off
title Jarvis - Installation
cd /d "%~dp0"
echo.
echo  Jarvis wird eingerichtet. Das dauert einige Minuten.
echo.
where python >nul 2>&1
if errorlevel 1 (
    echo  Python wurde nicht gefunden.
    echo  Bitte von https://www.python.org/downloads/ installieren und dabei
    echo  den Haken "Add python.exe to PATH" setzen. Danach diese Datei erneut starten.
    echo.
    pause
    exit /b 1
)
if not exist .venv (
    echo  [1/4] Python-Umgebung anlegen ...
    python -m venv .venv || goto :fehler
)
call .venv\Scripts\activate.bat
echo  [2/4] Pakete installieren ...
python -m pip install --quiet --upgrade pip
pip install --quiet -e ".[dev,webcam]" || goto :fehler
if not exist .env (
    if exist .env.txt (
        ren .env.txt .env
    ) else (
        copy .env.example .env >nul
    )
)
echo  [3/4] Verknuepfung auf dem Desktop anlegen ...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$d=[Environment]::GetFolderPath('Desktop'); $s=(New-Object -ComObject WScript.Shell).CreateShortcut($d+'\Jarvis.lnk'); $s.TargetPath='%~dp0Jarvis.bat'; $s.WorkingDirectory='%~dp0'; $s.IconLocation='%~dp0sprachassistent\jarvis.ico'; $s.Description='Jarvis Sprachassistent'; $s.Save()"
echo  [4/4] Fertig.
echo.
echo  Auf dem Desktop liegt jetzt "Jarvis". Gleich oeffnet sich die Datei .env:
echo  Dort den Claude-Schluessel und die anderen Zugangsdaten eintragen und speichern.
echo.
pause
start "" notepad .env
exit /b 0

:fehler
echo.
echo  Die Installation ist fehlgeschlagen. Bitte diese Meldung per Screenshot weitergeben.
pause
exit /b 1
