# SuperAI Tauri cleanup script.
# Removes the installed Tauri shell, packaged backend runtime cache, Tauri
# AppData, backend persistent data, temp files, registry entries, shortcuts,
# and app-owned processes/ports.

[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$DryRun,
    [switch]$StopOnly
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
$ErrorActionPreference = 'Continue'

$ScriptRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = (Resolve-Path (Join-Path $ScriptRoot '..\..')).Path

function Read-TauriConfig {
    $configPath = Join-Path $RepoRoot 'src-tauri\tauri.conf.json'
    $fallback = [pscustomobject]@{
        ProductName = 'SuperAI'
        BundleId = 'com.superautocutvideo.app'
        MainExeName = 'super-auto-cut-video.exe'
    }
    if (-not (Test-Path -LiteralPath $configPath)) { return $fallback }
    try {
        $json = Get-Content -LiteralPath $configPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $cargoPath = Join-Path $RepoRoot 'src-tauri\Cargo.toml'
        $mainName = $fallback.MainExeName
        if (Test-Path -LiteralPath $cargoPath) {
            $cargo = Get-Content -LiteralPath $cargoPath -Raw -Encoding UTF8
            $m = [regex]::Match($cargo, '(?m)^\s*name\s*=\s*"([^"]+)"')
            if ($m.Success) { $mainName = "$($m.Groups[1].Value).exe" }
        }
        return [pscustomobject]@{
            ProductName = [string]$json.productName
            BundleId = [string]$json.identifier
            MainExeName = $mainName
        }
    } catch {
        return $fallback
    }
}

$Tauri = Read-TauriConfig
$ProductNames = @($Tauri.ProductName) |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Sort-Object -Unique
if ($ProductNames.Count -eq 0) { $ProductNames = @('SuperAI') }
$ManufacturerNames = @($ProductNames)
$InstallFolderNames = @('SuperAIAutoCutVideo') | Sort-Object -Unique
$LegacyMachineInstallFolderNames = @('SuperAutoCutVideo') | Sort-Object -Unique
$BackendProductNames = @('SuperAutoCutVideo')
$BundleIds = @($Tauri.BundleId, 'com.superautocutvideo.app') |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Sort-Object -Unique
$MainExeNames = @($Tauri.MainExeName, 'super-auto-cut-video.exe') |
    Where-Object { -not [string]::IsNullOrWhiteSpace($_) } |
    Sort-Object -Unique
$BackendExeNames = @('superAutoCutVideoBackend.exe')
$AmbiguousProcessNames = @('ffmpeg.exe', 'ffprobe.exe', 'msedgewebview2.exe', 'python.exe', 'pythonw.exe')
$BackendPortRanges = @(
    [pscustomobject]@{ From = 8000; To = 8100 },
    [pscustomobject]@{ From = 18000; To = 18100 }
)
$ExtraBackendPorts = @(8080)

function Write-Section([string]$Title) {
    Write-Host ''
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
    Write-Host " $Title" -ForegroundColor Cyan
    Write-Host ('=' * 72) -ForegroundColor DarkCyan
}

function Write-Result([bool]$Ok, [string]$Text) {
    $mark = if ($Ok) { '[OK]' } else { '[--]' }
    $color = if ($Ok) { 'Green' } else { 'DarkGray' }
    Write-Host "  $mark $Text" -ForegroundColor $color
}

function Test-IsAdmin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $p = New-Object Security.Principal.WindowsPrincipal($id)
    return $p.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Ask-YesNo([string]$Question, [string]$Default = 'n') {
    if ($Yes) { return $true }
    $suffix = if ($Default -eq 'y') { '[Y/n]' } else { '[y/N]' }
    while ($true) {
        Write-Host "$Question $suffix " -NoNewline
        $key = [Console]::ReadKey($true)
        $ans = [string]$key.KeyChar
        if ($key.Key -eq [ConsoleKey]::Enter) { $ans = $Default }
        Write-Host $ans
        switch ($ans.Trim().ToLowerInvariant()) {
            'y' { return $true }
            'yes' { return $true }
            'n' { return $false }
            'no' { return $false }
        }
        Write-Host 'Please press y or n.' -ForegroundColor Yellow
    }
}

function Read-ActionChoice {
    while ($true) {
        Write-Host 'Your choice [y/s/d/n]: ' -NoNewline
        $key = [Console]::ReadKey($true)
        $choice = ([string]$key.KeyChar).Trim().ToLowerInvariant()
        Write-Host $choice
        if ($choice -in @('y', 's', 'd', 'n')) { return $choice }
        Write-Host 'Please press y, s, d, or n. There is no default action.' -ForegroundColor Yellow
    }
}

function Add-UniqueItem([System.Collections.ArrayList]$List, [object]$Item, [string]$Key) {
    foreach ($x in $List) {
        if ([string]$x.$Key -eq [string]$Item.$Key) { return }
    }
    [void]$List.Add($Item)
}

function Get-KnownTokens {
    @(
        $ProductNames,
        $InstallFolderNames,
        $BackendProductNames,
        $BundleIds,
        'superautocutvideo',
        'super-auto-cut-video',
        'super_auto_cut_backend'
    ) | ForEach-Object { $_ } | Where-Object { $_ } | Sort-Object -Unique
}

function Test-IsAppText([string]$Text) {
    if ([string]::IsNullOrWhiteSpace($Text)) { return $false }
    $lower = $Text.ToLowerInvariant()
    foreach ($token in Get-KnownTokens) {
        if ($lower.Contains(([string]$token).ToLowerInvariant())) { return $true }
    }
    return $false
}

function Get-ProcessPathSafe($Process) {
    try { return $Process.Path } catch { return $null }
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try {
        $p = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId" -ErrorAction SilentlyContinue
        if ($p) { return [string]$p.CommandLine }
    } catch {}
    return $null
}

function Scan-Processes {
    $items = New-Object System.Collections.ArrayList
    $certainNames = @($MainExeNames + $BackendExeNames) | Sort-Object -Unique
    foreach ($name in $certainNames) {
        $base = [IO.Path]::GetFileNameWithoutExtension($name)
        Get-Process -Name $base -ErrorAction SilentlyContinue | ForEach-Object {
            Add-UniqueItem $items ([pscustomobject]@{
                Kind = 'Process'
                Name = "$($_.ProcessName).exe"
                Id = $_.Id
                Path = Get-ProcessPathSafe $_
                CommandLine = Get-ProcessCommandLine $_.Id
                Ambiguous = $false
            }) 'Id'
        }
    }
    foreach ($name in $AmbiguousProcessNames) {
        $base = [IO.Path]::GetFileNameWithoutExtension($name)
        Get-Process -Name $base -ErrorAction SilentlyContinue | ForEach-Object {
            $path = Get-ProcessPathSafe $_
            $cmd = Get-ProcessCommandLine $_.Id
            if (Test-IsAppText "$path $cmd") {
                Add-UniqueItem $items ([pscustomobject]@{
                    Kind = 'Process'
                    Name = "$($_.ProcessName).exe"
                    Id = $_.Id
                    Path = $path
                    CommandLine = $cmd
                    Ambiguous = $true
                }) 'Id'
            }
        }
    }
    return @($items)
}

function Get-DefaultInstallDirs {
    $items = New-Object System.Collections.ArrayList
    $roots = @(
        [Environment]::GetFolderPath('ProgramFiles'),
        ${env:ProgramFiles(x86)},
        [Environment]::GetFolderPath('LocalApplicationData')
    ) | Where-Object { $_ }
    foreach ($root in $roots) {
        foreach ($folder in $InstallFolderNames) {
            Add-UniqueItem $items ([pscustomobject]@{
                Kind = 'InstallDir'
                Path = Join-Path $root $folder
                Desc = 'default install directory'
            }) 'Path'
        }
    }
    $machineRoots = @(
        [Environment]::GetFolderPath('ProgramFiles'),
        ${env:ProgramFiles(x86)}
    ) | Where-Object { $_ }
    foreach ($root in $machineRoots) {
        foreach ($folder in $LegacyMachineInstallFolderNames) {
            Add-UniqueItem $items ([pscustomobject]@{
                Kind = 'InstallDir'
                Path = Join-Path $root $folder
                Desc = 'legacy machine install directory'
            }) 'Path'
        }
    }
    return @($items)
}

function Get-RegistryInstallDirs {
    $items = New-Object System.Collections.ArrayList
    foreach ($product in $ProductNames) {
        $paths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$product",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$product",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$product"
        )
        foreach ($p in $paths) {
            try {
                if (-not (Test-Path -LiteralPath $p)) { continue }
                $props = Get-ItemProperty -LiteralPath $p -ErrorAction SilentlyContinue
                $raw = [string]$props.InstallLocation
                $raw = $raw.Trim('"')
                if ($raw) {
                    Add-UniqueItem $items ([pscustomobject]@{
                        Kind = 'InstallDir'
                        Path = $raw
                        Desc = 'install directory from registry'
                    }) 'Path'
                }
            } catch {}
        }
    }
    foreach ($manufacturer in $ManufacturerNames) {
        foreach ($product in $ProductNames) {
            $paths = @(
                "HKLM:\SOFTWARE\$manufacturer\$product",
                "HKLM:\SOFTWARE\WOW6432Node\$manufacturer\$product",
                "HKCU:\SOFTWARE\$manufacturer\$product"
            )
            foreach ($p in $paths) {
                try {
                    if (-not (Test-Path -LiteralPath $p)) { continue }
                    $raw = [string](Get-ItemProperty -LiteralPath $p -ErrorAction SilentlyContinue).'(default)'
                    $raw = $raw.Trim('"')
                    if ($raw) {
                        Add-UniqueItem $items ([pscustomobject]@{
                            Kind = 'InstallDir'
                            Path = $raw
                            Desc = 'install directory from manufacturer key'
                        }) 'Path'
                    }
                } catch {}
            }
        }
    }
    return @($items)
}

