param(
  [switch]$FullBackend,
  [ValidateSet('cpu','gpu','all')]
  [string]$Variant = 'all',
  [switch]$RecreateBackendVenv,
  [switch]$TauriDebug
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
$pythonCmd = "python"
$pythonArgsPrefix = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  try {
    $out = & py -3.11 "-c" "import sys; print('%d.%d' % (sys.version_info.major, sys.version_info.minor))" 2>$null
    $outNorm = ($out | Out-String).Trim().Trim([char]0xFEFF)
    if ($outNorm.StartsWith("3.11")) {
      $pythonCmd = "py"
      $pythonArgsPrefix = @("-3.11")
      Step "Using Python 3.11 via 'py -3.11'"
    }
  } catch { }
}
# Verify Python version >= 3.11
try {
  $ver = & $pythonCmd $pythonArgsPrefix "-c" "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
  if (-not $ver) { Fail "Failed to detect Python version" }
  $parts = $ver.Trim() -split '\.'
  if ([int]$parts[0] -lt 3 -or ([int]$parts[0] -eq 3 -and [int]$parts[1] -lt 11)) {
    Fail "Python >= 3.11 is required (detected $ver). Please install Python 3.11 and ensure 'py -3.11' or 'python' points to it."
  }
} catch {
  Fail "Python version check failed: $($_.Exception.Message)"
}
$npmCmd = "npm"
if (Get-Command cnpm -ErrorAction SilentlyContinue) {
    $npmCmd = "cnpm"
    Step "Using cnpm as package manager"
} else {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) { Fail "Command not found: npm" }
    Step "Using npm as package manager"
}
try { & $pythonCmd $pythonArgsPrefix "-m" "pip" "show" "pyinstaller" | Out-Null } catch { }
if (-not $?) { Step "Install PyInstaller" ; & $pythonCmd $pythonArgsPrefix "-m" "pip" "install" "pyinstaller" | Out-Null }

