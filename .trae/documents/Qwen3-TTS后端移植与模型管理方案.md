# Qwen3-TTS 后端移植与模型管理方案

## 目标
- 在后端集成精简版 Qwen3-TTS（基于 12Hz Tokenizer 与 0.6B 模型），支持“语音合成”和“快速声音克隆”两类能力。
- 统一“模型存放路径与下载管理”，同时兼容“直接运行代码（开发模式）”与“打包成 Tauri 应用（生产模式）”。
- 提供 REST API 让用户可点击后台下载模型，或手动复制已下载模型到指定目录。

## 能力与模型
- Tokenizer：Qwen3-TTS-Tokenizer-12Hz（用于语音编码/解码与声音克隆参考特征）
- 模型（0.6B 版本，满足中低资源部署）：
  - Qwen3-TTS-12Hz-0.6B-Base：支持“3秒快速声音克隆”，亦可作为基础合成
  - Qwen3-TTS-12Hz-0.6B-CustomVoice：支持“预置高质量音色”和指令化风格控制
- 特性参考官方说明：支持多语言、非流/流式生成、指令控制与较强的鲁棒性

## 目录规划与路径约定
- 使用后端已有的用户数据目录约定（app_paths.py）作为模型根目录，确保用户可见且与 Tauri 打包兼容
  - macOS：`~/Library/Application Support/SuperAutoCutVideo`
  - Windows：`%LOCALAPPDATA%/SuperAutoCutVideo`
  - Linux：`$XDG_DATA_HOME/SuperAutoCutVideo` 或 `~/.local/share/SuperAutoCutVideo`
- 模型根目录：
  - `{user_data_dir}/models/Qwen/`
  - 其中包含以下子目录（用户可直接查看与手动复制）：
    - `Qwen3-TTS-Tokenizer-12Hz/`
    - `Qwen3-TTS-12Hz-0.6B-Base/`
    - `Qwen3-TTS-12Hz-0.6B-CustomVoice/`
- 可选环境变量覆盖（高级用户/运维）：`QWEN_TTS_MODELS_DIR` 优先于上述默认路径

## 依赖与安装
- 必需：
  - `torch`（项目已包含）
  - `transformers`（>=4.39，推荐）
  - `huggingface_hub`
  - `librosa`
  - `soundfile`
  - `numpy`（项目已包含）
- 可选（大陆网络推荐）：
  - `modelscope`
- 后端建议在 `requirements.txt` 与 `requirements.runtime.txt` 同步加入上述依赖

## 下载管理设计
- 目标：统一入口，支持两种下载方式与手动复制
  - 方式一（推荐海外）：Hugging Face
  - 方式二（推荐中国大陆）：ModelScope
  - 手动复制：用户自行下载后，将模型文件夹放到 `{user_data_dir}/models/Qwen/` 下
- 下载目录结构：
  - `Qwen3-TTS-Tokenizer-12Hz`（目录）
  - `Qwen3-TTS-12Hz-0.6B-Base`（目录）
  - `Qwen3-TTS-12Hz-0.6B-CustomVoice`（目录）
- 统一模型注册表（后端常量）：
  - `registry = { "tokenizer_12hz": {"hf": "Qwen/Qwen3-TTS-Tokenizer-12Hz", "ms": "Qwen/Qwen3-TTS-Tokenizer-12Hz", "local": "Qwen3-TTS-Tokenizer-12Hz"}, "base_0_6b": {"hf": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "ms": "Qwen/Qwen3-TTS-12Hz-0.6B-Base", "local": "Qwen3-TTS-12Hz-0.6B-Base"}, "custom_0_6b": {"hf": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "ms": "Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", "local": "Qwen3-TTS-12Hz-0.6B-CustomVoice"} }`

### 下载器实现建议
- Hugging Face（Python 方式）：
```python
from huggingface_hub import snapshot_download
def download_hf(repo_id: str, local_dir: str):
    snapshot_download(repo_id, local_dir=local_dir, local_files_only=False, allow_patterns=None)
```
- ModelScope（Python 方式）：
```python
from modelscope.hub.snapshot_download import snapshot_download
def download_modelscope(model_id: str, local_dir: str):
    snapshot_download(model_id, cache_dir=local_dir)
```
- 若需 CLI（网络策略/环境受限时），可在后端以子进程方式调用提供的命令，但推荐优先使用 Python 方式以便跨平台与权限控制。

