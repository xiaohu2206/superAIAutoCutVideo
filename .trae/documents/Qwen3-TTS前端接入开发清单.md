# Qwen3-TTS 前端接入开发清单（低耦合版本）

## 背景
- 现有 TTS 设置入口：[`TtsSettings.tsx`](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/components/tts/TtsSettings.tsx)
- 现有音色展示与试听：[`TtsVoiceGallery.tsx`](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/components/tts/TtsVoiceGallery.tsx)
- 现有后端接口（Qwen3-TTS 模型与音色克隆）：`/api/tts/qwen3/*`
- 目标：在不破坏现有 tencent_tts / edge_tts 逻辑的前提下，为 `provider=qwen3_tts` 增加“上传参考音频→开始克隆→进度→音色列表CRUD→选择用于合成/试听”的完整 UI 闭环。

## 约束（必须遵守）
- 尽量减少与现有 TTS 代码耦合：避免在 `TtsSettings.tsx` / `TtsVoiceGallery.tsx` 里堆大量 `if (provider==="qwen3_tts") ...`
- Qwen3-TTS 相关逻辑独立成组件 + hooks + service，现有组件只做“装配/切换”
- 复用现有 `ttsService.previewVoice(...)` 与 “active_voice_id” 机制，不为 Qwen3 另起一套“试听播放器”

## 后端接口映射（前端需要对齐）

### 模型管理（下载/校验/手动拷贝引导）
- `GET /api/tts/qwen3/models`：列出本地模型状态（含 valid/missing）
- `POST /api/tts/qwen3/models/validate`：校验指定模型目录完整性
- `POST /api/tts/qwen3/models/download`：下载模型（body: `{ key, provider: "hf"|"modelscope" }`）
- `GET /api/tts/qwen3/models/open-path?key=...`：返回该模型应放置的本地目录路径（用于“复制路径/打开目录/手动拷贝引导”）
- WebSocket：scope=`qwen3_tts_models`（`type=progress|completed|error`，用于下载进度；`project_id` 为 `null`）

### 克隆音色 CRUD & 任务
- `POST /api/tts/qwen3/voices/upload`（multipart/form-data）
  - fields: `file`, `name`, `model_key`, `language`, `ref_text`, `instruct`, `x_vector_only_mode`
- `GET /api/tts/qwen3/voices`
- `GET /api/tts/qwen3/voices/{voice_id}`
- `PATCH /api/tts/qwen3/voices/{voice_id}`
- `DELETE /api/tts/qwen3/voices/{voice_id}?remove_files=0|1`
- `POST /api/tts/qwen3/voices/{voice_id}/clone`
- `GET /api/tts/qwen3/voices/{voice_id}/clone-status`
- WebSocket：scope=`qwen3_tts_voice_clone`（`type=progress|completed|error`，payload 含 `voice_id/job_id/phase/progress/message`，`project_id` 为 `null`）

### 试听与选择（复用现有 TTS 接口）
- `POST /api/tts/voices/{voice_id}/preview`（body 携带 `provider=qwen3_tts`, `config_id`）
- 选择音色：通过 `PATCH /api/tts/configs/{configId}` 设置 `active_voice_id=voice_id` 并激活配置（现有逻辑已实现）

## 推荐前端架构（低耦合）

### 新增目录（建议）
- `frontend/src/features/qwen3Tts/`
  - `services/qwen3TtsService.ts`：只负责调用 `/api/tts/qwen3/*`
  - `types.ts`：`Qwen3TtsVoice`、`Qwen3TtsModelStatus`、请求/响应类型
  - `hooks/`
    - `useQwen3Models()`：模型状态拉取、下载、校验、手动拷贝路径获取
    - `useQwen3Voices()`：列表加载/刷新、CRUD 封装
    - `useQwen3CloneJob()`：启动 clone + 订阅 ws scope + 提供进度状态
  - `components/`
    - `Qwen3ModelSection.tsx`：模型管理（状态 + 下载 + 校验 + 手动拷贝引导）
    - `Qwen3VoiceSection.tsx`：入口容器（上传 + 列表 + 克隆进度）
    - `Qwen3VoiceUploadDialog.tsx`：上传弹窗/抽屉
    - `Qwen3VoiceList.tsx`：列表（编辑/删除/开始克隆/选择）
    - `Qwen3CloneProgressItem.tsx`：单行进度条（可复用到列表行）

