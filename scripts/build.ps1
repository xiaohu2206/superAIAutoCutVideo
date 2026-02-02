param(
  [switch]$FullBackend
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Step($msg) { Write-Host "[+] $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" }
function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red ; exit 1 }

function Invoke-CompressArchiveWithRetry([string]$sourcePath, [string]$destinationPath, [int]$retries = 5, [int]$delayMs = 800) {
  for ($i = 1; $i -le $retries; $i++) {
    try {
      Compress-Archive -Path $sourcePath -DestinationPath $destinationPath -Force
      return
    } catch {
      Info "Compress-Archive retry $i/${retries}: $($_.Exception.Message)"
      try {
        Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force
        Get-Process super-auto-cut-video -ErrorAction SilentlyContinue | Stop-Process -Force
      } catch { }
      Start-Sleep -Milliseconds $delayMs
    }
  }
  Fail "Portable ZIP creation failed (file locked)"
}

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

$variants = @("cpu", "gpu")
$cfg = Get-Content -Raw 'src-tauri\\tauri.conf.json' | ConvertFrom-Json
$productName = $cfg.productName
$version = $cfg.version
$artifactBase = 'src-tauri\\target\\release\\dist'
New-Item -ItemType Directory -Force $artifactBase | Out-Null

foreach ($variant in $variants) {
  Step "Package backend ($variant)"
  Push-Location backend
  try {
    Step "Sanity-check Python packages (fix backports namespace)"
    try { pip show backports | Out-Null } catch { }
    if ($?) { Step "Uninstall problematic 'backports' package" ; pip uninstall -y backports | Out-Null }
    Step "Ensure backports.tarfile present"
    pip install -U backports.tarfile | Out-Null

    if ($FullBackend -and (Test-Path requirements.txt)) {
      Step "Install full dependencies (requirements.txt)"
      $tmpFull = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Get-Content requirements.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpFull
      pip install -r $tmpFull
      Remove-Item $tmpFull -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.runtime.txt) {
      Step "Install runtime dependencies (requirements.runtime.txt)"
      $tmpRuntime = Join-Path $env:TEMP "requirements.runtime.filtered.txt"
      (Get-Content requirements.runtime.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpRuntime
      pip install -r $tmpRuntime
      Remove-Item $tmpRuntime -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.txt) {
      Step "Fallback to requirements.txt (runtime file missing)"
      $tmpFullFallback = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Get-Content requirements.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpFullFallback
      pip install -r $tmpFullFallback
      Remove-Item $tmpFullFallback -Force -ErrorAction SilentlyContinue
    }
    else { Fail "No backend requirements file found" }

    pip uninstall -y torchaudio | Out-Null
    pip uninstall -y torch torchvision | Out-Null
    $suffix = if ($variant -eq "cpu") { "cpu" } else { "cu121" }
    $wheelDir = $env:TORCH_WHEEL_DIR
    $usedLocal = $false
    if ($wheelDir -and (Test-Path $wheelDir)) {
      $torchWhl = Join-Path $wheelDir "torch-2.5.1+${suffix}-cp311-cp311-win_amd64.whl"
      $visionWhl = Join-Path $wheelDir "torchvision-0.20.1+${suffix}-cp311-cp311-win_amd64.whl"
      if ((Test-Path $torchWhl) -and (Test-Path $visionWhl)) {
        Step "Install PyTorch from local wheels ($suffix)"
        pip install --no-index --find-links "$wheelDir" "$torchWhl" "$visionWhl"
        $usedLocal = $true
      } else {
        Info "Local wheels not found for variant=$suffix; fallback to official index"
      }
    }
    if (-not $usedLocal) {
      if ($variant -eq "cpu") {
        pip install torch==2.5.1+cpu torchvision==0.20.1+cpu --index-url https://download.pytorch.org/whl/cpu
      } else {
        pip install torch==2.5.1+cu121 torchvision==0.20.1+cu121 --index-url https://download.pytorch.org/whl/cu121
      }
    }
    if ($variant -eq "cpu") {
      pip install torchaudio==2.5.1+cpu --index-url https://download.pytorch.org/whl/cpu
    } else {
      pip install torchaudio==2.5.1+cu121 --index-url https://download.pytorch.org/whl/cu121
    }
    Step "Install qwen-tts (no-deps)"
    pip install qwen-tts --no-deps

    pyinstaller --clean --distpath dist backend.spec
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited with code $LASTEXITCODE" }
  }
  catch { Pop-Location ; Fail "Backend packaging failed: $($_.Exception.Message)" }
  finally { Pop-Location }

  Step "Copy backend executable to Tauri resources ($variant)"
  New-Item -ItemType Directory -Force src-tauri\\resources | Out-Null
  Microsoft.PowerShell.Management\Copy-Item -Force backend\\dist\\superAutoCutVideoBackend.exe src-tauri\\resources\\
  try {
    $ffmpegExe = Get-ChildItem "C:\ProgramData\chocolatey\lib\ffmpeg*" -Recurse -Include ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $ffprobeExe = Get-ChildItem "C:\ProgramData\chocolatey\lib\ffmpeg*" -Recurse -Include ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ffmpegExe) {
      $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
      if ($cmd) { $ffmpegExe = Get-Item $cmd.Path }
    }
    if (-not $ffprobeExe) {
      $cmd = Get-Command ffprobe -ErrorAction SilentlyContinue
      if ($cmd) { $ffprobeExe = Get-Item $cmd.Path }
    }
    if (-not $ffmpegExe -or -not $ffprobeExe) {
      if (Get-Command choco -ErrorAction SilentlyContinue) {
        Step "Install FFmpeg via Chocolatey"
        choco install ffmpeg -y --no-progress | Out-Null
        $ffmpegExe = Get-ChildItem "C:\ProgramData\chocolatey\lib\ffmpeg*" -Recurse -Include ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
        $ffprobeExe = Get-ChildItem "C:\ProgramData\chocolatey\lib\ffmpeg*" -Recurse -Include ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1
      } else {
        Info "FFmpeg not found and Chocolatey unavailable; please ensure ffmpeg.exe and ffprobe.exe are in PATH"
      }
    }
    if ($ffmpegExe) { Microsoft.PowerShell.Management\Copy-Item -Force $ffmpegExe.FullName "src-tauri\\resources\\ffmpeg.exe" }
    if ($ffprobeExe) { Microsoft.PowerShell.Management\Copy-Item -Force $ffprobeExe.FullName "src-tauri\\resources\\ffprobe.exe" }
  } catch { Info "Skip FFmpeg copy: $($_.Exception.Message)" }
 

  Step "Build Tauri app (Release) ($variant)"
  Push-Location src-tauri
  try {
    cargo tauri build
    if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build exited with code $LASTEXITCODE" }
  }
  catch { Pop-Location ; Fail "Tauri build failed: $($_.Exception.Message)" }
  finally { Pop-Location }

  Step "Create portable ZIP and installers ($variant)"
  $releaseDir = 'src-tauri\\target\\release'
  $portableTemp = Join-Path $releaseDir 'portable_temp'
  if (Test-Path $portableTemp) { Remove-Item $portableTemp -Recurse -Force }
  New-Item -ItemType Directory -Force $portableTemp | Out-Null
  Step "Ensure no running instances before zip ($variant)"
  try {
    Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process super-auto-cut-video -ErrorAction SilentlyContinue | Stop-Process -Force
  } catch { }
  Microsoft.PowerShell.Management\Copy-Item -Force (Join-Path $releaseDir 'super-auto-cut-video.exe') $portableTemp
  New-Item -ItemType Directory -Force (Join-Path $portableTemp 'resources') | Out-Null
  Microsoft.PowerShell.Management\Copy-Item -Force (Join-Path $releaseDir 'resources\\superAutoCutVideoBackend.exe') (Join-Path $portableTemp 'resources\\')
  $relRes = Join-Path $releaseDir 'resources'
  $ffmpegRelease = Join-Path $relRes 'ffmpeg.exe'
  $ffprobeRelease = Join-Path $relRes 'ffprobe.exe'
  $ffmpegPortable = Join-Path $portableTemp 'resources\\ffmpeg.exe'
  $ffprobePortable = Join-Path $portableTemp 'resources\\ffprobe.exe'
  if (Test-Path $ffmpegRelease) { Microsoft.PowerShell.Management\Copy-Item -Force $ffmpegRelease $ffmpegPortable }
  if (Test-Path $ffprobeRelease) { Microsoft.PowerShell.Management\Copy-Item -Force $ffprobeRelease $ffprobePortable }
  foreach ($doc in @('README.md','USAGE.md','LICENSE')) {
    if (Test-Path $doc) { Microsoft.PowerShell.Management\Copy-Item -Force $doc $portableTemp }
  }
  $safeProduct = ($productName -replace '[^A-Za-z0-9_.-]', '_')
  $zipName = "${safeProduct}_v${version}_${variant}_portable.zip"
  $variantOut = Join-Path $artifactBase $variant
  New-Item -ItemType Directory -Force $variantOut | Out-Null
  $zipPath = Join-Path $variantOut $zipName
  Invoke-CompressArchiveWithRetry (Join-Path $portableTemp '*') $zipPath
  Remove-Item $portableTemp -Recurse -Force

  Push-Location src-tauri
  try {
    Step "Build installers (NSIS + MSI) ($variant)"
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

  $installersOut = Join-Path $variantOut 'installers'
  New-Item -ItemType Directory -Force $installersOut | Out-Null
  foreach ($pair in @(
    @{ dir = 'src-tauri\\target\\release\\bundle\\nsis'; filter = '*.exe' },
    @{ dir = 'src-tauri\\target\\release\\bundle\\msi';  filter = '*.msi' }
  )) {
    $d = $pair.dir; $f = $pair.filter
    if (Test-Path $d) {
      Get-ChildItem -Path $d -Filter $f -ErrorAction SilentlyContinue | ForEach-Object {
        $base = $_.BaseName
        $ext = $_.Extension
        $dst = Join-Path $installersOut ("${base}_${variant}${ext}")
        Microsoft.PowerShell.Management\Copy-Item -Force $_.FullName $dst
      }
    }
  }

  Step "Build completed ($variant)"
  Info "App: src-tauri\\target\\release\\super-auto-cut-video.exe"
  Info "Backend: src-tauri\\target\\release\\resources\\superAutoCutVideoBackend.exe"
  Info "Portable ZIP: $zipPath"
  Info "Installers dir: $installersOut"
}
