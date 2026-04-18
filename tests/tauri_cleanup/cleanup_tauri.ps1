# ============================================================
#  SuperAI影视剪辑 Tauri 版本清理脚本 (核心逻辑)
#  1) 扫描所有与 Tauri 版本相关的: 进程 / 安装目录 / AppData /
#     后端数据 / 临时文件 / 注册表项 / 快捷方式 / 自启项
#  2) 把扫描到的条目分类打印给用户确认
#  3) 支持逐项跳过 (y=全部清理, n=取消, s=分项询问, d=仅停进程)
#  4) 清理时带重试与日志，尽量一次性彻底删除
#
#  使用方式:
#    直接被 cleanup_tauri.bat 调用 (管理员权限 + UTF-8)
#    也可独立运行: powershell -ExecutionPolicy Bypass -File cleanup_tauri.ps1
# ============================================================

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8

# ---------- 基础常量 ----------
$ProductName    = 'SuperAI影视剪辑'
$Manufacturer   = 'SuperAI影视剪辑'
$InstallFolder  = 'SuperAIAutoCutVideo'       # ASCII 安装文件夹名 (installer.nsi INSTALLDIRFOLDER)
$BackendProduct = 'SuperAutoCutVideo'         # 后端数据目录 (backend/modules/app_paths.py)
$BundleId       = 'com.superautocutvideo.app' # tauri.conf.json identifier
$MainExeNames   = @(
    'super-auto-cut-video.exe',
    'superAutoCutVideoBackend.exe'
)

# 可能与本应用相关、但属于通用进程的 (不主动杀, 只列出)
$AmbiguousProcessNames = @('ffmpeg.exe', 'ffprobe.exe', 'msedgewebview2.exe')

# ---------- 工具函数 ----------
function Write-Section($title) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
    Write-Host (" $title") -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
}

function Write-Item($ok, $text) {
    $mark = if ($ok) { '[√]' } else { '[ ]' }
    $color = if ($ok) { 'Green' } else { 'DarkGray' }
    Write-Host "  $mark $text" -ForegroundColor $color
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p  = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Safe-RemoveItem {
    param(
        [string]$Path,
        [int]$Retries = 3
    )
    if (-not $Path) { return $false }
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    for ($i=0; $i -lt $Retries; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            Start-Sleep -Milliseconds 400
        }
    }
    try {
        # 兜底: 尝试用 cmd 的 rd/del
        if ((Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue).PSIsContainer) {
            cmd /c rd /s /q "$Path" 2>$null | Out-Null
        } else {
            cmd /c del /f /q "$Path" 2>$null | Out-Null
        }
    } catch {}
    return (-not (Test-Path -LiteralPath $Path))
}

function Safe-RemoveRegKey {
    param([string]$Path)
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        try {
            reg delete "$($Path -replace '^HKLM:', 'HKLM' -replace '^HKCU:', 'HKCU')" /f 2>$null | Out-Null
        } catch {}
        return (-not (Test-Path -LiteralPath $Path))
    }
}

function Safe-RemoveRegValue {
    param([string]$Path, [string]$Name)
    try {
        if (Test-Path -LiteralPath $Path) {
            $v = Get-ItemProperty -LiteralPath $Path -Name $Name -ErrorAction SilentlyContinue
            if ($null -ne $v) {
                Remove-ItemProperty -LiteralPath $Path -Name $Name -Force -ErrorAction Stop
            }
        }
        return $true
    } catch { return $false }
}

function Ask-YesNo {
    param(
        [string]$Question,
        [string]$Default = 'n'
    )
    $suffix = if ($Default -eq 'y') { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        $ans = Read-Host "$Question $suffix"
        if ([string]::IsNullOrWhiteSpace($ans)) { $ans = $Default }
        switch ($ans.Trim().ToLower()) {
            'y' { return $true }
            'yes' { return $true }
            'n' { return $false }
            'no' { return $false }
        }
    }
}

# ---------- 扫描阶段 ----------

function Get-ProcessPathSafe($proc) {
    try { return $proc.Path } catch { return $null }
}

