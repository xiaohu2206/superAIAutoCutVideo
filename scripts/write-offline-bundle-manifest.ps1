<#
.SYNOPSIS
  根据已打包目录中的实际文件生成 offline-bundle-manifest.json（不复制、不下载任何包）。

.DESCRIPTION
  - 始终写入 backend_runtime_manifest，指向同目录下的 runtime-manifest.json（文件名可改）。
  - shell_installer：仅当目录里存在要分发的壳安装包时才写入；若只做后端分块增量、不更新桌面端，目录里无 exe 则自动省略该字段（避免离线更新报「未找到壳安装包」）。
  - 分块 zip 由 runtime-manifest + 本机 runtime_state 在应用内决定「需更新哪些」；本脚本不把「无需更新的分块」写进总清单（总清单本身也不列分块，仅指向后端清单）。

.PARAMETER BundleDir
  产物目录（与 runtime-manifest.json 同级），默认：src-tauri\target\release\dist\runtime-chunks

.PARAMETER RuntimeManifestFile
  后端清单文件名，默认 runtime-manifest.json

.PARAMETER ShellInstaller
  显式指定壳安装包文件名（须在 BundleDir 内存在）。不指定时按规则自动判断是否写入 shell_installer。

.PARAMETER OmitShellInstaller
  强制不写入 shell_installer（即使目录里有 exe）

.EXAMPLE
  .\scripts\write-offline-bundle-manifest.ps1 -BundleDir "D:\release\v1.2.8"
.EXAMPLE
  # 仅上传了分块 zip + 清单、未放 NSIS 时
  .\scripts\write-offline-bundle-manifest.ps1 -OmitShellInstaller
#>
param(
    [string]$BundleDir = "",
    [string]$RuntimeManifestFile = "runtime-manifest.json",
    [string]$ShellInstaller = "",
    [switch]$OmitShellInstaller
)

$ErrorActionPreference = "Stop"

if (-not $BundleDir) {
    $scriptRootDir = $null
    if (Test-Path variable:PSScriptRoot) { $scriptRootDir = Get-Variable PSScriptRoot -ValueOnly }
    $proj = if ($scriptRootDir) { Split-Path -Parent $scriptRootDir } else { (Get-Location).Path }
    $BundleDir = Join-Path $proj "src-tauri\target\release\dist\runtime-chunks"
}

$BundleDir = [System.IO.Path]::GetFullPath($BundleDir)
if (-not (Test-Path -LiteralPath $BundleDir -PathType Container)) {
    throw "目录不存在: $BundleDir"
}

$manifestPath = Join-Path $BundleDir $RuntimeManifestFile
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    throw "未找到后端清单: $manifestPath"
}

$outPath = Join-Path $BundleDir "offline-bundle-manifest.json"

$shellName = $null
if (-not $OmitShellInstaller) {
    if ($ShellInstaller) {
        $candidate = Join-Path $BundleDir $ShellInstaller
        if (-not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
            throw "指定的壳安装包不存在: $candidate"
        }
        $shellName = $ShellInstaller
    } else {
        $exes = @(Get-ChildItem -LiteralPath $BundleDir -File -Filter "*.exe" -ErrorAction SilentlyContinue)
        if ($exes.Count -eq 1) {
            $shellName = $exes[0].Name
        } elseif ($exes.Count -gt 1) {
            $setupOnes = @($exes | Where-Object { $_.Name -like "*setup*" -or $_.Name -like "*Setup*" })
            if ($setupOnes.Count -eq 1) {
                $shellName = $setupOnes[0].Name
            } else {
                throw "目录内有多个 .exe，请用 -ShellInstaller 指定壳安装包文件名，或使用 -OmitShellInstaller。文件: $($exes.Name -join ', ')"
            }
        }
    }
}

$o = [PSCustomObject]@{
    schema_version           = 1
    backend_runtime_manifest = $RuntimeManifestFile
}
if ($shellName) {
    $o | Add-Member -NotePropertyName shell_installer -NotePropertyValue $shellName
}

$json = $o | ConvertTo-Json -Compress
Set-Content -LiteralPath $outPath -Value $json -Encoding UTF8

# Console may mojibake Chinese/em-dash; keep status lines ASCII-only.
Write-Host "Written: $outPath"
if ($shellName) {
    Write-Host "  shell_installer: $shellName"
} else {
    Write-Host "  shell_installer: (not set; no single .exe in folder, or -OmitShellInstaller)"
}
