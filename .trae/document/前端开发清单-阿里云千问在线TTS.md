# 前端开发清单：阿里云千问（DashScope）在线 TTS

目标：在现有“设置页 → TTS”中，新增并完整支持 `qwen_online_tts` 提供商的配置、系统音色选择、复刻音色管理与试听。

后端已提供的关键能力（接口/行为约定）：
- 引擎列表：`GET /api/tts/engines`（已包含 provider=`qwen_online_tts`）
- 配置读写与激活：
  - `GET /api/tts/configs`
  - `PATCH /api/tts/configs/{config_id}`
  - `POST /api/tts/configs/{config_id}/activate`
  - `POST /api/tts/configs/{config_id}/test`
- 系统音色列表：`GET /api/tts/voices?provider=qwen_online_tts`
- 试听（系统音色名或复刻 voice_id 均可）：`POST /api/tts/voices/{voice_id}/preview`
- 复刻音色管理（在线）：`/api/tts/qwen-online/*`
  - `GET /api/tts/qwen-online/voices`
  - `POST /api/tts/qwen-online/voices/upload`
  - `PATCH /api/tts/qwen-online/voices/{voice_id}`
  - `DELETE /api/tts/qwen-online/voices/{voice_id}?remove_files=...`

参考现有实现：
- 设置页入口：`frontend/src/components/settingsPage/index.tsx`（tts 分支）
- TTS 主面板：`frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`
- Qwen3 本地音色管理与对话框组件：`frontend/src/features/qwen3Tts/components/*`

---

## 1. UI 与交互范围确认

- [ ] 在“引擎选择”下拉中展示千问在线 TTS（来自后端 engines meta，无需硬编码）
- [ ] 支持切换 provider 时自动创建默认配置与激活（沿用现有流程）
- [ ] `qwen_online_tts` 的凭据与可用性判定逻辑调整：
  - `edge_tts`：免凭据
  - `qwen3_tts`：免凭据（本地模型）
  - `tencent_tts`：需要 `secret_id` + `secret_key`
  - `qwen_online_tts`：仅需要 `secret_key`（或运行环境变量 `DASHSCOPE_API_KEY`，前端只能通过 test 结果感知）
- [ ] 系统音色：可浏览/搜索/选择/试听（试听通过后端生成一次性 preview）
- [ ] 复刻音色：可上传参考音频生成、列表展示、删除、选择为 active_voice_id、试听

---

## 2. 数据模型与类型

- [ ] 在设置页 types 中新增在线复刻音色类型（建议独立于 `TtsVoice`，避免字段含义冲突）：
  - `id/name/model/voice/ref_audio_url/ref_text/status/progress/last_error/created_at/updated_at`
- [ ] 约定“active_voice_id”的语义：
  - 系统音色：`active_voice_id = 系统音色名`（例如 `Cherry`）
  - 复刻音色：`active_voice_id = 在线复刻 voice_id`（UUID）

建议文件：
- `frontend/src/components/settingsPage/types.ts`
- 或在 `frontend/src/features/qwenOnlineTts/types.ts` 新建专用 types（更推荐，避免 settingsPage/types 过大）

---

## 3. API Client 扩展（services）

在现有 `apiClient`/`ttsService` 基础上新增在线复刻音色相关接口封装：

- [ ] `getQwenOnlineVoices()` -> `GET /api/tts/qwen-online/voices`
- [ ] `uploadQwenOnlineVoice(formData, configId?)` -> `POST /api/tts/qwen-online/voices/upload?config_id=...`
  - FormData 字段：`file`（必填）、`name`（可选）、`model`（可选）、`ref_text`（可选）
- [ ] `patchQwenOnlineVoice(voiceId, formData)` -> `PATCH /api/tts/qwen-online/voices/{voice_id}`
- [ ] `deleteQwenOnlineVoice(voiceId, removeFiles)` -> `DELETE /api/tts/qwen-online/voices/{voice_id}?remove_files=...`

建议文件：
- `frontend/src/services/clients.ts`
- `frontend/src/services/ttsService.ts`（或新建 `qwenOnlineTtsService.ts`）

---

## 4. 设置页：凭据区适配

现状：`TtsCredentialForm` 对非 edge 默认展示 SecretId/SecretKey，不适配在线千问（只有 API Key）。

实现建议（二选一）：

- [ ] 方案 A（推荐）：按 provider 拆分组件
  - `TtsCredentialFormTencent`：保留现有 SecretId/SecretKey
  - `TtsCredentialFormQwenOnline`：展示 API Key、region、extra_params
  - `TtsCredentialFormEdge`：代理
  - `TtsSettings.tsx` 中按 provider 渲染对应组件（类似当前 qwen3 的分支）