Step "Clean old artifacts"
@(
  'backend\\dist',
  'backend\\build',
  'src-tauri\\target\\release',
  'src-tauri\\target\\release\\dist',
  'src-tauri\\target\\debug',
  'src-tauri\\target\\debug\\dist',
  'src-tauri\\target\\tauri_cpu',
  'src-tauri\\target\\tauri_cpu_debug',
  'src-tauri\\target\\tauri_gpu',
  'src-tauri\\target\\tauri_gpu_debug'
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

$rootDir = (Get-Location).Path
$variants = if ($Variant -eq 'all') { @('cpu','gpu') } else { @($Variant) }
$cfg = Get-Content -Raw 'src-tauri\\tauri.conf.json' | ConvertFrom-Json
$productName = $cfg.productName
$version = $cfg.version
$artifactBase = if ($TauriDebug) { 'src-tauri\\target\\debug\\dist' } else { 'src-tauri\\target\\release\\dist' }
New-Item -ItemType Directory -Force $artifactBase | Out-Null

foreach ($variant in $variants) {
  Step "Package backend ($variant)"
  Push-Location backend
  try {
    $venvDir = Join-Path (Get-Location).Path (".venv_pack_{0}" -f $variant)
    if ($RecreateBackendVenv -and (Test-Path $venvDir)) {
      Step "Recreate backend venv ($variant)"
      Remove-Item $venvDir -Recurse -Force -ErrorAction SilentlyContinue
    }
    if (-not (Test-Path $venvDir)) {
      Step "Create backend venv ($variant)"
      & $pythonCmd $pythonArgsPrefix "-m" "venv" $venvDir
      if ($LASTEXITCODE -ne 0) { throw "venv creation failed (code $LASTEXITCODE)" }
    }
    $venvPy = Join-Path $venvDir 'Scripts\\python.exe'
    if (-not (Test-Path $venvPy)) { throw "venv python not found: $venvPy" }

    Step "Ensure pip available in venv ($variant)"
    $pipOk = $true
    try { & $venvPy "-m" "pip" "--version" | Out-Null } catch { $pipOk = $false }
    if ($LASTEXITCODE -ne 0) { $pipOk = $false }
    if (-not $pipOk) {
      Step "Bootstrap pip via ensurepip ($variant)"
      & $venvPy "-m" "ensurepip" "--upgrade" | Out-Null
      if ($LASTEXITCODE -ne 0) { throw "ensurepip failed (code $LASTEXITCODE)" }
    }

    Step "Upgrade pip tooling ($variant)"
    & $venvPy "-m" "pip" "install" "-U" "pip" "setuptools" "wheel" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed (code $LASTEXITCODE)" }

    Step "Ensure build deps (PyInstaller) ($variant)"
    & $venvPy "-m" "pip" "install" "-U" "pyinstaller" | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "pyinstaller install failed (code $LASTEXITCODE)" }

    Step "Sanity-check Python packages (fix backports namespace) ($variant)"
    try { & $venvPy "-m" "pip" "show" "backports" | Out-Null } catch { }
    if ($?) { Step "Uninstall problematic 'backports' package ($variant)" ; & $venvPy "-m" "pip" "uninstall" "-y" "backports" | Out-Null }
    Step "Ensure backports.tarfile present ($variant)"
    & $venvPy "-m" "pip" "install" "-U" "backports.tarfile" | Out-Null

    if ($FullBackend -and (Test-Path requirements.txt)) {
      Step "Install full dependencies (requirements.txt)"
      $tmpFull = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Get-Content requirements.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpFull
      & $venvPy "-m" "pip" "install" "-r" $tmpFull
      Remove-Item $tmpFull -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.runtime.txt) {
      Step "Install runtime dependencies (requirements.runtime.txt)"
      $tmpRuntime = Join-Path $env:TEMP "requirements.runtime.filtered.txt"
      (Get-Content requirements.runtime.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpRuntime
      & $venvPy "-m" "pip" "install" "-r" $tmpRuntime
      Remove-Item $tmpRuntime -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.txt) {
      Step "Fallback to requirements.txt (runtime file missing)"
      $tmpFullFallback = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Get-Content requirements.txt) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content $tmpFullFallback
      & $venvPy "-m" "pip" "install" "-r" $tmpFullFallback
      Remove-Item $tmpFullFallback -Force -ErrorAction SilentlyContinue
    }
    else { Fail "No backend requirements file found" }

    & $venvPy "-m" "pip" "uninstall" "-y" "torchaudio" | Out-Null
    & $venvPy "-m" "pip" "uninstall" "-y" "torch" "torchvision" | Out-Null
    $suffix = if ($variant -eq "cpu") { "cpu" } else { "cu121" }
    $wheelDir = $env:TORCH_WHEEL_DIR
    $usedLocal = $false
    if ($wheelDir -and (Test-Path $wheelDir)) {
      $torchWhl = Join-Path $wheelDir "torch-2.5.1+${suffix}-cp311-cp311-win_amd64.whl"
      $visionWhl = Join-Path $wheelDir "torchvision-0.20.1+${suffix}-cp311-cp311-win_amd64.whl"
      if ((Test-Path $torchWhl) -and (Test-Path $visionWhl)) {
        Step "Install PyTorch from local wheels ($suffix)"
        & $venvPy "-m" "pip" "install" "--no-index" "--find-links" "$wheelDir" "$torchWhl" "$visionWhl"
        if ($LASTEXITCODE -ne 0) { throw "PyTorch wheel install failed (code $LASTEXITCODE)" }
        $usedLocal = $true
      } else {
        Info "Local wheels not found for variant=$suffix; fallback to official index"
      }
    }
    if (-not $usedLocal) {
      if ($variant -eq "cpu") {
        & $venvPy "-m" "pip" "install" "torch==2.5.1+cpu" "torchvision==0.20.1+cpu" "--index-url" "https://download.pytorch.org/whl/cpu"
      } else {
        & $venvPy "-m" "pip" "install" "torch==2.5.1+cu121" "torchvision==0.20.1+cu121" "--index-url" "https://download.pytorch.org/whl/cu121"
      }
      if ($LASTEXITCODE -ne 0) { throw "PyTorch install failed (code $LASTEXITCODE)" }
    }
    if ($variant -eq "cpu") {
      & $venvPy "-m" "pip" "install" "torchaudio==2.5.1+cpu" "--index-url" "https://download.pytorch.org/whl/cpu"
    } else {
      & $venvPy "-m" "pip" "install" "torchaudio==2.5.1+cu121" "--index-url" "https://download.pytorch.org/whl/cu121"
    }
    if ($LASTEXITCODE -ne 0) { throw "Torchaudio install failed (code $LASTEXITCODE)" }

    Step "Sanity-check PyTorch imports ($variant)"
    & $venvPy "-c" "import torch, torchvision, torchaudio; print('torch_ok', torch.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "PyTorch import check failed (code $LASTEXITCODE)" }

    Step "Install qwen-tts (no-deps)"
    & $venvPy "-m" "pip" "install" "qwen-tts" "--no-deps"
    if ($LASTEXITCODE -ne 0) { throw "qwen-tts install failed (code $LASTEXITCODE)" }
    Step "Sanity-check Qwen3-TTS imports ($variant)"
    & $venvPy "-c" "import qwen_tts, librosa, onnxruntime, sox; print('qwen_tts_ok')"
    if ($LASTEXITCODE -ne 0) { throw "Qwen3-TTS import check failed (code $LASTEXITCODE)" }

    & $venvPy "-m" "PyInstaller" "--clean" "--distpath" "dist" "backend.spec"
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller exited with code $LASTEXITCODE" }
  }
  catch {
    $pos = $_.InvocationInfo.PositionMessage
    if ($pos) {
      Fail ("Backend packaging failed: {0}`n{1}" -f $_.Exception.Message, $pos)
    } else {
      Fail "Backend packaging failed: $($_.Exception.Message)"
    }
  }
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
 

  Step "Ensure no running instances before Tauri build ($variant)"
  try {
    Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force
    Get-Process super-auto-cut-video -ErrorAction SilentlyContinue | Stop-Process -Force
  } catch { }

  $profileName = if ($TauriDebug) { "debug" } else { "release" }
  Step "Build Tauri app ($profileName) ($variant)"
  $variantTargetDir = if ($TauriDebug) {
    Join-Path $rootDir ("src-tauri\\target\\tauri_{0}_debug" -f $variant)
  } else {
    Join-Path $rootDir ("src-tauri\\target\\tauri_{0}" -f $variant)
  }
  Push-Location src-tauri
  try {
    $oldCargoTargetDir = $env:CARGO_TARGET_DIR
    $env:CARGO_TARGET_DIR = $variantTargetDir
    if ($TauriDebug) {
      cargo tauri build --debug
      if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (--debug) exited with code $LASTEXITCODE" }
    } else {
      Step "Build installers (NSIS + MSI) ($variant)"
      cargo tauri build --bundles nsis,msi
      if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (nsis,msi) exited with code $LASTEXITCODE" }
    }
  }
  catch {
    if (-not $TauriDebug) {
      Info "Installer build (NSIS+MSI) failed, retry NSIS only: $($_.Exception.Message)"
      try { cargo tauri build --bundles nsis }
      catch { Fail "Installer build failed: $($_.Exception.Message)" }
      if ($LASTEXITCODE -ne 0) { Fail "Cargo tauri build (nsis) exited with code $LASTEXITCODE" }
    } else {
      Fail "Tauri debug build failed: $($_.Exception.Message)"
    }
  }
  finally { $env:CARGO_TARGET_DIR = $oldCargoTargetDir ; Pop-Location }

  Step "Create portable ZIP and installers ($variant)"
  $releaseDir = Join-Path $variantTargetDir $profileName
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
  $zipVariantSuffix = if ($TauriDebug) { "${variant}_debug" } else { $variant }
  $zipName = "${safeProduct}_v${version}_${zipVariantSuffix}_portable.zip"
  $variantOut = Join-Path $artifactBase $zipVariantSuffix
  New-Item -ItemType Directory -Force $variantOut | Out-Null
  $zipPath = Join-Path $variantOut $zipName
  Invoke-CompressArchiveWithRetry (Join-Path $portableTemp '*') $zipPath
  Remove-Item $portableTemp -Recurse -Force

  $installersOut = Join-Path $variantOut 'installers'
  New-Item -ItemType Directory -Force $installersOut | Out-Null
  foreach ($pair in @(
    @{ dir = (Join-Path $releaseDir 'bundle\\nsis'); filter = '*.exe' },
    @{ dir = (Join-Path $releaseDir 'bundle\\msi');  filter = '*.msi' }
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
  Info "App: $(Join-Path $releaseDir 'super-auto-cut-video.exe')"
  Info "Backend: $(Join-Path $releaseDir 'resources\\superAutoCutVideoBackend.exe')"
  Info "Portable ZIP: $zipPath"
  Info "Installers dir: $installersOut"
}
