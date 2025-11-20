#!/usr/bin/env bash
set -euo pipefail

# 将 backend/.venv/bin 置于 PATH 前，确保 `python` 指向虚拟环境解释器
ROOT_DIR="$(cd "$(dirname "$0")"/.. && pwd)"
VENV_BIN="$ROOT_DIR/backend/.venv/bin"

if [ ! -x "$VENV_BIN/python" ]; then
  echo "[ERR] 未发现 $VENV_BIN/python，请先创建虚拟环境并安装依赖"
  echo "      python3 -m venv backend/.venv"
  echo "      backend/.venv/bin/pip install -r backend/requirements.txt"
  exit 1
fi

export PATH="$VENV_BIN:$PATH"
echo "[OK] PATH 已注入：$VENV_BIN"
echo "[OK] Python 指向：$(which python)"
echo "[OK] Python 版本：$(python -V)"

# 如果本机已安装 Tauri CLI 和 Cargo，直接进入开发模式
if command -v cargo >/dev/null 2>&1; then
  if command -v tauri >/dev/null 2>&1; then
    (cd "$ROOT_DIR" && cargo tauri dev)
  else
    echo "[ERR] 未安装 tauri CLI。可选安装：npm i -g @tauri-apps/cli 或 cargo install tauri-cli"
    exit 2
  fi
else
  echo "[ERR] 未检测到 Cargo。请安装 Rust 工具链（如：brew install rustup-init && rustup-init）"
  echo "      然后运行：rustup default stable && cargo tauri dev"
  exit 3
fi