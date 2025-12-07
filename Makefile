# AI智能视频剪辑应用 - Makefile
# 简化开发和部署命令

.PHONY: help install dev build clean test lint format docker-dev docker-build docker-up docker-down

# 默认目标
help:
	@echo "AI智能视频剪辑应用 - 可用命令:"
	@echo ""
	@echo "开发命令:"
	@echo "  install     - 安装所有依赖"
	@echo "  dev         - 启动开发环境"
	@echo "  build       - 构建生产版本"
	@echo "  clean       - 清理构建文件"
	@echo ""
	@echo "代码质量:"
	@echo "  test        - 运行测试"
	@echo "  lint        - 代码检查"
	@echo "  format      - 代码格式化"
	@echo ""
	@echo "Docker 命令:"
	@echo "  docker-dev  - 启动开发环境 (Docker)"
	@echo "  docker-build- 构建 Docker 镜像"
	@echo "  docker-up   - 启动生产环境 (Docker)"
	@echo "  docker-down - 停止 Docker 服务"
	@echo ""
	@echo "其他命令:"
	@echo "  setup       - 初始化项目环境"
	@echo "  docs        - 生成文档"

# ========================================
# 开发命令
# ========================================

# 安装所有依赖
install:
	@echo "安装前端依赖..."
	cd frontend && npm install
	@echo "安装后端依赖..."
	cd backend && pip install -r requirements.txt
	@echo "安装 Tauri 依赖..."
	cd src-tauri && cargo build
	@echo "依赖安装完成!"

# 启动开发环境
dev:
	@echo "启动开发环境..."
ifeq ($(OS),Windows_NT)
	scripts\dev.bat
else
	./scripts/dev.sh
endif

# 构建生产版本
build:
	@echo "构建生产版本..."
ifeq ($(OS),Windows_NT)
	scripts\build.bat
else
	./scripts/build.sh
endif

# 清理构建文件
clean:
	@echo "清理构建文件..."
	rm -rf frontend/dist
	rm -rf frontend/node_modules
	rm -rf backend/__pycache__
	rm -rf backend/**/__pycache__
	rm -rf src-tauri/target
	rm -rf temp
	rm -rf output
	rm -rf logs
	@echo "清理完成!"

# ========================================
# 代码质量
# ========================================

# 运行测试
test:
	@echo "运行前端测试..."
	cd frontend && npm run test
	@echo "运行后端测试..."
	cd backend && python -m pytest
	@echo "测试完成!"

# 代码检查
lint:
	@echo "前端代码检查..."
	cd frontend && npm run lint
	@echo "后端代码检查..."
	cd backend && flake8 . --exclude .venv,__pycache__ --max-line-length 160
	cd backend && mypy .
	@echo "代码检查完成!"

# 代码格式化
format:
	@echo "格式化前端代码..."
	cd frontend && npm run format
	@echo "格式化后端代码..."
	cd backend && black .
	@echo "代码格式化完成!"

# ========================================
# Docker 命令
# ========================================

# 启动开发环境 (Docker)
docker-dev:
	@echo "启动 Docker 开发环境..."
	docker-compose -f docker-compose.dev.yml up -d
	@echo "开发环境已启动!"
	@echo "前端: http://localhost:1420"
	@echo "后端: http://localhost:8000"
	@echo "pgAdmin: http://localhost:5050"
	@echo "Redis Commander: http://localhost:8081"

# 构建 Docker 镜像
docker-build:
	@echo "构建 Docker 镜像..."
	docker build -t super-auto-cut-video:latest .
	@echo "镜像构建完成!"

# 启动生产环境 (Docker)
docker-up:
	@echo "启动 Docker 生产环境..."
	docker-compose up -d
	@echo "生产环境已启动!"
	@echo "应用: http://localhost:8000"

# 停止 Docker 服务
docker-down:
	@echo "停止 Docker 服务..."
	docker-compose down
	docker-compose -f docker-compose.dev.yml down
	@echo "Docker 服务已停止!"

# ========================================
# 其他命令
# ========================================

# 初始化项目环境
setup:
	@echo "初始化项目环境..."
	cp .env.example .env
	mkdir -p temp output logs data
	@echo "项目环境初始化完成!"
	@echo "请编辑 .env 文件配置您的环境变量"

# 生成文档
docs:
	@echo "生成文档..."
	cd backend && python -m pydoc -w .
	@echo "文档生成完成!"

# ========================================
# 快速启动命令
# ========================================

# 一键开发环境
quick-dev: setup install dev

# 一键生产构建
quick-build: clean install build

# 一键 Docker 开发
quick-docker: docker-build docker-dev
