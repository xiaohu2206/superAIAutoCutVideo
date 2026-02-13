@echo off
echo ========================================
echo   AI智能视频剪辑 - 生产环境打包脚本
echo ========================================
echo.

:: 检查是否在项目根目录
if not exist "frontend" (
    echo 错误: 请在项目根目录运行此脚本
    pause
    exit /b 1
)

:: 检查必要工具
echo 正在检查构建环境...

:: 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Node.js
    pause
    exit /b 1
)

:: 优先选择 cnpm（如不可用则回退 npm）
set PKG_MGR=cnpm
cnpm --version >nul 2>&1
if errorlevel 1 (
    set PKG_MGR=npm
    echo 提示: 未检测到 cnpm，回退使用 npm
)

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python
    pause
    exit /b 1
)

:: 检查 Rust
cargo --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Rust
    pause
    exit /b 1
)

:: 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
    if errorlevel 1 (
        echo 错误: PyInstaller 安装失败
        pause
        exit /b 1
    )
)

echo 构建环境检查完成
echo.

:: 清理之前的构建
echo [1/4] 清理之前的构建文件...
if exist "backend\dist" rmdir /s /q "backend\dist"
if exist "backend\build" rmdir /s /q "backend\build"
if exist "src-tauri\target\release" rmdir /s /q "src-tauri\target\release"
if exist "src-tauri\resources\superAutoCutVideoBackend.exe" del "src-tauri\resources\superAutoCutVideoBackend.exe"

:: 构建前端
echo [2/4] 构建前端...
cd frontend
if not exist "node_modules" (
    echo 安装前端依赖...
    %PKG_MGR% install
    if errorlevel 1 (
        echo 依赖安装失败，尝试再次安装...
        %PKG_MGR% install
        if errorlevel 1 (
            echo 错误: 前端依赖安装失败
            pause
            exit /b 1
        )
    )
)
%PKG_MGR% run build
if errorlevel 1 (
    echo 错误: 前端构建失败
    pause
    exit /b 1
)
cd ..

set VARIANTS=cpu gpu
for %%V in (%VARIANTS%) do (
    call :buildVariant %%V
)

echo.
echo ========================================
echo   构建完成！
echo ========================================
echo.
echo 输出文件位置:
echo   CPU 安装包: src-tauri\target\release\dist\cpu\installers\
echo   GPU 安装包: src-tauri\target\release\dist\gpu\installers\
echo.
echo 后端可执行文件: backend\dist\superAutoCutVideoBackend.exe
echo.

:: 显示文件大小
if exist "src-tauri\target\release\SuperAIAutoCutVideo.exe" (
    echo 应用大小:
    dir "src-tauri\target\release\SuperAIAutoCutVideo.exe" | findstr "SuperAIAutoCutVideo.exe"
)

echo.
echo 构建完成！
pause
exit /b 0

