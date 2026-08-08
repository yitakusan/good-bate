# Backup Stockgood SQLite DBs on start/stop.
# Usage: backup-db.ps1 -Reason start|stop
param(
  [ValidateSet("start", "stop")]
  [string]$Reason = "start",
  [int]$Keep = 30
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $root "backend\data"
$backupDir = Join-Path $dataDir "backups"
$python = Join-Path $root "backend\.venv\Scripts\python.exe"

New-Item -ItemType Directory -Force -Path $backupDir | Out-Null

if (-not (Test-Path $python)) {
  Write-Host "[backup] skip: missing backend\.venv"
  exit 0
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$targets = @(
  @{ Name = "stockgood"; Path = (Join-Path $dataDir "stockgood.sqlite") },
  @{ Name = "stockgood.shadow"; Path = (Join-Path $dataDir "stockgood.shadow.sqlite") }
)

$backed = 0
foreach ($target in $targets) {
  if (-not (Test-Path $target.Path)) { continue }
  $dest = Join-Path $backupDir ("{0}.{1}.{2}.sqlite" -f $target.Name, $stamp, $Reason)
  & $python -c @"
import sqlite3
from pathlib import Path
src = Path(r'''$($target.Path)''')
dst = Path(r'''$dest''')
src_conn = sqlite3.connect(str(src))
try:
    src_conn.execute('PRAGMA wal_checkpoint(TRUNCATE)')
except Exception:
    pass
dst_conn = sqlite3.connect(str(dst))
try:
    with dst_conn:
        src_conn.backup(dst_conn)
finally:
    dst_conn.close()
    src_conn.close()
print(dst.name)
"@
  if ($LASTEXITCODE -ne 0) {
    Write-Host "[backup] FAILED $($target.Name)"
    continue
  }
  $size = (Get-Item $dest).Length
  Write-Host ("[backup] {0} -> backups\{1} ({2:N1} KB)" -f $Reason, (Split-Path $dest -Leaf), ($size / 1KB))
  $backed += 1

  # Retention: keep newest $Keep per db name + reason suffix pattern
  $pattern = "$($target.Name).*.sqlite"
  Get-ChildItem -Path $backupDir -Filter $pattern -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -Skip $Keep |
    ForEach-Object {
      Remove-Item -LiteralPath $_.FullName -Force
      Write-Host "[backup] pruned $($_.Name)"
    }
}

if ($backed -eq 0) {
  Write-Host "[backup] nothing to backup (no sqlite files yet)"
}
exit 0
