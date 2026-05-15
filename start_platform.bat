@echo off
setlocal
cd /d "%~dp0"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Uruchamiam MSX THT Inserter Platform...
echo Adres: http://127.0.0.1:8780
echo.
"%PYTHON%" -m inserter_platform.server
pause
