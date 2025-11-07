@echo off
echo ========================================
echo   AI智能视频剪辑 - 开发环境启动脚本
echo ========================================
echo.

:: 检查是否在项目根目录
if not exist "frontend" (
    echo 错误: 请在项目根目录运行此脚本
    pause
    exit /b 1
)

:: 检查 Node.js
node --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Node.js，请先安装 Node.js
    pause
    exit /b 1
)

:: 检查 Python
python --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Python，请先安装 Python
    pause
    exit /b 1
)

:: 检查 Rust
cargo --version >nul 2>&1
if errorlevel 1 (
    echo 错误: 未找到 Rust，请先安装 Rust
    pause
    exit /b 1
)

echo 正在检查并安装依赖...
echo.

:: 安装前端依赖
echo [1/3] 安装前端依赖...
cd frontend
if not exist "node_modules" (
    echo 正在安装前端依赖...
    npm install
    if errorlevel 1 (
        echo 错误: 前端依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo 前端依赖已存在，跳过安装
)
cd ..

:: 安装后端依赖
echo [2/3] 检查后端依赖...
cd backend
pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo 正在安装后端依赖...
    pip install -r requirements.txt
    if errorlevel 1 (
        echo 错误: 后端依赖安装失败
        pause
        exit /b 1
    )
) else (
    echo 后端依赖已存在，跳过安装
)
cd ..

:: 构建 Tauri
echo [3/3] 检查 Tauri 依赖...
cd src-tauri
if not exist "target" (
    echo 正在构建 Tauri...
    cargo build
    if errorlevel 1 (
        echo 错误: Tauri 构建失败
        pause
        exit /b 1
    )
) else (
    echo Tauri 已构建，跳过构建
)
cd ..

echo.
echo ========================================
echo   依赖检查完成，启动开发环境...
echo ========================================
echo.

:: 启动开发环境
echo 正在启动 Tauri 开发环境...
echo 这将自动启动:
echo   - Python FastAPI 后端 (端口 8000)
echo   - React 前端开发服务器 (端口 1420)
echo   - Tauri 桌面应用
echo.
echo 请等待应用启动...

cd src-tauri
cargo tauri dev

echo.
echo 开发环境已关闭
pause