@echo off
title Jarvis - Aktualisierung
cd /d "%~dp0"
echo.
echo  Sicherung der Einstellungen ...
for /f "tokens=1-3 delims=. " %%a in ("%date%") do set "STAMP=%%c-%%b-%%a"
set "BACKUP=%~dp0backup\%STAMP%_%time:~0,2%%time:~3,2%"
set "BACKUP=%BACKUP: =0%"
mkdir "%BACKUP%" >nul 2>&1
if exist .env copy /y .env "%BACKUP%\.env" >nul
if exist .env.txt copy /y .env.txt "%BACKUP%\.env.txt" >nul
if exist .env.example copy /y .env.example "%BACKUP%\.env.example" >nul
echo  Gesichert nach: %BACKUP%
echo.
echo  Neueste Version von GitHub holen ...
set "URL=https://github.com/MayerMartin184/Sprachassistent/archive/refs/heads/claude/voice-controlled-task-assistant-li2q6c.zip"
set "TMP_DIR=%TEMP%\jarvis_update"
if exist "%TMP_DIR%" rmdir /s /q "%TMP_DIR%"
mkdir "%TMP_DIR%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol='Tls12'; Invoke-WebRequest -Uri '%URL%' -OutFile '%TMP_DIR%\src.zip'; Expand-Archive -Path '%TMP_DIR%\src.zip' -DestinationPath '%TMP_DIR%\x' -Force; $src=(Get-ChildItem '%TMP_DIR%\x' -Directory | Select-Object -First 1).FullName; Get-ChildItem -Path $src -Force | Where-Object { $_.Name -notin @('.env','.env.txt','.env.example') } | ForEach-Object { Copy-Item -Path $_.FullName -Destination '%~dp0' -Recurse -Force }; if (-not (Test-Path '%~dp0.env.example')) { Copy-Item -Path (Join-Path $src '.env.example') -Destination '%~dp0' }" || goto :fehler
echo  Pakete abgleichen ...
if exist .venv\Scripts\activate.bat (
    call .venv\Scripts\activate.bat
    pip install --quiet -e ".[dev,webcam]" || goto :fehler
)
rmdir /s /q "%TMP_DIR%"
echo.
echo  Fertig. Jarvis ist auf dem neuesten Stand.
echo  Deine Einstellungsdateien (.env, .env.example) wurden NICHT veraendert.
echo.
pause
exit /b 0

:fehler
echo.
echo  Aktualisierung fehlgeschlagen. Deine Einstellungen liegen gesichert in: %BACKUP%
pause
exit /b 1
