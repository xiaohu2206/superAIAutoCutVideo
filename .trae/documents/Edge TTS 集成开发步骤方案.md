# Edge TTS 集成开发步骤方案

目标：在现有项目中新增 Edge TTS（基于 edge-tts Python 库），与已有的腾讯云 TTS 并存，前后端均保持低耦合，UI 支持引擎切换、音色预览、语速设置、连通性测试。参考开源项目：https://github.com/rany2/edge-tts

## 一、准备工作

1. 安装依赖
   - 后端新增依赖：在 `backend/requirements.txt` 与（如有）`requirements.runtime.txt` 中添加：
     - `edge-tts>=6.1.12`（版本以实际为准）
   - 执行安装：`pip install -r backend/requirements.txt`

2. 目录与静态文件
   - 确认 FastAPI 已挂载静态目录 `/uploads` 与 `/backend/serviceData`（已存在）。
   - 新增音频预览存储目录：`backend/serviceData/tts/previews/`（用于保存试听文件）。
   - 若无自动创建机制，在启动或首次使用时确保目录存在。

## 二、后端开发

1. 新增 Edge TTS 服务类（与腾讯云分开，低耦合）
   - 新建文件：`backend/modules/tts/edge_tts_service.py`
   - 实现类 `EdgeTtsService`，包含：
     - `async list_voices()`：使用 `edge_tts.list_voices()` 拉取最新音色数据；若失败，则从缓存文件读取（见下文缓存策略）。
     - `async synthesize(text: str, voice_id: str, rate_percent: int) -> Tuple[file_path, url]`：使用 `edge_tts.Communicate(text, voice=voice_id, rate=f"{rate_percent:+d}%")` 生成音频文件（mp3/wav），保存到 `backend/serviceData/tts/previews/`，返回文件路径与可访问 URL（通过已挂载静态目录）。
     - 参数映射：`speed_ratio`（如 1.0、1.2、0.8）转换为 `rate_percent`（如 0、+20、-20）。

2. 音色缓存与数据映射
   - 新建缓存文件（可选）：`backend/serviceData/tts/edge_voices_cache.json`
   - `list_voices()` 获取后将原始数据缓存至上述 json，缓存策略：
     - TTL：24 小时；
     - 若在线拉取失败，使用缓存；缓存为空则返回空列表并提示前端。
   - 将 `edge-tts` 的字段映射为项目前端 `TtsVoice`：
     - `id`: ShortName（如 `zh-CN-XiaoxiaoNeural`）
     - `name`: FriendlyName（若无则使用 ShortName）
     - `language`: Locale（如 `zh-CN`）
     - `gender`: Gender（如 `Female/Male`）
     - `description`: 合成 `Locale + FriendlyName` 或原描述
     - 其他可选：`voice_quality`: 固定填充为 `Neural`；`voice_type_tag`: 为空；`voice_human_style`: 来自 `StyleList`（如有）

3. 扩展 TTS 配置管理
   - 文件：`backend/modules/config/tts_config.py`
   - 在 `TtsEngineConfigManager` 中新增 `EDGE_TTS` 的引擎元信息：
     - provider: `edge_tts`
     - display_name: `Edge TTS（微软）`
     - description: `免费，无需密钥；支持多语言神经音色`
     - required_fields: `[]`（无需凭据）
     - optional_fields: `["speed_ratio", "active_voice_id"]`
   - 新增获取 `edge_tts` 音色列表的分支逻辑：
     - `get_voice_list(provider="edge_tts") -> List[TtsVoice]`：调用 `EdgeTtsService.list_voices()`
   - 默认配置生成：
     - 当不存在 `edge_tts_default` 时创建：
       - `provider="edge_tts"`
       - `enabled=False`
       - `secret_id=None, secret_key=None, region=None`
       - `speed_ratio=1.0`
       - `active_voice_id=None`
       - `extra_params={}`