function Scan-Directories {
    $items = New-Object System.Collections.ArrayList
    foreach ($d in @(Get-DefaultInstallDirs) + @(Get-RegistryInstallDirs)) {
        if (Test-Path -LiteralPath $d.Path) { Add-UniqueItem $items $d 'Path' }
    }

    $local = [Environment]::GetFolderPath('LocalApplicationData')
    $roaming = [Environment]::GetFolderPath('ApplicationData')
    $temp = [IO.Path]::GetTempPath().TrimEnd('\')

    foreach ($bundleId in $BundleIds) {
        foreach ($root in @($roaming, $local)) {
            $p = Join-Path $root $bundleId
            if (Test-Path -LiteralPath $p) {
                Add-UniqueItem $items ([pscustomobject]@{
                    Kind = 'AppData'
                    Path = $p
                    Desc = "Tauri AppData ($bundleId)"
                }) 'Path'
            }
        }
    }

    foreach ($backendName in $BackendProductNames) {
        $p = Join-Path $local $backendName
        if (Test-Path -LiteralPath $p) {
            Add-UniqueItem $items ([pscustomobject]@{
                Kind = 'BackendData'
                Path = $p
                Desc = 'backend persistent data'
            }) 'Path'
        }
    }

    $tempItems = @(
        [pscustomobject]@{ Kind = 'Temp'; Path = (Join-Path $temp 'super_auto_cut_backend.log'); Desc = 'Rust backend startup log' },
        [pscustomobject]@{ Kind = 'Temp'; Path = (Join-Path $temp 'super_auto_cut_backend_py.log'); Desc = 'Python backend startup log' },
        [pscustomobject]@{ Kind = 'Temp'; Path = (Join-Path $temp 'super_auto_cut_backend_tmp'); Desc = 'backend temp directory' },
        [pscustomobject]@{ Kind = 'Temp'; Path = (Join-Path $temp 'MicrosoftEdgeWebview2Setup.exe'); Desc = 'WebView2 installer residue' },
        [pscustomobject]@{ Kind = 'Temp'; Path = (Join-Path $temp 'MicrosoftEdgeWebView2RuntimeInstaller.exe'); Desc = 'WebView2 offline installer residue' }
    )
    foreach ($x in $tempItems) {
        if (Test-Path -LiteralPath $x.Path) { Add-UniqueItem $items $x 'Path' }
    }
    return @($items)
}

function Scan-Registry {
    $items = New-Object System.Collections.ArrayList
    foreach ($product in $ProductNames) {
        $uninstallPaths = @(
            "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$product",
            "HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\$product",
            "HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall\$product"
        )
        foreach ($p in $uninstallPaths) {
            if (Test-Path -LiteralPath $p) {
                Add-UniqueItem $items ([pscustomobject]@{ Kind = 'RegKey'; Path = $p; Name = ''; Desc = 'uninstall entry' }) 'Path'
            }
        }
    }
    foreach ($manufacturer in $ManufacturerNames) {
        $paths = @(
            "HKLM:\SOFTWARE\$manufacturer",
            "HKLM:\SOFTWARE\WOW6432Node\$manufacturer",
            "HKCU:\SOFTWARE\$manufacturer"
        )
        foreach ($p in $paths) {
            if (Test-Path -LiteralPath $p) {
                Add-UniqueItem $items ([pscustomobject]@{ Kind = 'RegKey'; Path = $p; Name = ''; Desc = 'manufacturer key' }) 'Path'
            }
        }
    }
    $runKey = 'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Run'
    if (Test-Path -LiteralPath $runKey) {
        foreach ($product in $ProductNames) {
            try {
                $prop = Get-ItemProperty -LiteralPath $runKey -Name $product -ErrorAction SilentlyContinue
                if ($null -ne $prop) {
                    [void]$items.Add([pscustomobject]@{ Kind = 'RegValue'; Path = $runKey; Name = $product; Desc = 'autostart entry' })
                }
            } catch {}
        }
    }
    foreach ($bundleId in $BundleIds) {
        foreach ($p in @("HKLM:\SOFTWARE\Classes\$bundleId", "HKCU:\SOFTWARE\Classes\$bundleId")) {
            if (Test-Path -LiteralPath $p) {
                Add-UniqueItem $items ([pscustomobject]@{ Kind = 'RegKey'; Path = $p; Name = ''; Desc = 'deep link protocol' }) 'Path'
            }
        }
    }
    $wixRoots = @(
        'HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKLM:\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
        'HKCU:\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall'
    )
    foreach ($root in $wixRoots) {
        if (-not (Test-Path -LiteralPath $root)) { continue }
        Get-ChildItem -LiteralPath $root -ErrorAction SilentlyContinue | ForEach-Object {
            try {
                $props = Get-ItemProperty -LiteralPath $_.PSPath -ErrorAction SilentlyContinue
                $displayName = [string]$props.DisplayName
                $publisher = [string]$props.Publisher
                if ($ProductNames -contains $_.PSChildName) { return }
                if (($ProductNames -contains $displayName) -or (Test-IsAppText "$displayName $publisher")) {
                    Add-UniqueItem $items ([pscustomobject]@{ Kind = 'RegKey'; Path = $_.PSPath; Name = ''; Desc = 'legacy uninstall entry' }) 'Path'
                }
            } catch {}
        }
    }
    return @($items)
}

function Scan-Shortcuts {
    $items = New-Object System.Collections.ArrayList
    $locations = @(
        (Join-Path $env:PUBLIC 'Desktop'),
        (Join-Path $env:USERPROFILE 'Desktop'),
        (Join-Path $env:APPDATA 'Microsoft\Windows\Start Menu\Programs'),
        (Join-Path $env:ProgramData 'Microsoft\Windows\Start Menu\Programs')
    ) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
    foreach ($loc in $locations) {
        foreach ($product in $ProductNames) {
            $lnk = Join-Path $loc ($product + '.lnk')
            if (Test-Path -LiteralPath $lnk) {
                Add-UniqueItem $items ([pscustomobject]@{ Kind = 'Shortcut'; Path = $lnk; Desc = 'shortcut' }) 'Path'
            }
            $folder = Join-Path $loc $product
            if (Test-Path -LiteralPath $folder) {
                Add-UniqueItem $items ([pscustomobject]@{ Kind = 'Shortcut'; Path = $folder; Desc = 'start menu folder' }) 'Path'
            }
        }
    }
    return @($items)
}

function Scan-Ports {
    $items = New-Object System.Collections.ArrayList
    try {
        $listens = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue
    } catch {
        return @()
    }
    foreach ($c in $listens) {
        $port = [int]$c.LocalPort
        $hit = $ExtraBackendPorts -contains $port
        foreach ($r in $BackendPortRanges) {
            if ($port -ge $r.From -and $port -le $r.To) { $hit = $true; break }
        }
        if (-not $hit) { continue }
        $pid2 = [int]$c.OwningProcess
        if ($pid2 -le 0) { continue }
        $proc = Get-Process -Id $pid2 -ErrorAction SilentlyContinue
        if (-not $proc) { continue }
        $path = Get-ProcessPathSafe $proc
        $cmd = Get-ProcessCommandLine $pid2
        $isApp = Test-IsAppText "$path $cmd $($proc.Name)"
        $existing = @($items | Where-Object { $_.Id -eq $pid2 }) | Select-Object -First 1
        if ($existing) {
            if ($existing.Ports -notcontains $port) {
                $existing.Ports = @($existing.Ports + $port) | Sort-Object -Unique
            }
            continue
        }
        [void]$items.Add([pscustomobject]@{
            Kind = 'PortOccupier'
            Id = $pid2
            Name = $proc.Name
            Path = $path
            CommandLine = $cmd
            Ports = @($port)
            Ambiguous = (-not $isApp)
        })
    }
    return @($items)
}

function Get-DisplaySize([string]$Path) {
    try {
        $item = Get-Item -LiteralPath $Path -ErrorAction Stop
        if ($item.PSIsContainer) {
            $bytes = (Get-ChildItem -LiteralPath $Path -Recurse -Force -ErrorAction SilentlyContinue | Measure-Object Length -Sum).Sum
            if ($bytes) { return ('{0:N1} MB' -f ($bytes / 1MB)) }
            return '0 MB'
        }
        return ('{0:N1} KB' -f ($item.Length / 1KB))
    } catch {
        return ''
    }
}

function Print-ScanReport($Processes, $Directories, $Registry, $Shortcuts, $Ports) {
    Write-Section 'Scan result - no changes yet'
    Write-Host ("Products : {0}" -f ($ProductNames -join ' / ')) -ForegroundColor DarkGray
    Write-Host ("BundleIds: {0}" -f ($BundleIds -join ' / ')) -ForegroundColor DarkGray

    Write-Host ''
    Write-Host '--- Processes ---' -ForegroundColor Yellow
    if ($Processes.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray }
    foreach ($p in $Processes) {
        $tag = if ($p.Ambiguous) { '[path-hit]' } else { '[exact]' }
        $color = if ($p.Ambiguous) { 'DarkYellow' } else { 'Red' }
        Write-Host ("  {0} PID={1,-6} {2} path={3}" -f $tag, $p.Id, $p.Name, $p.Path) -ForegroundColor $color
    }

    Write-Host ''
    Write-Host '--- Directories / files ---' -ForegroundColor Yellow
    if ($Directories.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray }
    foreach ($d in $Directories) {
        $size = Get-DisplaySize $d.Path
        $suffix = if ($size) { " ($size)" } else { '' }
        Write-Host ("  [{0,-11}] {1}{2}" -f $d.Kind, $d.Path, $suffix) -ForegroundColor White
        Write-Host ("              -> {0}" -f $d.Desc) -ForegroundColor DarkGray
    }

    Write-Host ''
    Write-Host '--- Registry ---' -ForegroundColor Yellow
    if ($Registry.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray }
    foreach ($r in $Registry) {
        $suffix = if ($r.Kind -eq 'RegValue') { " [value: $($r.Name)]" } else { '' }
        Write-Host ("  [{0,-8}] {1}{2}" -f $r.Kind, $r.Path, $suffix) -ForegroundColor White
        Write-Host ("              -> {0}" -f $r.Desc) -ForegroundColor DarkGray
    }

    Write-Host ''
    Write-Host '--- Shortcuts ---' -ForegroundColor Yellow
    if ($Shortcuts.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray }
    foreach ($s in $Shortcuts) {
        Write-Host ("  [{0,-8}] {1}" -f $s.Kind, $s.Path) -ForegroundColor White
        Write-Host ("              -> {0}" -f $s.Desc) -ForegroundColor DarkGray
    }

    Write-Host ''
    Write-Host '--- Backend candidate ports ---' -ForegroundColor Yellow
    if ($Ports.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray }
    foreach ($p in $Ports) {
        $tag = if ($p.Ambiguous) { '[foreign]' } else { '[app]' }
        $color = if ($p.Ambiguous) { 'DarkYellow' } else { 'Red' }
        Write-Host ("  {0} ports={1,-18} PID={2,-6} {3} path={4}" -f $tag, ($p.Ports -join ','), $p.Id, $p.Name, $p.Path) -ForegroundColor $color
    }
}

function Stop-ProcessItems($Processes, [bool]$IncludeAmbiguous) {
    Write-Section 'Stop processes'
    if ($Processes.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray; return }
    foreach ($p in $Processes) {
        if ($p.Ambiguous -and -not $IncludeAmbiguous) {
            Write-Result $false ("Skip path-hit PID={0} {1}" -f $p.Id, $p.Name)
            continue
        }
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 250
            Write-Result $true ("Stopped PID={0} {1}" -f $p.Id, $p.Name)
        } catch {
            try {
                Start-Process -FilePath taskkill.exe -ArgumentList @('/F', '/PID', "$($p.Id)", '/T') -Wait -WindowStyle Hidden -ErrorAction Stop | Out-Null
                Write-Result (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) ("taskkill PID={0} {1}" -f $p.Id, $p.Name)
            } catch {
                Write-Result $false ("Failed PID={0} {1}: {2}" -f $p.Id, $p.Name, $_.Exception.Message)
            }
        }
    }
}