## 后端 API 设计（仅后端逻辑）
- 路由前缀：`/api/tts/qwen3`
- `GET /models`
  - 返回本地已存在模型的状态与路径
  - 响应示例：
    - `[{ "key": "tokenizer_12hz", "path": ".../Qwen3-TTS-Tokenizer-12Hz", "exists": true }, { "key": "base_0_6b", "path": ".../Qwen3-TTS-12Hz-0.6B-Base", "exists": false }, ...]`
- `POST /models/download`
  - 请求体：`{ "key": "base_0_6b", "provider": "hf" | "modelscope" }`
  - 行为：后端启动下载到 `{user_data_dir}/models/Qwen/{registry[key].local}`，返回进度（建议结合 ws_manager 推送进度）
- `POST /models/validate`
  - 请求体：`{ "key": "base_0_6b" }`
  - 行为：检查该目录是否包含关键权重文件（例如 config、model、processor 等），返回布尔值与缺失项
- `GET /models/open-path?key=...`
  - 返回该模型本地路径字符串，供前端用 Tauri Shell 打开目录

## 模型加载与推理服务
- Vendor 代码建议：将精简后的 `qwen_tts` 包放置在 `backend/modules/vendor/qwen_tts`，避免深度耦合
- 服务类示意：
```python
from pathlib import Path
from backend.modules.app_paths import user_data_dir
from backend.modules.vendor.qwen_tts import Qwen3TTSTokenizer, Qwen3TTSModel

class Qwen3TTSPathManager:
    def __init__(self):
        base = Path(user_data_dir()) / "models" / "Qwen"
        self.paths = {
            "tokenizer_12hz": base / "Qwen3-TTS-Tokenizer-12Hz",
            "base_0_6b": base / "Qwen3-TTS-12Hz-0.6B-Base",
            "custom_0_6b": base / "Qwen3-TTS-12Hz-0.6B-CustomVoice",
        }
    def path(self, key: str) -> Path:
        return self.paths[key]

class Qwen3TTSService:
    def __init__(self, device: str = "cpu"):
        self.device = device
        self.pm = Qwen3TTSPathManager()
        self.tokenizer = None
        self.model = None
    def load_tokenizer(self):
        p = str(self.pm.path("tokenizer_12hz"))
        self.tokenizer = Qwen3TTSTokenizer.from_pretrained(p, device_map=self.device)
    def load_model(self, key: str):
        p = str(self.pm.path(key))
        m = Qwen3TTSModel.from_pretrained(p, device_map=self.device)
        self.model = m.model
        self.processor = m.processor
    def synthesize(self, text: str, language: str = "Chinese", speaker: str | None = None):
        inputs = self.processor(text=[text])
        out = self.model.generate(
            input_ids=[inputs["input_ids"]],
            languages=[language],
            speakers=[speaker],
            non_streaming_mode=True,
            max_new_tokens=2048,
            do_sample=True,
            top_k=50, top_p=1.0, temperature=0.9,
        )
        # 依据返回结构取出音频（具体以模型版本为准）
        # 返回值建议保存为 wav 并给前端路径或直接字节流
        return out
    def clone_voice(self, ref_wav_path: str, text: str, language: str = "Chinese"):
        # 1) 使用 12Hz Tokenizer 对参考音频编码，得到 voice clone 所需的 embedding / codes
        enc = self.tokenizer.encode([ref_wav_path])
        # 2) 组装 voice_clone_prompt（以当前模型 API 为准，示意）
        voice_clone_prompt = {
            "ref_spk_embedding": [enc.audio_codes] if hasattr(enc, "audio_codes") else [],
            "x_vector_only_mode": [True],
            "icl_mode": [False],
            "ref_code": [None],
        }
        inputs = self.processor(text=[text])
        out = self.model.generate(
            input_ids=[inputs["input_ids"]],
            languages=[language],
            speakers=[None],
            voice_clone_prompt=voice_clone_prompt,
            non_streaming_mode=True,
        )
        return out
```
- 说明：
  - Base/CustomVoice 的差异在于是否按“预置音色”与“指令控制”使用；声音克隆流程需 Tokenizer 编码参考音频。
  - 具体 `generate` 返回结构与 `voice_clone_prompt` 字段以官方版本为准（可能随版本演进微调）。

