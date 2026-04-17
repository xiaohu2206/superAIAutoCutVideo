<#
.SYNOPSIS
  将 PyInstaller --onedir 产物拆分为三个分块 zip，并生成 runtime-manifest.json。

.DESCRIPTION
  用于生成"运行时分块更新"所需的产物。执行后会在 <OutputDir> 下生成：
    runtime-base-<ver>.zip      大体积稳定依赖（torch / CUDA / 科学计算 / ML …）
    app-deps-<ver>.zip          Web/API 与常用三方库（FastAPI / uvicorn 等），变更少于业务代码
    app-backend-<ver>.zip       exe、serviceData、业务 modules 等最常变部分
    runtime-manifest.json       远端清单（chunks 含上述三项），可直接托管到 CDN / GitHub Release
    offline-bundle-manifest.json  离线更新总清单（指向 runtime-manifest.json；完整打包时由 build.ps1 补全壳安装包文件名）

  仅改业务代码且依赖版本未变时，通常只有 app-backend 的 sha256 变化，用户只需下载该分块。

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

.PARAMETER RefManifest
  上一版（或上次发布）的 runtime-manifest.json 路径。若某分块 zip 的 SHA256 与该文件中同名分块一致，则从 OutputDir 中删除该 zip，减少网盘待上传体积。
  runtime-manifest.json 仍会包含全部分块元数据；仅本地未变更的 chunk 用户无需再下载。
  也可通过环境变量 SACV_REF_RUNTIME_MANIFEST 指定。

.EXAMPLE
  .\scripts\split-backend.ps1 -Variant gpu -Version 1.2.6 -BaseUrl "https://example.com/releases/v1.2.6/"
.EXAMPLE
  .\scripts\split-backend.ps1 -Variant gpu -RefManifest "D:\releases\v1.2.5\runtime-manifest.json"