现有 `settingsPage/components/tts/` 仅做“按 provider 渲染不同区域”：
- `TtsSettings.tsx`：保留引擎切换、配置读取/保存、active_voice_id 写回
- 将“凭据设置”区域拆成 provider-specific 面板（避免把 Qwen3 UI 塞进 `TtsCredentialForm.tsx`）

## 开发清单（可直接分配给前端同学）

### A. API & 类型（独立，不侵入旧 TTS）
- [ ] 在 `frontend/src/features/qwen3Tts/types.ts` 定义 `Qwen3TtsModelStatus`
  - [ ] 字段至少包含：`key/path/exists/valid/missing[]`
- [ ] 在 `frontend/src/features/qwen3Tts/services/qwen3TtsService.ts` 补齐模型接口封装：
  - [ ] `listModels()`
  - [ ] `validateModel(key)`
  - [ ] `downloadModel(key, provider)`
  - [ ] `getModelPath(key)`（对接 `/models/open-path`）
- [ ] 在 `frontend/src/features/qwen3Tts/types.ts` 定义 `Qwen3TtsVoice`（字段至少包含：`id/name/status/progress/ref_audio_url/ref_text/instruct/model_key/language/x_vector_only_mode/created_at/updated_at`）
- [ ] 在 `frontend/src/features/qwen3Tts/services/qwen3TtsService.ts` 封装接口：
  - [ ] `listVoices()`
  - [ ] `uploadVoice(formData)`
  - [ ] `getVoice(id)`
  - [ ] `patchVoice(id, partial)`
  - [ ] `deleteVoice(id, removeFiles)`
  - [ ] `startClone(id)` → 返回 `job_id`
  - [ ] `getCloneStatus(id)`
- [ ] `ApiClient` 增加“multipart 上传”能力（建议：新增 `postFormData(endpoint, formData)`，不要改动现有 JSON request 逻辑）

### B. WebSocket 进度订阅（与现有任务进度解耦）
现有 hook：[`useWsTaskProgress.ts`](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/hooks/useWsTaskProgress.ts) 强依赖 `projectId`，而 Qwen3 clone 的 `project_id` 是 `null`。
- [ ] 新增 hook：`useWsScopeProgress()`（或扩展现有 hook：允许 `projectId` 为空时不过滤 project_id）
  - [ ] 过滤条件（克隆音色）：`message.scope === "qwen3_tts_voice_clone"` 且 `message.voice_id === 当前 voice_id`
  - [ ] 过滤条件（模型下载）：`message.scope === "qwen3_tts_models"` 且按 `phase`/`message` 做展示即可（该 scope 不一定带 task_id）
  - [ ] 输出：`progress(0-100)`、`phase`、`message`、`type`
- [ ] 在 `useQwen3CloneJob()` 内部统一处理：HTTP 启动 clone + WS 监听 + 出错回退（比如拉取一次 `clone-status`）
- [ ] 在 `useQwen3Models()` 内部统一处理：HTTP 启动 download + WS 监听 + 结束后刷新 `listModels()`

### C. Qwen3 模型管理 UI（独立组件开发）
- [ ] 新增 `Qwen3ModelSection`
  - [ ] 展示模型列表（来自 `/api/tts/qwen3/models`），按 `valid/missing` 给出清晰状态
  - [ ] 每个模型提供操作：
    - [ ] 下载（provider 选择：`hf` / `modelscope`）
    - [ ] 校验（调用 `/models/validate`）
    - [ ] 复制本地目录（调用 `/models/open-path` 获取 path，再复制到剪贴板）
  - [ ] 手动拷贝引导文案（必须有）：
    - [ ] 告知用户“可将下载好的模型目录手动复制到该路径”
    - [ ] 给出“目标路径”与“模型 key 对应的目录名”
  - [ ] 下载进度展示（WebSocket scope=`qwen3_tts_models`）

### D. Qwen3 音色管理 UI（独立组件开发）
- [ ] 新增 `Qwen3VoiceSection`，只在 `provider === "qwen3_tts"` 时渲染
  - [ ] 顶部：模型管理区域（渲染 `Qwen3ModelSection`）
  - [ ] 顶部：上传参考音频按钮（打开 `Qwen3VoiceUploadDialog`）
  - [ ] 列表：展示所有 voice（含状态/进度/操作）
  - [ ] 空态：提示“先上传参考音频”
