@echo off
rem ============================================================
rem  SuperAI影视剪辑 Tauri 版本卸载清理脚本 (入口)
rem  - 无需安装 Python 即可直接双击运行
rem  - 自动请求管理员权限，自动切 UTF-8 代码页
rem  - 真正的扫描/确认/清理逻辑在同目录 cleanup_tauri.ps1
rem ============================================================

setlocal EnableExtensions EnableDelayedExpansion
chcp 65001 >nul 2>&1

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%cleanup_tauri.ps1"

if not exist "%PS1%" (
    echo [ERROR] 找不到 PowerShell 清理脚本: "%PS1%"
    pause
    exit /b 2
)

rem ---- 检查是否已具备管理员权限 ----
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo 需要管理员权限以清理 Program Files 下的安装目录和 HKLM 注册表项...
    echo 将尝试以管理员身份重新启动本脚本。
    powershell -NoProfile -ExecutionPolicy Bypass -Command ^
      "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b 0
)

rem ---- 以管理员身份调用 PowerShell 清理脚本 ----
powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
echo 清理脚本已结束，退出码: %RC%
pause
exit /b %RC%
