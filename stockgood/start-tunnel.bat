@echo off
chcp 65001 >nul
setlocal EnableExtensions

cd /d "%~dp0"

echo ========================================
echo   Stockgood Cloudflare Tunnel
echo ========================================
echo.
echo Temporary public HTTPS for friends in China.
echo Tunnel points at the frontend (5174); /api is proxied locally.
echo URL changes every time you restart this tunnel.
echo.

where cloudflared >nul 2>nul
if errorlevel 1 (
    echo [ERROR] cloudflared not found in PATH.
    echo.
    echo Install one of:
    echo   1^) winget install --id Cloudflare.cloudflared
    echo   2^) Download from https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/
    echo.
    echo Then reopen this window and run start-tunnel.bat again.
    echo.
    pause
    exit /b 1
)

REM Ensure local UI is up; start backend+frontend if needed.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { $r = Invoke-WebRequest -Uri 'http://127.0.0.1:5174' -UseBasicParsing -TimeoutSec 2; exit 0 } catch { exit 1 }" >nul 2>nul
if errorlevel 1 (
    echo Frontend not detected on http://127.0.0.1:5174
    echo Starting backend + frontend in background...
    if not defined STOCKGOOD_DB_MODE set STOCKGOOD_DB_MODE=production
    if not exist "backend\.venv\Scripts\python.exe" (
        echo [ERROR] missing backend\.venv — run install steps in README first.
        pause
        exit /b 1
    )
    if not exist "frontend\node_modules" (
        echo [ERROR] missing frontend\node_modules — run npm install first.
        pause
        exit /b 1
    )
    powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-bg.ps1"
    if errorlevel 1 (
        echo [ERROR] background start failed
        pause
        exit /b 1
    )
    echo Waiting for frontend...
    set /a _tries=0
    :wait_frontend
    set /a _tries+=1
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "try { Invoke-WebRequest -Uri 'http://127.0.0.1:5174' -UseBasicParsing -TimeoutSec 2 | Out-Null; exit 0 } catch { exit 1 }" >nul 2>nul
    if not errorlevel 1 goto frontend_ready
    if %_tries% GEQ 30 (
        echo [ERROR] frontend did not become ready. Check logs\frontend.log
        pause
        exit /b 1
    )
    timeout /t 2 /nobreak >nul
    goto wait_frontend
    :frontend_ready
    echo Frontend is ready.
    echo.
) else (
    echo Frontend already running on http://127.0.0.1:5174
    echo.
)

echo Starting tunnel to http://127.0.0.1:5174 ...
echo Look for a line like: https://xxxx.trycloudflare.com
echo Share the APPLY page with customers: https://xxxx.trycloudflare.com/apply
echo The Stockgood header will show tunnel status + copy apply link.
echo.
echo Security: anyone with the link can open /apply ^(and the admin root if they guess it^).
echo Prefer sharing only .../apply. Ctrl+C stops the tunnel.
echo Press Ctrl+C to stop the tunnel ^(local services keep running; use stop.bat to shut them down^).
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-tunnel.ps1"

echo.
echo Tunnel stopped.
pause