## 开发/生产兼容策略（Tauri）
- 模型始终存放于用户数据目录，不打包进应用，避免体积与更新问题
- 首次运行（开发或打包）：
  - 后端通过 `/models` 检查模型存在性，缺失则让前端展示下载入口
  - 下载进度可通过 WebSocket（ws_manager）推送，或轮询
- 打包后行为一致：路径不变，用户可在系统文件管理器中查看与备份

## 错误处理与回退
- 下载失败：
  - 自动切换 Provider（例如 Hugging Face -> ModelScope）
  - 返回标准错误码与详细日志（runtime_log_store）
- 模型加载失败：
  - 返回缺失文件提示与“打开目录”指引（GET /models/open-path）
- 资源限制：
  - GPU 不可用时自动使用 CPU（device_map="cpu"），提示性能影响

## 使用流程（面向后端）
1) 安装依赖（建议在两个 requirements 文件同步添加 transformers、huggingface_hub、librosa、soundfile、modelscope）
2) 在前端提供 UI 按钮调用 `POST /api/tts/qwen3/models/download`
3) 用户也可手动下载并复制目录到 `{user_data_dir}/models/Qwen/`
4) 通过 `GET /api/tts/qwen3/models` 验证路径与状态
5) 在 `tts_service.py` 中按需初始化 `Qwen3TTSService` 并调用 `synthesize` 或 `clone_voice`

## API 示例
- 列出模型状态：
```http
GET /api/tts/qwen3/models
```
- 下载模型（Hugging Face）：
```http
POST /api/tts/qwen3/models/download
Content-Type: application/json
{ "key": "base_0_6b", "provider": "hf" }
```
- 下载模型（ModelScope）：
```http
POST /api/tts/qwen3/models/download
Content-Type: application/json
{ "key": "custom_0_6b", "provider": "modelscope" }
```
- 验证模型：
```http
POST /api/tts/qwen3/models/validate
Content-Type: application/json
{ "key": "tokenizer_12hz" }
```
- 打开模型路径：
```http
GET /api/tts/qwen3/models/open-path?key=tokenizer_12hz
```

## 用户侧下载命令（文档用途）
- ModelScope（中国大陆推荐）：
```
pip install -U modelscope
modelscope download --model Qwen/Qwen3-TTS-Tokenizer-12Hz  --local_dir ./Qwen3-TTS-Tokenizer-12Hz
modelscope download --model Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice --local_dir ./Qwen3-TTS-12Hz-0.6B-CustomVoice
modelscope download --model Qwen/Qwen3-TTS-12Hz-0.6B-Base --local_dir ./Qwen3-TTS-12Hz-0.6B-Base
```
- Hugging Face：
```
pip install -U "huggingface_hub[cli]"
huggingface-cli download Qwen/Qwen3-TTS-Tokenizer-12Hz --local-dir ./Qwen3-TTS-Tokenizer-12Hz
huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice --local-dir ./Qwen3-TTS-12Hz-0.6B-CustomVoice
huggingface-cli download Qwen/Qwen3-TTS-12Hz-0.6B-Base --local-dir ./Qwen3-TTS-12Hz-0.6B-Base
```

## 已完成清单（实现落地）
- [x] Qwen3-TTS vendor 接入：`backend/modules/vendor/qwen_tts/__init__.py` 负责定位并导入 `qwen_tts`
- [x] 模型注册表与路径管理：`backend/modules/qwen3_tts_model_manager.py`
  - [x] 默认目录 `{user_data_dir}/models/Qwen/`，支持环境变量 `QWEN_TTS_MODELS_DIR` 覆盖
  - [x] 模型目录完整性校验（按 tokenizer / base / custom 规则检查关键文件）
  - [x] 支持 Hugging Face / ModelScope 两种下载方式
  - [x] 修复 ModelScope 下载目录不一致问题（下载产物复制到目标目录）
