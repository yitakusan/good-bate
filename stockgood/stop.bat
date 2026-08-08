@echo off
chcp 65001 >nul
setlocal

cd /d "%~dp0"

echo ========================================
echo   Stockgood one-click stop
echo ========================================
echo.

echo Stopping backend (port 8002)...
call :kill_port 8002

echo Stopping frontend (port 5174)...
call :kill_port 5174

REM leftover titled windows from older start.bat
taskkill /FI "WINDOWTITLE eq Stockgood Backend*" /T /F >nul 2>&1
taskkill /FI "WINDOWTITLE eq Stockgood Frontend*" /T /F >nul 2>&1

REM Wait briefly so SQLite releases file locks, then snapshot.
timeout /t 1 /nobreak >nul
echo.
echo Backing up database...
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\backup-db.ps1" -Reason stop

echo.
echo Done. Stockgood stopped.
echo Backups: backend\data\backups\
echo.
timeout /t 2 /nobreak >nul
exit /b 0

:kill_port
set "PORT=%~1"
set "FOUND="
for /f "tokens=5" %%P in ('netstat -ano 2^>nul ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  if not "%%P"=="0" (
    set "FOUND=1"
    echo   killing PID %%P on port %PORT%
    taskkill /F /PID %%P /T >nul 2>&1
  )
)
if not defined FOUND echo   (nothing listening on %PORT%)
exit /b 0
