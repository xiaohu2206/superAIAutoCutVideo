param(
  [switch]$FullBackend,
  [ValidateSet('cpu','gpu','all')]
  [string]$Variant = 'all',
  [switch]$GpuEmbedBackendZip,
  [switch]$RecreateBackendVenv,
  [switch]$TauriDebug,
  [switch]$SkipClean,
  [switch]$SkipPortable
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Step($msg) { Write-Host "[+] $msg" -ForegroundColor Cyan }
function Info($msg) { Write-Host "    $msg" }
function Fail($msg) { Write-Host "[x] $msg" -ForegroundColor Red ; exit 1 }

function Remove-DirWithRetry([string]$dirPath, [int]$retries = 6, [int]$delayMs = 700) {
  if (-not $dirPath) { return }
  if (-not (Test-Path $dirPath)) { return }
  for ($i = 1; $i -le $retries; $i++) {
    try {
      try {
        Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force
        Get-Process super-auto-cut-video -ErrorAction SilentlyContinue | Stop-Process -Force
      } catch { }

      try {
        $procs = Get-CimInstance Win32_Process -Filter "Name='python.exe'" -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
          $ep = $p.ExecutablePath
          $cl = $p.CommandLine
          $hit = $false
          if ($ep -and $ep.StartsWith($dirPath, [System.StringComparison]::OrdinalIgnoreCase)) { $hit = $true }
          elseif ($cl -and ($cl.IndexOf($dirPath, [System.StringComparison]::OrdinalIgnoreCase) -ge 0)) { $hit = $true }
          if ($hit) {
            try { Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue } catch { }
          }
        }
      } catch { }

      Microsoft.PowerShell.Management\Remove-Item $dirPath -Recurse -Force -ErrorAction SilentlyContinue
      if (-not (Test-Path $dirPath)) { return }
    } catch { }
    Start-Sleep -Milliseconds $delayMs
  }
  throw "failed to remove dir: $dirPath"
}

function Invoke-ProcessWithHeartbeat(
  [string]$filePath,
  [string[]]$argumentList,
  [string]$title,
  [int]$heartbeatSeconds = 30
) {
  $p = Start-Process -FilePath $filePath -ArgumentList $argumentList -WorkingDirectory (Get-Location).Path -NoNewWindow -PassThru
  $start = Get-Date
  $lastBeat = Get-Date
  while (-not $p.HasExited) {
    Start-Sleep -Seconds 2
    $p.Refresh()
    $now = Get-Date
    if ((New-TimeSpan -Start $lastBeat -End $now).TotalSeconds -ge $heartbeatSeconds) {
      $elapsed = New-TimeSpan -Start $start -End $now
      $cpuSec = 0
      $wsMb = 0
      try {
        $gp = Get-Process -Id $p.Id -ErrorAction SilentlyContinue
        if ($gp) {
          $cpuSec = [math]::Round($gp.CPU, 1)
          $wsMb = [math]::Round(($gp.WorkingSet64 / 1MB), 0)
        }
      } catch { }

      $baseZip = Join-Path (Get-Location).Path "build\\backend\\base_library.zip"
      $baseZipTime = ""
      if (Test-Path $baseZip) {
        try { $baseZipTime = (Get-Item $baseZip).LastWriteTime.ToString("HH:mm:ss") } catch { }
      }

      $distDir = Join-Path (Get-Location).Path "dist\\superAutoCutVideoBackend"
      $distCount = ""
      if (Test-Path $distDir) {
        try { $distCount = (Get-ChildItem -Path $distDir -Force -ErrorAction SilentlyContinue | Measure-Object).Count } catch { }
      }

      $suffix = ""
      if ($baseZipTime) { $suffix = $suffix + "; base_library.zip=" + $baseZipTime }
      if ($distCount -ne "") { $suffix = $suffix + "; dist_items=" + $distCount }
      $elapsedText = "{0:00}:{1:00}" -f [int]$elapsed.TotalMinutes, $elapsed.Seconds
      Info ("{0} running... elapsed={1} cpu={2}s ws={3}MB{4}" -f $title, $elapsedText, $cpuSec, $wsMb, $suffix)
      $lastBeat = $now
    }
  }
  $p.Refresh()
  $exitCode = 0
  try { $exitCode = $p.ExitCode } catch { $exitCode = 0 }
  if ($exitCode -eq $null) { $exitCode = 0 }
  return $exitCode
}