function Stop-PortItems($Ports, [bool]$IncludeForeign) {
    Write-Section 'Release ports'
    if ($Ports.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray; return }
    foreach ($p in $Ports) {
        if ($p.Ambiguous -and -not $IncludeForeign) {
            Write-Result $false ("Skip foreign PID={0} {1} ports={2}" -f $p.Id, $p.Name, ($p.Ports -join ','))
            continue
        }
        if (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) {
            Write-Result $true ("Already released PID={0} ports={1}" -f $p.Id, ($p.Ports -join ','))
            continue
        }
        try {
            Stop-Process -Id $p.Id -Force -ErrorAction Stop
            Start-Sleep -Milliseconds 250
            Write-Result $true ("Stopped PID={0} {1} ports={2}" -f $p.Id, $p.Name, ($p.Ports -join ','))
        } catch {
            try {
                Start-Process -FilePath taskkill.exe -ArgumentList @('/F', '/PID', "$($p.Id)", '/T') -Wait -WindowStyle Hidden -ErrorAction Stop | Out-Null
                Write-Result (-not (Get-Process -Id $p.Id -ErrorAction SilentlyContinue)) ("taskkill PID={0} ports={1}" -f $p.Id, ($p.Ports -join ','))
            } catch {
                Write-Result $false ("Failed PID={0}: {1}" -f $p.Id, $_.Exception.Message)
            }
        }
    }
}