function Scan-Processes {
    $list = @()
    foreach ($n in $MainExeNames) {
        $procs = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($n)) -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $list += [pscustomobject]@{
                Kind  = 'Process'
                Name  = $n
                Id    = $p.Id
                Path  = Get-ProcessPathSafe $p
                Ambiguous = $false
            }
        }
    }
    # 模糊进程: 只列同路径属于本应用的
    foreach ($n in $AmbiguousProcessNames) {
        $pn = [IO.Path]::GetFileNameWithoutExtension($n)
        $procs = Get-Process -Name $pn -ErrorAction SilentlyContinue
        foreach ($p in $procs) {
            $path = Get-ProcessPathSafe $p
            if ($null -ne $path) {
                $lower = $path.ToLower()
                if (
                    $lower -match [regex]::Escape($InstallFolder.ToLower()) -or
                    $lower -match [regex]::Escape($BundleId.ToLower()) -or
                    $lower -match [regex]::Escape($BackendProduct.ToLower()) -or
                    $lower -match 'superautocutvideobackend'
                ) {
                    $list += [pscustomobject]@{
                        Kind  = 'Process'
                        Name  = $n
                        Id    = $p.Id
                        Path  = $path
                        Ambiguous = $true
                    }
                }
            }
        }
    }
    return $list
}

function Scan-Directories {
    $candidates = @()

    $pf    = [Environment]::GetFolderPath('ProgramFiles')
    $pf86  = ${env:ProgramFiles(x86)}
    $la    = [Environment]::GetFolderPath('LocalApplicationData')
    $ra    = [Environment]::GetFolderPath('ApplicationData')
    $temp  = [IO.Path]::GetTempPath().TrimEnd('\')

    # 安装目录 (NSIS 安装器)
    $candidates += [pscustomobject]@{ Kind='InstallDir'; Path=(Join-Path $pf   $InstallFolder);  Desc='安装目录 (Program Files)' }
    if ($pf86) {
        $candidates += [pscustomobject]@{ Kind='InstallDir'; Path=(Join-Path $pf86 $InstallFolder);  Desc='安装目录 (Program Files x86)' }
    }
    $candidates += [pscustomobject]@{ Kind='InstallDir'; Path=(Join-Path $la   $InstallFolder);  Desc='安装目录 (per-user LocalAppData)' }

    # Tauri 自身 AppData (identifier)
    $candidates += [pscustomobject]@{ Kind='AppData';    Path=(Join-Path $ra   $BundleId);        Desc='Tauri AppData (Roaming, bundle id)' }
    $candidates += [pscustomobject]@{ Kind='AppData';    Path=(Join-Path $la   $BundleId);        Desc='Tauri AppData (Local, bundle id, 含 superAutoCutVideoBackend 解压、WebView2 缓存)' }

    # Python 后端持久化数据 (app_paths.py)
    $candidates += [pscustomobject]@{ Kind='BackendData'; Path=(Join-Path $la  $BackendProduct);  Desc='后端持久化数据 (uploads / config / data / app_settings.json)' }

    # 临时文件
    $candidates += [pscustomobject]@{ Kind='Temp';        Path=(Join-Path $temp 'super_auto_cut_backend.log'); Desc='后端日志' }
    $candidates += [pscustomobject]@{ Kind='Temp';        Path=(Join-Path $temp 'super_auto_cut_backend_tmp'); Desc='后端临时目录' }
    $candidates += [pscustomobject]@{ Kind='Temp';        Path=(Join-Path $temp 'MicrosoftEdgeWebview2Setup.exe'); Desc='WebView2 安装残留 (可选)' }

    return $candidates | Where-Object { Test-Path -LiteralPath $_.Path }
}

function Scan-Registry {
    $items = @()

    $uninstallPaths = @(
        "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ProductName",
        "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$ProductName",
        "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$ProductName"
    )
    foreach ($p in $uninstallPaths) {
        if (Test-Path -LiteralPath $p) {
            $items += [pscustomobject]@{ Kind='RegKey'; Path=$p; Desc='卸载信息 (Add/Remove Programs)' }
        }
    }

    # Manufacturer 键 (installer.nsi 写入安装路径 / 语言)
    $manuKeys = @(
        "HKLM:\SOFTWARE\$Manufacturer",
        "HKLM:\SOFTWARE\WOW6432Node\$Manufacturer",
        "HKCU:\SOFTWARE\$Manufacturer"
    )
    foreach ($p in $manuKeys) {
        if (Test-Path -LiteralPath $p) {
            $items += [pscustomobject]@{ Kind='RegKey'; Path=$p; Desc='厂商键 (安装路径/语言)' }
        }
    }

    # Run 自启项 value (非 key)
    $runKey = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
    if (Test-Path -LiteralPath $runKey) {
        $prop = Get-ItemProperty -LiteralPath $runKey -Name $ProductName -ErrorAction SilentlyContinue
        if ($null -ne $prop) {
            $items += [pscustomobject]@{ Kind='RegValue'; Path=$runKey; Name=$ProductName; Desc='开机自启 (HKCU\...\Run)' }
        }
    }

    # 深链接协议 (如果 bundle id 作为 URL 协议被写入)
    $deepLinkPaths = @(
        "HKLM:\SOFTWARE\Classes\$BundleId",
        "HKCU:\SOFTWARE\Classes\$BundleId"
    )
    foreach ($p in $deepLinkPaths) {
        if (Test-Path -LiteralPath $p) {
            $items += [pscustomobject]@{ Kind='RegKey'; Path=$p; Desc='深链接协议注册' }
        }
    }

    # WiX 老版本遗留: 扫描 Uninstall 根下 Publisher=产品名 的任意 GUID key
    $wixRoots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $wixRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $props = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
                if ($props -and $props.DisplayName -eq $ProductName -and $props.Publisher -eq $Manufacturer) {
                    # 避免和上面主 key 重复
                    if ($_.PSPath -notmatch [regex]::Escape($ProductName)) {
                        $items += [pscustomobject]@{ Kind='RegKey'; Path=$_.PSPath; Desc='老版本卸载键 (可能是 WiX 安装遗留)' }
                    }
                }
            } catch {}
        }
    }

    return $items
}

