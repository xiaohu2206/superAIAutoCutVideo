# SuperAutoCutVideo 使用说明

轻量、跨平台的一站式智能视频处理桌面应用。支持多视频上传与合并、AI脚本与TTS配音、实时进度反馈，以及两遍响度标准化等能力。

## 环境要求

- Node.js ≥ 18
- Python ≥ 3.11
- Rust (Tauri 构建环境)
- FFmpeg（需在系统 PATH）

## 安装依赖

```bash
# 前端依赖
cd frontend
npm install

# 后端依赖
cd ../backend
pip install -r requirements.txt
```

## 启动应用

### 方式一：一键启动（推荐）

```bash
# 在项目根目录执行
cargo tauri dev
```

Tauri 将自动：
- 启动 Python FastAPI 后端（默认端口 8000）
- 启动 React 前端开发服务器（端口 1420）
- 打开桌面应用窗口

### 方式二：手动开发模式

```bash
# 启动后端（推荐使用此入口，包含端口占用检测等）
cd backend
python main.py

# 启动前端开发服务器（端口 1420）
cd ../frontend
npm run dev
```

访问地址与端口：
- 前端开发：`http://localhost:1420`
- 后端 API：`http://127.0.0.1:8000`
- WebSocket：`ws://127.0.0.1:8000/ws`

## 基本使用流程

1. 导入或拖拽视频到应用
2. 选择处理方式（剪辑、合并、响度标准化等）
3. 可选：生成 AI 脚本与 TTS 配音，并自动与视频片段对齐
4. 开始处理，在状态面板查看实时进度
5. 处理完成后导出成片

## API 快速测试

详细接口说明参考 `docs/backend_api_documentation.md`。常用示例：

```bash
# 服务状态
curl http://127.0.0.1:8000/api/status

# 创建视频处理任务（示例字段）
curl -X POST http://127.0.0.1:8000/api/video/process \
  -H "Content-Type: application/json" \
  -d '{
        "video_path": "test.mp4",
        "output_path": "output.mp4",
        "settings": {}
      }'
```

## 打包

```bash
# 打包桌面应用
cargo tauri build
```

如需打包单独的后端可执行文件，请参考 `README.md` 中的生产环境打包章节。

## 常见问题

- 后端端口占用：确保 `8000` 未被占用；必要时停止占用进程后重试。
- FFmpeg 未安装：macOS 使用 `brew install ffmpeg`；Windows 使用 Chocolatey 安装。
- 依赖安装慢或编译：建议使用 Python 3.11/3.12，便于命中预编译轮子。
- 前端端口冲突：Vite 端口固定为 `1420`（`vite.config.ts` 中可调整）。

## 参考文档

- 项目概览与快速开始：`README.md`
- 后端 API 文档：`docs/backend_api_documentation.md`
- 前端开发说明：`docs/FRONTEND_README.md`

## 许可证

MIT License