- [x] 推理服务封装：`backend/modules/qwen3_tts_service.py`
  - [x] 懒加载模型 + 并发加载锁（避免并发请求重复加载）
  - [x] 支持 CustomVoice（需要 `speaker`）与 VoiceClone（需要 `ref_audio`）两种合成路径
  - [x] 输出 wav 文件（`soundfile` 写盘），返回时长与采样率
- [x] Qwen3-TTS 模型管理 API：`backend/routes/qwen3_tts_routes.py`
  - [x] `GET /api/tts/qwen3/models`：列出本地模型状态（含 valid/missing）
  - [x] `POST /api/tts/qwen3/models/validate`：校验模型目录完整性
  - [x] `POST /api/tts/qwen3/models/download`：下载模型并通过 WebSocket 推送进度（scope=`qwen3_tts_models`）
  - [x] `GET /api/tts/qwen3/models/open-path`：返回本地路径供前端打开目录
- [x] 路由注册：`backend/main.py` 已 include `qwen3_tts_router`
- [x] TTS 统一入口集成：`backend/modules/tts_service.py` 增加 `provider == "qwen3_tts"` 分支
- [x] 音色试听支持：`backend/routes/tts_routes.py` 增加 `provider == "qwen3_tts"` 试听合成并返回预览链接
- [x] 克隆音色存储（文件型 JSON）：`backend/modules/qwen3_tts_voice_store.py`
  - [x] 数据落盘：`{user_data_dir}/qwen3_tts_voices.json`
  - [x] 参考音频上传落盘：`/uploads/audios/qwen3_tts_voices/{voice_id}/...`（并回填 `ref_audio_url`）
- [x] Qwen3-TTS 克隆音色管理 API：`backend/routes/qwen3_tts_routes.py`
  - [x] `POST /api/tts/qwen3/voices/upload`：上传参考音频并创建音色
  - [x] `GET /api/tts/qwen3/voices`：查询音色列表
  - [x] `GET /api/tts/qwen3/voices/{voice_id}`：查询音色详情
  - [x] `PATCH /api/tts/qwen3/voices/{voice_id}`：更新音色信息
  - [x] `DELETE /api/tts/qwen3/voices/{voice_id}`：删除音色（可选删除本地文件）
- [x] 克隆任务启动与进度推送：`backend/routes/qwen3_tts_routes.py`
  - [x] `POST /api/tts/qwen3/voices/{voice_id}/clone`：开始克隆（参考音频标准化预处理）
  - [x] `GET /api/tts/qwen3/voices/{voice_id}/clone-status`：查询克隆进度与状态
  - [x] WebSocket 进度推送：scope=`qwen3_tts_voice_clone`
- [x] 合成/试听支持按克隆音色ID选用：`backend/modules/tts_service.py` 与 `backend/routes/tts_routes.py`
  - [x] VoiceClone 模型下：当未显式设置 `RefAudio` 时，允许用 `voice_id` 自动映射到本地音色的 `ref_audio`
- [x] 依赖补齐：`backend/requirements.txt` 与 `backend/requirements.runtime.txt` 增加 Qwen3-TTS 相关依赖（transformers / huggingface_hub / librosa / soundfile / modelscope）
- [x] 代码质量与可运行性校验
  - [x] flake8：新增/变更的 Qwen3-TTS 相关文件通过
  - [x] mypy：新增/变更的 Qwen3-TTS 相关文件通过（`--follow-imports=skip --allow-untyped-decorators --ignore-missing-imports`）
  - [x] compileall：后端编译通过

## 本地校验命令（参考）
```
backend/.venv/bin/python -m flake8 backend/modules/qwen3_tts_model_manager.py backend/modules/qwen3_tts_service.py backend/routes/qwen3_tts_routes.py backend/routes/tts_routes.py --max-line-length=160
backend/.venv/bin/python -m mypy --follow-imports=skip --allow-untyped-decorators backend/modules/qwen3_tts_model_manager.py backend/modules/qwen3_tts_service.py backend/routes/qwen3_tts_routes.py
backend/.venv/bin/python -m compileall backend -q
```

## 参考
- 官方仓库：https://github.com/QwenLM/Qwen3-TTS
- 支持语言与能力说明、下载方式见官方 README