- [ ] `Qwen3VoiceUploadDialog`
  - [ ] 输入：name/model_key/language/ref_text/instruct/x_vector_only_mode
  - [ ] 文件选择：音频文件（wav/mp3/m4a/flac/ogg/aac）
  - [ ] 上传成功后：刷新列表，并可选自动触发 `startClone`
- [ ] `Qwen3VoiceList`
  - [ ] 行内操作：试听（复用 `ttsService.previewVoice`）、选择、开始克隆、编辑、删除
  - [ ] 编辑：只允许改“展示名、ref_text、instruct、x_vector_only_mode、model_key、language”
  - [ ] 删除：二次确认，支持 remove_files 开关
- [ ] 列表行状态规范
  - [ ] `uploaded`：允许“开始克隆”
  - [ ] `cloning`：显示进度条（WS 推送），禁用重复 start
  - [ ] `ready`：允许“选择/试听/编辑/删除”
  - [ ] `failed`：显示 `last_error`，允许“重新开始克隆”

### E. 与现有 TTS 组件的最小接触点（必须改，但要克制）
目标：只改“装配点”，不要把 Qwen3 逻辑写进旧组件内部。

- [ ] `TtsSettings.tsx` 调整 `hasCredentials` 判定
  - [ ] 当 `provider === "qwen3_tts"` 时，视为 `true`（本地能力，无需 secret）
- [ ] `TtsCredentialForm.tsx` 不再用于 `qwen3_tts`
  - [ ] 在 `TtsSettings.tsx` 中按 provider 切换渲染：
    - `edge_tts` → 现有 `TtsCredentialForm`（含代理）
    - `tencent_tts` → 现有 `TtsCredentialForm`（secret）
    - `qwen3_tts` → 新增 `Qwen3VoiceSection`（模型选择/克隆/管理）
- [ ] `TtsVoiceGallery.tsx` 的过滤策略需要兼容 Qwen3
  - [ ] 当前非 tencent 会过滤仅 zh/en，Qwen3 的 `language=Auto` 会被过滤掉
  - [ ] 建议：把“语言过滤”从 Gallery 内移出，或新增 prop `filterMode`，使 `qwen3_tts` 不过滤
- [ ] Qwen3 音色如何接入 Gallery（两种方案择一）
  - [ ] 方案1（推荐，低耦合）：Qwen3 使用自己的 `Qwen3VoiceList`，不复用 `TtsVoiceGallery`
  - [ ] 方案2（复用，需适配）：将 `Qwen3TtsVoice` 映射为 `TtsVoice`
    - `id = voice.id`
    - `name = voice.name`
    - `description = voice.status/进度/错误信息拼接`
    - `category = "Qwen3 克隆音色"`

### F. 交互验收标准（前端自测用例）
- [ ] 切换到 Qwen3-TTS 引擎后，“凭据设置”区域不出现 SecretId/SecretKey 输入框
- [ ] 模型管理区能看到 3 个模型（tokenizer/base/custom），并能显示 valid/missing
- [ ] 点击“下载模型”能看到进度（WS scope=`qwen3_tts_models`），结束后状态刷新为 valid
- [ ] 若用户选择手动拷贝：能一键复制“目标模型目录路径”，并提示用户把模型复制进去
- [ ] 上传音频成功后列表出现新音色，状态为 `uploaded`
- [ ] 点击“开始克隆”后显示进度条，完成后状态变为 `ready`
- [ ] 任何阶段刷新页面，列表仍存在（后端 JSON 持久化），并能通过 `clone-status` 恢复状态
- [ ] 对 `ready` 音色点击“试听”，能播放 `/api/tts/voices/{voice_id}/preview` 返回的 `audio_url`
- [ ] 点击“选择”，能把该 voice_id 写入 `active_voice_id` 并显示“使用中”
- [ ] 删除音色后从列表消失；若 remove_files=true 则本地文件也删除（至少不影响后续）

## 实施优先级建议
- P0：上传 + 列表 + 开始克隆 + 进度 + 选择 + 试听（闭环）
- P1：编辑音色元信息（ref_text/instruct 等）
- P2：删除时支持 remove_files 开关、批量管理、排序/搜索