#>
param(
    [string]$BackendDir = "",
    [string]$OutputDir  = "",
    [string]$Version    = "",
    [string]$Variant    = "cpu",
    [string]$BaseUrl    = "",
    [string]$ProjectRoot = "",
    [string]$RefManifest = ""
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

if (-not $RefManifest -and $env:SACV_REF_RUNTIME_MANIFEST) {
    $RefManifest = $env:SACV_REF_RUNTIME_MANIFEST
}

Write-Host "========================================"
Write-Host "  Split Backend -> Runtime Chunks"
Write-Host "  BackendDir : $BackendDir"
Write-Host "  OutputDir  : $OutputDir"
Write-Host "  Version    : $Version"
Write-Host "  Variant    : $Variant"
if ($RefManifest) {
    Write-Host "  RefManifest: $RefManifest"
}
Write-Host "========================================"

if (-not (Test-Path $BackendDir)) {
    throw "后端产出目录不存在: $BackendDir"
}

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null

# ── 稳定依赖目录/文件模式（归入 runtime-base）───────────────────
# 规则：仅匹配 _internal 下「第二层」目录名（与 PyInstaller onedir 一致）。
# 业务代码、FastAPI/uvicorn 等小步迭代依赖留在 app-backend，避免 bump 依赖就整包重下 runtime-base。
# 若某目录仍落在 app-backend 且体积大，可在此按包名追加（或见下方 *.libs 通配）。

$basePatterns = @(
    # PyTorch / CUDA
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
    # 数值 / 图像 / 科学计算
    "numpy",
    "cv2",
    "PIL",
    "scipy",
    "sklearn",
    "skimage",
    "matplotlib",
    "pandas",
    "h5py",
    "sympy",
    "mpmath",
    "networkx",
    "regex",
    # 推理 / ONNX
    "onnx",
    "onnxruntime",
    # Hugging Face / 大模型生态
    "transformers",
    "tokenizers",
    "safetensors",
    "sentencepiece",
    "huggingface_hub",
    "accelerate",
    "bitsandbytes",
    "einops",
    "timm",
    "xformers",
    # 语音 / ASR / TTS / 本地 LLM（backend.spec 中常见大包）
    "soundfile",
    "librosa",
    "numba",
    "llvmlite",
    "funasr",
    "modelscope",
    "whisper",
    "llama_cpp",
    "voxcpm",
    "tiktoken",
    "dashscope",
    "qwen_tts",
    "ctranslate2",
    "faster_whisper",
    "openai",
    "av",
    "tensorflow",
    # 其他重型原生扩展
    "pydantic_core",
    "protobuf",
    "google",
    "setuptools",
    "pkg_resources",
    "cryptography",
    "imageio",
    "ffmpy",
    "lazy_loader",
    "filelock",
    "fsspec",
    "yaml",
    "_yaml"
)

# ── 中等体积、变更相对少的 pip 包（归入 app-deps，从原 app-backend 剥离）────────
# 匹配规则与 base 相同：仅 _internal 下第二层目录名。*.libs 亦按 stem 匹配。
# 未出现在此列表的 _internal 目录仍归 app-backend（与 exe / serviceData 等同为「常变层」）。

$midPatterns = @(
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
    "anyio",
    "sniffio",
    "h11",
    "httptools",
    "websockets",
    "wsproto",
    "httpx",
    "httpcore",
    "certifi",
    "charset_normalizer",
    "idna",
    "urllib3",
    "requests",
    "click",
    "typer",
    "rich",
    "markdown_it",
    "shellingham",
    "jinja2",
    "markupsafe",
    "multipart",
    "email_validator",
    "engineio",
    "python_engineio",
    "socketio",
    "python_socketio",
    "simple_websocket",
    "aiofiles",
    "aiosignal",
    "attrs",
    "frozenlist",
    "multidict",
    "yarl",
    "watchfiles",
    "orjson",
    "dotenv",
    "packaging",
    "six",
    "typing_extensions",
    "zipp",
    "importlib_metadata",
    "importlib_resources",
    "colorama",
    "pydantic_settings",
    "annotated_types",
    "dnspython",
    "uvloop",
    "win32",
    "pythonwin",
    "pywin32_system32"
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
        # PyInstaller / wheel：numpy.libs、scipy.libs、torch.libs 等与主包同名 stem
        if ($second -like "*.libs") {
            $stem = $second -replace '\.libs$', ''
            if ($stem) {
                foreach ($pat in $basePatterns) {
                    if ($stem -eq $pat -or $stem -like "$pat-*" -or $stem -like "${pat}.*") {
                        return $true
                    }
                }
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

function Is-MidItem {
    param([string]$RelPath)
    $parts = $RelPath -split '[/\\]'
    if ($parts.Count -ge 2 -and $parts[0] -eq "_internal") {
        $second = $parts[1]
        foreach ($pat in $midPatterns) {
            if ($second -eq $pat -or $second -like "$pat-*" -or $second -like "${pat}.*") {
                return $true
            }
        }
        if ($second -like "*.libs") {
            $stem = $second -replace '\.libs$', ''
            if ($stem) {
                foreach ($pat in $midPatterns) {
                    if ($stem -eq $pat -or $stem -like "$pat-*" -or $stem -like "${pat}.*") {
                        return $true
                    }
                }
            }
        }
    }
    return $false
}

$allFiles = Get-ChildItem -Path $BackendDir -Recurse -File
$baseFiles = @()
$midFiles  = @()
$appFiles  = @()

foreach ($f in $allFiles) {
    $rel = $f.FullName.Substring($BackendDir.Length).TrimStart('\','/')
    if (Is-BaseItem $rel) {
        $baseFiles += $rel
    } elseif (Is-MidItem $rel) {
        $midFiles += $rel
    } else {
        $appFiles += $rel
    }
}

Write-Host "`nruntime-base: $($baseFiles.Count) files"
Write-Host "app-deps   : $($midFiles.Count) files"
Write-Host "app-backend: $($appFiles.Count) files"

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
$midZipName  = "app-deps-$Version.zip"
$appZipName  = "app-backend-$Version.zip"
$baseZipPath = Join-Path $OutputDir $baseZipName
$midZipPath  = Join-Path $OutputDir $midZipName
$appZipPath  = Join-Path $OutputDir $appZipName

Write-Host "`nCreating $baseZipName ..."
New-ChunkZip -ZipPath $baseZipPath -RootDir $BackendDir -RelFiles $baseFiles

Write-Host "Creating $midZipName ..."
New-ChunkZip -ZipPath $midZipPath -RootDir $BackendDir -RelFiles $midFiles

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
$midSha  = Get-FileSHA256 $midZipPath
$appSha  = Get-FileSHA256 $appZipPath
$baseSize = (Get-Item $baseZipPath).Length
$midSize  = (Get-Item $midZipPath).Length
$appSize  = (Get-Item $appZipPath).Length

Write-Host "`nruntime-base : $baseSha ($([math]::Round($baseSize/1MB,1)) MB)"
Write-Host "app-deps     : $midSha ($([math]::Round($midSize/1MB,1)) MB)"
Write-Host "app-backend  : $appSha ($([math]::Round($appSize/1MB,1)) MB)"

# ── 与参考清单比对：未变化的分块不保留 zip（仅减少发布目录体积）──────

$refChunkSha = @{}
if ($RefManifest -and (Test-Path -LiteralPath $RefManifest)) {
    try {
        $refJson = Get-Content -LiteralPath $RefManifest -Raw -Encoding UTF8 | ConvertFrom-Json
        foreach ($c in @($refJson.chunks)) {
            if ($null -ne $c.name -and $null -ne $c.sha256) {
                $refChunkSha[[string]$c.name] = [string]$c.sha256
            }
        }
        Write-Host "`n已加载 RefManifest，按分块名比对 SHA256；一致则删除对应 zip。"
    } catch {
        Write-Warning "无法解析 RefManifest，将保留全部分块 zip: $($_.Exception.Message)"
        $refChunkSha = @{}
    }
} elseif ($RefManifest) {
    Write-Warning "RefManifest 路径不存在，将保留全部分块 zip: $RefManifest"
}

$omitPublish = @()
$chunkRows = @(
    @{ Name = "runtime-base"; ZipPath = $baseZipPath; Sha = $baseSha },
    @{ Name = "app-deps"; ZipPath = $midZipPath; Sha = $midSha },
    @{ Name = "app-backend"; ZipPath = $appZipPath; Sha = $appSha }
)
foreach ($row in $chunkRows) {
    $prev = $refChunkSha[$row.Name]
    if ($prev -and ($prev -eq $row.Sha) -and (Test-Path -LiteralPath $row.ZipPath)) {
        Remove-Item -LiteralPath $row.ZipPath -Force
        $omitPublish += $row.Name
        Write-Host "已省略发布 zip: $($row.Name)（SHA256 与 RefManifest 一致）"
    }
}
if ($refChunkSha.Count -gt 0 -and $omitPublish.Count -eq 0) {
    Write-Host "RefManifest 已提供，但当前各分块哈希均有变化，仍发布全部分块 zip。"
}

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
            name        = "app-deps"
            version     = $Version
            sha256      = $midSha
            size        = $midSize
            url         = "${BaseUrl}${midZipName}"
            description = "FastAPI / uvicorn / HTTP stack and common pip packages"
        },
        @{
            name        = "app-backend"
            version     = $Version
            sha256      = $appSha
            size        = $appSize
            url         = "${BaseUrl}${appZipName}"
            description = "Backend exe, serviceData, business modules (changes most often)"
        }
    )
}

$manifestPath = Join-Path $OutputDir "runtime-manifest.json"
$manifest | ConvertTo-Json -Depth 5 | Set-Content -Encoding UTF8 $manifestPath

# 离线更新总清单：与 runtime-manifest.json 同目录；壳安装包由 build.ps1 在 NSIS 产出后写入同目录并补全 shell_installer
$bundleManifestPath = Join-Path $OutputDir "offline-bundle-manifest.json"
@{
    schema_version             = 1
    backend_runtime_manifest   = "runtime-manifest.json"
} | ConvertTo-Json | Set-Content -Encoding UTF8 $bundleManifestPath

Write-Host "`nManifest written to: $manifestPath"
Write-Host "Offline bundle manifest: $bundleManifestPath"
Write-Host "`n=== Done ==="
Write-Host "Output files (zip 仅列出仍存在于 OutputDir 内的分块):"
if (Test-Path -LiteralPath $baseZipPath) { Write-Host "  $baseZipPath" }
if (Test-Path -LiteralPath $midZipPath) { Write-Host "  $midZipPath" }
if (Test-Path -LiteralPath $appZipPath) { Write-Host "  $appZipPath" }
Write-Host "  $manifestPath"
Write-Host "  $bundleManifestPath"
if ($omitPublish.Count -gt 0) {
    Write-Host ""
    Write-Host "说明: 已省略 $($omitPublish -join ', ') 的 zip。清单仍含其 sha256/size，仅已安装该哈希的用户可跳过下载。"
    Write-Host "      首次安装或缺少对应分块的用户需从完整包或其它渠道取得未上传的 zip。"
}
Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. 将 OutputDir 中实际存在的文件上传到网盘"
Write-Host "  2. （可选）设置 SACV_RUNTIME_MANIFEST_URL 指向清单 URL"