function Test-IsAppProcess($processPath) {
    # 判断一个进程路径是否属于本应用
    if (-not $processPath) { return $false }
    $lower = $processPath.ToLower()
    return (
        $lower -match [regex]::Escape($InstallFolder.ToLower())  -or
        $lower -match [regex]::Escape($BundleId.ToLower())       -or
        $lower -match [regex]::Escape($BackendProduct.ToLower()) -or
        $lower -match 'superautocutvideobackend'                 -or
        $lower -match 'super-auto-cut-video'
    )
}

function Scan-Ports {
    # 覆盖 main.rs/choose_backend_port 里的所有候选区间 + 常用的 8080
    $ranges = @(
        @{ From = 8000;  To = 8100 },
        @{ From = 18000; To = 18100 }
    )
    $extra = @(8080)

    $result = @()
    try {
        $listens = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
    } catch {
        $listens = @()
    }
    if (-not $listens) { return $result }

    foreach ($c in $listens) {
        $port = [int]$c.LocalPort
        $hit  = $false
        foreach ($r in $ranges) {
            if ($port -ge $r.From -and $port -le $r.To) { $hit = $true; break }
        }
        if (-not $hit -and ($extra -notcontains $port)) { continue }

        $pid2 = [int]$c.OwningProcess
        if ($pid2 -le 0) { continue }
        $proc = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $path = Get-ProcessPathSafe $proc
        $isApp = Test-IsAppProcess $path

        # 去重: 同 PID 多个端口只保留一条, 但把端口合并
        $existing = $result | Where-Object { $_.Id -eq $pid2 } | Select-Object -First 1
        if ($existing) {
            if ($existing.Ports -notcontains $port) {
                $existing.Ports = @($existing.Ports + $port) | Sort-Object -Unique
            }
            continue
        }

        $result += [pscustomobject]@{
            Kind      = 'PortOccupier'
            Id        = $pid2
            Name      = $proc.Name
            Path      = $path
            Ports     = @($port)
            Ambiguous = (-not $isApp)   # 路径命中本应用 => 不模糊; 否则 => 模糊(需要用户二次确认)
        }
    }

    return $result
}

function Scan-Shortcuts {
    $items = @()
    $locations = @(
        (Join-Path $env:PUBLIC 'Desktop'),
        (Join-Path $env:USERPROFILE 'Desktop'),
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs')
    )
    foreach ($loc in $locations) {
        if (-not (Test-Path -LiteralPath $loc)) { continue }
        $lnk = Join-Path $loc ($ProductName + '.lnk')
        if (Test-Path -LiteralPath $lnk) {
            $items += [pscustomobject]@{ Kind='Shortcut'; Path=$lnk; Desc='快捷方式' }
        }
        # 可能还有一个以 ProductName 命名的开始菜单子文件夹
        $folder = Join-Path $loc $ProductName
        if (Test-Path -LiteralPath $folder -PathType Container) {
            $items += [pscustomobject]@{ Kind='Shortcut'; Path=$folder; Desc='开始菜单文件夹' }
        }
    }
    return $items
}

