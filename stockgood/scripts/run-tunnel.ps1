# Run cloudflared quick tunnel and persist the public URL for the Stockgood UI.
$ErrorActionPreference = "Continue"
$root = Split-Path -Parent $PSScriptRoot
$logs = Join-Path $root "logs"
New-Item -ItemType Directory -Force -Path $logs | Out-Null
$urlFile = Join-Path $logs "tunnel-url.txt"
$pidFile = Join-Path $logs "tunnel.pid"
$logFile = Join-Path $logs "tunnel.log"

if (Test-Path $urlFile) { Remove-Item -Force $urlFile }
if (Test-Path $pidFile) { Remove-Item -Force $pidFile }

$cloudflared = Get-Command cloudflared -ErrorAction SilentlyContinue
if (-not $cloudflared) {
  Write-Host "[ERROR] cloudflared not in PATH"
  exit 1
}

Write-Host "Starting tunnel to http://127.0.0.1:5174 ..."
Write-Host "Public URL will appear below and in the Stockgood header."
Write-Host ""

$psi = New-Object System.Diagnostics.ProcessStartInfo
$psi.FileName = $cloudflared.Source
$psi.Arguments = "tunnel --url http://127.0.0.1:5174"
$psi.UseShellExecute = $false
$psi.RedirectStandardOutput = $true
$psi.RedirectStandardError = $true
$psi.CreateNoWindow = $false
$psi.WorkingDirectory = $root

$proc = New-Object System.Diagnostics.Process
$proc.StartInfo = $psi

$script:foundUrl = $null
$handler = {
  param($sender, $e)
  if (-not $e.Data) { return }
  $line = $e.Data
  Add-Content -Path $logFile -Value $line -Encoding UTF8
  Write-Host $line
  if (-not $script:foundUrl -and $line -match "https://[a-zA-Z0-9-]+\.trycloudflare\.com") {
    $script:foundUrl = $Matches[0]
    Set-Content -Path $urlFile -Value $script:foundUrl -Encoding UTF8
    Write-Host ""
    Write-Host ("[tunnel] URL saved for UI: {0}" -f $script:foundUrl)
    Write-Host ("[tunnel] Share apply page with customers: {0}/apply" -f $script:foundUrl)
    Write-Host ""
  }
}

$proc.add_OutputDataReceived($handler)
$proc.add_ErrorDataReceived($handler)

[void]$proc.Start()
$proc.Id | Set-Content -Path $pidFile -Encoding UTF8
$proc.BeginOutputReadLine()
$proc.BeginErrorReadLine()

try {
  $proc.WaitForExit()
} finally {
  if (Test-Path $urlFile) { Remove-Item -Force $urlFile -ErrorAction SilentlyContinue }
  if (Test-Path $pidFile) { Remove-Item -Force $pidFile -ErrorAction SilentlyContinue }
  Write-Host "[tunnel] stopped; UI badge will show offline."
}