function Invoke-CompressArchiveWithRetry([string]$sourceDir, [string]$destinationPath, [int]$retries = 5, [int]$delayMs = 800) {
  if (-not (Test-Path $sourceDir)) { Fail "Zip source not found: $sourceDir" }
  try { Add-Type -AssemblyName System.IO.Compression } catch { }
  try { Add-Type -AssemblyName System.IO.Compression.FileSystem } catch { }
  for ($i = 1; $i -le $retries; $i++) {
    try {
      if (Test-Path $destinationPath) { Microsoft.PowerShell.Management\Remove-Item $destinationPath -Force -ErrorAction SilentlyContinue }
      $destParent = Split-Path -Parent $destinationPath
      if ($destParent -and (-not (Test-Path $destParent))) {
        New-Item -ItemType Directory -Force $destParent | Out-Null
      }
      $base = (Resolve-Path $sourceDir).Path
      $baseTrim = $base.TrimEnd('\')
      $baseLen = $baseTrim.Length + 1
      $fs = [System.IO.File]::Open($destinationPath, [System.IO.FileMode]::CreateNew)
      try {
        $zip = New-Object System.IO.Compression.ZipArchive($fs, [System.IO.Compression.ZipArchiveMode]::Create, $false)
        try {
          Get-ChildItem -Path $baseTrim -Recurse -File -Force | ForEach-Object {
            $full = $_.FullName
            $rel = $full.Substring($baseLen)
            [System.IO.Compression.ZipFileExtensions]::CreateEntryFromFile($zip, $full, $rel, [System.IO.Compression.CompressionLevel]::Optimal) | Out-Null
          }
        } finally {
          $zip.Dispose()
        }
      } finally {
        $fs.Dispose()
      }
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

function Ensure-FFmpegInTauriResources([string]$venvPy) {
  $baseRoot = $script:rootDir
  if (-not $baseRoot) { $baseRoot = (Get-Location).Path }
  $resDir = Join-Path $baseRoot "src-tauri\\resources"
  New-Item -ItemType Directory -Force $resDir | Out-Null
  $ffmpegOut = Join-Path $resDir "ffmpeg.exe"
  $ffprobeOut = Join-Path $resDir "ffprobe.exe"
  if ((Test-Path $ffmpegOut) -and (Test-Path $ffprobeOut)) { return }

  try {
    if ($venvPy -and (Test-Path $venvPy)) {
      $p = (& $venvPy "-c" "import imageio_ffmpeg; print(imageio_ffmpeg.get_ffmpeg_exe())" 2>$null | Select-Object -First 1)
      if ($p) {
        $pp = $p.Trim()
        if ($pp -and (Test-Path $pp)) {
          try {
            Microsoft.PowerShell.Management\Copy-Item -Force $pp $ffmpegOut
          } catch { }
          try {
            $ffprobeFromImageio = Join-Path (Split-Path -Parent $pp) "ffprobe.exe"
            if (-not (Test-Path $ffprobeOut) -and (Test-Path $ffprobeFromImageio)) {
              Microsoft.PowerShell.Management\Copy-Item -Force $ffprobeFromImageio $ffprobeOut
            }
          } catch { }
          if ((Test-Path $ffmpegOut) -and (Test-Path $ffprobeOut)) { return }
        }
      }
    }
  } catch { }

  try {
    $ffmpegExe = Get-ChildItem "C:\\ProgramData\\chocolatey\\lib\\ffmpeg*" -Recurse -Include ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    $ffprobeExe = Get-ChildItem "C:\\ProgramData\\chocolatey\\lib\\ffmpeg*" -Recurse -Include ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $ffmpegExe) {
      $cmd = Get-Command ffmpeg -ErrorAction SilentlyContinue
      if ($cmd) { $ffmpegExe = Get-Item $cmd.Path }
    }
    if (-not $ffprobeExe) {
      $cmdp = Get-Command ffprobe -ErrorAction SilentlyContinue
      if ($cmdp) { $ffprobeExe = Get-Item $cmdp.Path }
    }
    if ($ffmpegExe -and (-not (Test-Path $ffmpegOut))) {
      try { Microsoft.PowerShell.Management\Copy-Item -Force $ffmpegExe.FullName $ffmpegOut } catch { }
    }
    if ($ffprobeExe -and (-not (Test-Path $ffprobeOut))) {
      try { Microsoft.PowerShell.Management\Copy-Item -Force $ffprobeExe.FullName $ffprobeOut } catch { }
    }
    if (-not (Test-Path $ffmpegOut)) { Info "FFmpeg not found; please ensure ffmpeg.exe is available." }
    if (-not (Test-Path $ffprobeOut)) { Info "FFprobe not found; please ensure ffprobe.exe is available." }
  } catch { }
}

function Patch-GpuNsisInstaller([string]$installerNsiPath) {
  if (-not (Test-Path $installerNsiPath)) { Fail "NSIS script not found: $installerNsiPath" }
  $content = Get-Content -Raw -Encoding UTF8 $installerNsiPath
  $alreadyHasBackendCopy = $content -match [regex]::Escape("superAutoCutVideoBackend_gpu.zip")

  if ($content -notmatch '(?m)^!ifndef OUTFILE\s*$') {
    $content = [regex]::Replace(
      $content,
      '(?m)^!define OUTFILE "([^"]+)"\s*$',
      { param($m) ("!ifndef OUTFILE`r`n!define OUTFILE `"$($m.Groups[1].Value)`"`r`n!endif") }
    )
  }

  if (-not $alreadyHasBackendCopy) {
    $insertPattern = 'File /a "/oname=resources\\ffmpeg\.exe" "[^"]+ffmpeg\.exe"'
    if ($content -notmatch $insertPattern) {
      Fail "Failed to patch NSIS script (marker not found): $insertPattern"
    }

    $snippet = @"

    SetOverwrite on
    StrCpy `$R0 "`$EXEDIR\superAutoCutVideoBackend_gpu.zip"
    StrCpy `$R1 "superAutoCutVideoBackend_gpu.zip"
    `${IfNot} `${FileExists} "`$R0"
      StrCpy `$R0 "`$EXEDIR\superAutoCutVideoBackend.zip"
      StrCpy `$R1 "superAutoCutVideoBackend.zip"
    `${EndIf}

    `${If} `${FileExists} "`$R0"
      DetailPrint "Copy backend zip: `$R0"
      CopyFiles /SILENT "`$R0" "`$INSTDIR\resources"
      `${If} `$R1 != "superAutoCutVideoBackend.zip"
        Delete "`$INSTDIR\resources\superAutoCutVideoBackend.zip"
        Rename "`$INSTDIR\resources\`$R1" "`$INSTDIR\resources\superAutoCutVideoBackend.zip"
      `${EndIf}
    `${Else}
      `${If} `${Silent}
        Abort
      `${Else}
        MessageBox MB_ICONSTOP|MB_OK "GPU backend zip not found. Place superAutoCutVideoBackend_gpu.zip next to the installer and retry."
        Abort
      `${EndIf}
    `${EndIf}
"@

    $content = $content -replace $insertPattern, ('$&' + $snippet)
  }

  $uninstallMarker = 'Delete "$INSTDIR\resources\ffmpeg.exe"'
  if ($content -match [regex]::Escape($uninstallMarker) -and $content -notmatch [regex]::Escape('Delete "$INSTDIR\resources\superAutoCutVideoBackend.zip"')) {
    $content = $content -replace [regex]::Escape($uninstallMarker), ($uninstallMarker + "`r`n    Delete `"`$INSTDIR\resources\superAutoCutVideoBackend.zip`"")
  }

  Microsoft.PowerShell.Management\Set-Content -Encoding UTF8 -NoNewline -Path $installerNsiPath -Value $content
}

function Get-TauriMakensisPath() {
  $p = Join-Path $env:LOCALAPPDATA "tauri\\NSIS\\Bin\\makensis.exe"
  if (Test-Path $p) { return $p }
  $p = Join-Path $env:LOCALAPPDATA "tauri\\NSIS\\makensis.exe"
  if (Test-Path $p) { return $p }
  $p = Join-Path $env:LOCALAPPDATA "tauri\\NSIS\\makensisw.exe"
  if (Test-Path $p) { return $p }
  $cmd = Get-Command makensis -ErrorAction SilentlyContinue
  if ($cmd) { return $cmd.Path }
  Fail "NSIS makensis not found"
}

Step "Check project root"
if (-not (Test-Path frontend) -or -not (Test-Path src-tauri)) { Fail "Run from project root (must contain 'frontend' and 'src-tauri')" }

$repoRoot = (Get-Location).Path
$tempRoot = Join-Path $repoRoot '.sacv_build_tmp'
New-Item -ItemType Directory -Force $tempRoot | Out-Null
$buildTemp = Join-Path $tempRoot 'build_temp'
New-Item -ItemType Directory -Force $buildTemp | Out-Null
$pipCache = Join-Path $tempRoot 'pip_cache'
New-Item -ItemType Directory -Force $pipCache | Out-Null
$env:TEMP = $buildTemp
$env:TMP = $buildTemp
$env:PIP_CACHE_DIR = $pipCache

Step "Check toolchain"
foreach ($cmd in @('node','cargo')) {
  if (-not (Get-Command $cmd -ErrorAction SilentlyContinue)) { Fail "Command not found: $cmd" }
}
if (-not (Get-Command python -ErrorAction SilentlyContinue) -and -not (Get-Command py -ErrorAction SilentlyContinue)) {
  Fail "Command not found: python (or py)"
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

if ($SkipClean) {
  Step "Skip cleaning old artifacts"
} else {
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
      try { Microsoft.PowerShell.Management\Remove-Item $_ -Recurse -Force -ErrorAction Stop }
      catch { Info "Skip cleaning (locked or in use): $_" }
    }
  }
  try { if (Test-Path 'src-tauri\\resources\\superAutoCutVideoBackend.exe') { Microsoft.PowerShell.Management\Remove-Item 'src-tauri\\resources\\superAutoCutVideoBackend.exe' -Force -ErrorAction Stop } }
  catch { Info "Skip removing resource backend (locked): src-tauri\\resources\\superAutoCutVideoBackend.exe" }
  try { if (Test-Path 'src-tauri\\resources\\superAutoCutVideoBackend') { Microsoft.PowerShell.Management\Remove-Item 'src-tauri\\resources\\superAutoCutVideoBackend' -Recurse -Force -ErrorAction Stop } }
  catch { Info "Skip removing resource backend dir (locked): src-tauri\\resources\\superAutoCutVideoBackend" }
  try { if (Test-Path 'src-tauri\\resources\\superAutoCutVideoBackend.zip') { Microsoft.PowerShell.Management\Remove-Item 'src-tauri\\resources\\superAutoCutVideoBackend.zip' -Force -ErrorAction Stop } }
  catch { Info "Skip removing resource backend zip (locked): src-tauri\\resources\\superAutoCutVideoBackend.zip" }
}

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

$rootDir = $repoRoot
$variants = if ($Variant -eq 'all') { @('cpu','gpu') } else { @($Variant) }
$cfg = Microsoft.PowerShell.Management\Get-Content -Raw 'src-tauri\\tauri.conf.json' | ConvertFrom-Json
$productName = $cfg.productName
$version = $cfg.version
$artifactBase = if ($TauriDebug) {
  Join-Path $rootDir 'src-tauri\\target\\debug\\dist'
} else {
  Join-Path $rootDir 'src-tauri\\target\\release\\dist'
}
New-Item -ItemType Directory -Force $artifactBase | Out-Null

foreach ($variant in $variants) {
  Step "Package backend ($variant)"
  Push-Location backend
  try {
    $venvDir = Join-Path (Get-Location).Path (".venv_pack_{0}" -f $variant)
    if ($RecreateBackendVenv -and (Test-Path $venvDir)) {
      Step "Recreate backend venv ($variant)"
      Remove-DirWithRetry $venvDir
    }
    $venvCfg = Join-Path $venvDir 'pyvenv.cfg'
    $venvPy = Join-Path $venvDir 'Scripts\\python.exe'
    if (Test-Path $venvDir) {
      $venvHealthy = (Test-Path $venvCfg) -and (Test-Path $venvPy)
      if (-not $venvHealthy) {
        Step "Broken backend venv detected, recreate ($variant)"
        Remove-DirWithRetry $venvDir
        if (Test-Path $venvDir) { throw "failed to remove broken venv: $venvDir" }
      }
    }
    if (-not (Test-Path $venvDir)) {
      Step "Create backend venv ($variant)"
      & $pythonCmd $pythonArgsPrefix "-m" "venv" $venvDir
      if ($LASTEXITCODE -ne 0) { throw "venv creation failed (code $LASTEXITCODE)" }
    }
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

    Step "Configure pip mirror ($variant)"
    $env:PIP_INDEX_URL = "https://mirrors.aliyun.com/pypi/simple/"
    $env:SETUPTOOLS_USE_DISTUTILS = "stdlib"

    Step "Upgrade pip tooling ($variant)"
    $pipToolingOk = $false
    try {
      & $venvPy "-m" "pip" "show" "setuptools" | Out-Null
      if ($LASTEXITCODE -eq 0) {
        & $venvPy "-m" "pip" "show" "wheel" | Out-Null
        if ($LASTEXITCODE -eq 0) { $pipToolingOk = $true }
      }
    } catch { $pipToolingOk = $false }
    if (-not $pipToolingOk) {
      & $venvPy "-m" "pip" "install" "--disable-pip-version-check" "--no-input" "--timeout" "120" "--retries" "5" "-U" "pip" "setuptools" "wheel"
      if ($LASTEXITCODE -ne 0) { throw "pip bootstrap failed (code $LASTEXITCODE)" }
    }

    Step "Ensure build deps (PyInstaller) ($variant)"
    $pyinstallerOk = $false
    try {
      & $venvPy "-m" "pip" "show" "pyinstaller" | Out-Null
      if ($LASTEXITCODE -eq 0) { $pyinstallerOk = $true }
    } catch { $pyinstallerOk = $false }
    if (-not $pyinstallerOk) {
      & $venvPy "-m" "pip" "install" "--disable-pip-version-check" "--no-input" "--timeout" "120" "--retries" "5" "-U" "pyinstaller"
      if ($LASTEXITCODE -ne 0) { throw "pyinstaller install failed (code $LASTEXITCODE)" }
    }

    Step "Sanity-check Python packages (fix backports namespace) ($variant)"
    try { & $venvPy "-m" "pip" "show" "backports" | Out-Null } catch { }
    if ($?) { Step "Uninstall problematic 'backports' package ($variant)" ; & $venvPy "-m" "pip" "uninstall" "-y" "backports" | Out-Null }
    Step "Ensure backports.tarfile present ($variant)"
    $backportsTarOk = $false
    try {
      & $venvPy "-m" "pip" "show" "backports.tarfile" | Out-Null
      if ($LASTEXITCODE -eq 0) { $backportsTarOk = $true }
    } catch { $backportsTarOk = $false }
    if (-not $backportsTarOk) {
      & $venvPy "-m" "pip" "install" "--disable-pip-version-check" "--no-input" "--timeout" "120" "--retries" "5" "-U" "backports.tarfile"
    }

    if ($FullBackend -and (Test-Path requirements.txt)) {
      Step "Install full dependencies (requirements.txt)"
      $tmpFull = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Microsoft.PowerShell.Management\Get-Content requirements.txt -Encoding UTF8) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Microsoft.PowerShell.Management\Set-Content $tmpFull -Encoding UTF8
      & $venvPy "-m" "pip" "install" "-r" $tmpFull
    Microsoft.PowerShell.Management\Remove-Item $tmpFull -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.runtime.txt) {
      Step "Install runtime dependencies (requirements.runtime.txt)"
      $tmpRuntime = Join-Path $env:TEMP "requirements.runtime.filtered.txt"
      (Microsoft.PowerShell.Management\Get-Content requirements.runtime.txt -Encoding UTF8) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Microsoft.PowerShell.Management\Set-Content $tmpRuntime -Encoding UTF8
      & $venvPy "-m" "pip" "install" "-r" $tmpRuntime
      if ($LASTEXITCODE -ne 0) {
        Info "Runtime dependency install failed; retry once ($variant)"
        & $venvPy "-m" "pip" "install" "-r" $tmpRuntime
      }
      if ($LASTEXITCODE -ne 0) { throw "Runtime dependency install failed (code $LASTEXITCODE)" }
    Microsoft.PowerShell.Management\Remove-Item $tmpRuntime -Force -ErrorAction SilentlyContinue
    }
    elseif (Test-Path requirements.txt) {
      Step "Fallback to requirements.txt (runtime file missing)"
      $tmpFullFallback = Join-Path $env:TEMP "requirements.full.filtered.txt"
      (Microsoft.PowerShell.Management\Get-Content requirements.txt -Encoding UTF8) | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Microsoft.PowerShell.Management\Set-Content $tmpFullFallback -Encoding UTF8
      & $venvPy "-m" "pip" "install" "-r" $tmpFullFallback
    Microsoft.PowerShell.Management\Remove-Item $tmpFullFallback -Force -ErrorAction SilentlyContinue
    }
    else { Fail "No backend requirements file found" }

    if ($variant -ne "cpu") {
      Step "Ensure llama-cpp-python is CUDA-built (GGML_CUDA=on) ($variant)"
      & $venvPy "-m" "pip" "install" "--disable-pip-version-check" "--no-input" "--timeout" "120" "--retries" "5" "-U" "ninja"
      if ($LASTEXITCODE -ne 0) { throw "ninja install failed (code $LASTEXITCODE)" }

      $oldCmakeArgs = $env:CMAKE_ARGS
      $oldForceCmake = $env:FORCE_CMAKE
      $oldCmakeGen = $env:CMAKE_GENERATOR
      try {
        $env:CMAKE_ARGS = "-DGGML_CUDA=on"
        $env:FORCE_CMAKE = "1"
        $env:CMAKE_GENERATOR = "Ninja"
        
        # Load vcvars64.bat if available to ensure MSVC compiler is found
        $vcvars = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
        if (Test-Path $vcvars) {
            cmd.exe /c "call `"$vcvars`" && `"$venvPy`" -m pip install --force-reinstall --no-cache-dir --no-deps llama-cpp-python==0.3.16"
        } else {
            & $venvPy "-m" "pip" "install" "--force-reinstall" "--no-cache-dir" "--no-deps" "llama-cpp-python==0.3.16"
        }
        
        if ($LASTEXITCODE -ne 0) { throw "llama-cpp-python CUDA build install failed (code $LASTEXITCODE)" }

        $llamaDiag = & $venvPy "-c" "import llama_cpp; import llama_cpp.llama_cpp as ll; print('llama_cpp', getattr(llama_cpp, '__version__', None)); print('supports_gpu_offload', bool(ll.llama_supports_gpu_offload()))"
        if ($LASTEXITCODE -ne 0) { throw "llama-cpp-python import/diag failed (code $LASTEXITCODE)" }
        $llamaDiagText = ($llamaDiag | Out-String)
        if ($llamaDiagText -notmatch 'supports_gpu_offload\s+True') { throw "llama-cpp-python was installed but GPU offload is not enabled; expected GGML_CUDA=on" }
      } finally {
        $env:CMAKE_ARGS = $oldCmakeArgs
        $env:FORCE_CMAKE = $oldForceCmake
        $env:CMAKE_GENERATOR = $oldCmakeGen
      }
    }

    $suffix = if ($variant -eq "cpu") { "cpu" } else { "cu128" }
    $desiredTag = if ($variant -eq "cpu") { "+cpu" } else { "+cu128" }
    $torchAlreadyOk = $false
    try {
      $vers = & $venvPy "-c" "import torch, torchvision, torchaudio; print(torch.__version__); print(torchvision.__version__); print(torchaudio.__version__)" 2>$null
      if ($LASTEXITCODE -eq 0) {
        $versText = ($vers | Out-String)
        if ($versText -match [regex]::Escape($desiredTag)) {
          $torchAlreadyOk = $true
        }
      }
    } catch { }
    if ($torchAlreadyOk) {
      Step "PyTorch already installed ($desiredTag) ($variant) - skip reinstall"
    } else {
      & $venvPy "-m" "pip" "uninstall" "-y" "torchaudio" | Out-Null
      & $venvPy "-m" "pip" "uninstall" "-y" "torch" "torchvision" | Out-Null
    }
    $wheelDir = $env:TORCH_WHEEL_DIR
    $usedLocal = $false
    if (-not $torchAlreadyOk -and $wheelDir -and (Test-Path $wheelDir)) {
      $torchWhl = Join-Path $wheelDir "torch-2.7.1+${suffix}-cp311-cp311-win_amd64.whl"
      $visionWhl = Join-Path $wheelDir "torchvision-0.22.1+${suffix}-cp311-cp311-win_amd64.whl"
      if ((Test-Path $torchWhl) -and (Test-Path $visionWhl)) {
        Step "Install PyTorch from local wheels ($suffix)"
        & $venvPy "-m" "pip" "install" "--no-deps" "--no-index" "--find-links" "$wheelDir" "$torchWhl" "$visionWhl"
        if ($LASTEXITCODE -ne 0) { throw "PyTorch wheel install failed (code $LASTEXITCODE)" }
        $usedLocal = $true
      } else {
        Info "Local wheels not found for variant=$suffix; fallback to official index"
      }
    }
    if (-not $torchAlreadyOk -and -not $usedLocal) {
      if ($variant -eq "cpu") {
        & $venvPy "-m" "pip" "install" "torch==2.7.1+cpu" "torchvision==0.22.1+cpu" "--index-url" "https://download.pytorch.org/whl/cpu" "--extra-index-url" "$env:PIP_INDEX_URL"
      } else {
        & $venvPy "-m" "pip" "install" "torch==2.7.1+cu128" "torchvision==0.22.1+cu128" "--index-url" "https://download.pytorch.org/whl/cu128" "--extra-index-url" "$env:PIP_INDEX_URL"
        if ($LASTEXITCODE -ne 0) {
          Info "Official PyTorch index failed; fallback to Aliyun wheels (-f)"
          & $venvPy "-m" "pip" "install" "torch==2.7.1+cu128" "torchvision==0.22.1+cu128" "-f" "https://mirrors.aliyun.com/pytorch-wheels/cu128/" "--extra-index-url" "$env:PIP_INDEX_URL"
        }
      }
      if ($LASTEXITCODE -ne 0) { throw "PyTorch install failed (code $LASTEXITCODE)" }
    }
    if (-not $torchAlreadyOk) {
      if ($variant -eq "cpu") {
        & $venvPy "-m" "pip" "install" "torchaudio==2.7.1+cpu" "--index-url" "https://download.pytorch.org/whl/cpu" "--extra-index-url" "$env:PIP_INDEX_URL"
      } else {
        & $venvPy "-m" "pip" "install" "torchaudio==2.7.1+cu128" "--index-url" "https://download.pytorch.org/whl/cu128" "--extra-index-url" "$env:PIP_INDEX_URL"
        if ($LASTEXITCODE -ne 0) {
          Info "Official PyTorch index failed; fallback to Aliyun wheels (-f)"
          & $venvPy "-m" "pip" "install" "torchaudio==2.7.1+cu128" "-f" "https://mirrors.aliyun.com/pytorch-wheels/cu128/" "--extra-index-url" "$env:PIP_INDEX_URL"
        }
      }
      if ($LASTEXITCODE -ne 0) { throw "Torchaudio install failed (code $LASTEXITCODE)" }
    }

    Step "Sanity-check PyTorch imports ($variant)"
    & $venvPy "-c" "import torch, torchvision, torchaudio; print('torch_ok', torch.__version__)"
    if ($LASTEXITCODE -ne 0) { throw "PyTorch import check failed (code $LASTEXITCODE)" }

    Step "Install qwen-tts (no-deps)"
    & $venvPy "-m" "pip" "install" "qwen-tts" "--no-deps"
    if ($LASTEXITCODE -ne 0) { throw "qwen-tts install failed (code $LASTEXITCODE)" }
    Step "Sanity-check Qwen3-TTS imports ($variant)"
    & $venvPy "-c" "import qwen_tts, librosa, onnxruntime, sox; print('qwen_tts_ok')"
    if ($LASTEXITCODE -ne 0) { throw "Qwen3-TTS import check failed (code $LASTEXITCODE)" }

    if ($variant -eq "gpu") {
      Step "Install VoxCPM (no-deps) ($variant)"
      & $venvPy "-m" "pip" "install" "voxcpm" "--no-deps"
      if ($LASTEXITCODE -ne 0) { throw "voxcpm install failed (code $LASTEXITCODE)" }
      Step "Sanity-check VoxCPM imports ($variant)"
      & $venvPy "-c" "import voxcpm; from voxcpm import VoxCPM; from modules.vendor.voxcpm_tts import VoxCPMTTSModel; print('voxcpm_ok')"
      if ($LASTEXITCODE -ne 0) { throw "VoxCPM import check failed (code $LASTEXITCODE)" }
    }

    $distRoot = Join-Path (Get-Location).Path "dist\\superAutoCutVideoBackend"
    $distExe = Join-Path $distRoot "superAutoCutVideoBackend.exe"
    $distVariantMarker = Join-Path $distRoot ".build_variant"
    $shouldRebuildBackend = $true
    if (Test-Path $distExe) {
      $shouldRebuildBackend = $false
      try {
        if (Test-Path $distVariantMarker) {
          $builtVariant = (Get-Content $distVariantMarker -ErrorAction SilentlyContinue | Select-Object -First 1)
          if ($builtVariant -and ($builtVariant.Trim().ToLower() -ne $variant.Trim().ToLower())) {
            $shouldRebuildBackend = $true
          }
        } else {
          $shouldRebuildBackend = $true
        }
        $distTime = (Get-Item $distExe).LastWriteTime
        $watchPaths = @('main.py','backend.spec','routes','modules','services','serviceData')
        $latest = Get-ChildItem -Path $watchPaths -Recurse -File -ErrorAction SilentlyContinue |
          Where-Object { $_.Name -eq 'backend.spec' -or $_.Extension -eq '.py' -or $_.FullName -match '\\\\serviceData\\\\' } |
          Sort-Object LastWriteTime -Descending |
          Select-Object -First 1
        if ($latest -and $latest.LastWriteTime -gt $distTime) { $shouldRebuildBackend = $true }
      } catch {
        $shouldRebuildBackend = $true
      }
      if (-not $shouldRebuildBackend) { Step "Backend already built - skip PyInstaller ($variant)" }
    }
    if ($shouldRebuildBackend) {
      Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
      Start-Sleep -Milliseconds 300
      $oldWarn = $env:PYTHONWARNINGS
      $env:PYTHONWARNINGS = "ignore"
      $exitCode = Invoke-ProcessWithHeartbeat $venvPy @("-m","PyInstaller","--clean","--noconfirm","--distpath","dist","backend.spec") ("PyInstaller ($variant)") 30
      $env:PYTHONWARNINGS = $oldWarn
      if ($exitCode -ne 0) { throw "PyInstaller exited with code $exitCode" }
    }
    if (Test-Path $distExe) {
      try { Set-Content -Path $distVariantMarker -Value $variant -Encoding ASCII } catch { }
    }
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
  $tauriResDir = Join-Path $rootDir 'src-tauri\\resources'
  $backendDistDir = Join-Path $rootDir 'backend\\dist\\superAutoCutVideoBackend'
  $backendResDir = Join-Path $tauriResDir 'superAutoCutVideoBackend'
  $backendResZip = Join-Path $tauriResDir 'superAutoCutVideoBackend.zip'
  New-Item -ItemType Directory -Force $tauriResDir | Out-Null
  if (Test-Path $backendResDir) {
    Microsoft.PowerShell.Management\Remove-Item $backendResDir -Recurse -Force -ErrorAction SilentlyContinue
  }
  if (Test-Path $backendResZip) {
    Microsoft.PowerShell.Management\Remove-Item $backendResZip -Force -ErrorAction SilentlyContinue
  }
  Microsoft.PowerShell.Management\Copy-Item -Recurse -Force $backendDistDir $backendResDir
  Invoke-CompressArchiveWithRetry $backendDistDir $backendResZip
  try { Ensure-FFmpegInTauriResources $venvPy } catch { Info "Skip FFmpeg prepare: $($_.Exception.Message)" }
 

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
      cargo tauri build --debug --config tauri.bundle.conf.json
      if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (--debug) exited with code $LASTEXITCODE" }
    } else {
      if ($variant -eq 'gpu') {
        if ($GpuEmbedBackendZip) {
          Step "Build installer (NSIS, embed backend zip) ($variant)"
          cargo tauri build --bundles nsis --config tauri.gpu.embed.nsis.conf.json
        } else {
          Step "Build installer (NSIS) ($variant)"
          cargo tauri build --bundles nsis --config tauri.gpu.nsis.conf.json
        }
        if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (nsis) exited with code $LASTEXITCODE" }
      } else {
        Step "Build installers (NSIS + MSI) ($variant)"
        cargo tauri build --bundles nsis,msi --config tauri.bundle.conf.json
        if ($LASTEXITCODE -ne 0) { throw "Cargo tauri build (nsis,msi) exited with code $LASTEXITCODE" }
      }
    }
  }
  catch {
    if (-not $TauriDebug) {
      Info "Installer build (NSIS+MSI) failed, retry NSIS only: $($_.Exception.Message)"
      try { cargo tauri build --bundles nsis --config tauri.bundle.conf.json }
      catch { Fail "Installer build failed: $($_.Exception.Message)" }
      if ($LASTEXITCODE -ne 0) { Fail "Cargo tauri build (nsis) exited with code $LASTEXITCODE" }
    } else {
      Fail "Tauri debug build failed: $($_.Exception.Message)"
    }
  }
  finally { $env:CARGO_TARGET_DIR = $oldCargoTargetDir ; Pop-Location }

  if (-not $TauriDebug -and $variant -eq 'gpu' -and -not $GpuEmbedBackendZip) {
    Step "Patch NSIS installer (GPU offline zip copy)"
    $installerNsi = Join-Path $variantTargetDir "release\\nsis\\x64\\installer.nsi"
    Patch-GpuNsisInstaller $installerNsi
    $makensis = Get-TauriMakensisPath
    $bundleNsisDir = Join-Path $variantTargetDir "release\\bundle\\nsis"
    $bundleExe = $null
    if (Test-Path $bundleNsisDir) {
      try { $bundleExe = Get-ChildItem -Path $bundleNsisDir -Filter '*.exe' -ErrorAction SilentlyContinue | Select-Object -First 1 } catch { }
    }
    if ($bundleExe -and (Test-Path $bundleExe.FullName)) {
      $outArg = "/DOUTFILE=$($bundleExe.FullName)"
      & $makensis $outArg $installerNsi | Out-Null
      if ($LASTEXITCODE -ne 0) {
        $tmpOut = Join-Path $env:TEMP ("nsis_{0}_{1}.exe" -f $variant, ([guid]::NewGuid().ToString("N")))
        $tmpArg = "/DOUTFILE=$tmpOut"
        & $makensis $tmpArg $installerNsi | Out-Null
        if ($LASTEXITCODE -ne 0) { Fail "makensis failed with exit code $LASTEXITCODE" }
        try {
          Microsoft.PowerShell.Management\Copy-Item -Force $tmpOut $bundleExe.FullName
        } finally {
          Microsoft.PowerShell.Management\Remove-Item $tmpOut -Force -ErrorAction SilentlyContinue
        }
      }
    } else {
      & $makensis $installerNsi | Out-Null
    }
    if ($LASTEXITCODE -ne 0) { Fail "makensis failed with exit code $LASTEXITCODE" }
  }

  Step "Create portable ZIP and installers ($variant)"
  $releaseDir = Join-Path $variantTargetDir $profileName
  $zipVariantSuffix = if ($TauriDebug) { "${variant}_debug" } else { $variant }
  $variantOut = Join-Path $artifactBase $zipVariantSuffix
  New-Item -ItemType Directory -Force $variantOut | Out-Null

  $zipPath = ""
  if (-not $SkipPortable) {
    $portableTemp = Join-Path $releaseDir 'portable_temp'
    if (Test-Path $portableTemp) { Microsoft.PowerShell.Management\Remove-Item $portableTemp -Recurse -Force }
    New-Item -ItemType Directory -Force $portableTemp | Out-Null
    Step "Ensure no running instances before zip ($variant)"
    try {
      Get-Process superAutoCutVideoBackend -ErrorAction SilentlyContinue | Stop-Process -Force
      Get-Process super-auto-cut-video -ErrorAction SilentlyContinue | Stop-Process -Force
    } catch { }
    Microsoft.PowerShell.Management\Copy-Item -Force (Join-Path $releaseDir 'super-auto-cut-video.exe') $portableTemp
    New-Item -ItemType Directory -Force (Join-Path $portableTemp 'resources') | Out-Null
    $backendZipInRelease = Join-Path $releaseDir 'resources\\superAutoCutVideoBackend.zip'
    $backendZipForPortable = if (Test-Path $backendZipInRelease) { $backendZipInRelease } else { Join-Path $rootDir 'src-tauri\\resources\\superAutoCutVideoBackend.zip' }
    Microsoft.PowerShell.Management\Copy-Item -Force $backendZipForPortable (Join-Path $portableTemp 'resources\\superAutoCutVideoBackend.zip')
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
    $zipName = "${safeProduct}_v${version}_${zipVariantSuffix}_portable.zip"
    $zipPath = Join-Path $variantOut $zipName
    Invoke-CompressArchiveWithRetry $portableTemp $zipPath
    Microsoft.PowerShell.Management\Remove-Item $portableTemp -Recurse -Force
  }

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
        try {
          Microsoft.PowerShell.Management\Copy-Item -Force $_.FullName $dst
        } catch {
          $stamp = (Get-Date -Format 'yyyyMMddHHmmss')
          $dst2 = Join-Path $installersOut ("${base}_${variant}_${stamp}${ext}")
          Microsoft.PowerShell.Management\Copy-Item -Force $_.FullName $dst2
        }
      }
    }
  }

  if (-not $TauriDebug -and $variant -eq 'gpu' -and -not $GpuEmbedBackendZip) {
    $srcZip = Join-Path $rootDir 'src-tauri\\resources\\superAutoCutVideoBackend.zip'
    if (Test-Path $srcZip) {
      $dstZip = Join-Path $installersOut 'superAutoCutVideoBackend_gpu.zip'
      try {
        Microsoft.PowerShell.Management\Copy-Item -Force $srcZip $dstZip
      } catch {
        try {
          if (Test-Path $dstZip) { Microsoft.PowerShell.Management\Remove-Item $dstZip -Force -ErrorAction SilentlyContinue }
          Microsoft.PowerShell.Management\Move-Item -Force $srcZip $dstZip
        } catch {
          throw
        }
      }
    }
  }

  Step "Build completed ($variant)"
  Info "App: $(Join-Path $releaseDir 'super-auto-cut-video.exe')"
  Info "Backend ZIP: $(Join-Path $releaseDir 'resources\\superAutoCutVideoBackend.zip')"
  if ($zipPath) { Info "Portable ZIP: $zipPath" }
  Info "Installers dir: $installersOut"
}
