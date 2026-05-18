param(
  [switch]$KeepExtracted,
  [switch]$NoFrontendInstall
)

$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$frontendDir = Join-Path $root "frontend"
$tauriDir = Join-Path $root "src-tauri"
$resourceDir = Join-Path $tauriDir "resources"
$zipPath = Join-Path $resourceDir "superAutoCutVideoBackend.zip"
$extractDir = Join-Path $resourceDir "superAutoCutVideoBackend"

if (-not (Test-Path -LiteralPath $zipPath)) {
  throw "Missing backend zip: $zipPath. Run build.ps1 once, or copy superAutoCutVideoBackend.zip into src-tauri\resources."
}

if (-not $KeepExtracted -and (Test-Path -LiteralPath $extractDir)) {
  Write-Host "Removing existing extracted backend: $extractDir"
  Remove-Item -LiteralPath $extractDir -Recurse -Force
}

if (-not $NoFrontendInstall) {
  if (-not (Test-Path -LiteralPath (Join-Path $frontendDir "node_modules"))) {
    Write-Host "Installing frontend dependencies..."
    npm -C $frontendDir install
  }
}

$env:TAURI_DEV = "1"
$env:FORCE_PACKAGED_BACKEND = "1"
$env:SACV_FORCE_BACKEND_REEXTRACT = if ($KeepExtracted) { "0" } else { "1" }

Write-Host ""
Write-Host "Starting Tauri dev with packaged backend extraction progress enabled."
Write-Host "Zip: $zipPath"
Write-Host "FORCE_PACKAGED_BACKEND=$env:FORCE_PACKAGED_BACKEND"
Write-Host "SACV_FORCE_BACKEND_REEXTRACT=$env:SACV_FORCE_BACKEND_REEXTRACT"
Write-Host ""

Push-Location $tauriDir
try {
  cargo tauri dev
} finally {
  Pop-Location
}
