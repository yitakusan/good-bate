@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ID=%~1"
if "%ID%"=="" set /p ID=Paste the extension ID from the popup: 
if "%ID%"=="" (
  echo Extension ID is required.
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0register-host.ps1" -ExtensionId "%ID%"
if errorlevel 1 exit /b 1
echo Registered. Reload the extension, then click it again.
endlocal