:buildVariant
set VARIANT=%1
echo [3/4] 打包后端 (%VARIANT%)...
cd backend
echo 安装后端依赖...
if exist "requirements.runtime.txt" (
    echo 使用精简运行时依赖 requirements.runtime.txt（排除 qwen-tts 以避免解析冲突）
    powershell -NoProfile -Command "(Get-Content 'requirements.runtime.txt') | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content 'requirements.runtime.filtered.txt'"
    pip install -r requirements.runtime.filtered.txt
    del /f /q requirements.runtime.filtered.txt 2>nul
    if errorlevel 1 (
        echo 错误: 后端依赖安装失败
        pause
        exit /b 1
    )
) else (
    powershell -NoProfile -Command "(Get-Content 'requirements.txt') | Where-Object { $_ -notmatch '^\s*qwen-tts\s*$' } | Set-Content 'requirements.full.filtered.txt'"
    pip install -r requirements.full.filtered.txt
    del /f /q requirements.full.filtered.txt 2>nul
    if errorlevel 1 (
        echo 错误: 后端依赖安装失败
        pause
        exit /b 1
    )
)
pip show opencv-python >nul 2>&1
if errorlevel 1 (
    echo 安装 OpenCV 依赖...
    pip install opencv-python
    if errorlevel 1 (
        echo 错误: OpenCV 安装失败
        pause
        exit /b 1
    )
)
pip show python-multipart >nul 2>&1
if errorlevel 1 (
    echo 安装 python-multipart 依赖...
    pip install python-multipart
    if errorlevel 1 (
        echo 错误: python-multipart 安装失败
        pause
        exit /b 1
    )
)
pip uninstall -y torchaudio
pip uninstall -y torch torchvision
if /I "%VARIANT%"=="cpu" (set "SUFFIX=cpu") else (set "SUFFIX=cu128")
set "TORCH_WHL=%TORCH_WHEEL_DIR%\torch-2.7.1+%SUFFIX%-cp311-cp311-win_amd64.whl"
set "VISION_WHL=%TORCH_WHEEL_DIR%\torchvision-0.22.1+%SUFFIX%-cp311-cp311-win_amd64.whl"
if defined TORCH_WHEEL_DIR if exist "%TORCH_WHL%" if exist "%VISION_WHL%" (
    echo 使用本地轮子安装 PyTorch (%SUFFIX%)
    pip install --no-deps --no-index --find-links "%TORCH_WHEEL_DIR%" "%TORCH_WHL%" "%VISION_WHL%"
) else (
    if /I "%VARIANT%"=="cpu" (
        pip install --no-deps torch==2.7.1+cpu torchvision==0.22.1+cpu --index-url https://download.pytorch.org/whl/cpu
    ) else (
        pip install --no-deps torch==2.7.1+cu128 torchvision==0.22.1+cu128 --index-url https://download.pytorch.org/whl/cu128
    )
)
if /I "%VARIANT%"=="cpu" (
    pip install --no-deps torchaudio==2.7.1+cpu --index-url https://download.pytorch.org/whl/cpu
) else (
    pip install --no-deps torchaudio==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
)
echo 安装 qwen-tts（不解析依赖）
pip install qwen-tts --no-deps
if exist "dist" rmdir /s /q "dist"
pyinstaller backend.spec
if errorlevel 1 (
    echo 错误: 后端打包失败
    pause
    exit /b 1
)
echo 复制后端可执行文件...
if not exist "..\src-tauri\resources" mkdir "..\src-tauri\resources"
copy /y "dist\superAutoCutVideoBackend.exe" "..\src-tauri\resources\"
if errorlevel 1 (
    echo 错误: 复制后端可执行文件失败
    pause
    exit /b 1
)
rem 复制 FFmpeg 到资源目录（优先 Chocolatey，其次 PATH）
for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem \"C:\ProgramData\chocolatey\lib\ffmpeg*\" -Recurse -Include ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1 | %{$_.FullName}"') do set "FFMPEG_EXE=%%I"
for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem \"C:\ProgramData\chocolatey\lib\ffmpeg*\" -Recurse -Include ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1 | %{$_.FullName}"') do set "FFPROBE_EXE=%%I"
if not defined FFMPEG_EXE for /f "delims=" %%I in ('where ffmpeg 2^>nul') do set "FFMPEG_EXE=%%I"
if not defined FFPROBE_EXE for /f "delims=" %%I in ('where ffprobe 2^>nul') do set "FFPROBE_EXE=%%I"
if not defined FFMPEG_EXE if exist "%ProgramData%\chocolatey\bin\choco.exe" (
    echo 尝试通过 Chocolatey 安装 FFmpeg...
    choco install ffmpeg -y --no-progress
    for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem \"C:\ProgramData\chocolatey\lib\ffmpeg*\" -Recurse -Include ffmpeg.exe -ErrorAction SilentlyContinue | Select-Object -First 1 | %{$_.FullName}"') do set "FFMPEG_EXE=%%I"
    for /f "delims=" %%I in ('powershell -NoProfile -Command "Get-ChildItem \"C:\ProgramData\chocolatey\lib\ffmpeg*\" -Recurse -Include ffprobe.exe -ErrorAction SilentlyContinue | Select-Object -First 1 | %{$_.FullName}"') do set "FFPROBE_EXE=%%I"
)
if defined FFMPEG_EXE copy /y "%FFMPEG_EXE%" "..\src-tauri\resources\ffmpeg.exe"
if defined FFPROBE_EXE copy /y "%FFPROBE_EXE%" "..\src-tauri\resources\ffprobe.exe"
if not defined FFMPEG_EXE echo 提示: 未发现 ffmpeg.exe，应用可能无法使用部分音视频功能
if not defined FFPROBE_EXE echo 提示: 未发现 ffprobe.exe，应用可能无法使用部分音视频功能
cd ..
if exist "src-tauri\target\release" rmdir /s /q "src-tauri\target\release"
echo [4/4] 构建 Tauri 应用 (%VARIANT%)...
cd src-tauri
cargo tauri build
if errorlevel 1 (
    echo 错误: Tauri 应用构建失败
    pause
    exit /b 1
)
cd ..
call :collectArtifacts %VARIANT%
exit /b 0

:collectArtifacts
set VARIANT=%1
set DIST_DIR=src-tauri\target\release\dist\%VARIANT%
if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if not exist "%DIST_DIR%\installers" mkdir "%DIST_DIR%\installers"
for %%F in (src-tauri\target\release\bundle\nsis\*.exe) do (
    copy /y "%%F" "%DIST_DIR%\installers\%%~nF_%VARIANT%%%~xF"
)
for %%F in (src-tauri\target\release\bundle\msi\*.msi) do (
    copy /y "%%F" "%DIST_DIR%\installers\%%~nF_%VARIANT%%%~xF"
)
exit /b 0
