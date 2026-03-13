# 后端开发清单：VoxCPM 本地 TTS（含声音复刻）

## 目标

- 新增一个本地 TTS Provider：`voxcpm_tts`
- 支持“声音复刻/音色克隆”后，使用克隆音色进行语音合成
- 接入方式与现有 `qwen3_tts` 保持一致：可下载模型、校验模型、管理音色资产、统一 `tts_service.synthesize()` 走配音流程

相关资源：

- VoxCPM-0.5B（ModelScope）：https://modelscope.cn/models/OpenBMB/VoxCPM-0.5B/files
- VoxCPM-1.5B（ModelScope）：https://modelscope.cn/models/OpenBMB/VoxCPM1.5/files
- 开源参考（推理逻辑示例）：https://github.com/OpenBMB/VoxCPM/blob/main/app.py

---

## 现有实现可直接参考（Qwen3-TTS）

重点是“模型下载/校验/落盘 + 音色资产管理 + 合成入口统一走 tts_service”：

- 路由（模型管理 / 音色管理 / 克隆预处理）：[qwen3_tts_routes.py](file:///e:/learn/superAutoCutVideoApp/backend/routes/qwen3_tts_routes.py)
- 模型路径与下载/校验： [qwen3_tts_model_manager.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_model_manager.py)
- 推理与写 wav： [qwen3_tts_service.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_service.py)
- 音色资产（本地 JSON DB + uploads 路径）： [qwen3_tts_voice_store.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_voice_store.py)
- 统一配音入口（按 provider 分发）：[tts_service.py:L134-L314](file:///e:/learn/superAutoCutVideoApp/backend/modules/tts_service.py#L134-L314)
- 业务侧调用方式（统一只调 tts_service）：  
  - [video_generation_service.py:L281-L287](file:///e:/learn/superAutoCutVideoApp/backend/services/video_generation_service.py#L281-L287)  
  - [jianying_draft_manager.py:L927](file:///e:/learn/superAutoCutVideoApp/backend/services/jianying_draft_manager.py#L927) / [jianying_draft_manager.py:L1023-L1029](file:///e:/learn/superAutoCutVideoApp/backend/services/jianying_draft_manager.py#L1023-L1029)
- 统一“音色试听”入口（对 qwen3 做了专门分支）：[tts_routes.py:L553-L675](file:///e:/learn/superAutoCutVideoApp/backend/routes/tts_routes.py#L553-L675)

---

## VoxCPM 接入总体结构（建议对齐 Qwen3-TTS）

建议新增 3 类模块 + 1 个路由：

1) 模型管理（下载/校验/路径）
- `backend/modules/voxcpm_tts_model_manager.py`

2) 音色资产（上传参考音频、持久化、预处理状态）
- `backend/modules/voxcpm_tts_voice_store.py`

3) VoxCPM 推理服务（加载模型、执行 voice clone 合成、输出 wav）
- `backend/modules/voxcpm_tts_service.py`

4) 专用路由（模型与音色管理；进度通过 WS 广播）
- `backend/routes/voxcpm_tts_routes.py`（例如 `prefix="/api/tts/voxcpm"`）

然后把 VoxCPM 接到统一 TTS：

- 在 [tts_service.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/tts_service.py) 增加 `provider == "voxcpm_tts"` 分支
- 在 [tts_routes.py](file:///e:/learn/superAutoCutVideoApp/backend/routes/tts_routes.py) 增加 `provider == "voxcpm_tts"` 的“试听生成”分支
- 在 [tts_config.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/config/tts_config.py) 注册 provider + 默认配置
- 在 [main.py](file:///e:/learn/superAutoCutVideoApp/backend/main.py) include 新 router

---

## 开发清单（按阶段）

### A. 调研确认（必须先做）

- [ ] 阅读 VoxCPM `app.py`，确认最小可运行的“合成”调用链：输入参数、返回音频格式、采样率、是否需要 ref_text、是否分两阶段（先提取 speaker embedding / 再合成）。
- [ ] 在 ModelScope 的文件列表中确认“模型最小必需文件集合”，据此定义 `validate_model_dir()` 规则。  
  - 参考 Qwen3 的校验方式：[validate_model_dir()](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_model_manager.py#L122-L141)
- [ ] 确认 VoxCPM 的“参考音频”要求：采样率（16k/24k/48k）、声道（mono/stereo）、格式（wav）、时长范围、是否需要截断/降噪/静音裁剪等。
- [ ] 确认 VoxCPM 的硬件策略：CPU 是否可跑、GPU 是否必须、显存/内存大概需求；是否需要 fp16/bf16；是否存在 Windows 特定依赖（dll、长路径）。

验收口径（调研输出）：

- [ ] 产出一份 VoxCPM 推理“最小参数表”（text/ref_audio/ref_text/device/seed 等）与输出规格（wav+sr）。
- [ ] 产出一份“模型目录校验规则”（必需文件名/后缀集合）。

---

### B. Provider 与配置接入（统一 TTS 框架）

- [ ] 在 [tts_config.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/config/tts_config.py) 中把 `voxcpm_tts` 加到 provider 白名单（`TtsEngineConfig.validate_provider`）。
- [ ] 在 `TtsEngineConfigManager` 默认配置中新增 `voxcpm_tts_default`：  
  - `provider="voxcpm_tts"`  
  - `enabled=False`  
  - `active_voice_id=None`（优先从 voice_store 选择）  
  - `extra_params` 规划（对齐 qwen3 的风格）：
    - `ModelKey`: `voxcpm_0_5b` / `voxcpm_1_5b`
    - `Language`: `Auto/zh/en`（若 VoxCPM 支持）
    - `Device`: `cpu/cuda:0/auto`
    - `RefAudio` / `RefText`（仅当你决定支持“纯配置式 voice clone”，不依赖 voice_store）
    - 其他 VoxCPM 特有采样参数（如 temperature/top_p 等）
- [ ] 在 [tts_service.py](file:///e:/learn/superAutoCutVideoApp/backend/modules/tts_service.py) 增加 `provider == "voxcpm_tts"` 分支，并保持返回结构兼容：`{"success": True, "path": "...", "duration": ..., "sample_rate": ...}`。
- [ ] 在 [tts_routes.py](file:///e:/learn/superAutoCutVideoApp/backend/routes/tts_routes.py) 增加 `provider == "voxcpm_tts"` 的试听逻辑（参考 qwen3 分支）：  
  - 从 `voxcpm_tts_voice_store` 取 `voice_id` 资产  
  - 校验模型可用  
  - 生成临时 wav，写入 preview cache 并返回 `/api/tts/voices/preview/{id}`
- [ ] 在 [main.py](file:///e:/learn/superAutoCutVideoApp/backend/main.py) 注册 `voxcpm_tts_routes.router`（与 `qwen3_tts_router` 并列）。

验收口径：

- [ ] “切换 provider 为 voxcpm_tts”后，业务侧调用（例如视频生成）无需改代码即可走 VoxCPM 合成：
  - [video_generation_service.py:L281-L287](file:///e:/learn/superAutoCutVideoApp/backend/services/video_generation_service.py#L281-L287)
  - [jianying_draft_manager.py:L927](file:///e:/learn/superAutoCutVideoApp/backend/services/jianying_draft_manager.py#L927)

---

### C. 模型管理（下载 / 校验 / 目录结构）

建议直接复用 Qwen3 的结构与容错（ModelScope cache 目录合并、进度上报、validate 校验）：

- [ ] 新增 `VoxCPM` 模型 registry（参考 [QWEN3_TTS_MODEL_REGISTRY](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_model_manager.py#L10-L51)）：
  - `voxcpm_0_5b` → `OpenBMB/VoxCPM-0.5B`
  - `voxcpm_1_5b` → `OpenBMB/VoxCPM1.5`
- [ ] 新增 `VoxCPMPathManager`：
  - 环境变量：`VOXCPM_TTS_MODELS_DIR`（风格对齐 `QWEN_TTS_MODELS_DIR`）
  - 默认目录：`uploads/models/OpenBMB/VoxCPM/...`（或 `uploads/models/VoxCPM/...`，需统一命名）
- [ ] 新增 `download_model_snapshot(key, provider, target_dir)`：
  - provider 最少支持 `modelscope`（必要），可选支持 `hf`
  - 处理 ModelScope 下载到 cache 后的“目录合并搬运”（参考 [_merge_move](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_model_manager.py#L143-L173)）
  - 清理 `.modelscope_cache`（若需要）
- [ ] 新增 `validate_model_dir(key, model_dir)`：
  - 必须基于 VoxCPM 实际文件结构落地；不要照搬 Qwen3 的 `config.json`/`processor_config.json`，而是按 VoxCPM 真实依赖定义
  - 至少要校验“配置文件存在 + 权重文件存在（.safetensors/.bin）”
- [ ] 路由支持（参考 [qwen3_tts_routes.py](file:///e:/learn/superAutoCutVideoApp/backend/routes/qwen3_tts_routes.py)）：
  - `GET /api/tts/voxcpm/models`：列出本地模型状态（exists/valid/missing/path）
  - `POST /api/tts/voxcpm/models/validate`
  - `POST /api/tts/voxcpm/models/download`：启动下载任务（用子进程 + queue 汇报进度）
  - `GET /api/tts/voxcpm/models/downloads`：查询进行中的下载
  - `POST /api/tts/voxcpm/models/downloads/{key}/stop`：停止下载
  - `GET /api/tts/voxcpm/models/open-path`：打开模型目录（桌面端调试友好）
- [ ] 进度广播：沿用 `modules.ws_manager.manager.broadcast()`，scope 命名建议 `voxcpm_tts_models`

验收口径：

- [ ] 0.5B/1.5B 两个模型都能完成“下载→校验通过→服务可加载”
- [ ] 校验失败时能明确指出缺失文件列表（missing 字段）

---

### D. 音色资产（voice store）与“声音复刻”流程

目标：前端上传一段参考音频（可选 ref_text），后端将其标准化并存储为一个 `voice_id`，后续合成只需传 `voice_id`。

- [ ] 新增 `VoxCPMTTSVoice` 数据结构（参考 [Qwen3TTSVoice](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_voice_store.py#L47-L65)）：
  - `id/name`
  - `kind`: 建议先只做 `clone`（后续再扩展 custom_role/design_clone）
  - `model_key/language`
  - `ref_audio_path/ref_audio_url/ref_text`
  - `status/progress/last_error/meta/created_at/updated_at`
- [ ] 新增 `VoxCPMTTSVoiceStore`（JSON DB 存放到 `user_data_dir()/voxcpm_tts_voices.json`）
- [ ] 上传接口：
  - `POST /api/tts/voxcpm/voices/upload`：保存原始音频到 `uploads/audios/voxcpm_tts_voices/{voice_id}/raw.*` 并创建记录（status=uploaded）
- [ ] 预处理/标准化接口（异步 job）：
  - `POST /api/tts/voxcpm/voices/{voice_id}/clone`：启动“音频重采样/声道转换/裁剪”等预处理
  - `GET /api/tts/voxcpm/voices/{voice_id}/clone-status`：查询状态
  - 参考 Qwen3 的 ffmpeg 发现与转换实现：[_find_ffmpeg()](file:///e:/learn/superAutoCutVideoApp/backend/routes/qwen3_tts_routes.py#L724-L799) / [_convert_to_16k_mono_wav()](file:///e:/learn/superAutoCutVideoApp/backend/routes/qwen3_tts_routes.py#L808-L848)
- [ ] 预处理输出文件命名：`ref_{sr}_{mono}.wav`（例如 `ref_16k_mono.wav`），并把 `ref_audio_path` 更新为标准化文件路径（status=ready）。
- [ ] 删除接口：
  - `DELETE /api/tts/voxcpm/voices/{voice_id}?remove_files=true`
- [ ] 进度广播：scope 命名建议 `voxcpm_tts_voice_clone`

验收口径：

- [ ] 上传后能在 voices 列表中看到记录
- [ ] clone job 结束后 status=ready，ref_audio_path 指向标准化 wav
- [ ] remove_files=true 时能清理 uploads 下对应目录

---

### E. VoxCPM 推理服务（加载模型 + 合成）

对齐 `qwen3_tts_service` 的设计目标：单例 service、按 model_key 懒加载、线程池执行推理、输出 wav、返回统一 dict。

- [ ] 新增 `VoxCPMTTSService`：
  - `get_runtime_status()`：loaded/model_key/model_path/device/precision/last_error 等
  - `_load_model(model_key, device, precision)`：缓存模型实例，避免重复加载
  - `synthesize_by_voice_asset(text, out_path, voice_asset, device=None, **params)`：核心入口（类似 [synthesize_by_voice_asset](file:///e:/learn/superAutoCutVideoApp/backend/modules/qwen3_tts_service.py#L1064-L1137)）
  - `_write_wav(out_path, wav, sr)`：保证 wav 格式一致
- [ ] 设备策略：
  - `Device` 来自 `tts_config.extra_params["Device"]`（与 qwen3 对齐）
  - `auto` 时可扩展“优先 GPU”策略（可选）
- [ ] 合成参数策略：
  - 基础只实现 voice clone 合成；可选再支持不带 ref_audio 的“默认音色”
  - 将采样参数（top_p/temperature/max_tokens 等）统一从 `extra_params` 读取，保证可配
- [ ] Windows 兼容：
  - 若 VoxCPM 依赖大量 dll/长路径，参考 qwen3 的 Windows 路径/环境处理策略（必要时移植）
- [ ] 失败语义：
  - 缺模型：返回 `model_invalid:...`（与 qwen3 一致，方便前端提示）
  - 缺依赖：返回 `missing_dependency:...`
  - voice 不可用：`voice_not_ready` / `voice_not_found`

验收口径：

- [ ] 使用 `voice_id`（ready 状态）可以成功生成 wav
- [ ] 返回结果包含 `path/duration/sample_rate`（duration 可通过 ffprobe 或由采样点计算）

---

### F. 统一合成链路联调（覆盖真实业务入口）

- [ ] `tts_service.synthesize()` 走 voxcpm 分支：
  - voice_id 为空：走 `cfg.active_voice_id`（若你选择支持）
  - voice_id 非空：优先从 `voxcpm_tts_voice_store.get(voice_id)` 找到资产后合成
- [ ] `tts_routes` 试听可用：
  - provider=voxcpm_tts 时 `/api/tts/voices/{voice_id}/preview` 能返回一次性试听音频链接
- [ ] 业务侧无感：
  - 运行“视频生成/剪映导出”流程时，不需要改业务代码即可产出配音文件

---

## 建议的命名与约定（对齐现有工程）

- Provider 字符串：`voxcpm_tts`（全小写）
- uploads 目录建议：
  - 模型：`uploads/models/OpenBMB/VoxCPM/...`
  - 音频资产：`uploads/audios/voxcpm_tts_voices/{voice_id}/...`
- voice store DB：`user_data_dir()/voxcpm_tts_voices.json`
- WS scope：
  - 模型下载：`voxcpm_tts_models`
  - 音色克隆：`voxcpm_tts_voice_clone`

