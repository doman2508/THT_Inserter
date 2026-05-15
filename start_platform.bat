@echo off
setlocal
cd /d "%~dp0"

set "INSERTER_PLATFORM_HOST=0.0.0.0"
set "INSERTER_PLATFORM_PORT=8780"
set "INSERTER_PLATFORM_PUBLIC_URL=http://192.168.1.10:%INSERTER_PLATFORM_PORT%"

if exist ".venv\Scripts\python.exe" (
    set "PYTHON=.venv\Scripts\python.exe"
) else (
    set "PYTHON=python"
)

echo Uruchamiam MSX THT Inserter Platform...
echo Lokalnie: http://127.0.0.1:%INSERTER_PLATFORM_PORT%
echo W sieci:  %INSERTER_PLATFORM_PUBLIC_URL%
echo.
"%PYTHON%" -m inserter_platform.server
pause
