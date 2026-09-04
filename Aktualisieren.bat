@echo off
title Jarvis - Aktualisierung
cd /d "%~dp0"
echo.
echo  Neueste Version von GitHub holen ...
set "URL=https://github.com/MayerMartin184/Sprachassistent/archive/refs/heads/claude/voice-controlled-task-assistant-li2q6c.zip"
set "TMP_DIR=%TEMP%\jarvis_update"
if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
mkdir "%TMP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%URL%' -OutFile '%TMP_DIR%\src.zip'; Expand-Archive -Path '%TMP_DIR%\src.zip' -DestinationPath '%TMP_DIR%\x' -Force; $src=(Get-ChildItem '%TMP_DIR%\x' -Directory | Select-Object -First 1).FullName; Copy-Item -Path ($src+'\*') -Destination '%~dp0' -Recurse -Force" || goto :fehler
echo  Pakete abgleichen ...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    pip install --quiet -e ".[dev,webcam]" || goto :fehler
)
rmdir /s /q "%TMP_DIR%"
echo.
echo  Fertig. Jarvis ist auf dem neuesten Stand. Deine .env wurde nicht veraendert.
echo.
pause
exit /b 0

:fehler
echo.
echo  Aktualisierung fehlgeschlagen. Bitte diese Meldung per Screenshot weitergeben.
pause
exit /b 1
