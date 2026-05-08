# Hook installieren (einmalig nach git clone ausfuehren)
$hookSrc = "$PSScriptRoot\pre-push"
$hookDst = "$PSScriptRoot\..\git\hooks\pre-push"
$hooksDir = Split-Path $hookDst

if (-not (Test-Path $hooksDir)) { New-Item -ItemType Directory -Path $hooksDir | Out-Null }
Copy-Item $hookSrc $hookDst -Force
Write-Host "Hook installiert: $hookDst"
Write-Host "Nicht vergessen: GITHUB_TOKEN=ghp_... in .env eintragen!"
