# 暗色主题未完成适配交接清单

## 背景

当前已经完成第一轮主题机制改造：

- `frontend/tailwind.config.js` 已改为 `darkMode: "class"`。
- `frontend/src/App.tsx` 已新增 `sacv_theme` 本地存储、首次跟随系统、切换后同步 `html.dark`。
- `frontend/src/components/Navigation.tsx` 已新增左侧主题切换按钮。
- `frontend/src/index.css` 已增加一批全局 `.dark` 兜底规则，暗色主背景为 `rgb(18, 18, 18)`。
- 项目管理首页相关组件做过第一轮暗色补丁。

但这只是基础层和首页层，项目编辑页、设置页、TTS/模型配置页仍有大量硬编码亮色 class。下一轮应继续全量扫描 `frontend/src`，补齐明显未适配暗色主题的 `bg-white/bg-gray/text-gray/border-gray/hover` 等样式。

## 目标

继续全量扫描 `frontend/src`，把所有明显没适配暗色主题的亮色硬编码补齐。重点优先级：

1. 项目编辑页：`ProjectEditPage.tsx` 及 `components/projectEdit/**`
2. 设置页：`components/settingsPage/**`
3. TTS/模型 feature：`features/omnivoiceTts/**`、`features/indextts/**`、`features/qwenOnlineTts/**`、`features/visionModel/**`、`features/subtitleAsr/**`
4. 登录/用户资料弹窗：`components/auth/**`

暗色视觉基准：

- App 主背景：`#121212`
- 面板/卡片：`#1f1f1f` 或 `#242424`
- 边框：`white/10` 到 `white/15`
- 主文字：`zinc-100`
- 次级文字：`zinc-400`
- disabled/placeholder：`zinc-500`
- hover：`white/10` 或对应品牌色 `*-500/10`

## 高优先级文件

这些文件命中硬编码亮色样式最多，且属于用户高频流程。建议优先处理。

### 项目编辑主流程

- `frontend/src/pages/ProjectEditPage.tsx`
  - 顶部项目标题栏仍有 `bg-white`、`bg-gray-100`、`text-gray-*`。
  - `stepButtonClass` 需要返回带 `dark:` 的 active/disabled/idle 状态。
  - 顶部步骤分段控件暗色应为 `dark:bg-[#1f1f1f]` 或 `dark:bg-white/10`。

- `frontend/src/components/projectEdit/ProjectOperations.tsx`
  - 扫描命中最多，优先级最高。
  - 重点检查操作按钮、状态块、提示块、导出/下载/删除一类区域。

- `frontend/src/components/projectEdit/ProjectEditUploadStep.tsx`
  - 上传页有多处上传区域、提示、进度、表格/列表。
  - 文件/视频源子区域可能仍有白底和浅灰边框。

- `frontend/src/components/projectEdit/ProjectEditCopywritingStep.tsx`
  - 命中很多，重点检查文案编辑区、生成日志、按钮、结果面板。

- `frontend/src/components/projectEdit/ProjectEditGenerateStep.tsx`
  - 命中较少但属于主流程第三步，需确认生成状态、按钮、结果区域。

- `frontend/src/components/projectEdit/VideoSourcesManager.tsx`
  - 上传视频列表、拖拽排序行、进度条、说明标签仍有大量灰白样式。

- `frontend/src/components/projectEdit/SceneListTable.tsx`
  - 表格、表头、行 hover、空态、操作按钮需要暗色。

- `frontend/src/components/projectEdit/OmniMultimodalShotsTable.tsx`
  - Omni 镜头表格和操作区需要统一暗色。

- `frontend/src/components/projectEdit/SubtitleEditor.tsx`
  - 字幕编辑区域、表格行、输入框、按钮需要重点检查。

- `frontend/src/components/projectEdit/TaskQueueFloatingBall.tsx`
  - 浮动任务面板、弹出列表、状态块可能仍是白底。

### 项目编辑弹窗和高级配置

