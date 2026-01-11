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

:: 打包后端
echo [3/4] 打包后端...
cd backend
echo 安装后端依赖...
if exist "requirements.runtime.txt" (
    echo 使用精简运行时依赖 requirements.runtime.txt
    pip install -r requirements.runtime.txt
    if errorlevel 1 (
        echo 错误: 后端依赖安装失败
        pause
        exit /b 1
    )
) else (
    pip install -r requirements.txt
    if errorlevel 1 (
        echo 错误: 后端依赖安装失败
        pause
        exit /b 1
    )
)
:: 确保打包包含 OpenCV
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
:: 确保表单上传支持
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
pyinstaller backend.spec
if errorlevel 1 (
    echo 错误: 后端打包失败
    pause
    exit /b 1
)

:: 复制后端可执行文件到 Tauri 资源目录
echo 复制后端可执行文件...
if not exist "..\src-tauri\resources" mkdir "..\src-tauri\resources"
copy "dist\superAutoCutVideoBackend.exe" "..\src-tauri\resources\"
if errorlevel 1 (
    echo 错误: 复制后端可执行文件失败
    pause
    exit /b 1
)
cd ..

:: 构建 Tauri 应用
echo [4/4] 构建 Tauri 应用...
cd src-tauri
cargo tauri build
if errorlevel 1 (
    echo 错误: Tauri 应用构建失败
    pause
    exit /b 1
)
cd ..

echo.
echo ========================================
echo   构建完成！
echo ========================================
echo.
echo 输出文件位置:
echo   Windows 安装包: src-tauri\target\release\bundle\msi\
echo   Windows 便携版: src-tauri\target\release\bundle\nsis\
echo   可执行文件: src-tauri\target\release\
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
