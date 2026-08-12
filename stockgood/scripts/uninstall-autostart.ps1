# Remove Stockgood Startup shortcut (current user).
$ErrorActionPreference = "Stop"
$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
$lnkPath = Join-Path $startup "Stockgood.lnk"

if (Test-Path $lnkPath) {
  Remove-Item -Force $lnkPath
  Write-Host "Autostart removed: $lnkPath"
} else {
  Write-Host "No Stockgood Startup shortcut found."
}