# ---------- 报告 + 交互 ----------

function Print-Scan-Report($procs, $dirs, $regs, $shortcuts, $ports) {
    Write-Section '扫描结果 (DRY-RUN，尚未做任何改动)'

    Write-Host ''
    Write-Host '--- 相关进程 ---' -ForegroundColor Yellow
    if ($procs.Count -eq 0) {
        Write-Host '  (无)' -ForegroundColor DarkGray
    } else {
        foreach ($p in $procs) {
            $tag = if ($p.Ambiguous) { '[模糊匹配]' } else { '[确定]' }
            $color = if ($p.Ambiguous) { 'DarkYellow' } else { 'Red' }
            Write-Host ("  {0} PID={1,-6} {2}  path={3}" -f $tag, $p.Id, $p.Name, $p.Path) -ForegroundColor $color
        }
    }

    Write-Host ''
    Write-Host '--- 目录 / 文件 ---' -ForegroundColor Yellow
    if ($dirs.Count -eq 0) {
        Write-Host '  (无)' -ForegroundColor DarkGray
    } else {
        foreach ($d in $dirs) {
            $size = ''
            try {
                if ((Get-Item -LiteralPath $d.Path).PSIsContainer) {
                    $bytes = (Get-ChildItem -LiteralPath $d.Path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
                    if ($bytes) { $size = ('  ({0:N1} MB)' -f ($bytes / 1MB)) }
                } else {
                    $bytes = (Get-Item -LiteralPath $d.Path).Length
                    if ($bytes) { $size = ('  ({0:N1} KB)' -f ($bytes / 1KB)) }
                }
            } catch {}
            Write-Host ("  [{0,-11}] {1}{2}" -f $d.Kind, $d.Path, $size) -ForegroundColor White
            Write-Host ("              -> {0}" -f $d.Desc) -ForegroundColor DarkGray
        }
    }

    Write-Host ''
    Write-Host '--- 注册表 ---' -ForegroundColor Yellow
    if ($regs.Count -eq 0) {
        Write-Host '  (无)' -ForegroundColor DarkGray
    } else {
        foreach ($r in $regs) {
            $suffix = if ($r.Kind -eq 'RegValue') { " [值: $($r.Name)]" } else { '' }
            Write-Host ("  [{0,-8}] {1}{2}" -f $r.Kind, $r.Path, $suffix) -ForegroundColor White
            Write-Host ("              -> {0}" -f $r.Desc) -ForegroundColor DarkGray
        }
    }

    Write-Host ''
    Write-Host '--- 快捷方式 ---' -ForegroundColor Yellow
    if ($shortcuts.Count -eq 0) {
        Write-Host '  (无)' -ForegroundColor DarkGray
    } else {
        foreach ($s in $shortcuts) {
            Write-Host ("  [{0,-8}] {1}" -f $s.Kind, $s.Path) -ForegroundColor White
            Write-Host ("              -> {0}" -f $s.Desc) -ForegroundColor DarkGray
        }
    }

    Write-Host ''
    Write-Host '--- 端口占用 (后端候选区间 8000-8100 / 18000-18100) ---' -ForegroundColor Yellow
    if ($null -eq $ports -or $ports.Count -eq 0) {
        Write-Host '  (无)' -ForegroundColor DarkGray
    } else {
        foreach ($p in $ports) {
            $tag = if ($p.Ambiguous) { '[第三方]' } else { '[本应用]' }
            $color = if ($p.Ambiguous) { 'DarkYellow' } else { 'Red' }
            $portsStr = ($p.Ports | ForEach-Object { $_.ToString() }) -join ','
            Write-Host ("  {0} port {1,-24} PID={2,-6} {3}" -f $tag, $portsStr, $p.Id, $p.Name) -ForegroundColor $color
            if ($p.Path) {
                Write-Host ("              -> {0}" -f $p.Path) -ForegroundColor DarkGray
            }
        }
    }
}

# ---------- 清理阶段 ----------

function Stop-Processes($procs, [switch]$IncludeAmbiguous) {
    Write-Section '停止相关进程'
    if ($procs.Count -eq 0) { Write-Host '  (无进程需停止)' -ForegroundColor DarkGray; return }

    foreach ($p in $procs) {
        if ($p.Ambiguous -and -not $IncludeAmbiguous) {
            Write-Item $false ("跳过模糊进程 PID={0} {1}" -f $p.Id, $p.Name)
            continue
        }
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 200
            Write-Item $true ("已停止 PID={0} {1}" -f $p.Id, $p.Name)
        } catch {
            # 兜底用 taskkill
            cmd /c "taskkill /F /PID $($p.Id) /T" 2>$null | Out-Null
            if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
                Write-Item $true ("已停止 PID={0} {1} (taskkill)" -f $p.Id, $p.Name)
            } else {
                Write-Item $false ("无法停止 PID={0} {1}: {2}" -f $p.Id, $p.Name, $_.Exception.Message)
            }
        }
    }

    # 以 name 为单位再扫一遍，避免遗漏 (后端进程可能多开)
    foreach ($n in $MainExeNames) {
        $procs2 = Get-Process -Name ([IO.Path]::GetFileNameWithoutExtension($n)) -ErrorAction SilentlyContinue
        foreach ($p in $procs2) {
            try { Stop-Process -Id $p.Id -Force -ErrorAction Stop } catch {}
        }
    }
}

