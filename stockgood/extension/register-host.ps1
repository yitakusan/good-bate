param(
  [Parameter(Mandatory = $true)]
  [string]$ExtensionId
)

$ErrorActionPreference = "Stop"
if ($ExtensionId -notmatch "^[a-p]{32}$") {
  throw "Extension ID must be 32 letters a-p."
}

$here = Split-Path -Parent $MyInvocation.MyCommand.Path
$hostCmd = Join-Path $here "native-host\host.cmd"
$manifestPath = Join-Path $here "native-host\com.stockgood.launcher.json"
$manifest = [ordered]@{
  name = "com.stockgood.launcher"
  description = "Start Stockgood"
  path = $hostCmd
  type = "stdio"
  allowed_origins = @("chrome-extension://$ExtensionId/")
}
$manifest | ConvertTo-Json | Set-Content -Encoding ascii -Path $manifestPath

$keys = @(
  "HKCU:\Software\Google\Chrome\NativeMessagingHosts\com.stockgood.launcher",
  "HKCU:\Software\Microsoft\Edge\NativeMessagingHosts\com.stockgood.launcher"
)
foreach ($key in $keys) {
  New-Item -Path $key -Force | Out-Null
  New-ItemProperty -Path $key -Name "(default)" -Value $manifestPath -Force | Out-Null
}
Write-Output "Registered native host for $ExtensionId"