- `frontend/src/components/projectEdit/TrimVideoModal.tsx`
- `frontend/src/components/projectEdit/TrimRangesPanel.tsx`
- `frontend/src/components/projectEdit/TrimPlayerPanel.tsx`
- `frontend/src/components/projectEdit/timeline/TrimTimelineUi.tsx`
- `frontend/src/components/projectEdit/advancedConfig/OriginalRatioSlider.tsx`
- `frontend/src/components/projectEdit/advancedConfig/PromptTemplateList.tsx`
- `frontend/src/components/projectEdit/advancedConfig/ScriptLengthSelector.tsx`
- `frontend/src/components/projectEdit/advancedConfig/CustomScriptLengthModal.tsx`
- `frontend/src/components/projectEdit/advancedConfig/TemplateModal.tsx`
- `frontend/src/components/projectEdit/advancedConfig/DeleteConfirmModal.tsx`
- `frontend/src/components/projectEdit/advancedConfig/PreviewModal.tsx`

处理重点：

- 模态框容器：`dark:bg-[#1f1f1f] dark:border-white/10`
- 模态框 footer：`dark:bg-[#181818] dark:border-white/10`
- 表单输入：`dark:bg-[#242424] dark:border-white/10 dark:text-zinc-100`
- 表格/列表 hover：`dark:hover:bg-white/10`
- 预览/代码块：`dark:bg-[#181818] dark:text-zinc-200`

### Omni 子流程

- `frontend/src/components/projectEdit/omni/ShotPickerModal.tsx`
- `frontend/src/components/projectEdit/omni/BulkTtsChoiceModal.tsx`
- `frontend/src/components/projectEdit/omni/OmniScriptPreviewPanel.tsx`
- `frontend/src/components/projectEdit/omni/OmniScriptSegmentList.tsx`
- `frontend/src/components/projectEdit/omni/OmniFullNarrationScriptWorkspace.tsx`
- `frontend/src/components/projectEdit/omni/SegmentDurationControl.tsx`
- `frontend/src/components/projectEdit/omni/SegmentTypeToggle.tsx`

部分 Omni 文件已有 `dark:`，但不完整。要检查是否仍有未配套的 `bg-white`、`border-gray-*`、`text-gray-*`。

## 设置页重点清单

设置页外壳已有部分暗色，但内部配置组件仍有大量硬编码。

### 设置页入口

- `frontend/src/components/settingsPage/index.tsx`
  - 右侧内容区现在是 `dark:bg-gray-900/70`，建议统一成 `dark:bg-[#121212]` 或 `dark:bg-[#181818]/70`。
  - 侧栏 active/hover 可继续保留蓝色，但背景建议从 `dark:bg-gray-900` 收敛到 `#181818`。

### 模型配置

- `frontend/src/components/settingsPage/components/models/aiSearchShot/AiSearchShotModelSettings.tsx`
  - 命中 32 处，是设置页最高优先级之一。
  - 需要处理平台选择、API 输入、向量模型/召回模型卡片、测试结果、超时/重试输入。

- `frontend/src/components/settingsPage/components/models/video/UnifiedModelSettings.tsx`
  - 命中 30 处。
  - 需要处理模型管理卡片、测试结果、模型列表、进度条、输入框和按钮。

- `frontend/src/components/settingsPage/components/models/integrated/IntegratedModelSettings.tsx`
  - 命中 29 处。
  - 部分已有 `dark:`，但表单 label、输入框、底部按钮仍需补齐。

- `frontend/src/components/settingsPage/components/models/video/VideoModelSettings.tsx`
- `frontend/src/components/settingsPage/components/models/content/ContentModelSettings.tsx`
  - 表单 label/input/button/result panel 需要补齐暗色。

### 监控和基础设置