function Safe-RemoveItem([string]$Path, [int]$Retries = 5) {
    if (-not $Path) { return $true }
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    for ($i = 1; $i -le $Retries; $i++) {
        try {
            Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
            return $true
        } catch {
            Start-Sleep -Milliseconds (350 * $i)
        }
    }
    return (-not (Test-Path -LiteralPath $Path))
}

function Safe-RemoveRegKey([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return $true }
    try {
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
        return $true
    } catch {
        return (-not (Test-Path -LiteralPath $Path))
    }
}

function Safe-RemoveRegValue([string]$Path, [string]$Name) {
    try {
        if (Test-Path -LiteralPath $Path) {
            Remove-ItemProperty -LiteralPath $Path -Name $Name -Force -ErrorAction SilentlyContinue
        }
        return $true
    } catch {
        return $false
    }
}

function Find-Uninstallers {
    $items = New-Object System.Collections.ArrayList
    foreach ($d in @(Get-RegistryInstallDirs) + @(Get-DefaultInstallDirs)) {
        $u = Join-Path $d.Path 'uninstall.exe'
        if (Test-Path -LiteralPath $u) { Add-UniqueItem $items ([pscustomobject]@{ Path = $u }) 'Path' }
    }
    return @($items)
}

function Invoke-Uninstallers {
    Write-Section 'Run official uninstallers'
    $uninstallers = Find-Uninstallers
    if ($uninstallers.Count -eq 0) {
        Write-Host '  (none)' -ForegroundColor DarkGray
        return
    }
    foreach ($u in $uninstallers) {
        if (-not (Ask-YesNo "Run silent uninstall: $($u.Path) ?" 'y')) { continue }
        try {
            $proc = Start-Process -FilePath $u.Path -ArgumentList @('/P', '/S') -Wait -PassThru -WindowStyle Hidden -ErrorAction Stop
            Write-Result $true ("uninstall.exe exit code: {0}" -f $proc.ExitCode)
        } catch {
            Write-Result $false ("uninstall.exe failed: {0}" -f $_.Exception.Message)
        }
    }
}

