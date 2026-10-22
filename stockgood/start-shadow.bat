@echo off
REM Shadow/test DB launcher. Chinese-named wrapper calls this file.
chcp 65001 >nul
setlocal
cd /d "%~dp0"
echo ========================================
echo   Stockgood SHADOW (test) start
echo   Test DB only - not production stock
echo ========================================
echo.
set STOCKGOOD_DB_MODE=shadow
call "%~dp0start.bat"