function Stop-PortOccupiers($ports, [switch]$IncludeForeign) {
    Write-Section '释放被占用的后端端口'
    if ($null -eq $ports -or $ports.Count -eq 0) {
        Write-Host '  (无端口占用)' -ForegroundColor DarkGray
        return
    }
    foreach ($p in $ports) {
        $portsStr = ($p.Ports | ForEach-Object { $_.ToString() }) -join ','
        if ($p.Ambiguous -and -not $IncludeForeign) {
            Write-Item $false ("跳过第三方进程 PID={0} {1} [端口 {2}]" -f $p.Id, $p.Name, $portsStr)
            continue
        }
        if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
            # 已经在前面的进程终止阶段被杀掉了
            Write-Item $true ("已释放 端口 {0} (PID={1} {2} 已退出)" -f $portsStr, $p.Id, $p.Name)
            continue
        }
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 200
            Write-Item $true ("已终止 PID={0} {1} [端口 {2}]" -f $p.Id, $p.Name, $portsStr)
        } catch {
            cmd /c "taskkill /F /PID $($p.Id) /T" 2>$null | Out-Null
            if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
                Write-Item $true ("已终止 PID={0} {1} [端口 {2}] (taskkill)" -f $p.Id, $p.Name, $portsStr)
            } else {
                Write-Item $false ("无法终止 PID={0} {1} [端口 {2}]: {3}" -f $p.Id, $p.Name, $portsStr, $_.Exception.Message)
            }
        }
    }
}

function Run-Uninstaller-IfAny {
    Write-Section '尝试调用官方 uninstaller (如果存在)'
    $pf   = [Environment]::GetFolderPath('ProgramFiles')
    $pf86 = ${env:ProgramFiles(x86)}
    $la   = [Environment]::GetFolderPath('LocalApplicationData')
    $candidates = @(
        (Join-Path $pf   (Join-Path $InstallFolder 'uninstall.exe')),
        (Join-Path $pf86 (Join-Path $InstallFolder 'uninstall.exe')),
        (Join-Path $la   (Join-Path $InstallFolder 'uninstall.exe'))
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }

    if ($candidates.Count -eq 0) {
        Write-Host '  (未找到 uninstall.exe, 跳过)' -ForegroundColor DarkGray
        return
    }

    foreach ($u in $candidates) {
        Write-Host "  发现: $u" -ForegroundColor White
        if (Ask-YesNo '    -> 以静默模式调用它执行卸载吗? (会先于手动清理执行，更干净)' 'y') {
            try {
                # /P = passive 模式 (Tauri NSIS 模板支持), 同时把 AppData 勾上
                $proc = Start-Process -FilePath $u -ArgumentList '/P','/S' -Wait -PassThru -ErrorAction Stop
                Write-Item $true ("uninstall.exe 退出码 = {0}" -f $proc.ExitCode)
            } catch {
                Write-Item $false ("uninstall.exe 失败: {0}" -f $_.Exception.Message)
            }
        }
    }
}

function Remove-Directories($dirs) {
    Write-Section '删除目录 / 文件'
    if ($dirs.Count -eq 0) { Write-Host '  (无)' -ForegroundColor DarkGray; return }
    foreach ($d in $dirs) {
        $ok = Safe-RemoveItem -Path $d.Path
        Write-Item $ok ("{0} -- {1}" -f $d.Path, $d.Desc)
    }
}

