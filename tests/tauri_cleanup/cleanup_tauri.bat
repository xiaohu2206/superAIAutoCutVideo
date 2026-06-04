@echo off
rem SuperAI Tauri cleanup entrypoint.
rem Switches to UTF-8, requests admin rights, then runs cleanup_tauri.ps1.

setlocal EnableExtensions
chcp 65001 >nul 2>&1

set "SCRIPT_DIR=%~dp0"
set "PS1=%SCRIPT_DIR%cleanup_tauri.ps1"

if not exist "%PS1%" (
    echo [ERROR] PowerShell cleanup script not found: "%PS1%"
    pause
    exit /b 2
)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator rights are required for Program Files and HKLM cleanup.
    echo Restarting this script with elevation...
    powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath '%~f0' -ArgumentList '%*' -Verb RunAs"
    exit /b 0
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%PS1%" %*
set "RC=%ERRORLEVEL%"

echo.
echo Cleanup script finished. Exit code: %RC%
pause
exit /b %RC%