function Remove-Directories($Directories) {
    Write-Section 'Remove directories / files'
    if ($Directories.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray; return }
    foreach ($d in $Directories) {
        $ok = Safe-RemoveItem $d.Path
        Write-Result $ok ("{0} -- {1}" -f $d.Path, $d.Desc)
    }
}

function Remove-Registry($Registry) {
    Write-Section 'Remove registry entries'
    if ($Registry.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray; return }
    foreach ($r in $Registry) {
        if ($r.Kind -eq 'RegValue') {
            $ok = Safe-RemoveRegValue $r.Path $r.Name
            Write-Result $ok ("[value] {0}!{1} -- {2}" -f $r.Path, $r.Name, $r.Desc)
        } else {
            $ok = Safe-RemoveRegKey $r.Path
            Write-Result $ok ("[key] {0} -- {1}" -f $r.Path, $r.Desc)
        }
    }
}

function Remove-Shortcuts($Shortcuts) {
    Write-Section 'Remove shortcuts'
    if ($Shortcuts.Count -eq 0) { Write-Host '  (none)' -ForegroundColor DarkGray; return }
    foreach ($s in $Shortcuts) {
        $ok = Safe-RemoveItem $s.Path
        Write-Result $ok ("{0} -- {1}" -f $s.Path, $s.Desc)
    }
}

