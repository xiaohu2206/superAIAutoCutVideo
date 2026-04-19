<#
.SYNOPSIS
  将「运行时分块」目录整理为可上传网盘的最小离线补丁文件夹。

.DESCRIPTION
  典型流程：
  1. 用 split-backend.ps1 打出分块，并传入上一版 runtime-manifest.json（-RefManifest），
     未变化的分块 zip 会被删除，仅保留需更新的 zip；清单仍含全部分块的 sha256。
  2. 运行本脚本，把 runtime-manifest.json、offline-bundle-manifest.json 与目录内仍存在的
     所有 .zip 复制到 StagingDir，便于整夹上传。

  客户端若已通过上一版安装与清单中「未随包上传」分块相同 SHA 的依赖，应用内选
  offline-bundle-manifest.json 后只会校验/解压本次目录里实际存在的 zip，无需大体积包。

.PARAMETER SourceDir
  含 runtime-manifest.json 的目录，默认同 split-backend 输出：src-tauri\target\release\dist\runtime-chunks

.PARAMETER StagingDir
  输出目录；默认在 SourceDir 下创建子目录 patch-for-offline-<时间戳>
#>
param(
    [string]$SourceDir = "",
    [string]$StagingDir = ""
)

$ErrorActionPreference = "Stop"

if (-not $SourceDir) {
    $scriptRootDir = $null
    if (Test-Path variable:PSScriptRoot) { $scriptRootDir = (Get-Variable PSScriptRoot -ValueOnly) }
    $ProjectRoot = if ($scriptRootDir) { Split-Path -Parent $scriptRootDir } else { (Get-Location).Path }
    $SourceDir = Join-Path $ProjectRoot "src-tauri\target\release\dist\runtime-chunks"
}

$SourceDir = [System.IO.Path]::GetFullPath($SourceDir)
if (-not (Test-Path -LiteralPath $SourceDir)) {
    throw "SourceDir 不存在: $SourceDir"
}

$manifestPath = Join-Path $SourceDir "runtime-manifest.json"
$bundlePath = Join-Path $SourceDir "offline-bundle-manifest.json"
if (-not (Test-Path -LiteralPath $manifestPath)) {
    throw "未找到 runtime-manifest.json: $manifestPath（请先运行 split-backend.ps1）"
}
if (-not (Test-Path -LiteralPath $bundlePath)) {
    throw "未找到 offline-bundle-manifest.json: $bundlePath"
}

if (-not $StagingDir) {
    $stamp = Get-Date -Format "yyyyMMdd-HHmmss"
    $StagingDir = Join-Path $SourceDir "patch-for-offline-$stamp"
}
$StagingDir = [System.IO.Path]::GetFullPath($StagingDir)
New-Item -ItemType Directory -Force -Path $StagingDir | Out-Null

Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $StagingDir "runtime-manifest.json") -Force
Copy-Item -LiteralPath $bundlePath -Destination (Join-Path $StagingDir "offline-bundle-manifest.json") -Force

$zips = Get-ChildItem -LiteralPath $SourceDir -Filter "*.zip" -File
$totalMb = 0.0
foreach ($z in $zips) {
    Copy-Item -LiteralPath $z.FullName -Destination (Join-Path $StagingDir $z.Name) -Force
    $totalMb += $z.Length / 1MB
}

Write-Host ""
Write-Host "已写入: $StagingDir"
Write-Host "  清单: runtime-manifest.json, offline-bundle-manifest.json"
Write-Host "  分块 zip 数量: $($zips.Count)（合计约 $([math]::Round($totalMb, 1)) MB）"
foreach ($z in $zips) {
    Write-Host "    - $($z.Name) ($([math]::Round($z.Length / 1MB, 1)) MB)"
}
Write-Host ""
Write-Host "可将该文件夹整体上传到网盘；用户仅下载此夹后，在应用「关于」里选择 offline-bundle-manifest.json。"