- [ ] 方案 B：在 `TtsCredentialForm` 内做 provider 分支（文件会变复杂，不推荐）

在线千问凭据与参数 UI 字段（建议）：
- [ ] API Key（使用 `secret_key` 字段存储；label 显示为 “DashScope API Key”）
- [ ] region（建议下拉：`cn` / `intl`）
- [ ] extra_params（按需展示）：
  - `Model`（下拉白名单：`qwen3-tts-flash`、`qwen3-tts-instruct-flash`、`qwen3-tts-vc-2026-01-22` 等）
  - `LanguageType`（例如 `Chinese`）
  - `Instructions`（可选）
  - `OptimizeInstructions`（可选开关）
  - `BaseUrl`（可选覆盖，北京）

连通性测试：
- [ ] `provider=qwen_online_tts` 时允许点击“测试连通性”，并正确展示后端返回 message
- [ ] 测试按钮置灰条件使用新的 `hasCredentials` 规则（qwen_online_tts 仅需要 secret_key 已设置）

涉及文件：
- `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`
- `frontend/src/components/settingsPage/components/tts/TtsCredentialForm.tsx`（或拆分新文件）

---

## 5. 设置页：音色库适配（系统音色）

系统音色使用现有 `TtsVoiceGallery` 即可，但需要保证：
- [ ] `loadVoices("qwen_online_tts")` 可正常加载并展示
- [ ] `hasCredentials` 规则正确，否则“选择/试听”会被错误禁用
- [ ] 试听调用：
  - `ttsService.previewVoice(voice.id, { provider, config_id, text })`
  - 对在线千问一般没有 `sample_wav_url`，必须走后端生成 preview

---

## 6. 在线复刻音色管理区（新增 UI）

建议在 TTS 设置页中，当 `provider === "qwen_online_tts"` 时，在“凭据设置”与“音色库”之间插入一个“复刻音色”区块，功能对齐 qwen3 的体验，但更轻量：

- [ ] 复刻音色列表
  - 展示字段：name、status、model、updated_at、last_error（失败时）
  - 操作：试听、选择为当前音色、删除
  - 选择条件：`status === "ready"`

- [ ] 上传对话框（参考 Qwen3VoiceUploadDialog 的交互）
  - 上传音频文件（mp3/wav/m4a/flac/ogg/aac）
  - 可选：名称、ref_text、模型（默认 `qwen3-tts-vc-2026-01-22`）
  - 提交后显示 loading，返回成功后刷新列表

- [ ] 试听复刻音色
  - 走统一 preview 接口：`POST /api/tts/voices/{voice_id}/preview`（voice_id 为复刻 voice_id）
  - url 为 `/api/tts/voices/preview/{preview_id}`，用现有播放逻辑即可

UI 组件建议：
- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceSection.tsx`
- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceList.tsx`
- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceUploadDialog.tsx`
- 进度条可复用 `Qwen3CloneProgressItem`（虽然后端当前是同步创建，但复用样式可保持一致）

---

## 7. 关键细节与坑位清单

- [ ] `active_voice_id` 可能是系统音色名，也可能是 UUID（复刻 voice_id）；UI 上需要区分展示：
  - 当前激活信息区可以展示：当 active_voice_id 命中复刻列表时，显示复刻 name；否则显示系统音色名称
- [ ] `TtsCredentialForm` 当前的提示文案写死“腾讯云鉴权失败/已连接腾讯云”，需要对 qwen_online_tts 适配
- [ ] `TtsVoiceGallery` 当前 `canSelect` 逻辑对非腾讯=需要 hasCredentials；在线千问必须修正 hasCredentials 判断
- [ ] `PATCH /api/tts/configs/{id}` 保存后端会脱敏为 `***`；前端输入框需要复用现有 “****” 回显策略
- [ ] preview 接口超时较长（前端 client 已给 300s）；上传音色也需要设置较长 timeout（建议 120s~300s）

---

## 8. 验收清单（手工）

- [ ] 引擎列表能看到“千问在线 TTS”，切换后会激活 `qwen_online_tts_default`
- [ ] 填写 API Key 后，点击“测试连通性”成功
- [ ] 系统音色列表能加载、能试听、能设为当前音色
- [ ] 上传参考音频能创建复刻音色，状态为 ready，可试听
- [ ] 选择复刻音色为当前音色后，`active_voice_id` 写入并保持生效
- [ ] 删除复刻音色后列表刷新，删除后不会再被选中

