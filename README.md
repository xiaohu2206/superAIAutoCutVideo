<img src="frontend/src/assets/logo.png" alt="SuperAIAutoCutVideo Logo" width="120" />

# SuperAI·AutoCutVideo · AI智能视频剪辑
轻量、跨平台的一站式智能视频处理桌面应用，短剧、影视解说剪辑，开箱即用，目前只支持通过字幕自动剪辑。（免费）


## 软件版本
- <a href="https://github.com/xiaohu2206/superAIAutoCutVideo/releases/download/v1.0.2/superAIAutoCutVideo-1.0.2.zip">SuperAI-v1.0.2</a>

### 帮忙点个star，感谢兄弟 ❤❤❤
<img src="docs/image/addstar.png" alt="帮忙点个star，感谢兄弟" width="300" />

## 亮点特性
- 2026-01-14: 打包成 Windows 版本
- 2026-01-07：支持导出为剪映草稿
- 2025-12-14：添加电影解说控制输出篇幅（短篇、中篇、长偏 - 高级配置）
- 2025-12-14：加入电影解说
- 2025-12-13：加入大模型集合平台(openRouter)
- 支持腾讯tts、edge tts  
- 支持上传字幕文件（高级配置）
- 支持自定义提示词（高级配置）
- 自动提取视频字幕
- 短剧解说工作流：多集上传 → 自动合并 → 生成解说脚本（暂时只支持字幕分析） → 生成解说视频
- 多项目管理：支持创建、切换与独立配置


### 添加功能
1. 2026-01-22：edge-tts支持英文、错误日志
2. 2026-01-22：可配置（生成脚本条数、解说和原片的占比、生成脚本语言

### 解决问题
1. 对uploads的垃圾数据进行清理
2. 缓存目录uploads更新无效的问题
3. 打开应用启动了两个后端服务，导致更改uploads目录失败问题
4. 添加可以看到解析的字幕
5. 添加生成时间
6. 有时候生成的脚本不更新，一直是初次生成的脚本。
7. edge-tts试音添加loading
8. PC版本不会保存记录，间隔几个小时，打开需要重新配置
等等若干问题....


## 更新计划（持续更新优化中....
- 添加手动剪辑片头片尾
- 本地ASR识别字幕、多类型脚本风格
- 添加index tts
- 添加影视解说功能
- 添加 OCR 识别字幕
- 添加whisper提取字幕
- 添加视觉分析视频功能

## 文档与支持
- 打包说明：`docs/打包说明.md`


## 联系方式
<img src="docs/image/weixinqun.png" alt="微信码" width="300" />
- 微信群

<img src="docs/image/douyin.png" alt="抖音码" width="160" />
- 抖音号：`xiaohu_111`

- 微信号：`interest_dog`



## 快速开始
前置要求：`Node.js ≥ 18`、`Python ≥ 3.11`、`Rust`、`FFmpeg`


### Windows（PowerShell）
```powershell
# 安装前端依赖（优先使用 cnpm）
cd frontend
cnpm install

# 创建并使用后端虚拟环境（无需激活）
cd ..
py -3 -m venv backend\.venv
backend\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
backend\.venv\Scripts\python.exe backend\main.py

# 启动桌面应用
```

### macOS

```bash
# 安装前端依赖
cd frontend
cnpm install

# 创建并使用后端虚拟环境（可不激活）
cd ..
python3 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
backend/.venv/bin/python backend/main.py

```


## 说明

如果大家有不懂的或者想优化添加的功能请联系我，比如需要我录制教程视频都可以。现在版本还不稳定，没有做版本管理，还在断断续续更新中，不懂代码的用起来可能还有难度。

## 许可证

MIT

## 致谢

- Tauri · React · FastAPI · FFmpeg · OpenCV
