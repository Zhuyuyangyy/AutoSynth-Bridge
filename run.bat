@echo off
chcp 65001 >nul
echo ========================================
echo AutoSynth-Bridge V0.1 - Windows Launcher
echo ========================================
echo.

REM Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Install from https://python.org
    pause
    exit /b 1
)

REM Install dependencies
echo [1/3] Installing dependencies...
pip install playwright >nul 2>&1
if errorlevel 1 (
    echo [WARNING] pip install playwright failed, trying --user...
    pip install --user playwright >nul 2>&1
)

REM Install browsers
echo [2/3] Installing Chromium (headless)...
playwright install chromium
if errorlevel 1 (
    echo [WARNING] playwright install failed, trying edge...
    playwright install edge
)

REM Run server
echo [3/3] Starting server on http://127.0.0.1:8090
echo.
echo Server will start. Press Ctrl+C to stop.
echo.
echo API endpoints:
echo   GET  http://127.0.0.1:8090/health
echo   POST http://127.0.0.1:8090/api/web/debate
echo   POST http://127.0.0.1:8090/api/debate
echo   POST http://127.0.0.1:8090/api/pipeline/full
echo.
cd /d "%~dp0"
python main.py
pause