- `frontend/src/components/settingsPage/components/WebSocketMessagesPanel.tsx`
- `frontend/src/components/settingsPage/components/LogConsolePanel.tsx`
- `frontend/src/components/settingsPage/components/StatusPanel.tsx`
- `frontend/src/components/settingsPage/components/GlobalParamsSettings.tsx`
- `frontend/src/components/settingsPage/components/AboutSection.tsx`
- `frontend/src/components/settingsPage/components/FilePickerDemo.tsx`
- `frontend/src/components/settingsPage/components/JianyingDraftPathSection.tsx`
- `frontend/src/components/settingsPage/components/StorageSettingsSection.tsx`

`StorageSettingsSection.tsx` 已有较多 `dark:`，但仍有零散重复/错误 class，例如 `text-slate-500  text-gray-500`，建议顺手清理。

### TTS 设置

- `frontend/src/components/settingsPage/components/tts/TtsSettings.tsx`
- `frontend/src/components/settingsPage/components/tts/TtsVoiceGallery.tsx`
- `frontend/src/components/settingsPage/components/tts/TtsCredentialForm.tsx`
- `frontend/src/components/settingsPage/components/tts/TtsCredentialFormQwenOnline.tsx`
- `frontend/src/components/settingsPage/components/tts/TtsSpeedSlider.tsx`
- `frontend/src/components/settingsPage/components/tts/LabeledGroup.tsx`

建议先处理容器、输入框、按钮和 voice card，避免暗色下出现大片白色卡片。

## Feature 目录重点清单

这些组件被设置页或编辑页引用，用户会直接看到。

- `frontend/src/features/omnivoiceTts/components/OmniVoiceTtsSection.tsx`
  - 命中 38 处。
  - 克隆音色、生成试听、连通性测试、删除弹窗都有白底/灰字/灰边。

- `frontend/src/features/indextts/components/IndexTtsSection.tsx`
  - 命中 38 处。
  - 与 OmniVoice 类似，应并行按同一规则处理。

- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceList.tsx`
- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceUploadDialog.tsx`
- `frontend/src/features/qwenOnlineTts/components/QwenOnlineVoiceSection.tsx`
  - 音色列表、上传弹窗、按钮、空态需要补齐。

- `frontend/src/features/visionModel/components/VisionModelSettings.tsx`
- `frontend/src/features/visionModel/components/MoondreamLocalModelPanel.tsx`
  - 模型管理/模型测试卡片、状态 badge、进度条、结果区需要统一暗色。

- `frontend/src/features/subtitleAsr/components/SubtitleAsrSettings.tsx`
- `frontend/src/features/subtitleAsr/components/FunAsrModelOptionsList.tsx`
- `frontend/src/features/subtitleAsr/components/FunAsrDownloadProgress.tsx`
  - ASR 模型卡片、下载状态、空态、按钮需要补齐。

## 认证/用户资料

这些不是本次重点，但会被导航登录入口触发，暗色下也容易露白。

- `frontend/src/components/auth/LoginRegisterModal.tsx`
- `frontend/src/components/auth/UserProfile.tsx`
- `frontend/src/components/auth/UserProfileLicenses.tsx`

建议统一：

- 弹窗：`dark:bg-[#1f1f1f] dark:border-white/10`
- 输入 wrapper：`dark:bg-[#242424] dark:border-white/10`
- tab active：`dark:bg-white/10 dark:text-zinc-100`
- license card：`dark:bg-[#242424] dark:border-white/10`

## 建议实施方式

不要只依赖 `index.css` 的全局覆盖。当前全局覆盖能兜底一部分，但很多组件使用：

- 条件字符串返回 class，例如 `isActive ? "bg-white text-gray-900" : ...`
- 渐变背景，例如 `from-white via-...`
- 组合 class，例如 `bg-white/80`、`border` 无颜色、`text-gray-700`
- 弹窗 footer、表格 hover、disabled 状态

这些需要在组件里显式加 `dark:`，否则视觉不稳定。

推荐处理规则：