Write-Host ''
Write-Host '################################################################' -ForegroundColor Magenta
Write-Host '#  SuperAI Tauri cleanup tool' -ForegroundColor Magenta
Write-Host ("#  Product: {0}" -f ($ProductNames -join ' / ')) -ForegroundColor Magenta
Write-Host ("#  Bundle : {0}" -f ($BundleIds -join ' / ')) -ForegroundColor Magenta
Write-Host '################################################################' -ForegroundColor Magenta

if (-not (Test-IsAdmin)) {
    Write-Host ''
    Write-Host '[WARN] Not running as administrator. Program Files and HKLM cleanup may fail.' -ForegroundColor Yellow
    if (-not (Ask-YesNo 'Continue anyway?' 'n')) { exit 1 }
}

$processes = Scan-Processes
$directories = Scan-Directories
$registry = Scan-Registry
$shortcuts = Scan-Shortcuts
$ports = Scan-Ports

Print-ScanReport $processes $directories $registry $shortcuts $ports

if ($DryRun) {
    Write-Host ''
    Write-Host 'DryRun: no changes were made.' -ForegroundColor Green
    exit 0
}

$choice = 'n'
if ($Yes) {
    $choice = 'y'
} elseif ($StopOnly) {
    $choice = 'd'
} else {
    Write-Host ''
    Write-Host 'Choose an action:' -ForegroundColor Cyan
    Write-Host '  y : full cleanup' -ForegroundColor Cyan
    Write-Host '  s : ask per category' -ForegroundColor Cyan
    Write-Host '  d : stop processes / release ports only' -ForegroundColor Cyan
    Write-Host '  n : cancel' -ForegroundColor Cyan
    $choice = Read-ActionChoice
}

