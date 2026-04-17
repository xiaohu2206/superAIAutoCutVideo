<#
.SYNOPSIS
  将 PyInstaller --onedir 产物拆分为 runtime-base + app-backend 两个分块 zip，
  并生成 runtime-manifest.json。

.DESCRIPTION
  用于生成"运行时分块更新"所需的产物。执行后会在 <OutputDir> 下生成：
    runtime-base-<ver>.zip      大体积稳定依赖（torch / CUDA / Python runtime …）
    app-backend-<ver>.zip       后端应用代码（exe + 常变模块）
    runtime-manifest.json       远端清单，可直接托管到 CDN / GitHub Release

.PARAMETER BackendDir
  PyInstaller --onedir 产出目录，默认 backend\dist\superAutoCutVideoBackend

.PARAMETER OutputDir
  分块产物输出目录，默认 src-tauri\target\release\dist\runtime-chunks

.PARAMETER Version
  版本号，默认读取 src-tauri\tauri.conf.json 中的 version

.PARAMETER Variant
  cpu 或 gpu，默认 cpu

.PARAMETER BaseUrl
  分块 zip 下载地址前缀（用于写入 manifest 的 url 字段），
  例如 https://github.com/user/repo/releases/download/v1.2.6/
  默认为空字符串（需发布前手动替换）

.PARAMETER ProjectRoot
  仓库根目录。若为空则从脚本路径推导；由 build.ps1 调用时建议显式传入，避免在 StrictMode 下 $PSScriptRoot 为空时 Split-Path 失败。

.EXAMPLE
  .\scripts\split-backend.ps1 -Variant gpu -Version 1.2.6 -BaseUrl "https://example.com/releases/v1.2.6/"
#>
param(
    [string]$BackendDir = "",
    [string]$OutputDir  = "",
    [string]$Version    = "",
    [string]$Variant    = "cpu",
    [string]$BaseUrl    = "",
    [string]$ProjectRoot = ""
)

$ErrorActionPreference = "Stop"

if (-not $ProjectRoot) {
    $scriptRootDir = $null
    if (Test-Path variable:PSScriptRoot) {
        $scriptRootDir = (Get-Variable PSScriptRoot -ValueOnly)
    }
    if ($scriptRootDir) {
        $ProjectRoot = Split-Path -Parent $scriptRootDir
    }
    if (-not $ProjectRoot -and $MyInvocation.MyCommand.Path) {
        $ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
    }
    if (-not $ProjectRoot) {
        $ProjectRoot = (Get-Location).Path
    }
}

# ── 默认值 ────────────────────────────────────────────────────────

if (-not $BackendDir) {
    $BackendDir = Join-Path $ProjectRoot "backend\dist\superAutoCutVideoBackend"
}
if (-not $OutputDir) {
    $OutputDir = Join-Path $ProjectRoot "src-tauri\target\release\dist\runtime-chunks"
}
if (-not $Version) {
    $confPath = Join-Path $ProjectRoot "src-tauri\tauri.conf.json"
    if (Test-Path $confPath) {
        $conf = Get-Content -Raw $confPath | ConvertFrom-Json
        $Version = $conf.version
    }
    if (-not $Version) { $Version = "0.0.0" }
}

Write-Host "========================================"
Write-Host "  Split Backend -> Runtime Chunks"
Write-Host "  BackendDir : $BackendDir"
Write-Host "  OutputDir  : $OutputDir"
Write-Host "  Version    : $Version"
Write-Host "  Variant    : $Variant"
Write-Host "========================================"

