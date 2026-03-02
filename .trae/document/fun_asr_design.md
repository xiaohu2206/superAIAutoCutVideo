# FunASR 功能引入设计清单

## 1. 依赖与环境准备
- [ ] **依赖包**: 确认 `funasr` 与 `modelscope` 库的引入。
- [ ] **环境检查**: 确保 `torch`、`torchaudio` 环境满足 FunASR 运行要求（特别是 GPU 版本）。
- [ ] **VAD 模型**: 这里的 Nano 模型推荐配合 `fsmn-vad` 使用以支持长音频，需确保该 VAD 模型也能被下载和加载。

## 2. 后端核心模块设计

### 2.1 模型管理器 (`backend/modules/fun_asr_model_manager.py`)
参考 `qwen3_tts_model_manager.py` 实现。
- [ ] **模型注册表 (`FUN_ASR_MODEL_REGISTRY`)**:
  - **Fun-ASR-Nano-2512**:
    - `ms_repo_id`: `FunAudioLLM/Fun-ASR-Nano-2512`
    - `desc`: "支持中文（含7种方言、26种口音）、英文、日文。支持歌词识别与说唱。"
    - `languages`: `["中文", "英文", "日文"]`
  - **Fun-ASR-MLT-Nano-2512**:
    - `ms_repo_id`: `FunAudioLLM/Fun-ASR-MLT-Nano-2512`
    - `desc`: "支持31种语言。"
    - `languages`: `["中文", "英文", "粤语", "日文", "韩文", "越南语", "印尼语", "泰语", "马来语", "菲律宾语", "阿拉伯语", "印地语", "保加利亚语", "克罗地亚语", "捷克语", "丹麦语", "荷兰语", "爱沙尼亚语", "芬兰语", "希腊语", "匈牙利语", "爱尔兰语", "拉脱维亚语", "立陶宛语", "马耳他语", "波兰语", "葡萄牙语", "罗马尼亚语", "斯洛伐克语", "斯洛文尼亚语", "瑞典语"]`
  - **fsmn-vad** (辅助模型):
    - `ms_repo_id`: `iic/speech_fsmn_vad_zh-cn-16k-common-pytorch` (或 FunASR 默认使用的 VAD ID)
    - 用于长音频切分，需自动关联下载或作为独立项管理。

- [ ] **路径管理 (`FunASRPathManager`)**:
  - 确定模型存储根目录 (e.g., `uploads/models/FunASR`).
  - 提供 `model_path(key)` 方法解析绝对路径。
- [ ] **校验逻辑 (`validate_model_dir`)**:
  - 检查模型目录下关键文件是否存在 (e.g., `model.pt`, `config.yaml` 等)。
- [ ] **下载逻辑**:
  - 封装 `modelscope` 的 snapshot_download。
  - 支持指定 `model_id` 下载。
  - 支持断点续传。
  - 实现 `get_model_total_bytes` 用于计算下载进度。

### 2.2 硬件加速检测 (`backend/modules/fun_asr_acceleration.py`)
参考 `backend/modules/qwen3_tts_acceleration/detector.py`。
- [ ] **检测功能**:
  - 检测 CUDA 是否可用。
  - 获取显存大小、显卡型号。
  - 根据显存大小推荐是否启用 GPU 推理。

### 2.3 FunASR 服务封装 (`backend/modules/fun_asr_service.py`)
- [ ] **类定义 (`FunASRService`)**:
  - 单例模式或全局实例。
- [ ] **模型加载 (`load_model`)**:
  - 参数: `model_key`, `device`, `enable_vad` (默认 True)。
  - 逻辑:
    - 检查模型文件是否存在。
    - 调用 `funasr.AutoModel`。
    - 若 `enable_vad` 为 True，同时加载 `fsmn-vad` (需指定 `vad_model` 参数及 `vad_kwargs={"max_single_segment_time": 30000}`)。
    - 设置 `trust_remote_code=True`。
- [ ] **推理接口 (`transcribe`)**:
  - 输入: 音频文件路径。
  - 输出: SRT 格式所需的段落列表 (start, end, text)。
  - 逻辑: 调用 `model.generate()`。
  - 注意: Nano 模型返回结果可能需要解析 (查看文档示例 `res[0]["text"]` 或配合 VAD 后的结果结构)。需适配为 `[{start, end, text}]` 格式。如果模型本身不返回时间戳（文档 Todo 中提到 "Support returning timestamps"），可能需要依赖 VAD 的切分时间戳或者确认 Nano 是否已支持 timestamp 输出。**注意**: 文档 TODO 列出了 "Support returning timestamps"，这意味着当前 Nano 模型可能**不直接返回字级或句级时间戳**，或者功能受限。如果不支持时间戳，可能需要使用 VAD 切分后的时间段作为字幕时间轴，或者寻找 workaround (如 `batch_size_s` 切分)。设计时需注明这一点风险，优先使用 VAD 切分的时间作为粗略时间戳。
- [ ] **测试接口**:
  - 提供内置的短音频文件。
  - 验证模型加载和推理链路。

## 3. API 路由设计 (`backend/routes/fun_asr_routes.py`)
参考 `qwen3_tts_routes.py`，提供标准化的 RESTful API。

### 3.1 模型管理
- [ ] `GET /api/asr/funasr/models`: 获取模型列表及状态（支持 Nano-2512 和 MLT-Nano-2512）。
- [ ] `POST /api/asr/funasr/models/validate`: 手动触发模型校验。
- [ ] `GET /api/asr/funasr/models/open-path`: **在系统文件管理器中打开模型目录** (允许用户手动拷贝模型)。