if ($choice -eq 'n') {
    Write-Host ''
    Write-Host 'Cancelled. No changes were made.' -ForegroundColor Yellow
    exit 0
}

$includeAmbiguous = $false
if (@($processes | Where-Object { $_.Ambiguous }).Count -gt 0) {
    $includeAmbiguous = Ask-YesNo 'Stop path-hit ffmpeg/WebView2/python processes too?' 'y'
}

$appPorts = @($ports | Where-Object { -not $_.Ambiguous })
$foreignPorts = @($ports | Where-Object { $_.Ambiguous })
$killForeignPorts = $false
if ($foreignPorts.Count -gt 0) {
    Write-Host ''
    Write-Host 'These port owners do not look app-owned and are skipped by default:' -ForegroundColor Yellow
    foreach ($p in $foreignPorts) {
        Write-Host ("  PID={0} {1} ports={2} path={3}" -f $p.Id, $p.Name, ($p.Ports -join ','), $p.Path) -ForegroundColor Yellow
    }
    $killForeignPorts = Ask-YesNo 'Force-stop these foreign port owners?' 'n'
}

Stop-ProcessItems $processes $includeAmbiguous
$portsToStop = @($appPorts)
if ($killForeignPorts) { $portsToStop += @($foreignPorts) }
Stop-PortItems $portsToStop $killForeignPorts