4. 路由改造（后端 API）
   - 文件：`backend/routes/tts_routes.py`
   - GET `/api/tts/engines`：返回包含两个引擎元信息（`tencent_tts` 与 `edge_tts`）。
   - GET `/api/tts/voices?provider=edge_tts`：
     - 调用 `EdgeTtsService.list_voices()` 返回音色列表。
   - GET `/api/tts/configs`：
     - 返回当前所有引擎配置（含 `edge_tts_default`），以及 `active_config_id`。
   - PATCH `/api/tts/configs/{configId}`：
     - 对 `edge_tts_default` 允许更新 `speed_ratio`、`active_voice_id`、`enabled`、`description`、`extra_params`；
     - 忽略/不保存 `secret_id/secret_key/region`。
   - POST `/api/tts/configs/{configId}/activate`：
     - 切换激活引擎为 `edge_tts_default` 时，仅设置激活状态，不校验凭据。
   - POST `/api/tts/configs/{configId}/test`：
     - `edge_tts` 执行一次简短合成（文本如 `"你好，这是 Edge TTS 测试"`），使用当前或默认音色，返回 `success`/耗时/信息。
   - POST `/api/tts/voices/{voiceId}/preview`：
     - 请求体接受 `{ text?: string; provider?: string; config_id?: string }`
     - 当 `provider=edge_tts` 时，调用 `EdgeTtsService.synthesize(...)` 生成试听音频，返回 `audio_url`（或 `sample_wav_url` 字段，前端已兼容）。

5. 日志与错误处理
   - 在 `EdgeTtsService` 的网络/IO 操作处加入异常捕获，统一返回错误信息。
   - 缓存读取失败时，记录日志并返回空列表或错误码给前端。

## 三、前端开发

1. 引擎选择 UI
   - 文件：`frontend/src/components/settingsPage/components/tts/TtsEngineSelect.tsx`
   - 改动：
     - 移除固定文案“当前仅支持腾讯云 TTS”；
     - 按 `engines` 动态渲染 `{display_name}`，展示 `description`；
     - 保持 `onProviderChange` 事件不变。

2. 统一凭据表单处理
   - 文件：`frontend/src/components/settingsPage/components/tts/TtsCredentialForm.tsx`
   - 改动：
     - 根据当前配置 `config.provider` 或引擎元信息 `required_fields` 判断是否显示 `secret_id/secret_key/region` 输入框；
     - 当 `provider=edge_tts` 时隐藏凭据输入，展示说明“该引擎无需密钥”；保留“测试连通性”按钮可用。

3. TTS 设置页逻辑
   - 文件：`frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`
   - 改动：
     - `hasCredentials` 计算：若当前引擎 `required_fields` 为空（Edge TTS），则视为“无需凭据”，UI 状态不降级；
     - 初始化流程：`getEngines()` 返回后，若未配置 `edge_tts_default`，调用创建默认配置接口；
     - `loadVoices(provider)` 兼容 `edge_tts`；
     - 试听逻辑：若无 `sample_wav_url`，调用 `ttsService.previewVoice(voiceId, { provider, config_id, text })` 获取 `audio_url` 并播放；
     - 语速滑块依旧使用 `speed_ratio`（映射与后端一致）。

4. 服务层与类型
   - 文件：`frontend/src/services/ttsService.ts` 与 `clients.ts`
     - 保持现有 API 方法不变（后端已兼容 `provider=edge_tts`）。
   - 文件：`frontend/src/components/settingsPage/types.ts`
     - `TtsEngineMeta` 用 `required_fields: []` 表示无需凭据；
     - `TtsVoice` 字段保持不变，Edge TTS 映射字段即可。
   - 文件：`frontend/src/components/settingsPage/utils.ts`
     - `getTtsConfigIdByProvider("edge_tts")` 返回默认 `edge_tts_default`（现有逻辑已支持）。

5. 音色库 UI
   - 文件：`frontend/src/components/settingsPage/components/tts/TtsVoiceGallery.tsx`
   - 若 `edge_tts` 音色无 `sample_wav_url`，依旧通过 `preview` 接口返回的 `audio_url` 播放（现有逻辑已兼容，无需改动）。

## 四、接口与数据契约（示例，无须分析）

1. GET `/api/tts/engines` 响应示例
   - `[{ provider:"tencent_tts", display_name:"腾讯云 TTS", required_fields:["secret_id","secret_key","region"] }, { provider:"edge_tts", display_name:"Edge TTS（微软）", required_fields:[] }]`

2. GET `/api/tts/voices?provider=edge_tts` 响应示例
   - `[{ id:"zh-CN-XiaoxiaoNeural", name:"Xiaoxiao", language:"zh-CN", gender:"Female", description:"zh-CN Xiaoxiao" }]`

