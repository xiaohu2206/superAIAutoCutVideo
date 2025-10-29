# 超级自动剪辑视频应用 - 使用说明

## 项目概述
这是一个基于AI的智能视频剪辑应用，支持自动场景检测、视频压缩、格式转换等功能。

## 技术栈
- **前端**: React + TypeScript + Vite + Tauri 2.x
- **后端**: Python + FastAPI + WebSocket
- **UI框架**: Tailwind CSS + Lucide Icons

## 快速开始

### 1. 环境要求
- Node.js 16+
- Python 3.8+
- Rust (用于Tauri桌面应用)

### 2. 安装依赖

#### 后端依赖
```bash
cd backend
pip install -r requirements.txt
```

#### 前端依赖
```bash
cd frontend
npm install
```

### 3. 运行应用

#### 方式一：Web版本（推荐用于开发和测试）
1. 启动后端服务：
```bash
cd backend
python -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload
```

2. 启动前端开发服务器：
```bash
cd frontend
npm run dev
```

3. 在浏览器中访问：http://localhost:1420

#### 方式二：桌面应用（需要完整的Rust构建环境）
```bash
cd frontend
npm run tauri dev
```

## 功能特性

### 已实现功能
- ✅ 视频文件选择和信息获取
- ✅ 实时WebSocket通信
- ✅ 视频处理任务管理
- ✅ 响应式UI界面
- ✅ 后端API服务
- ✅ 前后端状态同步

### 核心API端点
- `GET /` - 服务状态检查
- `GET /api/status` - 详细状态信息
- `POST /api/video/process` - 视频处理请求
- `GET /api/task/{task_id}` - 任务状态查询
- `WebSocket /ws` - 实时通信

## 开发状态

### 已完成
- [x] 前端TypeScript编译错误修复
- [x] Tauri配置从1.x升级到2.x
- [x] Web版本功能验证
- [x] 端到端功能测试

### 待完成
- [ ] Windows构建环境问题解决
- [ ] 完整的视频处理功能实现
- [ ] 更多视频格式支持

## 故障排除

### 常见问题
1. **端口1420被占用**: 停止其他使用该端口的服务
2. **后端连接失败**: 确保后端服务在8000端口正常运行
3. **Tauri构建失败**: 需要安装Visual Studio Build Tools或使用GNU工具链

### 测试命令
```bash
# 测试后端API
curl http://127.0.0.1:8000/api/status

# 测试视频处理端点
curl -X POST http://127.0.0.1:8000/api/video/process \
  -H "Content-Type: application/json" \
  -d '{"video_path":"test.mp4","output_path":"output.mp4","settings":{}}'
```

## 贡献指南
1. Fork项目
2. 创建功能分支
3. 提交更改
4. 发起Pull Request

## 许可证
MIT License