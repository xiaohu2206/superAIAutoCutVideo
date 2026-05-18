[CmdletBinding()]
param(
  [string[]]$InstallDir = @(),
  [int[]]$Ports = @(18000,18001,18002,18003,18004,18005,8000,8001,8002,8003,8004,8005)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Continue'

function Add-Line([string]$Text = "") {
  Add-Content -LiteralPath $script:ReportPath -Encoding UTF8 -Value $Text
}

function Add-Section([string]$Title) {
  Add-Line ""
  Add-Line ("==== {0} ====" -f $Title)
}

function Copy-IfExists([string]$Path, [string]$DestinationDir) {
  if (-not $Path) { return }
  if (Test-Path -LiteralPath $Path) {
    New-Item -ItemType Directory -Force -Path $DestinationDir | Out-Null
    try {
      Copy-Item -LiteralPath $Path -Destination $DestinationDir -Force -ErrorAction Stop
    } catch {
      Add-Line ("copy failed: {0} -> {1}: {2}" -f $Path, $DestinationDir, $_.Exception.Message)
    }
  }
}

function Add-CommandOutput([string]$Title, [scriptblock]$Block) {
  Add-Section $Title
  try {
    $out = & $Block 2>&1 | Out-String
    if ($out.Trim()) {
      Add-Line $out.TrimEnd()
    } else {
      Add-Line "(no output)"
    }
  } catch {
    Add-Line ("ERROR: {0}" -f $_.Exception.Message)
  }
}

function Get-ProcessInfos {
  $names = @("super-auto-cut-video.exe", "superAutoCutVideoBackend.exe", "msedgewebview2.exe")
  Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $names -contains $_.Name } |
    Select-Object Name, ProcessId, ParentProcessId, ExecutablePath, CommandLine
}

function Add-InstallRootCandidate([System.Collections.Generic.List[string]]$List, [string]$Path) {
  if (-not $Path) { return }
  try {
    $resolved = [System.IO.Path]::GetFullPath($Path)
    if (-not ($List | Where-Object { $_ -ieq $resolved })) {
      [void]$List.Add($resolved)
    }
  } catch {
    if (-not ($List | Where-Object { $_ -ieq $Path })) {
      [void]$List.Add($Path)
    }
  }
}

function Get-InstallRootCandidates {
  $list = [System.Collections.Generic.List[string]]::new()
  foreach ($dir in $InstallDir) {
    Add-InstallRootCandidate $list $dir
  }

  foreach ($p in (Get-ProcessInfos)) {
    if ($p.ExecutablePath) {
      $exeDir = Split-Path -Parent $p.ExecutablePath
      Add-InstallRootCandidate $list $exeDir

      $cur = $exeDir
      for ($i = 0; $i -lt 5; $i++) {
        if (-not $cur) { break }
        if (Test-Path -LiteralPath (Join-Path $cur "resources")) {
          Add-InstallRootCandidate $list $cur
        }
        $parent = Split-Path -Parent $cur
        if ($parent -eq $cur) { break }
        $cur = $parent
      }
    }
  }

  Add-InstallRootCandidate $list (Join-Path $env:LOCALAPPDATA "SuperAIAutoCutVideo")
  Add-InstallRootCandidate $list (Join-Path $env:LOCALAPPDATA "SuperAutoCutVideo")
  Add-InstallRootCandidate $list "D:\wordRuanJian\SuperAutoCutVideo"
  Add-InstallRootCandidate $list "D:\wordRuanJian\SuperAIAutoCutVideo"
  return $list
}

function Add-ResourceStatus([string]$Root) {
  Add-Section ("Install root: {0}" -f $Root)
  if (-not (Test-Path -LiteralPath $Root)) {
    Add-Line "root_exists=false"
    return
  }

  Add-Line "root_exists=true"
  $resources = Join-Path $Root "resources"
  Add-Line ("resources={0}" -f $resources)
  Add-Line ("resources_exists={0}" -f (Test-Path -LiteralPath $resources))

  $zip = Join-Path $resources "superAutoCutVideoBackend.zip"
  $extract = Join-Path $resources "superAutoCutVideoBackend"
  $exe1 = Join-Path $extract "superAutoCutVideoBackend.exe"
  $exe2 = Join-Path $extract "superAutoCutVideoBackend\superAutoCutVideoBackend.exe"

  foreach ($item in @($zip, $extract, $exe1, $exe2)) {
    if (Test-Path -LiteralPath $item) {
      $gi = Get-Item -LiteralPath $item -Force
      Add-Line ("exists: {0} | type={1} | size={2} | mtime={3}" -f $item, $gi.PSIsContainer, $(if ($gi.PSIsContainer) { "" } else { $gi.Length }), $gi.LastWriteTime)
    } else {
      Add-Line ("missing: {0}" -f $item)
    }
  }

  if (Test-Path -LiteralPath $resources) {
    Add-Line ""
    Add-Line "resources top-level:"
    Get-ChildItem -LiteralPath $resources -Force -ErrorAction SilentlyContinue |
      Select-Object Mode, Length, LastWriteTime, Name |
      Format-Table -AutoSize | Out-String | ForEach-Object { Add-Line $_.TrimEnd() }
  }

  if (Test-Path -LiteralPath $extract) {
    Add-Line ""
    Add-Line "backend extract top-level:"
    Get-ChildItem -LiteralPath $extract -Force -ErrorAction SilentlyContinue |
      Select-Object Mode, Length, LastWriteTime, Name |
      Format-Table -AutoSize | Out-String | ForEach-Object { Add-Line $_.TrimEnd() }
  }
}