function Remove-Registry($regs) {
    Write-Section '清理注册表'
    if ($regs.Count -eq 0) { Write-Host '  (无)' -ForegroundColor DarkGray; return }
    foreach ($r in $regs) {
        if ($r.Kind -eq 'RegValue') {
            $ok = Safe-RemoveRegValue -Path $r.Path -Name $r.Name
            Write-Item $ok ("[值] {0}!{1} -- {2}" -f $r.Path, $r.Name, $r.Desc)
        } else {
            $ok = Safe-RemoveRegKey -Path $r.Path
            Write-Item $ok ("[键] {0} -- {1}" -f $r.Path, $r.Desc)
        }
    }
}

function Remove-Shortcuts($shortcuts) {
    Write-Section '删除快捷方式'
    if ($shortcuts.Count -eq 0) { Write-Host '  (无)' -ForegroundColor DarkGray; return }
    foreach ($s in $shortcuts) {
        $ok = Safe-RemoveItem -Path $s.Path
        Write-Item $ok ("{0} -- {1}" -f $s.Path, $s.Desc)
    }
}

# ---------- 主流程 ----------

Write-Host ''
Write-Host '################################################################' -ForegroundColor Magenta
Write-Host '#  SuperAI影视剪辑 Tauri 版本清理工具' -ForegroundColor Magenta
Write-Host ('#  产品名: {0}    Bundle Id: {1}' -f $ProductName, $BundleId) -ForegroundColor Magenta
Write-Host '################################################################' -ForegroundColor Magenta

if (-not (Test-IsAdmin)) {
    Write-Host ''
    Write-Host '[WARN] 当前不是管理员权限，HKLM 注册表和 Program Files 安装目录可能清理失败。' -ForegroundColor Yellow
    Write-Host '       建议关闭本窗口，双击 cleanup_tauri.bat 重新运行。' -ForegroundColor Yellow
    if (-not (Ask-YesNo '是否仍然继续 (仅清理当前用户可访问的部分)?' 'n')) { exit 1 }
}

# 1) 扫描
$procs     = Scan-Processes
$dirs      = Scan-Directories
$regs      = Scan-Registry
$shortcuts = Scan-Shortcuts
$ports     = Scan-Ports

Print-Scan-Report -procs $procs -dirs $dirs -regs $regs -shortcuts $shortcuts -ports $ports

# 2) 交互
Write-Host ''
Write-Host '请确认: 以上所有条目将被清理。' -ForegroundColor Cyan
Write-Host '  y : 全部清理 (推荐)' -ForegroundColor Cyan
Write-Host '  s : 分类逐项确认' -ForegroundColor Cyan
Write-Host '  d : 仅停止相关进程 / 释放端口，不删除任何文件和注册表' -ForegroundColor Cyan
Write-Host '  n : 完全取消退出 (什么都不做)' -ForegroundColor Cyan

$choice = ''
while ($choice -notin @('y','s','d','n')) {
    $choice = (Read-Host '你的选择 [y/s/d/N]').Trim().ToLower()
    if ([string]::IsNullOrWhiteSpace($choice)) { $choice = 'n' }
}

if ($choice -eq 'n') {
    Write-Host ''
    Write-Host '已取消，未做任何改动。' -ForegroundColor Yellow
    exit 0
}

# 3) 执行
$includeAmbiguous = $false
if ($procs | Where-Object { $_.Ambiguous }) {
    $includeAmbiguous = Ask-YesNo '检测到模糊进程 (ffmpeg/ffprobe/msedgewebview2 中疑似本应用的)，是否一并杀掉?' 'y'
}

# 端口占用处理 (默认: 本应用直接杀; 第三方必须显式确认才杀)
$killAppPorts     = $false
$killForeignPorts = $false
$appPorts     = @($ports | Where-Object { -not $_.Ambiguous })
$foreignPorts = @($ports | Where-Object { $_.Ambiguous })
if ($appPorts.Count -gt 0) {
    $killAppPorts = Ask-YesNo ("发现 {0} 个占用后端候选端口的本应用进程，是否强制终止?" -f $appPorts.Count) 'y'
}
if ($foreignPorts.Count -gt 0) {
    Write-Host '  以下进程占用后端候选端口，但看起来不是本应用:' -ForegroundColor Yellow
    foreach ($fp in $foreignPorts) {
        $ps = ($fp.Ports -join ',')
        Write-Host ("    PID={0} {1} [端口 {2}] path={3}" -f $fp.Id, $fp.Name, $ps, $fp.Path) -ForegroundColor Yellow
    }
    $killForeignPorts = Ask-YesNo '是否也强杀这些第三方进程? (慎选, 默认 N)' 'n'
}

