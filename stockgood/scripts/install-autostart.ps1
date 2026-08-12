# Create Startup shortcut for Stockgood tray (current user).
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$target = Join-Path $root "start-tray.bat"
if (-not (Test-Path $target)) {
  throw "missing start-tray.bat at $target"
}

$startup = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
New-Item -ItemType Directory -Force -Path $startup | Out-Null
$lnkPath = Join-Path $startup "Stockgood.lnk"

$wsh = New-Object -ComObject WScript.Shell
$shortcut = $wsh.CreateShortcut($lnkPath)
$shortcut.TargetPath = $target
$shortcut.WorkingDirectory = $root
$shortcut.WindowStyle = 7  # Minimized
$shortcut.Description = "Stockgood tray (autostart)"
$shortcut.Save()

Write-Host "Autostart installed:"
Write-Host "  $lnkPath"
Write-Host "  -> $target"
Write-Host "Log off/on or reboot to start with Windows (after user login)."
