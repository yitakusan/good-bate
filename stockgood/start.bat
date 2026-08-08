@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

if not defined STOCKGOOD_DB_MODE set STOCKGOOD_DB_MODE=production

echo ========================================
if /I "%STOCKGOOD_DB_MODE%"=="shadow" (
  echo   Stockgood SHADOW start
) else (
  echo   Stockgood production start
)
echo ========================================
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] missing backend\.venv
    echo Run:
    echo   cd backend
    echo   python -m venv .venv
    echo   .venv\Scripts\python.exe -m pip install -r requirements.txt
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

echo Starting backend + frontend in background...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-bg.ps1"
if errorlevel 1 (
    echo [ERROR] background start failed
    pause
    exit /b 1
)

echo Waiting for services...
timeout /t 5 /nobreak >nul

echo Opening browser...
start "" "http://localhost:5174"
start "" "http://localhost:8002/docs"

echo.
echo Started in background:
echo   Mode     %STOCKGOOD_DB_MODE%
echo   UI       http://localhost:5174
echo   API docs http://localhost:8002/docs
echo   Logs     logs\backend.log / logs\frontend.log
echo   Backups  backend\data\backups\  ^(auto on start/stop^)
echo   Stop     stop.bat
if /I "%STOCKGOOD_DB_MODE%"=="production" (
  echo   Shadow   start-shadow.bat  ^(test DB^)
)
echo.
echo This window will close in 3 seconds...
timeout /t 3 /nobreak >nul
exit /b 0
