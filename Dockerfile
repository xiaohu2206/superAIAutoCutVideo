# AI智能视频剪辑应用 - Docker 配置
# 多阶段构建，优化镜像大小

# ========================================
# 阶段 1: 前端构建
# ========================================
FROM node:18-alpine AS frontend-builder

WORKDIR /app/frontend

# 复制前端依赖文件
COPY frontend/package*.json ./
COPY frontend/yarn.lock* ./

# 安装依赖
RUN npm ci --only=production

# 复制前端源码
COPY frontend/ ./

# 构建前端
RUN npm run build

# ========================================
# 阶段 2: 后端构建
# ========================================
FROM python:3.11-slim AS backend-builder

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    cmake \
    pkg-config \
    libopencv-dev \
    libavformat-dev \
    libavcodec-dev \
    libavdevice-dev \
    libavutil-dev \
    libswscale-dev \
    libswresample-dev \
    libavfilter-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app/backend

# 复制后端依赖文件
COPY backend/requirements.txt ./

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端源码
COPY backend/ ./

# ========================================
# 阶段 3: 生产镜像
# ========================================
FROM python:3.11-slim AS production

# 安装运行时依赖
RUN apt-get update && apt-get install -y \
    libopencv-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 创建应用用户
RUN useradd --create-home --shell /bin/bash app

WORKDIR /app

# 从构建阶段复制文件
COPY --from=backend-builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin
COPY --from=backend-builder /app/backend ./backend
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# 创建必要的目录
RUN mkdir -p /app/temp /app/output /app/data /app/logs

# 设置权限
RUN chown -R app:app /app

# 切换到应用用户
USER app

# 设置环境变量
ENV PYTHONPATH=/app/backend
ENV BACKEND_HOST=0.0.0.0
ENV BACKEND_PORT=8000
ENV TEMP_DIR=/app/temp
ENV OUTPUT_DIR=/app/output
ENV LOG_LEVEL=INFO

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]