@echo off
chcp 65001 >nul
echo ========================================
echo AutoSynth-Bridge V0.2 - CDP辩论引擎
echo ========================================
echo.

REM 检查Chrome调试端口
netstat -ano | findstr ":9222" >nul
if errorlevel 1 (
    echo [错误] Chrome未运行在调试模式
    echo 请先双击: 1_start_chrome.bat
    pause
    exit /b 1
)
echo [OK] Chrome调试端口正常

REM 运行CDP辩论Demo
echo.
echo 正在启动CDP浏览器引擎...
echo 请在打开的浏览器中登录 ChatGPT 和 Gemini
echo.
python cdp_browser.py
pause
