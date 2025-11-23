<img src="frontend/src/assets/logo.png" alt="SuperAIAutoCutVideo Logo" width="120" />

# SuperAIAutoCutVideo · AI智能视频剪辑

轻量、跨平台的一站式智能视频处理桌面应用，开箱即用，适合内容创作者和团队快速产出高质量视频。

## 亮点特性

- 多项目管理：支持创建、切换与独立配置
- 短剧解说工作流：多集上传 → 自动合并 → 生成解说脚本 → 生成解说视频
- AI 辅助脚本与配音，自动混流与响度标准化
- 支持多视频上传、合并与基础剪辑
- 实时进度反馈与双向通信（HTTP + WebSocket）
- 现代技术栈：React + TypeScript + Tauri + Python FastAPI + FFmpeg

## 更新计划

- 添加影视解说功能
- 添加视觉分析视频功能

## 快速开始

前置要求：`Node.js ≥ 18`、`Python ≥ 3.11`、`Rust`、`FFmpeg`

```bash
# 安装前端依赖
cd frontend && npm install

# 安装后端依赖
cd ../backend && pip install -r requirements.txt

# 回到项目根目录，一键启动桌面应用
cd .. && cargo tauri dev
```

## 打包

```bash
cargo tauri build
```

## 文档与支持

- 后端 API 文档：`docs/backend_api_documentation.md`
- 前端说明：`docs/FRONTEND_README.md`
- 使用指南：`USAGE.md`

## 许可证

MIT

## 致谢

- Tauri · React · FastAPI · FFmpeg · OpenCV