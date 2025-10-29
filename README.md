# AI智能视频剪辑桌面应用

基于 React + Tauri + FastAPI 构建的跨平台智能视频处理桌面应用。

## 🚀 项目特性

- **跨平台支持**: 支持 Windows 和 macOS 平台
- **现代化技术栈**: React 18 + TypeScript + TailwindCSS + Tauri + Python FastAPI
- **实时通信**: HTTP API + WebSocket 双向通信
- **智能视频处理**: 基于 OpenCV + FFmpeg 的视频处理能力
- **美观界面**: 现代化 UI 设计，支持深色模式
- **一键打包**: 支持打包为独立的桌面应用程序

## 🏗️ 技术架构

```
React (前端)
    │  HTTP / WebSocket
    ▼
Tauri (Rust桥接)
    │  启动/停止Python后端
    ▼
Python FastAPI (后端)
    │  OpenCV / FFmpeg
    ▼
视频处理引擎
```

### 技术栈详情

**前端层 (React)**
- React 18 + TypeScript
- TailwindCSS + Lucide Icons
- Vite 构建工具
- 响应式设计

**桌面容器 (Tauri)**
- Rust 编写的轻量级容器
- 文件系统访问
- 进程管理
- 系统通知

**后端层 (Python FastAPI)**
- FastAPI 异步框架
- WebSocket 实时通信
- OpenCV 视频处理
- FFmpeg 媒体处理

## 📁 项目结构

```
superAutoCutVideoApp/
├─ frontend/                    # React 前端
│   ├─ src/
│   │   ├─ components/         # React 组件
│   │   │   ├─ Navigation.tsx  # 导航组件
│   │   │   ├─ VideoProcessor.tsx # 视频处理组件
│   │   │   ├─ StatusPanel.tsx # 状态面板
│   │   │   └─ SettingsPage.tsx # 设置页面
│   │   ├─ pages/              # 页面组件
│   │   ├─ api/                # API 客户端
│   │   │   └─ client.ts       # API 和 WebSocket 客户端
│   │   ├─ App.tsx             # 主应用组件
│   │   ├─ main.tsx            # 应用入口
│   │   └─ index.css           # 全局样式
│   ├─ package.json            # 前端依赖配置
│   ├─ vite.config.ts          # Vite 配置
│   ├─ tailwind.config.js      # TailwindCSS 配置
│   └─ tsconfig.json           # TypeScript 配置
│
├─ backend/                     # Python FastAPI 后端
│   ├─ main.py                 # FastAPI 应用入口
│   ├─ modules/                # 后端模块
│   │   ├─ __init__.py
│   │   └─ video_processor.py  # 视频处理模块
│   └─ requirements.txt        # Python 依赖
│
├─ src-tauri/                   # Tauri 容器配置
│   ├─ src/
│   │   └─ main.rs             # Tauri 主程序
│   ├─ resources/              # 资源文件目录
│   ├─ tauri.conf.json         # Tauri 配置
│   └─ Cargo.toml              # Rust 依赖配置
│
└─ README.md                    # 项目说明文档
```

## 🛠️ 开发环境搭建

### 前置要求

1. **Node.js** (>= 18.0.0)
2. **Python** (>= 3.8)
3. **Rust** (>= 1.70.0)
4. **FFmpeg** (系统环境变量)

### 安装依赖

1. **安装前端依赖**
```bash
cd frontend
npm install
```

2. **安装后端依赖**
```bash
cd backend
pip install -r requirements.txt
```

3. **安装 Tauri 依赖**
```bash
cd src-tauri
cargo build
```

## 🚀 运行项目

### 开发模式

1. **启动后端服务**
```bash
cd backend
python main.py
```

2. **启动前端开发服务器**
```bash
cd frontend
npm run dev
```

3. **启动 Tauri 开发模式**
```bash
cd src-tauri
cargo tauri dev
```

### 一键启动 (推荐)

```bash
# 在项目根目录执行
cargo tauri dev
```

Tauri 会自动：
- 启动 Python FastAPI 后端 (端口 8000)
- 启动 React 前端开发服务器 (端口 1420)
- 打开桌面应用窗口

## 📦 打包部署

### 开发环境打包

```bash
# 打包为桌面应用
cargo tauri build
```

### 生产环境打包

1. **打包 Python 后端**
```bash
cd backend
pyinstaller --onefile --name superAutoCutVideoBackend main.py
```

2. **复制后端可执行文件**
```bash
# Windows
copy backend/dist/superAutoCutVideoBackend.exe src-tauri/resources/

# macOS/Linux
cp backend/dist/superAutoCutVideoBackend src-tauri/resources/
```

3. **打包 Tauri 应用**
```bash
cargo tauri build --release
```

### 输出文件

**Windows:**
- `src-tauri/target/release/bundle/msi/SuperAutoCutVideo_1.0.0_x64_en-US.msi`
- `src-tauri/target/release/bundle/nsis/SuperAutoCutVideo_1.0.0_x64-setup.exe`

**macOS:**
- `src-tauri/target/release/bundle/dmg/SuperAutoCutVideo_1.0.0_x64.dmg`
- `src-tauri/target/release/bundle/macos/SuperAutoCutVideo.app`

## 🔧 配置说明

### 端口配置

- **前端开发服务器**: `http://localhost:1420`
- **Python FastAPI 后端**: `http://127.0.0.1:8000`
- **WebSocket 连接**: `ws://127.0.0.1:8000/ws`

### 环境变量

```bash
# 后端配置
BACKEND_HOST=127.0.0.1
BACKEND_PORT=8000
DEBUG=true

# 前端配置
VITE_API_BASE_URL=http://127.0.0.1:8000
VITE_WS_URL=ws://127.0.0.1:8000/ws
```

## 🎯 功能演示

### 1. API 测试
- 点击 "调用后端API (HTTP)" 测试 HTTP 连接
- 返回 "Hello from FastAPI!" 消息

### 2. WebSocket 连接
- 点击 "连接WebSocket" 建立实时连接
- 每秒接收心跳消息和时间戳

### 3. 视频处理 (开发中)
- 文件选择和上传
- 处理参数配置
- 实时进度显示
- 结果预览和下载

## 🐛 常见问题

### 1. 后端启动失败
```bash
# 检查 Python 环境
python --version
pip list

# 重新安装依赖
pip install -r backend/requirements.txt
```

### 2. 前端编译错误
```bash
# 清理缓存
npm cache clean --force
rm -rf node_modules package-lock.json
npm install
```

### 3. Tauri 构建失败
```bash
# 更新 Rust
rustup update

# 清理构建缓存
cargo clean
cargo build
```

### 4. FFmpeg 未找到
```bash
# Windows (使用 Chocolatey)
choco install ffmpeg

# macOS (使用 Homebrew)
brew install ffmpeg

# Ubuntu/Debian
sudo apt update
sudo apt install ffmpeg
```

## 🤝 贡献指南

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 打开 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情。

## 🙏 致谢

- [Tauri](https://tauri.app/) - 现代化桌面应用框架
- [React](https://reactjs.org/) - 用户界面库
- [FastAPI](https://fastapi.tiangolo.com/) - 现代化 Python Web 框架
- [TailwindCSS](https://tailwindcss.com/) - 实用优先的 CSS 框架
- [OpenCV](https://opencv.org/) - 计算机视觉库
- [FFmpeg](https://ffmpeg.org/) - 多媒体处理工具

---

**SuperAutoCutVideo Team** © 2024