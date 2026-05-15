@echo off
setlocal
cd /d "%~dp0"

set "INSERTER_REPORT_DIR=\\DOKUMENTACJE\__NARZEDZIA__\Raporty_inserter"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Uruchamiam serwer raportow MSX THT Inserter...
echo Katalog raportow: %INSERTER_REPORT_DIR%
echo.
"%PYTHON%" report_server.py
pause
