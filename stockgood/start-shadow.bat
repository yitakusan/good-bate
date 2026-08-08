@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ========================================
echo   Stockgood SHADOW (test) start
echo   测试影子库 · 不参与实际库存
echo ========================================
echo.

set STOCKGOOD_DB_MODE=shadow
call "%~dp0start.bat"
