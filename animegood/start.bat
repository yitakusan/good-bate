@echo off
chcp 65001 >nul
setlocal EnableDelayedExpansion

cd /d "%~dp0"

echo ========================================
echo   Animegood local start
echo ========================================
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] missing backend\.venv
    echo Run:
    echo   cd backend
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
    echo   .venv\Scripts\python.exe -m playwright install chromium
    echo.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo [ERROR] missing frontend\node_modules
    echo Run:
    echo   cd frontend
    echo   npm install
    echo.
    pause
    exit /b 1
)

echo [1/3] Starting backend on 127.0.0.1:8001 ...
REM Use python -m (not uvicorn.exe/playwright.exe): Windows venv launchers break after the project folder is moved.
start "Animegood Backend" cmd /k "cd /d %~dp0backend && .venv\Scripts\python.exe -m playwright install chromium && .venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8001"

timeout /t 2 /nobreak >nul

echo [2/3] Starting frontend on 0.0.0.0:5173 (LAN/VPN OK) ...
start "Animegood Frontend" cmd /k "cd /d %~dp0frontend && npm run dev -- --host"

echo.
echo Waiting for services...
timeout /t 5 /nobreak >nul

echo [3/3] Opening browser...
start "" "http://localhost:5173"
start "" "http://localhost:8001/docs"

echo.
echo Started:
echo   You (this PC)     http://localhost:5173
echo   API docs          http://localhost:8001/docs
echo.
echo Share with friends on same VPN / LAN:
echo   Ask them to open  http://YOUR_VPN_OR_LAN_IP:5173
echo   Example Tailscale: http://100.x.x.x:5173
echo.
echo Tips:
echo   - Backend stays on 127.0.0.1; Vite proxies /api for remote users
echo   - Allow Windows Firewall inbound TCP 5173 if blocked
echo   - Set ANIMEGOOD_ADMIN_TOKEN before sharing (block scrape/clear)
echo   - Keep this PC awake; close Backend/Frontend windows to stop
echo.
pause