- `bg-white` -> `dark:bg-[#1f1f1f]`
- `bg-white/80`、`bg-white/90` -> `dark:bg-[#1f1f1f]/80` 或 `/90`
- `bg-gray-50`、`bg-slate-50` -> `dark:bg-[#181818]`
- `bg-gray-100`、`bg-slate-100` -> `dark:bg-[#242424]` 或 `dark:bg-white/10`
- `border-gray-200`、`border-slate-200` -> `dark:border-white/10`
- `border-gray-300`、`border-slate-300` -> `dark:border-white/15`
- `text-gray-900`、`text-slate-900`、`text-slate-950` -> `dark:text-zinc-100`
- `text-gray-700`、`text-slate-700` -> `dark:text-zinc-200`
- `text-gray-600`、`text-slate-600` -> `dark:text-zinc-300`
- `text-gray-500`、`text-slate-500` -> `dark:text-zinc-400`
- `text-gray-400`、`text-slate-400` -> `dark:text-zinc-500`
- `hover:bg-gray-50`、`hover:bg-slate-50` -> `dark:hover:bg-white/10`
- `hover:bg-gray-100`、`hover:bg-slate-100` -> `dark:hover:bg-white/10`
- `divide-gray-100/200` -> `dark:divide-white/10`
- 表单输入统一加：`dark:bg-[#242424] dark:border-white/10 dark:text-zinc-100 dark:placeholder:text-zinc-500`
- 结果/日志/代码块统一加：`dark:bg-[#181818] dark:border-white/10 dark:text-zinc-200`

## 快速扫描命令

用下面命令找剩余高风险 class：

```powershell
rg "bg-white|bg-gray-|bg-slate-|text-gray-|text-slate-|border-gray-|border-slate-|hover:bg-gray-|hover:bg-slate-|divide-gray-|divide-slate-" frontend\src -n
```

按文件命中数排序：

```powershell
$patterns='bg-white|bg-gray-|bg-slate-|text-gray-|text-slate-|border-gray-|border-slate-|hover:bg-gray-|hover:bg-slate-|divide-gray-|divide-slate-'
rg $patterns frontend\src -n | ForEach-Object { ($_ -split ':')[0] } | Group-Object | Sort-Object Count -Descending | Select-Object Count,Name
```

只看项目编辑页：

```powershell
rg "bg-white|bg-gray-|bg-slate-|text-gray-|text-slate-|border-gray-|border-slate-|hover:bg-gray-|hover:bg-slate-|divide-gray-|divide-slate-" frontend\src\pages\ProjectEditPage.tsx frontend\src\components\projectEdit -n
```

只看设置页：

```powershell
rg "bg-white|bg-gray-|bg-slate-|text-gray-|text-slate-|border-gray-|border-slate-|hover:bg-gray-|hover:bg-slate-|divide-gray-|divide-slate-" frontend\src\components\settingsPage frontend\src\features -n
```

## 验收清单

完成后至少检查：

- 项目编辑页三步流程：上传、文案生成、生成视频。
- 项目编辑页内所有弹窗：裁剪、覆盖确认、Omni 选择、镜头选择、模板/预览/删除。
- 设置页所有左侧 section：聚合模型、剪映路径、TTS、字幕识别、存储、全局参数、监控、关于。
- TTS 相关页面：OmniVoice、IndexTTS、Qwen 在线音色列表和上传弹窗。
- 登录/用户资料弹窗。

执行验证：

```powershell
cd frontend
npm run build
npm run type-check
```

注意：当前 `npm run type-check` 在主题改造前后都被既有问题阻塞，常见错误包括未使用变量和旧类型问题。不要把这些全部归因到暗色主题改造；若只做主题补齐，至少确保 `npm run build` 通过。

## 额外注意

- 不要回退已经完成的主题机制：`darkMode: "class"`、`sacv_theme`、`Navigation` 主题按钮都要保留。
- 不要把暗色主背景改回 Tailwind 默认 `gray-900`，用户明确要求暗黑背景颜色为 `18,18,18`。
- 如果遇到局部组件颜色很多，优先改容器、文字、边框、hover 和输入框，不要做大范围结构重构。
- 处理条件 class 时，亮色分支保持现状，只给暗色追加 `dark:`。