if ($choice -eq 'd') {
    Write-Host ''
    Write-Host 'Stop-only mode completed. Files and registry were not changed.' -ForegroundColor Green
    exit 0
}

$doDirs = $true
$doRegs = $true
$doShortcuts = $true
$doUninstaller = $true
if ($choice -eq 's') {
    $doUninstaller = Ask-YesNo 'Run official uninstall.exe first?' 'y'
    $doDirs = Ask-YesNo "Remove $($directories.Count) directories/files?" 'y'
    $doRegs = Ask-YesNo "Remove $($registry.Count) registry entries?" 'y'
    $doShortcuts = Ask-YesNo "Remove $($shortcuts.Count) shortcuts?" 'y'
}

if ($doUninstaller) { Invoke-Uninstallers }

$directories = Scan-Directories
$registry = Scan-Registry
$shortcuts = Scan-Shortcuts

if ($doDirs) { Remove-Directories $directories }
if ($doRegs) { Remove-Registry $registry }
if ($doShortcuts) { Remove-Shortcuts $shortcuts }

Write-Section 'Final verification'
$leftDirs = Scan-Directories
$leftRegs = Scan-Registry
$leftShortcuts = Scan-Shortcuts
$leftProcesses = Scan-Processes
$leftPorts = Scan-Ports
$leftPortsReported = @($leftPorts | Where-Object { -not $_.Ambiguous -or $killForeignPorts })

$allClean = (
    $leftDirs.Count -eq 0 -and
    $leftRegs.Count -eq 0 -and
    $leftShortcuts.Count -eq 0 -and
    $leftProcesses.Count -eq 0 -and
    $leftPortsReported.Count -eq 0
)

if ($allClean) {
    Write-Host '  OK: cleanup completed.' -ForegroundColor Green
} else {
    Write-Host '  Residue remains; reboot and run again if files are locked:' -ForegroundColor Yellow
    foreach ($x in $leftDirs) { Write-Host "    - [DIR ] $($x.Path)" -ForegroundColor Yellow }
    foreach ($x in $leftRegs) { Write-Host "    - [REG ] $($x.Path)" -ForegroundColor Yellow }
    foreach ($x in $leftShortcuts) { Write-Host "    - [LNK ] $($x.Path)" -ForegroundColor Yellow }
    foreach ($x in $leftProcesses) { Write-Host "    - [PROC] PID=$($x.Id) $($x.Name)" -ForegroundColor Yellow }
    foreach ($x in $leftPortsReported) { Write-Host "    - [PORT] PID=$($x.Id) $($x.Name) ports=$($x.Ports -join ',')" -ForegroundColor Yellow }
    if (@($leftPorts | Where-Object { $_.Ambiguous }).Count -gt 0 -and -not $killForeignPorts) {
        Write-Host '  Note: foreign port owners were intentionally skipped.' -ForegroundColor DarkGray
    }
}

Write-Host ''
Write-Host 'Done.' -ForegroundColor Green
exit 0
