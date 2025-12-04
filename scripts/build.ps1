param(
  [switch]$FullBackend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Step($msg) { Write-Host "[+] $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" }
function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red ; exit 1 }

Step "Check project root"
if (-not (Test-Path frontend) -or -not (Test-Path src-tauri)) { Fail "Run from project root (must contain 'frontend' and 'src-tauri')" }

Step "Check toolchain"
foreach ($cmd in @('node','python','pip','cargo')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Fail "Command not found: $cmd" }
}
$npmCmd = "npm"
if (Get-Command cnpm -ErrorAction SilentlyContinue) {
    $npmCmd = "cnpm"
    Step "Using cnpm as package manager"
} else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Command not found: npm" }
    Step "Using npm as package manager"
}
try { pip show pyinstaller | Out-Null } catch { }
if (-not $?) { Step "Install PyInstaller" ; pip install pyinstaller | Out-Null }

Step "Clean old artifacts"
@(
  'backend\\dist',
  'backend\\build',
  'src-tauri\\target\\release',
  'src-tauri\\target\\release\\dist'
) | ForEach-Object {
  if (Test-Path $_) {
    try { Remove-Item $_ -Recurse -Force -ErrorAction Stop }
    catch { Info "Skip cleaning (locked or in use): $_" }
  }
}
try { if (Test-Path 'src-tauri\\resources\\superAutoCutVideoBackend.exe') { Remove-Item 'src-tauri\\resources\\superAutoCutVideoBackend.exe' -Force -ErrorAction Stop } }
catch { Info "Skip removing resource backend (locked): src-tauri\\resources\\superAutoCutVideoBackend.exe" }

Step "Build frontend"
Push-Location frontend
try {
  if (-not (Test-Path node_modules)) { 
      if ($npmCmd -eq "cnpm") {
          Step "Install frontend deps (cnpm install)" ; cnpm install
      } else {
          Step "Install frontend deps (npm ci)" ; npm ci
      }
  }
  & $npmCmd run build
}
catch { Pop-Location ; Fail "Frontend build failed: $($_.Exception.Message)" }
Pop-Location

Step "Package backend"
Push-Location backend
try {
  Step "Sanity-check Python packages (fix backports namespace)"
  try { pip show backports | Out-Null } catch { }
  if ($?) { Step "Uninstall problematic 'backports' package" ; pip uninstall -y backports | Out-Null }
  Step "Ensure backports.tarfile present"
  pip install -U backports.tarfile | Out-Null

  if ($FullBackend -and (Test-Path requirements.txt)) {
    Step "Install full dependencies (requirements.txt)"
    pip install -r requirements.txt
  }
  elseif (Test-Path requirements.runtime.txt) {
    Step "Install runtime dependencies (requirements.runtime.txt)"
    pip install -r requirements.runtime.txt
  }
  elseif (Test-Path requirements.txt) {
    Step "Fallback to requirements.txt (runtime file missing)"
    pip install -r requirements.txt
  }
  else { Fail "No backend requirements file found" }

  pyinstaller --clean --distpath dist backend.spec
  if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited with code $LASTEXITCODE" }
}
catch { Pop-Location ; Fail "Backend packaging failed: $($_.Exception.Message)" }
finally { Pop-Location }

Step "Copy backend executable to Tauri resources"
New-Item -ItemType Directory -Force src-tauri\\resources | Out-Null
Copy-Item -Force backend\\dist\\superAutoCutVideoBackend.exe src-tauri\\resources\\

Step "Build Tauri app (Release)"
Push-Location src-tauri
try {
  cargo tauri build
  if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build exited with code $LASTEXITCODE" }
}
catch { Pop-Location ; Fail "Tauri build failed: $($_.Exception.Message)" }
finally { Pop-Location }

Step "Create portable ZIP and installers"
# Read product name and version from tauri.conf.json for artifact naming
$cfg = Get-Content -Raw 'src-tauri\\tauri.conf.json' | ConvertFrom-Json
$productName = $cfg.productName
$version = $cfg.version
$artifactBase = 'src-tauri\\target\\release\\dist'
New-Item -ItemType Directory -Force $artifactBase | Out-Null

# Prepare minimal portable directory structure
$releaseDir = 'src-tauri\\target\\release'
$portableTemp = Join-Path $releaseDir 'portable_temp'
if (Test-Path $portableTemp) { Remove-Item $portableTemp -Recurse -Force }
New-Item -ItemType Directory -Force $portableTemp | Out-Null
Copy-Item -Force (Join-Path $releaseDir 'super-auto-cut-video.exe') $portableTemp
New-Item -ItemType Directory -Force (Join-Path $portableTemp 'resources') | Out-Null
Copy-Item -Force (Join-Path $releaseDir 'resources\\superAutoCutVideoBackend.exe') (Join-Path $portableTemp 'resources\\')

# Optionally include docs if present
foreach ($doc in @('README.md','USAGE.md','LICENSE')) {
  if (Test-Path $doc) { Copy-Item -Force $doc $portableTemp }
}

# Sanitize product name for file name (replace non-word chars)
$safeProduct = ($productName -replace '[^A-Za-z0-9_.-]', '_')
$zipName = "${safeProduct}_v${version}_portable.zip"
$zipPath = Join-Path $artifactBase $zipName
Compress-Archive -Path (Join-Path $portableTemp '*') -DestinationPath $zipPath -Force
Remove-Item $portableTemp -Recurse -Force

# Build installers (NSIS/MSI) with fallback to NSIS only
Push-Location src-tauri
try {
  Step "Build installers (NSIS + MSI)"
  cargo tauri build --bundles nsis,msi
  if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (nsis,msi) exited with code $LASTEXITCODE" }
}
catch {
  Info "Installer build (NSIS+MSI) failed, retry NSIS only: $($_.Exception.Message)"
  try { cargo tauri build --bundles nsis }
  catch { Pop-Location ; Fail "Installer build failed: $($_.Exception.Message)" }
  if ($LASTEXITCODE -ne 0) { Pop-Location ; Fail "Cargo tauri build (nsis) exited with code $LASTEXITCODE" }
}
finally { Pop-Location }

# Collect installers into dist\installers
$installersOut = Join-Path $artifactBase 'installers'
New-Item -ItemType Directory -Force $installersOut | Out-Null
foreach ($pair in @(
  @{ dir = 'src-tauri\\target\\release\\bundle\\nsis'; filter = '*.exe' },
  @{ dir = 'src-tauri\\target\\release\\bundle\\msi';  filter = '*.msi' }
)) {
  $d = $pair.dir; $f = $pair.filter
  if (Test-Path $d) {
    Get-ChildItem -Path $d -Filter $f -ErrorAction SilentlyContinue | ForEach-Object {
      Copy-Item -Force $_.FullName $installersOut
    }
  }
}

Step "Build completed"
Info "App: src-tauri\\target\\release\\super-auto-cut-video.exe"
Info "Backend: src-tauri\\target\\release\\resources\\superAutoCutVideoBackend.exe"
Info "Portable ZIP: $zipPath"
Info "Installers dir: $installersOut"