### 3.2 下载管理
- [ ] `POST /api/asr/funasr/models/download`: 启动后台下载任务。
- [ ] `GET /api/asr/funasr/models/downloads`: 获取当前下载任务进度 (支持轮询或通过 WS 广播)。
- [ ] `POST /api/asr/funasr/models/downloads/stop`: 中断下载任务。
- [ ] **WebSocket 广播**: 复用或新增 WS 消息类型，实时推送下载进度、速度、完成状态。

### 3.3 功能测试
- [ ] `POST /api/asr/funasr/test`: 使用当前选中的模型对默认音频进行识别，返回识别文本，用于验证环境。

### 3.4 硬件状态
- [ ] `GET /api/asr/funasr/acceleration-status`: 返回 GPU/CPU 支持情况。

## 4. 业务逻辑集成

### 4.1 项目数据模型更新
- [ ] 在 `Project` 模型或相关配置中添加字段:
  - `asr_provider`: 枚举值 `bcut` (原版), `fun_asr` (新版)。
  - `asr_model_key`: 选用的 FunASR 模型 Key (如 `nano_2512` 或 `mlt_nano_2512`)。

### 4.2 字幕提取服务改造 (`backend/services/extract_subtitle_service.py`)
- [ ] **重构 `extract_subtitle` 方法**:
  - 参入参数 `req` 中增加 `asr_provider` 和 `asr_model_key`。
  - 默认值保持为 `bcut` 以兼容旧逻辑。
- [ ] **分支处理**:
  - 当 `provider == 'fun_asr'` 时，调用 `FunASRService.transcribe`。
  - 处理 FunASR 的加载和推理进度 (通过 WS 推送 `loading_model`, `transcribing` 等状态)。
- [ ] **结果适配**:
  - 将 FunASR 的输出结果转换为系统通用的 `segments` 格式。**重点解决时间戳问题** (若模型不支持，使用 VAD 切分时间)。

### 4.3 项目路由适配 (`backend/routes/project_routes.py`)
- [ ] 更新 `POST /{project_id}/extract-subtitle` 接口:
  - `ExtractSubtitleRequest` Body 中增加 `asr_provider` (str) 和 `asr_model_key` (str) 字段。
  - 将参数透传给 `extract_subtitle_service`。

## 5. 用户体验与交互设计 (后端支持)

### 5.1 模型下载体验
- [ ] **断点续传与刷新支持**: 下载状态存储在内存变量中 (如 `_download_states`)，并提供接口查询。前端刷新页面后通过 `GET /downloads` 接口恢复进度条显示。
- [ ] **手动导入**: 用户通过 `open-path` 打开文件夹放入模型后，点击前端的“校验”按钮 (`/validate` 接口) 即可刷新状态为“可用”。

### 5.2 字幕生成体验
- [ ] 在提取字幕时，若选择 FunASR 且模型未加载，WebSocket 推送“模型加载中...”状态。
- [ ] 若显存不足或加载失败，捕获异常并推送明确的错误信息给前端。

## 6. 默认配置与常量
- [ ] **默认测试音频**: 在 `backend/assets/` 下放置一个 `test_audio_16k.wav`，用于环境自检。

## 7. 参考代码示例 (Implementation Reference)

以下为 FunASR Nano 模型调用的参考代码，开发时请严格参考此逻辑（包括参数配置和语言名称）：

```python
from funasr import AutoModel

def main():
    model_dir = "FunAudioLLM/Fun-ASR-Nano-2512"
    model = AutoModel(
        model=model_dir,
        trust_remote_code=True,
        remote_code="./model.py",
        device="cuda:0",
        # hub：download models from ms (for ModelScope) or hf (for Hugging Face).
        hub="hf"
    )

    wav_path = f"{model.model_path}/example/zh.mp3"
    res = model.generate(
        input=[wav_path],
        cache={},
        batch_size=1,
        hotwords=["开放时间"],
        # 中文、英文、日文 for Fun-ASR-Nano-2512
        # 中文、英文、粤语、日文、韩文、越南语、印尼语、泰语、马来语、菲律宾语、阿拉伯语、
        # 印地语、保加利亚语、克罗地亚语、捷克语、丹麦语、荷兰语、爱沙尼亚语、芬兰语、希腊语、
        # 匈牙利语、爱尔兰语、拉脱维亚语、立陶宛语、马耳他语、波兰语、葡萄牙语、罗马尼亚语、
        # 斯洛伐克语、斯洛文尼亚语、瑞典语 for Fun-ASR-MLT-Nano-2512
        language="中文",
        itn=True, # or False
    )
    text = res[0]["text"]
    print(text)

    model = AutoModel(
        model=model_dir,
        trust_remote_code=True,
        vad_model="fsmn-vad",
        vad_kwargs={"max_single_segment_time": 30000},
        remote_code="./model.py",
        device="cuda:0",
    )
    res = model.generate(input=[wav_path], cache={}, batch_size=1)
    text = res[0]["text"]
    print(text)


if __name__ == "__main__":
    main()


from model import FunASRNano

def main():
    model_dir = "FunAudioLLM/Fun-ASR-Nano-2512"
    m, kwargs = FunASRNano.from_pretrained(model=model_dir, device="cuda:0")
    m.eval()

    wav_path = f"{kwargs['model_path']}/example/zh.mp3"
    res = m.inference(data_in=[wav_path], **kwargs)
    text = res[0][0]["text"]
    print(text)

if __name__ == "__main__":
    main()
```
