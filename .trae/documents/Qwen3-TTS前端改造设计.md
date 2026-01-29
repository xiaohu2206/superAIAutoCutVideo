# Qwen3-TTS 前端改造设计

## 目标与范围

目标：将现有「仅支持 Base 克隆音色」的 Qwen3-TTS 配置，重构为按三类模型能力组织的完整体验，并保持“模型下载/手动拷贝/校验”能力不变。

三类能力（按模型分类）：

- Base：语音克隆（上传参考音频 → 预处理 → 克隆音色 → 合成）
- CustomVoice：固定角色配音（选择内置说话人/语言 → 生成“角色音色条目” → 合成）
- VoiceDesign：文本设定角色配音（输入设计说明 → 生成参考音频 → 自动建克隆音色条目 → 合成）【尽量简洁】

不在本次范围：

- 具体代码实现与 UI 细节微调（本文件只给出架构与交互设计）
- 与其它 provider 的配置改造（仅定义 Qwen3-TTS 内部重构方式）

## 现状问题（必须修正）

现有实现的核心问题是“用 Base 克隆音色的结构去承载所有模式”，导致：

- 音色数据结构只支持 ref_audio_path（无法表达 CustomVoice 的 speaker/语言组合，无法表达 VoiceDesign 的设计输入与产物）
- UI 只有“上传参考音频/克隆”流程（见 [Qwen3VoiceSection.tsx](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/frontend/src/features/qwen3Tts/components/Qwen3VoiceSection.tsx)），缺少模式选择与模型能力引导
- 模型筛选只拿 base_*（见 Qwen3VoiceSection 的 modelKeys 逻辑），CustomVoice/VoiceDesign 模型难以进入用户路径

## 信息架构（IA）

前端页面分成两层：

1) 「配音形式」：面向“如何创建/使用音色”的入口（普通克隆/默认角色/设计克隆）
2) 「Qwen 音色列表」：面向“已有音色资产”的统一列表，独立于配音形式选择

对应 UI 结构建议：

- Qwen3-TTS 模型（保留现有下载/校验/复制路径能力）
- 配音形式（Radio/Tab）
- 模式面板（根据配音形式变化的创建向导）
- Qwen 音色列表（始终显示，所有模式创建的音色都在这里管理/试听/选择）

## 配音形式与交互流程

### A. 普通克隆配音（Base）

入口：用户选择“普通克隆配音”

展示的可下载模型：

- Qwen3-TTS-12Hz-0.6B-Base（内部 key：base_0_6b）
- Qwen3-TTS-12Hz-1.7B-Base（内部 key：base_1_7b）
- Qwen/Qwen3-TTS-12Hz-1.7B-Base（同属 base_1_7b 的远端来源展示）

创建流程：

1. 上传参考音频（文件）与可选 ref_text / instruct / x_vector_only_mode
2. 点击“开始克隆”（预处理任务：重采样、写入标准 wav、更新状态）
3. 克隆完成后自动：
   - 将新音色加入“Qwen 音色列表”
   - 设为当前使用音色（可选：按产品需求决定默认行为）

约束与提示：

- Base 模式必须依赖 Base 模型可用（模型不存在/校验失败时给出阻断提示与一键跳转下载）

### B. 默认角色配音（CustomVoice）

入口：用户选择“默认角色配音”

展示的可下载模型：

- Qwen3-TTS-12Hz-0.6B-CustomVoice（key：custom_0_6b）
- Qwen3-TTS-12Hz-1.7B-CustomVoice（key：custom_1_7b）
- Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice（同属 custom_1_7b 的远端来源展示）

创建流程（创建的是“角色音色条目”，不是上传克隆）：

1. 选择模型（0.6B/1.7B）
2. 选择语言（中文/英文/日文…，来源于后端查询模型支持能力）
3. 选择说话人（speaker，按语言分组/筛选）
4. 可选填写 instruct（风格指令）
5. 点击“创建音色”
6. 创建完成后统一进入“Qwen 音色列表”，可试听/可设为当前使用音色

约束与提示：

- speaker 必须来自模型支持列表（前端仅展示后端返回的支持项）
- 不需要 ref_audio，不需要“克隆/预处理”
### 说话人支持
说话人	语音描述	母语
Vivian	明亮、略带锐利感的年轻女声。	中文
Serena	温暖柔和的年轻女声。	中文
Uncle_Fu	音色低沉醇厚的成熟男声。	中文
Dylan	清晰自然的北京青年男声。	中文（北京方言）
Eric	略带沙哑但明亮活泼的成都男声。	中文（四川方言）
Ryan	富有节奏感的动态男声。	英语
Aiden	清晰中频、阳光的美式男声。	英语
Ono_Anna	轻快灵动的俏皮日语女声。	日语
Sohee	情感丰富的温暖韩语女声。	韩语

### C. 设计克隆配音（VoiceDesign → Base）

入口：用户选择“设计克隆配音”

展示的可下载模型：

- Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign（key：voice_design_1_7b）
- Qwen/Qwen3-TTS-12Hz-1.7B-Base（key：base_1_7b）
- Qwen3-TTS-12Hz-1.7B/0.6B-Base（key：base_1_7b/base_0_6b）

创建流程（以“设计说明生成参考音频 → 自动创建可复用克隆音色”为核心）：

1. 选择 VoiceDesign 模型（目前仅 1.7B）
2. 选择语言（建议默认 Auto，允许手动指定）
3. 输入：
   - 目标文本 text（用于生成一段参考音频）
   - 设计说明 instruct（用于描述角色音色）
4. 点击“生成并创建克隆音色”
5. 后端异步任务流程：
   - VoiceDesign 生成 reference.wav
   - 对 reference.wav 做 16k mono 标准化
   - 创建音色条目并标记为 ready
6. 进入“Qwen 音色列表”，可试听/可设为当前使用音色

说明：

- 设计克隆产物最终使用 Base 的 clone 机制进行后续合成，因此生成的音色条目在结构上更接近“普通克隆音色”，但带有 voice_design 元数据（instruct、reference_text 等）

## “Qwen 音色列表”统一透出规则

列表不受配音形式选择影响，始终展示全部音色条目，并且“模型支持的功能都透出给用户使用”，建议透出能力：

- 试听（统一调用 preview）
- 设为当前使用音色（ready 状态可选）
- 编辑（名称、语言、instruct 等，视后端允许字段）
- 删除（可选删除本地音频文件）
- 对需要异步处理的条目展示进度（普通克隆/设计克隆）

列表建议新增的视觉标签：

- 类型：普通克隆 / 默认角色 / 设计克隆
- 关联模型：base/custom/voice_design + 规模（0.6B/1.7B）
- 语言与说话人（默认角色必须显示 speaker）

## 前端状态与模块拆分建议

### 数据分层

建议把 Qwen3-TTS 从“组件自带状态”升级为“领域模块”分层：

- services：只负责 API 请求（保留 [qwen3TtsService.ts](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/frontend/src/features/qwen3Tts/services/qwen3TtsService.ts) 的模式）
- hooks：只负责请求状态与缓存（类似现有 useQwen3Models/useQwen3Voices）
- components：只负责渲染与交互

### 建议的领域对象

将现有 `Qwen3TtsVoice` 从“克隆音色”升级为“音色资产条目”，前端统一处理：

- id
- name
- kind：clone | custom_role | design_clone
- model_key
- language
- speaker（custom_role 必填）
- ref_audio_url/ref_audio_path（clone/design_clone 才有）
- status/progress/last_error（异步条目才会变化）
- meta（承载设计说明、原始文件信息等）

### 组件拆分（建议）

在现有 [Qwen3VoiceSection.tsx](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/frontend/src/features/qwen3Tts/components/Qwen3VoiceSection.tsx) 的基础上重构为：

- Qwen3EntrySection（容器：模型区 + 配音形式 + 模式面板 + 音色列表）
- Qwen3ModeSelector（配音形式选择器）
- Qwen3CloneCreatePanel（普通克隆配音创建面板：上传/开始克隆）
- Qwen3CustomRoleCreatePanel（默认角色创建面板：语言/说话人选择）
- Qwen3VoiceDesignCreatePanel（设计克隆创建面板：text/instruct + 创建）
- Qwen3VoiceList（保留并扩展：展示多种 kind）

## 与全局 TTS 设置的集成

现有入口位于 [TtsSettings.tsx](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/frontend/src/components/settingsPage/components/tts/TtsSettings.tsx#L325-L329)：

- `Qwen3VoiceSection` 仍作为子模块挂载
- “设为当前音色”继续调用外层 `handleSetActiveVoice`，但 activeVoiceId 应统一指向“音色资产条目 id”

## API 约定（前端需要的最小契约）

前端改造依赖后端提供更明确的能力与资源结构，以下为“前端视角的最小契约”（具体由后端设计文档给出）：

- 模型：
  - list models：返回每个 key 的 exists/valid/missing/path，额外返回 model_type（base/custom/voice_design）与 display_name 列表（用于展示用户关心的“Qwen3-TTS-12Hz-1.7B-Base”与 “Qwen/Qwen3…”）
  - download/validate/open-path：保持不变
- 音色资产：
  - list voices：返回统一 voice assets 列表（包含 kind、speaker、status 等）
  - create clone voice：上传文件创建（现有 upload 接口可升级为 create，或继续保留 upload）
  - create custom role voice：无需文件，传 model_key/language/speaker/instruct
  - create voice design clone：传 model_key/text/instruct/language，后端异步生成并创建音色资产
  - preview voice：统一用 voice_id 试听，返回 audio_url

## 迁移策略（平滑升级）

为了不打断已有用户：

- 保留现有“上传参考音频 → 克隆”能力，旧数据仍能展示
- 将旧的 voice 条目在列表上标为 kind=clone
- 新增 kind=custom_role/design_clone 后，列表统一处理，避免再开第二个列表

