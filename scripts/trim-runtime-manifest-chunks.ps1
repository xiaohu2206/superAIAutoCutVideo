<#
.SYNOPSIS
  从 runtime-manifest.json 的 chunks 中移除指定分块（用于增量离线包：不带的 zip 就不要写在清单里）。

.PARAMETER ManifestPath
  runtime-manifest.json 路径

.PARAMETER Remove
  要移除的分块 name，可多次传入。例: -Remove runtime-base

.EXAMPLE
  .\scripts\trim-runtime-manifest-chunks.ps1 -ManifestPath ".\src-tauri\target\release\dist\runtime-chunks\runtime-manifest.json" -Remove runtime-base
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ManifestPath,
    [Parameter(Mandatory = $true)]
    [string[]]$Remove
)

$ErrorActionPreference = "Stop"
$ManifestPath = [System.IO.Path]::GetFullPath($ManifestPath)
if (-not (Test-Path -LiteralPath $ManifestPath)) {
    throw "文件不存在: $ManifestPath"
}

$removeSet = @{}
foreach ($r in $Remove) { $removeSet[$r.Trim().ToLowerInvariant()] = $true }

$raw = Get-Content -LiteralPath $ManifestPath -Raw -Encoding UTF8
$bom = [char]0xFEFF
if ($raw.StartsWith($bom)) { $raw = $raw.Substring(1) }
$j = $raw | ConvertFrom-Json
if (-not $j.chunks) { throw "清单中没有 chunks 字段" }

$newChunks = @()
foreach ($c in @($j.chunks)) {
    $n = [string]$c.name
    if (-not $removeSet.ContainsKey($n.ToLowerInvariant())) {
        $newChunks += $c
    }
}
$j.chunks = @($newChunks)

$out = $j | ConvertTo-Json -Depth 10
[System.IO.File]::WriteAllText($ManifestPath, $out, [System.Text.UTF8Encoding]::new($false))
Write-Host "Updated: $ManifestPath"
Write-Host "Remaining chunk names: $(($newChunks | ForEach-Object { $_.name }) -join ', ')"
