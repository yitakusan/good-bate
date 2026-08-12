@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

if not defined STOCKGOOD_DB_MODE set STOCKGOOD_DB_MODE=production

if not exist "backend\.venv\Scripts\pythonw.exe" (
  if not exist "backend\.venv\Scripts\python.exe" (
    echo [ERROR] missing backend\.venv
    echo Run: cd backend ^& python -m venv .venv ^& .venv\Scripts\python.exe -m pip install -r requirements.txt
    pause
    exit /b 1
  )
)

if not exist "frontend\node_modules" (
  echo [ERROR] missing frontend\node_modules
  echo Run: cd frontend ^& npm install
  pause
  exit /b 1
)

REM Prefer pythonw (no console). Fall back to python.
set "PYW=%~dp0backend\.venv\Scripts\pythonw.exe"
set "PY=%~dp0backend\.venv\Scripts\python.exe"
if exist "%PYW%" (
  start "" "%PYW%" "%~dp0scripts\tray_app.py"
) else (
  start "" "%PY%" "%~dp0scripts\tray_app.py"
)
exit /b 0