function Probe-Port([int]$Port) {
  $base = "http://127.0.0.1:$Port"
  foreach ($path in @("/api/hello", "/api/server/info")) {
    $url = "$base$path"
    try {
      $resp = Invoke-WebRequest -Uri $url -UseBasicParsing -TimeoutSec 2
      Add-Line ("OK {0} status={1}" -f $url, $resp.StatusCode)
      $text = $resp.Content
      if ($text.Length -gt 1000) { $text = $text.Substring(0, 1000) }
      Add-Line $text
    } catch {
      Add-Line ("FAIL {0}: {1}" -f $url, $_.Exception.Message)
    }
  }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$diagRoot = Join-Path (Get-Location).Path ".sacv_diagnostics"
$outDir = Join-Path $diagRoot "startup_$stamp"
New-Item -ItemType Directory -Force -Path $outDir | Out-Null
$script:ReportPath = Join-Path $outDir "report.txt"
New-Item -ItemType File -Force -Path $script:ReportPath | Out-Null

Add-Section "Basic"
Add-Line ("time={0}" -f (Get-Date -Format o))
Add-Line ("user={0}\{1}" -f $env:USERDOMAIN, $env:USERNAME)
Add-Line ("computer={0}" -f $env:COMPUTERNAME)
Add-Line ("cwd={0}" -f (Get-Location).Path)
Add-Line ("powershell={0}" -f $PSVersionTable.PSVersion)
Add-Line ("localappdata={0}" -f $env:LOCALAPPDATA)
Add-Line ("appdata={0}" -f $env:APPDATA)
Add-Line ("temp={0}" -f $env:TEMP)
Add-Line ("dotnet_temp={0}" -f ([System.IO.Path]::GetTempPath()))

Add-CommandOutput "Git" {
  git rev-parse --short HEAD
  git status --short
}

Add-CommandOutput "Processes" {
  Get-ProcessInfos | Format-List
}

Add-CommandOutput "Ports" {
  netstat -ano | Select-String -Pattern "127\.0\.0\.1:(1800[0-9]|1801[0-9]|800[0-9]|801[0-9])"
}

Add-Section "HTTP probes"
foreach ($port in $Ports) {
  Probe-Port $port
}

Add-Section "Install resource status"
$roots = Get-InstallRootCandidates
foreach ($root in $roots) {
  Add-ResourceStatus $root
}

Add-Section "Copied logs"
$logsDir = Join-Path $outDir "logs"
$tempCandidates = [System.Collections.Generic.List[string]]::new()
foreach ($tempDir in @(
  $env:TEMP,
  [System.IO.Path]::GetTempPath(),
  (Join-Path $env:LOCALAPPDATA "Temp"),
  (Join-Path $env:WINDIR "Temp")
)) {
  if ($tempDir -and -not ($tempCandidates | Where-Object { $_ -ieq $tempDir })) {
    [void]$tempCandidates.Add($tempDir)
  }
}
foreach ($tempDir in $tempCandidates) {
  Copy-IfExists (Join-Path $tempDir "super_auto_cut_backend.log") $logsDir
  Copy-IfExists (Join-Path $tempDir "super_auto_cut_frontend.log") $logsDir
}
Copy-IfExists (Join-Path $env:APPDATA "com.superautocutvideo.app\logs\tauri.log") $logsDir
Copy-IfExists (Join-Path $env:LOCALAPPDATA "com.superautocutvideo.app\logs\tauri.log") $logsDir
Get-ChildItem -LiteralPath $logsDir -Force -ErrorAction SilentlyContinue |
  Select-Object Name, Length, LastWriteTime |
  Format-Table -AutoSize | Out-String | ForEach-Object { Add-Line $_.TrimEnd() }

$zipPath = Join-Path $diagRoot "startup_$stamp.zip"
if (Test-Path -LiteralPath $zipPath) {
  Remove-Item -LiteralPath $zipPath -Force
}
Compress-Archive -LiteralPath $outDir -DestinationPath $zipPath -Force

Write-Host "[OK] Diagnostics written:" -ForegroundColor Green
Write-Host "  $script:ReportPath"
Write-Host "  $zipPath"
