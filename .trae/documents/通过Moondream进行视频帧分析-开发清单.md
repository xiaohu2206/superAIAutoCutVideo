# 通过 Moondream 分析视频帧 — 开发清单

目标：在现有“提取镜头”流程完成镜头分割后，基于每个镜头（含合并信息 merged_from）抽取中间帧，使用 Moondream 模型进行视觉理解，回填到场景结果中；并提供设置页的模型管理与测试能力，以及前端进度可视化与列表展示。


## 背景与参照

- 设置页栏目位置参考：[constants.ts:L21-34](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/constants.ts#L21-L34)
- FunASR 模型管理与下载/校验/测试参考（比照实现接口/状态流）：
  - 路由参考：[fun_asr_routes.py:L365-543](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/routes/fun_asr_routes.py#L365-L543)
  - 模型路径与校验参考：[fun_asr_model_manager.py](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/modules/fun_asr_model_manager.py)
- 镜头分割产出结构与 merged_from 字段来源：
  - 计算流程与保存 JSON 参考：[extract_scene_service.py:L62-391](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/services/extract_scene_service.py#L62-L391) 和优化合并逻辑 [extract_scene_service.py:L392-523](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/services/extract_scene_service.py#L392-L523)
  - 场景数据拉取接口：[project_routes.py:L619-679](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/backend/routes/project_routes.py#L619-L679)
- 前端展示与交互位置：
  - 上传/提取页主容器：[ProjectEditUploadStep.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/projectEdit/ProjectEditUploadStep.tsx)
  - 场景列表展示（需新增列显示分析内容）：[SceneListTable.tsx:L10-54](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/projectEdit/SceneListTable.tsx#L10-L54)
  - FunASR 设置页参考实现：[SubtitleAsrSettings.tsx](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/features/subtitleAsr/components/SubtitleAsrSettings.tsx)
- Moondream GPU 参考代码与依赖样例（Windows 可使用 GPU 加速）：[docs/cache/moondream-gpu](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/docs/cache/moondream-gpu)
- Moondream2 GGUF 模型下载页（提供给用户复制/下载）：https://www.modelscope.cn/models/moondream/moondream2-gguf/files


## 功能范围

1) 设置页新增“视觉分析模型”Tab，仅支持选择“Moondream”模型；支持打开目录、校验完整性、（可选）一键下载与停止、测试推理。
2) “提取镜头”流程完成后，对每个 scene 抽取中帧进行视觉分析；当 scene 是多个原始镜头合并而成（存在 merged_from）时，按 merged_from 内每个原始片段各抽取一帧并分析，结果汇总回填一个字符串字段用于展示。
3) 提供分析模式：
   - 视觉分析不带字幕的镜头（仅 subtitle 为“无”的 scene）
   - 视觉分析所有镜头
4) 分析过程中透出进度（总进度含镜头分割 + 视觉分析两个阶段）。
5) SceneListTable 新增一列展示“视觉分析”结果。
6) 代码组织：功能独立文件，封装函数，遵从现有模块风格与路径管理约定。


## 模型目录与校验规范

Moondream2-GGUF 模型目录结构（根目录可由环境变量或默认路径决定）：

```
configuration.json
moondream2-mmproj-f16.gguf
moondream2-text-model-f16.gguf
moondream2.preset.json
README.md                 # 可选
.gitattributes            # 可选
```

路径管理策略：

- 环境变量：`MOONDREAM_MODELS_DIR`（优先）
- 默认：`uploads/models/Moondream`（基于后端 `uploads_dir()`，参照 FunASR 放置到 `uploads/models/<Component>`）。

校验规则：

- 必须存在：`configuration.json`、`moondream2-mmproj-f16.gguf`、`moondream2-text-model-f16.gguf`、`moondream2.preset.json`
- 可选：`README.md`、`.gitattributes`


## 架构与数据流

- 触发：前端点击“提取镜头” → 后端进行镜头分割 → 完成后调用帧分析服务 → 更新 `{project_id}_scenes.json` → 前端刷新结果并展示“视觉分析”列。
- 统一进度：沿用 `task_progress_store`，scope 使用 `extract_scene`，phase 从 `analyze_vision_start` 到 `analyze_vision_done`，总进度覆盖两个阶段。
- 并发：帧分析支持高并发（默认无限制，可配置），避免阻塞事件循环。


## 后端实施清单

