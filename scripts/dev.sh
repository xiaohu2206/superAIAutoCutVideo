#!/bin/bash

echo "========================================"
echo "  AI智能视频剪辑 - 开发环境启动脚本"
echo "========================================"
echo

# 检查是否在项目根目录
if [ ! -d "frontend" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "错误: 未找到 Node.js，请先安装 Node.js"
    exit 1
fi

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "错误: 未找到 Python，请先安装 Python"
    exit 1
fi

# 检查 Rust
if ! command -v cargo &> /dev/null; then
    echo "错误: 未找到 Rust，请先安装 Rust"
    exit 1
fi

echo "正在检查并安装依赖..."
echo

# 安装前端依赖
echo "[1/3] 安装前端依赖..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "正在安装前端依赖..."
    npm install
    if [ $? -ne 0 ]; then
        echo "错误: 前端依赖安装失败"
        exit 1
    fi
else
    echo "前端依赖已存在，跳过安装"
fi
cd ..

# 安装后端依赖
echo "[2/3] 检查后端依赖..."
cd backend

# 检查 Python 命令
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    PYTHON_CMD="python"
fi

# 检查是否已安装 fastapi
if ! $PYTHON_CMD -c "import fastapi" &> /dev/null; then
    echo "正在安装后端依赖..."
    $PYTHON_CMD -m pip install -r requirements.txt
    if [ $? -ne 0 ]; then
        echo "错误: 后端依赖安装失败"
        exit 1
    fi
else
    echo "后端依赖已存在，跳过安装"
fi
cd ..

# 构建 Tauri
echo "[3/3] 检查 Tauri 依赖..."
cd src-tauri
if [ ! -d "target" ]; then
    echo "正在构建 Tauri..."
    cargo build
    if [ $? -ne 0 ]; then
        echo "错误: Tauri 构建失败"
        exit 1
    fi
else
    echo "Tauri 已构建，跳过构建"
fi
cd ..

echo
echo "========================================"
echo "  依赖检查完成，启动开发环境..."
echo "========================================"
echo

# 启动开发环境
echo "正在启动 Tauri 开发环境..."
echo "这将自动启动:"
echo "  - Python FastAPI 后端 (端口 8000)"
echo "  - React 前端开发服务器 (端口 1420)"
echo "  - Tauri 桌面应用"
echo
echo "请等待应用启动..."

cd src-tauri
cargo tauri dev

echo
echo "开发环境已关闭"