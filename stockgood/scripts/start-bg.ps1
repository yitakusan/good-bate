$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null

$dbMode = if ($env:STOCKGOOD_DB_MODE) { $env:STOCKGOOD_DB_MODE } else { "production" }

# Snapshot DB before services start.
try {
  & (Join-Path $PSScriptRoot "backup-db.ps1") -Reason start
} catch {
  Write-Host "[backup] start backup warning: $_"
}

$python = Join-Path $root "backend\.venv\Scripts\python.exe"
$backendCmd = @(
  "cd /d `"$root\backend`""
  "&&"
  "set STOCKGOOD_DB_MODE=$dbMode"
  "&&"
  "`"$python`" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8002"
  ">> `"$logs\backend.log`" 2>&1"
) -join " "

$frontendCmd = @(
  "cd /d `"$root\frontend`""
  "&&"
  "npm run dev -- --host"
  ">> `"$logs\frontend.log`" 2>&1"
) -join " "

Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/c", $backendCmd | Out-Null
Start-Sleep -Seconds 2
Start-Process -WindowStyle Hidden -FilePath "cmd.exe" -ArgumentList "/c", $frontendCmd | Out-Null