# 先停进程, 避免文件占用
Stop-Processes -procs $procs -IncludeAmbiguous:$includeAmbiguous

# 再释放端口 (本应用/第三方 分别按前面的确认决定)
if ($killAppPorts -or $killForeignPorts) {
    $toKill = @()
    if ($killAppPorts)     { $toKill += $appPorts }
    if ($killForeignPorts) { $toKill += $foreignPorts }
    Stop-PortOccupiers -ports $toKill -IncludeForeign:$killForeignPorts
}

if ($choice -eq 'd') {
    Write-Host ''
    Write-Host '已停止相关进程 / 释放端口，按要求未删除任何文件和注册表。' -ForegroundColor Green
    exit 0
}

# 如果是全量模式, 优先调用官方 uninstaller (若存在), 让它先自己清一轮
if ($choice -eq 'y') {
    Run-Uninstaller-IfAny
}

if ($choice -eq 's') {
    # 分项确认
    $doDirs = Ask-YesNo "删除 $($dirs.Count) 个目录/文件?" 'y'
    $doRegs = Ask-YesNo "清理 $($regs.Count) 个注册表项?" 'y'
    $doShs  = Ask-YesNo "删除 $($shortcuts.Count) 个快捷方式?" 'y'
    $doUn   = Ask-YesNo '先尝试调用官方 uninstall.exe (若存在)?' 'y'
    if ($doUn) { Run-Uninstaller-IfAny }
} else {
    $doDirs = $true; $doRegs = $true; $doShs = $true
}

# uninstaller 可能已经删了一部分, 重新扫一遍残留
$dirs      = Scan-Directories
$regs      = Scan-Registry
$shortcuts = Scan-Shortcuts

if ($doDirs) { Remove-Directories -dirs $dirs }
if ($doRegs) { Remove-Registry     -regs $regs }
if ($doShs)  { Remove-Shortcuts    -shortcuts $shortcuts }

# 4) 收尾确认
Write-Section '最终状态校验'
$leftDirs  = Scan-Directories
$leftRegs  = Scan-Registry
$leftShs   = Scan-Shortcuts
$leftPrs   = Scan-Processes
$leftPorts = Scan-Ports
# 第三方端口占用若用户不同意杀就不算"残留"
$leftPortsReported = @($leftPorts | Where-Object { -not $_.Ambiguous -or $killForeignPorts })

$allClean = ($leftDirs.Count -eq 0) -and ($leftRegs.Count -eq 0) -and ($leftShs.Count -eq 0) -and ($leftPrs.Count -eq 0) -and ($leftPortsReported.Count -eq 0)

if ($allClean) {
    Write-Host '  √ 一切干净，Tauri 版本已彻底清理。' -ForegroundColor Green
} else {
    Write-Host '  以下条目未能自动清理 (可能需要手动处理或重启后再执行一次):' -ForegroundColor Yellow
    foreach ($x in $leftDirs)          { Write-Host "    - [DIR ] $($x.Path)"                                        -ForegroundColor Yellow }
    foreach ($x in $leftRegs)          { Write-Host "    - [REG ] $($x.Path)"                                        -ForegroundColor Yellow }
    foreach ($x in $leftShs)           { Write-Host "    - [LNK ] $($x.Path)"                                        -ForegroundColor Yellow }
    foreach ($x in $leftPrs)           { Write-Host "    - [PROC] PID=$($x.Id) $($x.Name)"                           -ForegroundColor Yellow }
    foreach ($x in $leftPortsReported) { Write-Host "    - [PORT] PID=$($x.Id) $($x.Name) ports=$($x.Ports -join ',')" -ForegroundColor Yellow }
    if (@($leftPorts | Where-Object { $_.Ambiguous }).Count -gt 0 -and -not $killForeignPorts) {
        Write-Host '  (注: 第三方端口占用按你的选择未处理，不计入残留。)' -ForegroundColor DarkGray
    }
}

Write-Host ''
Write-Host '完成。' -ForegroundColor Green
exit 0
