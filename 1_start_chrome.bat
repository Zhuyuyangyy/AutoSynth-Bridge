"""
AutoSynth-Bridge 快速启动器 (Windows)
一键启动：Chrome调试模式 → CDP连接 → 辩论自动化

使用方法：
    1. 先双击 1_start_chrome.bat（只做一次）
    2. 然后双击 2_run_bridge.bat
"""
@echo off
chcp 65001 >nul
echo ========================================
echo AutoSynth-Bridge V0.2 - CDP Edition
echo ========================================
echo.
echo [检查项]
echo.

REM 检查Chrome路径
where chrome >nul 2>&1
if %errorlevel%==0 (
    set CHROME=chrome
) else (
    set "CHROME=C:\Program Files\Google\Chrome\Application\chrome.exe"
    if not exist "%CHROME%" (
        set "CHROME=C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"
    )
)

if not exist "%CHROME%" (
    echo [错误] 未找到Chrome浏览器
    echo 请安装Chrome: https://www.google.com/chrome/
    pause
    exit /b 1
)

echo [OK] Chrome: %CHROME%

REM 检查Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请安装Python 3.10+
    pause
    exit /b 1
)
echo [OK] Python: 
python --version

REM 安装依赖
echo.
echo [安装Python依赖...]
pip install websockets playwright fastapi uvicorn >nul 2>&1
if errorlevel 1 (
    pip install --user websockets playwright fastapi uvicorn >nul 2>&1
)

echo [OK] 依赖就绪

REM 启动Chrome调试模式（如果还没启动）
echo.
echo [检查Chrome调试端口...]
netstat -ano | findstr ":9222" >nul
if errorlevel 1 (
    echo [启动Chrome调试模式...]
    start "" "%CHROME%" --remote-debugging-port=9222 --user-data-dir="%USERPROFILE%\chrome_debug_profile" --new-window "https://chat.openai.com" "https://gemini.google.com"
    timeout /t 5 >nul
    echo [OK] Chrome已启动（调试端口 9222）
) else (
    echo [OK] Chrome调试端口已就绪
)

echo.
echo ========================================
echo 准备就绪！
echo.
echo 打开浏览器登录 ChatGPT 和 Gemini
echo 然后双击: 2_run_bridge.bat
echo ========================================
pause
