# 仅构建 GPU 离线安装包，输出到：
#   src-tauri\target\release\dist\gpu\installers\
# 分发时需同目录带上 superAutoCutVideoBackend_gpu.zip（脚本会自动复制到 installers）
#
# 用法（项目根目录）：
#   .\scripts\build-gpu-installer.ps1
#   .\scripts\build-gpu-installer.ps1 -Clean          # 全量清理后重建
#   .\scripts\build-gpu-installer.ps1 -RecreateBackendVenv
#   .\scripts\build-gpu-installer.ps1 -GpuEmbedBackendZip   # 单文件安装包（后端 zip 打进 NSIS，体积大）

[CmdletBinding()]
param(
  [switch]$Clean,
  [switch]$RecreateBackendVenv,
  [switch]$GpuEmbedBackendZip,
  [switch]$RuntimeChunks,
  [string]$RefRuntimeManifest = ""
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path (Join-Path $root 'frontend')) -or -not (Test-Path (Join-Path $root 'src-tauri'))) {
  Write-Error "请在项目根目录运行，或通过 scripts\build-gpu-installer.ps1 调用"
}

Push-Location $root
try {
  $args = @(
    '-Variant', 'gpu',
    '-SkipPortable'
  )
  if (-not $Clean) { $args += '-SkipClean' }
  if ($RecreateBackendVenv) { $args += '-RecreateBackendVenv' }
  if ($GpuEmbedBackendZip) { $args += '-GpuEmbedBackendZip' }
  if ($RuntimeChunks) { $args += '-RuntimeChunks' }
  if ($RefRuntimeManifest) { $args += '-RefRuntimeManifest'; $args += $RefRuntimeManifest }

  & (Join-Path $PSScriptRoot 'build.ps1') @args
  if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

  $out = Join-Path $root 'src-tauri\target\release\dist\gpu\installers'
  Write-Host ""
  Write-Host "[OK] GPU 安装包目录: $out" -ForegroundColor Green
  if (Test-Path $out) {
    Get-ChildItem -Path $out -File | ForEach-Object { Write-Host "     $($_.Name)" }
  }
}
finally {
  Pop-Location
}
