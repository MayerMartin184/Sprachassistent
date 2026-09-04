@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    call "%~dp0Installieren.bat"
    exit /b
)
start "" "%~dp0.venv\Scripts\pythonw.exe" -m sprachassistent
