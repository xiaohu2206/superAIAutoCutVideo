## 目标与现状
- 目标：参考 Qwen3-TTS 的“模型下载/校验/打开目录/下载进度（可刷新恢复）/中断”交互，新增「字幕识别」独立设置页，并在项目「提取字幕」时允许选择 ASR 类型（内置 API=bcut；本地 FunASR=本次新增）与语言。
- 现状：后端已提供 FunASR 模型管理与字幕提取参数（`asr_provider/asr_model_key/asr_language/itn/hotwords`），前端目前 `extract-subtitle` 只传 `force`，UI 也写死“只支持中文”。

## 1) 新增“字幕识别”设置页（独立组件）
### 1.1 设置页入口
- 修改 [constants.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/constants.ts)：新增 section `{ id: "subtitleAsr", label: "字幕识别", icon: Subtitles }`（新增图标 import）。
- 修改 [settingsPage/index.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/index.tsx)：新增 `case "subtitleAsr"` 渲染新组件 `SubtitleAsrSettings`。

### 1.2 组件与文件拆分（参考 qwen3Tts 但保持解耦）
在 `frontend/src/features/subtitleAsr/` 下新增：
- `services/funAsrService.ts`：对接后端 API
  - `GET /api/asr/funasr/models`
  - `POST /api/asr/funasr/models/validate`
  - `POST /api/asr/funasr/models/download`
  - `GET /api/asr/funasr/models/downloads`
  - `POST /api/asr/funasr/models/downloads/stop`
  - `GET /api/asr/funasr/models/open-path?key=...`
  - `GET /api/asr/funasr/acceleration-status`
  - `POST /api/asr/funasr/test`
- `types.ts`：定义 ModelStatus、DownloadTask、AccelerationStatus、TestResult 等类型（不复用 qwen3 的类型，避免耦合）。
- `hooks/useFunAsrModels.ts`：完全照 [useQwen3Models.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/features/qwen3Tts/hooks/useQwen3Models.ts) 的模式实现：
  - 列表 refresh + validate + download + stop + openDir
  - 页面刷新恢复：调用 `/models/downloads` 拉取运行中的任务
  - WS 监听：`scope: "fun_asr_models"`（与后端广播一致），更新 downloadsByKey
- `constants.ts`：
  - 模型选项：`Fun-ASR-Nano-2512`、`Fun-ASR-MLT-Nano-2512`（每个选项包含所需 keys；建议把 `fsmn_vad` 作为依赖一起检查/下载/校验）
  - 语言列表：
    - Nano：中文/英文/日文
    - MLT：按你给的 31 种中文名称
- `components/FunAsrModelOptionsList.tsx`：参考 [Qwen3ModelOptionsList.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/features/qwen3Tts/components/Qwen3ModelOptionsList.tsx) 做一个 FunASR 专用版本（避免复用导致耦合）。
- `components/FunAsrDownloadProgress.tsx`：参考 [Qwen3DownloadProgress.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/features/qwen3Tts/components/Qwen3DownloadProgress.tsx)
- `components/SubtitleAsrSettings.tsx`：设置页主体，包含：
  - 模型状态卡片（可下载/停止/校验/打开目录）
  - 加速状态（GPU/CPU）展示
  - “默认音频测试”：选择模型 + 语言（下拉），调用 `/api/asr/funasr/test` 展示识别结果/报错

## 2) 项目“提取字幕”时提供 ASR 选择与语言选择
### 2.1 扩展前端 Project 类型（与后端字段对齐）
- 修改 [project.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/types/project.ts)：给 `Project` 增加可选字段：
  - `asr_provider?: "bcut" | "fun_asr"`
  - `asr_model_key?: string | null`
  - `asr_language?: string | null`

### 2.2 修改提取字幕 API 调用以传参
- 修改 [projectService.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/services/projectService.ts#L346-L355)：
  - `extractSubtitle(projectId, opts)` 支持传 `{ force, asr_provider, asr_model_key, asr_language }`（以及预留 itn/hotwords）。
- 修改调用方 [useProjects.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/hooks/useProjects.ts#L370-L388) 与 [useProjectEditUploadStep.ts](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/hooks/useProjectEditUploadStep.ts)：
  - 在 `onExtractSubtitle` 中把当前 UI 选择的 provider/model/language 透传。

### 2.3 UI：在“字幕提取”区加入选择器（文件拆分）
- 新增组件 `frontend/src/components/projectEdit/SubtitleAsrSelector.tsx`：
  - ASR 类型：
    - 内置 API（bcut）— 强制语言=中文，UI 提示“仅支持中文”
    - FunASR（本地）— 可选择模型（Nano / MLT）与语言下拉
  - 语言下拉内容跟随模型：Nano 显示 中文/英文/日文；MLT 显示 31 种
  - 默认值：
    - 若项目已有 `project.asr_provider/asr_model_key/asr_language` 则回显
    - 否则默认 bcut + 中文
- 修改 [ProjectEditUploadStep.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/projectEdit/ProjectEditUploadStep.tsx)：
  - 替换现在顶部固定文案“自动解析字幕只支持中文语言”，改为：
    - bcut 模式下提示“内置 API 仅支持中文”
    - FunASR 模式下提示“可选语言；需先在设置-字幕识别下载模型”
  - 在“提取字幕”按钮上方插入 `SubtitleAsrSelector`。

## 3) 必要时的后端小改造（按需）
- 若前端需要“停止下载”走 path 参数风格（像 qwen3）：可在后端 [fun_asr_routes.py](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/routes/fun_asr_routes.py) 追加 `POST /models/downloads/{key}/stop`（与现有 body 版并存）。
- 若希望进度条显示“总大小”：在 [fun_asr_model_manager.py](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/modules/fun_asr_model_manager.py) 给两个模型 + VAD 增加近似 total_bytes 常量（否则前端仍可正常显示 downloadedBytes 与渐进进度）。

## 4) 验证方式
- 手工验证：
  - 设置页：模型列表加载、下载/停止/校验/打开目录、刷新页面后下载任务仍能恢复显示。
  - 项目页：选择 bcut → 语言锁中文；选择 FunASR → 可选模型与语言；点击提取字幕后 WS 进度正常滚动。
- 代码级校验：TypeScript 类型检查与构建（确保新增模块不引入循环依赖）。

如果你确认该方案，我会退出计划模式并开始按上述拆分直接编码实现（包含必要的后端小补丁）。