1. 模型路径与校验
   - 新增模块：`backend/modules/moondream_model_manager.py`
     - `MoondreamPathManager`：解析模型根目录（支持 `MOONDREAM_MODELS_DIR`），构造默认路径 `uploads/models/Moondream/Moondream2-GGUF`。
     - `validate_model_dir(model_dir: Path) -> Tuple[bool, List[str]]`：按上文校验规范返回缺失项。
     - （可选）`download_model_snapshot(provider="modelscope")`：调用 ModelScope SDK 下载；或提示用户手动下载/复制到目录。

2. 模型管理与测试路由（比照 FunASR 路由风格）
   - 新增：`backend/routes/moondream_routes.py`
     - `GET /vision/moondream/models`：返回当前本地模型状态（路径、exists、valid、missing、sources）。
     - `POST /vision/moondream/models/validate`：校验目录完整性。
     - `POST /vision/moondream/models/download`、`GET /vision/moondream/models/downloads`、`POST /vision/moondream/models/downloads/stop`（可选，与 FunASR 同步语义）。
     - `GET /vision/moondream/models/open-path?`：打开系统文件管理器至模型目录父层。
     - `POST /vision/moondream/test`：使用内置示例图片运行一次简单 caption 以验证模型可用（若无示例则用视频封面帧或占位图）。

3. 帧抽取与视觉分析服务
   - 新增：`backend/services/vision_frame_analysis_service.py`
     - `class VisionFrameAnalyzer`：
       - `extract_center_frame(video_path: Path, t_start: float, t_end: float) -> np.ndarray`：使用 OpenCV 抽取中位时间的单帧（RGB）。
       - `infer_with_moondream(img: np.ndarray) -> str`：载入 Moondream GGUF（llama-cpp-python 后端，Windows 可启用 GPU），返回简要描述文本；内部可调用 `docs/cache/moondream-gpu` 示例中的图像优化逻辑（等比缩放到 1024 最大边）。
       - `analyze_scenes(video_path, scenes, mode, progress_cb)`：按模式决定分析的 scene 集合；如 scene.merged_from 为多个原始片段，则分别在每个原始片段中取中帧，依次推理，拼接结果（使用 `；` 分隔）。
     - 并发：
       - 使用 `asyncio` + `run_in_executor` 或 `asyncio.Semaphore` 控制负载；默认无限制（“无上限并发”），提供环境变量 `VISION_ANALYSIS_MAX_CONCURRENCY`（0/空为无限制）。
     - 进度透出：
       - 在 `extract_scene_service` 完成分割写入后，继续调用 `VisionFrameAnalyzer.analyze_scenes`；按总数量分配 10%→100% 的余量进度（例如分割完成时 90%，分析逐帧累计至 100%）。

4. 与镜头分割服务集成
   - 修改：`backend/services/extract_scene_service.py`
     - 在任务末尾（完成镜头 JSON 写入后）根据请求参数 `analyze_vision` 与 `vision_mode` 触发帧分析；
     - 更新已生成的 `{project_id}_scenes.json`：为每个 scene 增加 `vision` 字段（字符串，合并多帧结果）。
   - 修改：`backend/routes/project_routes.py`
     - `POST /{project_id}/extract-scene` 接收可选参数：
       ```json
       { "force": false, "task_id": "...", "analyzeVision": true, "visionMode": "no_subtitles" | "all" }
       ```
     - 进度接口沿用 `/{project_id}/scene-status/{task_id}`，message/phase 体现“视觉分析”阶段文案。


## 前端实施清单

