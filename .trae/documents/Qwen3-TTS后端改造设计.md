# Qwen3-TTS 后端改造设计

## 目标与原则

目标：重构 Qwen3-TTS 的后端领域模型与 API，使其天然支持三类模型能力，并为前端提供“模式引导 + 统一音色资产列表”的稳定契约。

三类能力（按模型分类）：

- Base：语音克隆（generate_voice_clone）
- CustomVoice：固定角色配音（generate_custom_voice）
- VoiceDesign：文本设定角色配音（generate_voice_design → 产出参考音频 → 转为 Base 可复用克隆音色）

原则：

- 保留并兼容现有“模型下载/手动拷贝/校验”能力与路径管理方式（见 [qwen3_tts_model_manager.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/qwen3_tts_model_manager.py) 与 [qwen3_tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/qwen3_tts_routes.py)）
- 音色从“仅克隆音色”升级为“音色资产（Voice Asset）”，统一承载三类模式
- 合成入口统一（tts_service 与 preview_voice）只接受 voice_asset_id，避免把 speaker/路径字符串塞进 voice_id
- 异步任务可观测（WebSocket scope、phase、progress 与持久化状态一致）

## 现状问题（必须修正）

当前实现主要由以下模块组成：

- 模型管理：Qwen3TTSModelManager（下载/校验/路径）
- 推理服务：Qwen3TTSService（只实现 custom 与 clone 的合成到 wav）
- 音色存储：Qwen3TTSVoiceStore（强制 ref_audio_path，适配上传克隆）
- 路由：qwen3_tts_routes（模型管理 + 上传音色 + “克隆预处理”）
- 通用 TTS：tts_service（根据 provider 选择 qwen3_tts 并调用 synthesize_to_wav）
- 试听：tts_routes.preview_voice 对 qwen3_tts 做了特例分支

主要结构性问题：

- VoiceStore 数据结构无法表达 CustomVoice（speaker/语言/指令）与 VoiceDesign（设计输入/生成参考音频/关联 Base 克隆）
- preview/synthesize 的参数决策分散在 tts_routes 与 tts_service 中，导致“同一音色的合成参数”难以统一与复用
- 模型 registry 只用 key 表达“目录”，缺少“模型类型（base/custom/voice_design）”与“用户可理解名称（Qwen3-TTS-12Hz-1.7B-Base / Qwen/Qwen3…）”的表达层

## 领域模型重构

### 1) 模型（Model）元数据层

保留现有 key（用于本地目录名与 API 传参），扩展元数据字段：

- key：base_0_6b | base_1_7b | custom_0_6b | custom_1_7b | voice_design_1_7b
- model_type：base | custom_voice | voice_design
- size：0.6B | 1.7B
- display_names：用于前端展示“Qwen3-TTS-12Hz-1.7B-Base”等友好名称与远端 repo 名称
- sources：
  - hf_repo_id（HuggingFace：Qwen/Qwen3-TTS-12Hz-…）
  - ms_model_id（ModelScope：Qwen/Qwen3-TTS-12Hz-…）
  - local_dir_name（仍由 key 映射到固定目录名）

用户要求的模型列表与后端内部 key 的对应建议：

- Qwen3-TTS-12Hz-1.7B/0.6B-Base → base_1_7b / base_0_6b
- Qwen3-TTS-12Hz-1.7B/0.6B-CustomVoice → custom_1_7b / custom_0_6b
- Qwen/Qwen3-TTS-12Hz-1.7B-Base → base_1_7b（source=hf/ms）
- Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign → voice_design_1_7b（source=hf/ms）
- Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice → custom_1_7b（source=hf/ms）

### 2) 音色资产（Voice Asset）

将 [qwen3_tts_voice_store.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/qwen3_tts_voice_store.py) 的 `Qwen3TTSVoice` 升级为可表达三类模式的结构（建议字段）：

- id: str
- name: str
- kind: "clone" | "custom_role" | "design_clone"
- model_key: str
- language: str
- speaker: Optional[str]（custom_role 必填；clone/design_clone 可为空）
- ref_audio_path: Optional[str]（clone/design_clone 才有）
- ref_audio_url: Optional[str]
- ref_text: Optional[str]（clone/design_clone 可选；custom_role 不需要）
- instruct: Optional[str]（三种都允许）
- x_vector_only_mode: bool（clone/design_clone 才有意义；custom_role 可忽略或固定为 True）
- status: "uploaded" | "cloning" | "ready" | "failed" | ...
- progress: int
- last_error: Optional[str]
- meta: Dict[str, Any]（存放 original_filename、voice_design_text、voice_design_instruct、sample_rate、duration 等）
- created_at/updated_at

关键语义：

- clone：用户上传参考音频后创建；需要“预处理/克隆准备”任务
- custom_role：基于 CustomVoice 的 speaker 创建；不需要文件、不需要预处理，创建即 ready
- design_clone：由 VoiceDesign 生成参考音频，再走预处理，最终以 Base clone 使用；属于异步任务

存储路径建议（保持 uploads 体系不变）：

- uploads/audios/qwen3_tts_voices/{voice_id}/
  - raw.*（上传原始音频，clone）
  - ref_16k_mono.wav（标准化参考音频，clone/design_clone）
  - design_reference.wav（VoiceDesign 输出，design_clone）

## 推理服务重构

