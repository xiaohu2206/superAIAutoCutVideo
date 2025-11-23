#!/bin/bash

echo "========================================"
echo "  AI智能视频剪辑 - 生产环境打包脚本"
echo "========================================"
echo

# 检查是否在项目根目录
if [ ! -d "frontend" ]; then
    echo "错误: 请在项目根目录运行此脚本"
    exit 1
fi

# 检查必要工具
echo "正在检查构建环境..."

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "错误: 未找到 Node.js"
    exit 1
fi

# 检查 Python
PYTHON_CMD="python3"
if ! command -v python3 &> /dev/null; then
    if ! command -v python &> /dev/null; then
        echo "错误: 未找到 Python"
        exit 1
    fi
    PYTHON_CMD="python"
fi

# 检查 Rust
if ! command -v cargo &> /dev/null; then
    echo "错误: 未找到 Rust"
    exit 1
fi

# 检查 PyInstaller
if ! $PYTHON_CMD -c "import PyInstaller" &> /dev/null; then
    echo "正在安装 PyInstaller..."
    $PYTHON_CMD -m pip install pyinstaller
    if [ $? -ne 0 ]; then
        echo "错误: PyInstaller 安装失败"
        exit 1
    fi
fi

echo "构建环境检查完成"
echo

# 清理之前的构建
echo "[1/4] 清理之前的构建文件..."
rm -rf backend/dist
rm -rf backend/build
rm -rf src-tauri/target/release
rm -f src-tauri/resources/superAutoCutVideoBackend

# 构建前端
echo "[2/4] 构建前端..."
cd frontend
if [ ! -d "node_modules" ]; then
    echo "安装前端依赖..."
    npm ci || {
        echo "npm ci 失败，尝试 npm install...";
        npm install || { echo "错误: 前端依赖安装失败"; exit 1; };
    }
fi
npm run build
if [ $? -ne 0 ]; then
    echo "错误: 前端构建失败"
    exit 1
fi
cd ..

# 打包后端
echo "[3/4] 打包后端..."
cd backend
$PYTHON_CMD -m pip install --upgrade pip >/dev/null 2>&1 || true
if [ -f "requirements.runtime.txt" ]; then
    echo "安装后端运行时依赖 requirements.runtime.txt..."
    $PYTHON_CMD -m pip install -r requirements.runtime.txt || { echo "错误: 后端依赖安装失败"; exit 1; }
elif [ -f "requirements.txt" ]; then
    echo "安装后端依赖 requirements.txt..."
    $PYTHON_CMD -m pip install -r requirements.txt || { echo "错误: 后端依赖安装失败"; exit 1; }
fi
$PYTHON_CMD -m PyInstaller --onefile --noconsole --name superAutoCutVideoBackend --distpath dist main.py
if [ $? -ne 0 ]; then
    echo "错误: 后端打包失败"
    exit 1
fi

# 复制后端可执行文件到 Tauri 资源目录
echo "复制后端可执行文件..."
mkdir -p ../src-tauri/resources
cp dist/superAutoCutVideoBackend ../src-tauri/resources/
if [ $? -ne 0 ]; then
    echo "错误: 复制后端可执行文件失败"
    exit 1
fi
cd ..

# 构建 Tauri 应用
echo "[4/4] 构建 Tauri 应用..."
cd src-tauri
cargo tauri build --release
if [ $? -ne 0 ]; then
    echo "错误: Tauri 应用构建失败"
    exit 1
fi
cd ..

echo
echo "========================================"
echo "  构建完成！"
echo "========================================"
echo
echo "输出文件位置:"

# 检测操作系统并显示相应的输出文件
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "  macOS 应用包: src-tauri/target/release/bundle/macos/"
    echo "  macOS 安装包: src-tauri/target/release/bundle/dmg/"
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "  Linux 应用包: src-tauri/target/release/bundle/appimage/"
    echo "  Debian 包: src-tauri/target/release/bundle/deb/"
fi

echo "  可执行文件: src-tauri/target/release/"
echo
echo "后端可执行文件: backend/dist/superAutoCutVideoBackend"
echo

# 显示文件大小
if [ -f "src-tauri/target/release/super-auto-cut-video" ]; then
    echo "应用大小:"
    ls -lh src-tauri/target/release/super-auto-cut-video | awk '{print $5 " " $9}'
fi

echo
echo "构建完成！"