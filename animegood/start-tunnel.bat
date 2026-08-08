@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo   Animegood Cloudflare Tunnel
echo ========================================
echo.
echo Prerequisite: frontend already running on http://localhost:5173
echo   (run start.bat first, wait until the page opens)
echo.
echo This creates a temporary public HTTPS URL. Share it with your friend.
echo The URL changes every time you restart this tunnel.
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

echo Starting tunnel to http://127.0.0.1:5173 ...
echo Look for a line like: https://xxxx.trycloudflare.com
echo Give that URL to your friend. Keep this window open.
echo.
echo Tip: set ANIMEGOOD_ADMIN_TOKEN before sharing.
echo Press Ctrl+C to stop the tunnel.
echo.

cloudflared tunnel --url http://127.0.0.1:5173

echo.
echo Tunnel stopped.
pause