3. GET `/api/tts/configs` 响应示例
   - `{ configs:{ "edge_tts_default": { provider:"edge_tts", enabled:false, speed_ratio:1.0, active_voice_id:null, extra_params:{} }, "tencent_tts_default":{ ... } }, active_config_id:"tencent_tts_default" }`

4. POST `/api/tts/voices/{voiceId}/preview` 请求示例
   - `{ text:"你好，欢迎使用 Edge TTS", provider:"edge_tts", config_id:"edge_tts_default" }`
   - 响应：`{ success:true, audio_url:"/backend/serviceData/tts/previews/xxx.mp3" }`

5. POST `/api/tts/configs/{configId}/test` 响应示例
   - `{ success:true, config_id:"edge_tts_default", provider:"edge_tts", message:"合成成功，用时 230ms" }`

## 五、开发步骤清单

后端：
1. 新增文件 `backend/modules/tts/edge_tts_service.py`，实现 `list_voices` 与 `synthesize`。
2. 在 `backend/modules/config/tts_config.py`：
   - 添加 `edge_tts` 引擎元信息；
   - 扩展 `get_voice_list` 支持 `edge_tts`；
   - 默认创建 `edge_tts_default` 配置。
3. 在 `backend/routes/tts_routes.py`：
   - `GET /api/tts/engines` 返回 Edge TTS；
   - `GET /api/tts/voices` 兼容 `provider=edge_tts`；
   - `PATCH/GET/POST` 配置与测试接口兼容 Edge TTS；
   - `POST /api/tts/voices/{voiceId}/preview` 支持 Edge TTS 的试听合成。
4. 新增并确保可写目录 `backend/serviceData/tts/previews/`；实现 URL 返回。
5. 加入缓存机制 `backend/serviceData/tts/edge_voices_cache.json`，`list_voices` 调用时读写缓存。
6. 在 `backend/requirements.txt` 添加 `edge-tts` 并安装。
7. 编写错误处理与日志。

前端：
8. 更新 `TtsEngineSelect.tsx`：动态渲染引擎（含 Edge TTS），移除固定提示。
9. 更新 `TtsCredentialForm.tsx`：当 `provider=edge_tts` 隐藏凭据输入，保留测试按钮。
10. 更新 `TtsSettings.tsx`：
    - `hasCredentials` 按 `required_fields` 判定，Edge TTS 视为无需凭据；
    - 初始化时若不存在 `edge_tts_default`，调用创建/保存默认配置；
    - `loadVoices("edge_tts")` 获取音色列表；
    - 试听调用 `preview` 接口播放返回 `audio_url`。
11. 确认 `ttsService.ts` 与 `clients.ts` 无需改动（已按 provider 参数路由）。
12. 验证 `TtsVoiceGallery.tsx` 试听逻辑对 `audio_url` 的兼容。

测试与验收：
13. 单元测试：后端 `EdgeTtsService.list_voices`、`synthesize`、路由返回；异常网络情况下缓存回退。
14. 联调测试：前端引擎切换、音色列表加载、试听播放、语速调节、激活引擎。
15. 跨平台测试：macOS/Windows 下播放路径与静态服务可用性。
16. 文档与演示：在 README/设置页帮助中新增 Edge TTS 使用说明。

## 六、配置与默认值建议

- `edge_tts_default`：
  - `speed_ratio`: 1.0（映射 rate="+0%"）
  - `active_voice_id`: 推荐默认中文音色（如 `zh-CN-XiaoxiaoNeural`），若首次拉取为空则留空。
- 试听文本默认值：`"你好，欢迎使用 Edge TTS"`（可在前端提供可编辑输入框，当前结构已支持在请求体传入）

## 七、注意事项

- Edge TTS 不需要密钥，前端 UI 不应将其视为“降级”；连通性测试应可正常运行。
- 语速映射需与后端一致：`speed_ratio`（0.5~2.0）映射到 `rate` 百分比（-50%~+100%）可根据产品需要做限制。
- 声音列表缓存避免频繁请求官方声库列表，提升性能；设置 TTL 并提供手动刷新机制（后续可扩展）。
- 试听生成的音频文件需清理策略（例如按时间/数量清理），避免累积占用空间。


        