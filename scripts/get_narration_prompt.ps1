Param(
    [Parameter(Mandatory = $true)] [string] $DramaName,
    [string] $PlotAnalysis,
    [string] $Subtitles,
    [string] $PlotAnalysisPath,
    [string] $SubtitlesPath,
    [string] $OutputPath
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$pyTemp = $null
$TempDir = $null

# 解析仓库根目录并设置 PYTHONPATH，确保可导入 prompts 模块
$RepoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$BackendPath = Join-Path $RepoRoot 'backend'
$env:PYTHONPATH = "$BackendPath;$env:PYTHONPATH"

function Read-OrUse {
    Param(
        [string] $Text,
        [string] $Path,
        [string] $Name
    )
    if ($Path) {
        if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
            throw "文件不存在: $Name 路径 '$Path'"
        }
        return (Get-Content -LiteralPath $Path -Raw)
    }
    if ($Text) { return $Text }
    throw "缺少 $Name：请提供 -$Name 或 -${Name}Path"
}

$plot = Read-OrUse -Text $PlotAnalysis -Path $PlotAnalysisPath -Name 'PlotAnalysis'
$subs = Read-OrUse -Text $Subtitles -Path $SubtitlesPath -Name 'Subtitles'

$variables = @{
    drama_name       = $DramaName
    plot_analysis    = $plot
    subtitle_content = $subs
}
$varsJson = $variables | ConvertTo-Json -Depth 10

# 写入临时 Python 脚本并执行
$TempDir = $env:TEMP
if (-not $TempDir) { $TempDir = [System.IO.Path]::GetTempPath() }
$pyTemp = Join-Path $TempDir ("get_narration_prompt_" + [Guid]::NewGuid().ToString() + ".py")
$jsonTemp = Join-Path $TempDir ("get_narration_vars_" + [Guid]::NewGuid().ToString() + ".json")
$pyCode = @'
import json, sys
try:
    from modules.prompts.prompt_manager import prompt_manager
except Exception as e:
    print(json.dumps({"error": f"导入提示词管理器失败: {e}"}, ensure_ascii=False))
    sys.exit(1)

KEY = "short_drama_narration:script_generation"

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error":"缺少变量 JSON 文件路径"}, ensure_ascii=False)); sys.exit(1)
    json_path = sys.argv[1]
    try:
        with open(json_path, 'r', encoding='utf-8-sig') as f:
            vars_json = json.load(f)
    except Exception as e:
        print(json.dumps({"error": f"读取变量 JSON 失败: {e}"}, ensure_ascii=False)); sys.exit(1)
    try:
        rendered = prompt_manager.render_prompt(KEY, vars_json)
        messages = prompt_manager.build_chat_messages(KEY, vars_json)
        out = {"rendered": rendered, "messages": messages}
        print(json.dumps(out, ensure_ascii=False))
    except Exception as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        sys.exit(2)

if __name__ == "__main__":
    main()
'@

Set-Content -LiteralPath $pyTemp -Value $pyCode -Encoding UTF8
Set-Content -LiteralPath $jsonTemp -Value $varsJson -Encoding UTF8

try {
    $result = & python $pyTemp $jsonTemp
} catch {
    # 尝试使用 py 启动器
    $result = & py -3 $pyTemp $jsonTemp
}

if ($pyTemp) { Remove-Item -LiteralPath $pyTemp -ErrorAction SilentlyContinue }
if ($jsonTemp) { Remove-Item -LiteralPath $jsonTemp -ErrorAction SilentlyContinue }

if ($OutputPath) {
    $outDir = Split-Path -Parent $OutputPath
    if ($outDir -and -not (Test-Path -LiteralPath $outDir)) {
        New-Item -ItemType Directory -Path $outDir | Out-Null
    }
    Set-Content -LiteralPath $OutputPath -Value $result -Encoding UTF8
    Write-Host "已写入: $OutputPath"
} else {
    Write-Output $result
}