以 [qwen3_tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/qwen3_tts_service.py) 为核心，建议拆出更清晰的三个能力方法：

- synthesize_custom_voice_to_wav(text, out_path, model_key, language, speaker, instruct, device)
- synthesize_voice_clone_to_wav(text, out_path, model_key, language, ref_audio, ref_text, x_vector_only_mode, device)
- synthesize_voice_design_to_wav(text, out_path, model_key, language, instruct, device)

并在上层提供一个统一入口：

- synthesize_by_voice_asset(text, out_path, voice_asset, device_override?) → 内部按 kind/model_type 选择上述三者

模型加载与缓存：

- 允许同一进程中按 model_key 热切换（已有 _model_key/_model 缓存）
- VoiceDesign 可能与 Base 同时被使用，后续可扩展为“多模型实例缓存”（本次只做设计，先不实现）

模型能力查询（供前端做语言/说话人选择）：

- list_supported_speakers(model_key)
- list_supported_languages(model_key)

## API 设计（建议）

### 1) 模型管理（保持并扩展）

保留现有接口（路径与语义不变）：

- GET /api/tts/qwen3/models
- POST /api/tts/qwen3/models/validate
- POST /api/tts/qwen3/models/download
- GET /api/tts/qwen3/models/open-path

扩展返回字段（不破坏兼容）：

- model_type、size、display_names、sources

### 2) 音色资产管理（统一三种模式）

建议新增/调整接口（可保留旧接口一段时间并标记 deprecated）：

- GET /api/tts/qwen3/voices
  - 返回 voice assets 列表（含 kind/speaker/ref_audio_url 等）
- POST /api/tts/qwen3/voices/clone/upload
  - 上传文件创建 clone 资产（等价于现有 /voices/upload，但语义更明确）
- POST /api/tts/qwen3/voices/custom-role
  - 创建 custom_role 资产（model_key/language/speaker/instruct/name）
- POST /api/tts/qwen3/voices/design-clone
  - 创建 design_clone 资产并启动异步任务（voice_design_model_key/base_model_key/language/text/instruct/name）
- PATCH /api/tts/qwen3/voices/{voice_id}
- DELETE /api/tts/qwen3/voices/{voice_id}?remove_files=0|1

能力查询接口（给 CustomVoice 模式）：

- GET /api/tts/qwen3/models/{model_key}/capabilities
  - 返回 supported_languages / supported_speakers（可按 language 分组返回）

### 3) 试听与合成入口统一

当前试听入口位于 [tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L439-L732) 的 `preview_voice`，已经对 qwen3_tts 做了特例分支，但仍以“voice_id 字符串”做决策。

改造目标：

- preview_voice(provider=qwen3_tts) 始终把 voice_id 视为 voice_asset_id
- 后端通过 voice_store 查询资产信息，再调用 qwen3_tts_service.synthesize_by_voice_asset
- 对 custom_role：由 voice_asset.speaker 决定角色
- 对 clone/design_clone：由 voice_asset.ref_audio_path/ref_text/x_vector_only_mode 决定克隆

同时，tts_service 的 qwen3_tts 分支（见 [tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/tts_service.py)）应改为同样的策略：

- active_voice_id 必须是 voice_asset_id
- 合成时优先从 store 取资产参数，而不是从 extra_params 拼装

extra_params 的定位建议：

- 只保留“全局推理设置”的兜底/覆盖项（device、采样策略等）
- 不再承载 voice 级别的 speaker/ref_audio/ref_text（这些应进入 voice_asset）

## 异步任务设计（克隆与设计克隆）

复用现有 WebSocket 广播模式（见 [qwen3_tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/qwen3_tts_routes.py) 的 scope= qwen3_tts_models / qwen3_tts_voice_clone），建议：

- clone：继续使用 scope="qwen3_tts_voice_clone"
- design_clone：新增 scope="qwen3_tts_voice_design_clone"（或统一为 qwen3_tts_voice_jobs，通过 voice_id + job_type 区分）

phase 建议：

- design_clone：
  - design_generate（VoiceDesign 推理）
  - preprocess_load_audio
  - preprocess_write_wav
  - done / error
- clone：
  - load_audio / write_wav / done / error（沿用现有）

voice_store 的状态持久化与 WS 事件必须同源，避免“WS 显示完成但 store 未 ready”。

## 兼容与迁移

### 旧数据兼容

现有 qwen3_tts_voices.json 中的条目默认视为：

- kind="clone"
- ref_audio_path 保持必填

迁移步骤建议：

- store 加载时如果缺 kind，则自动补 "clone"
- custom_role/design_clone 新字段缺失时保持 None，不影响旧条目

### 接口兼容

短期内：

- 保留 /voices/upload 与 /voices/{id}/clone（旧“克隆预处理”流程）
- 新增接口用于 custom_role 与 design_clone

长期：

- 将 clone 与 design_clone 都统一到 /voices/{id}/jobs/{job_type} 形式（可选）

## 验收清单（后端）

- 模型：仍支持下载/校验/复制路径；并能在 list 接口返回 model_type 与展示名
- 音色资产：能创建三种 kind，并统一在 /voices 列表返回
- 合成：tts_service 与 preview_voice 均能通过 voice_asset_id 正确合成三种模式
- 进度：clone 与 design_clone 异步任务可通过 WS 展示并落库