1. 设置页 Tab
   - 修改栏目配置：在设置页增加“视觉分析模型”（如 id: `visionModel`）。参考：[constants.ts:L21-34](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/settingsPage/constants.ts#L21-L34)。
   - 新增模块：`frontend/src/features/visionModel`
     - `components/VisionModelSettings.tsx`：比照 `SubtitleAsrSettings.tsx`，提供模型状态、打开目录、校验、（可选）下载/停止、测试按钮；
     - `services/moondreamService.ts`：封装 `/vision/moondream/*` 路由；
     - `hooks/useMoondreamModels.ts`：管理模型状态/下载/验证/测试。

2. 项目编辑页交互
   - 在“提取镜头”按钮旁新增模式选择（单选）：
     - “视觉分析不带字幕的镜头”
     - “视觉分析所有镜头”
     - 默认选“不带字幕的镜头”。
   - 发起 `extract-scene` 请求时携带 `analyzeVision` 与 `visionMode` 参数；
   - 进度条：在现有“镜头提取进度”下方增加“视觉分析进度”或复用同一条进度，以阶段文案区分；
   - 场景列表：`SceneListTable` 新增一列“视觉分析”，展示 `scene.vision` 内容（溢出省略，hover 提示完整文本）。参照：[SceneListTable.tsx:L10-54](file:///Users/jiangchao/Documents/%E6%B1%9F%E6%B1%90%E7%91%B6/%E5%AD%A6%E4%B9%A0/%E6%B5%8B%E8%AF%95/superAIAutoCutVideo/frontend/src/components/projectEdit/SceneListTable.tsx#L10-L54)。

3. 服务层与类型
   - 扩展 `projectService.extractScene` 支持附带 `analyzeVision`、`visionMode`；
   - 拉取场景数据后，前端直接读取新增的 `vision` 字段展示。


## 场景 JSON 结构变更

- 文件：`uploads/analyses/{project_id}_scenes.json`
- 变更：`scenes[i]` 增加字段
  - `vision: string` — 该镜头的视觉简述文本；当 merged_from 有多段时取各段中帧的描述并用 `；` 拼接。
- 兼容性：未生成视觉分析时该字段缺省；前端渲染时判空显示“—”。


## 进度与错误处理

- 进度分配建议：
  - 0%→90%：镜头分割（沿用原逻辑）；
  - 90%→100%：视觉分析（按需细分 phase：`analyze_vision_start`、`analyze_vision_infer`、`analyze_vision_done`）。
- 错误：
  - 模型缺失/校验失败 → 返回 503，提示“请先在‘模型管理’下载或检查本地文件完整性”；
  - 推理异常 → 返回 500，进度置为 failed；
  - 不阻塞已有镜头分割结果的读取（仅缺失 `vision` 字段）。


## 并发与性能

- 默认支持“无上限并发”图像分析；为避免资源抢占，提供环境变量 `VISION_ANALYSIS_MAX_CONCURRENCY` 控制上限（0 或空代表不限制）。
- Windows 环境可启用 llama-cpp GPU（见 `docs/cache/moondream-gpu/requirements.txt`）；Mac 可走 CPU 或 MPS（如可用）。
- 图片输入在推理前应当缩放至最长边不超过 1024（参考 `docs/cache/moondream-gpu/image_utils.py`），减少内存占用并提升吞吐。


## 依赖与配置

- Python 依赖（后端）：
  - `Pillow`（图像处理）
  - `llama-cpp-python`（GGUF 推理后端）
  - （可选）`transformers`、`accelerate`（如支持 Hf 后端测试）
- Node 前端无新增硬性依赖；遵从现有构建/风格（优先使用 cnpm）。


## 验收标准

1. 设置页出现“视觉分析模型”Tab；可打开目录、校验模型；测试按钮在模型齐备时返回非空文本。
2. 点击“提取镜头”并选择“视觉分析不带字幕的镜头”，仅对 subtitle 为“无”的镜头写入 `vision` 字段；“视觉分析所有镜头”对全部镜头写入。
3. 如某镜头由多段 merged_from 合并而成，最终 `vision` 为各段中帧描述文本的拼接。
4. 分析过程中前端能看到进度更新；完成后 SceneListTable 新增列显示对应文本。
5. 模型缺失、目录不完整、推理错误有清晰错误提示且不影响已完成的镜头分割结果读取。


## 开发任务清单（按模块）

后端：

- 新增 `modules/moondream_model_manager.py`，实现路径/校验/（可选）下载能力
- 新增 `routes/moondream_routes.py`，包含列表、校验、（可选）下载、打开目录、测试接口
- 新增 `services/vision_frame_analysis_service.py`，实现帧抽取、Moondream 推理、并发与进度回调
- 修改 `services/extract_scene_service.py`，在任务尾部挂接视觉分析（可控开关与模式）并更新 JSON
- 修改 `routes/project_routes.py`，扩展 `extract-scene` 接口参数与进度 phase 文案

前端：

- 修改设置页栏目，增加“视觉分析模型”入口并接入 `VisionModelSettings`
- 新增 `features/visionModel` 模块：组件、服务、hooks（比照 FunASR）
- 修改 `ProjectEditUploadStep.tsx`，新增视觉分析模式选择与进度展示，调用带参 `extractScene`
- 修改 `SceneListTable.tsx`，新增“视觉分析”列，展示 `scene.vision`


## 备注

- 统一遵循“功能独立文件、封装函数”的约定；用纯函数拆分算法与 IO。
- 模型下载地址提供为参考；优先支持用户手动复制到目录后校验与测试（与 FunASR 一致的 UX）。
- 为避免破坏性影响，第一次上线默认关闭自动视觉分析（需用户勾选）。