if (-not (Test-Path $BackendDir)) {
    throw "后端产出目录不存在: $BackendDir"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# ── 稳定依赖目录/文件模式（归入 runtime-base）───────────────────

$basePatterns = @(
    "torch",
    "torchvision",
    "torchaudio",
    "nvidia",
    "cublas",
    "cuda",
    "cudnn",
    "cufft",
    "curand",
    "cusolver",
    "cusparse",
    "nccl",
    "triton",
    "numpy",
    "numpy.libs",
    "cv2",
    "PIL",
    "scipy",
    "sklearn",
    "skimage",
    "matplotlib",
    "pandas",
    "h5py",
    "onnx",
    "onnxruntime",
    "transformers",
    "tokenizers",
    "safetensors",
    "sentencepiece",
    "soundfile",
    "librosa",
    "numba",
    "llvmlite"
)

$baseDllPatterns = @(
    "python*.dll",
    "vcruntime*.dll",
    "msvcp*.dll",
    "api-ms-win-*.dll",
    "ucrtbase*.dll",
    "concrt*.dll",
    "libcrypto*.dll",
    "libssl*.dll",
    "libffi*.dll",
    "sqlite3.dll"
)

# ── 收集文件 ──────────────────────────────────────────────────────

$internalDir = Join-Path $BackendDir "_internal"
$hasInternal = Test-Path $internalDir

function Is-BaseItem {
    param([string]$RelPath)
    $parts = $RelPath -split '[/\\]'
    if ($parts.Count -ge 2 -and $parts[0] -eq "_internal") {
        $second = $parts[1]
        foreach ($pat in $basePatterns) {
            if ($second -eq $pat -or $second -like "$pat-*" -or $second -like "${pat}.*") {
                return $true
            }
        }
        foreach ($pat in $baseDllPatterns) {
            if ($second -like $pat) {
                return $true
            }
        }
        if ($second -eq "base_library.zip") { return $true }
    }
    return $false
}

$allFiles = Get-ChildItem -Path $BackendDir -Recurse -File
$baseFiles = @()
$appFiles  = @()

foreach ($f in $allFiles) {
    $rel = $f.FullName.Substring($BackendDir.Length).TrimStart('\','/')
    if (Is-BaseItem $rel) {
        $baseFiles += $rel
    } else {
        $appFiles += $rel
    }
}

Write-Host "`nruntime-base: $($baseFiles.Count) files"
Write-Host "app-backend : $($appFiles.Count) files"

# ── 压缩 ──────────────────────────────────────────────────────────

function New-ChunkZip {
    param(
        [string]$ZipPath,
        [string]$RootDir,
        [string[]]$RelFiles
    )
    if (Test-Path $ZipPath) { Remove-Item -Force $ZipPath }

    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::Open($ZipPath, 'Create')
    try {
        foreach ($rel in $RelFiles) {
            $full = Join-Path $RootDir $rel
            if (Test-Path $full) {
                $entry = $zip.CreateEntry($rel.Replace('\', '/'), [System.IO.Compression.CompressionLevel]::Optimal)
                $stream = $entry.Open()
                try {
                    $bytes = [System.IO.File]::ReadAllBytes($full)
                    $stream.Write($bytes, 0, $bytes.Length)
                } finally {
                    $stream.Close()
                }
            }
        }
    } finally {
        $zip.Dispose()
    }
}

$baseZipName = "runtime-base-$Version.zip"
$appZipName  = "app-backend-$Version.zip"
$baseZipPath = Join-Path $OutputDir $baseZipName
$appZipPath  = Join-Path $OutputDir $appZipName

Write-Host "`nCreating $baseZipName ..."
New-ChunkZip -ZipPath $baseZipPath -RootDir $BackendDir -RelFiles $baseFiles

Write-Host "Creating $appZipName ..."
New-ChunkZip -ZipPath $appZipPath -RootDir $BackendDir -RelFiles $appFiles

# ── SHA256 ────────────────────────────────────────────────────────

function Get-FileSHA256 {
    param([string]$Path)
    $hasher = [System.Security.Cryptography.SHA256]::Create()
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $hash = $hasher.ComputeHash($stream)
        return ($hash | ForEach-Object { $_.ToString("x2") }) -join ''
    } finally {
        $stream.Close()
        $hasher.Dispose()
    }
}

$baseSha = Get-FileSHA256 $baseZipPath
$appSha  = Get-FileSHA256 $appZipPath
$baseSize = (Get-Item $baseZipPath).Length
$appSize  = (Get-Item $appZipPath).Length

Write-Host "`nruntime-base : $baseSha ($([math]::Round($baseSize/1MB,1)) MB)"
Write-Host "app-backend  : $appSha ($([math]::Round($appSize/1MB,1)) MB)"

# ── 生成 manifest ────────────────────────────────────────────────

$manifest = @{
    schema_version   = 1
    runtime_version  = $Version
    variant          = $Variant
    min_app_version  = $null
    created_at       = (Get-Date -Format "yyyy-MM-ddTHH:mm:ssZ")
    chunks           = @(
        @{
            name        = "runtime-base"
            version     = $Version
            sha256      = $baseSha
            size        = $baseSize
            url         = "${BaseUrl}${baseZipName}"
            description = "Python runtime + heavy dependencies (torch, CUDA, numpy …)"
        },
        @{
            name        = "app-backend"
            version     = $Version
            sha256      = $appSha
            size        = $appSize
            url         = "${BaseUrl}${appZipName}"
            description = "Backend application code and lightweight modules"
        }
    )
}

$manifestPath = Join-Path $OutputDir "runtime-manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $manifestPath

Write-Host "`nManifest written to: $manifestPath"
Write-Host "`n=== Done ==="
Write-Host "Output files:"
Write-Host "  $baseZipPath"
Write-Host "  $appZipPath"
Write-Host "  $manifestPath"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Upload the 3 files to your CDN / GitHub Release"
Write-Host "  2. Set SACV_RUNTIME_MANIFEST_URL env var to the manifest URL"
Write-Host "  3. Fill pubkey & endpoints in tauri.conf.json for shell updater"
