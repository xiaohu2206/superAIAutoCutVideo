# 并发配音改造说明

## 背景

本项目的“生成视频 / 生成剪映草稿”流程都包含逐段配音（TTS）步骤。历史实现中，并发控制集中在“项目级任务”入队与 worker 数量，而配音片段是在单个任务内部串行执行，导致：

- 单个任务里即使有 16 段配音，也只能 1 路串行合成
- 并发配置无法提升配音吞吐，只能影响“同时跑几个项目任务”

## 现状问题定位

### 1) TaskScheduler 的并发不等于配音并发

TaskScheduler 的并发是按 scope 建 worker 池，控制“任务条目”同时执行数量：

- [task_scheduler.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/task_scheduler.py)

路由中把“生成视频/草稿”作为单个任务入队，因此该并发只控制“同时跑几个生成任务”：

- [project_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/project_routes.py)

### 2) 配音片段串行

剪映草稿与视频生成都在 for 循环里逐段 `await tts_service.synthesize(...)`，天然串行：

- 剪映草稿：[jianying_draft_manager.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/services/jianying_draft_manager.py)
- 视频生成：[video_generation_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/services/video_generation_service.py)

## 改造目标

- 将“并发控制点”下沉到“配音片段并发”
- 单任务内配音支持有限并发（默认 4，可配置），避免把 TTS/显卡/CPU 打爆
- 保留取消、失败定位、WebSocket 进度可用
- 移除 allow_same_project_parallel：同项目同 scope 不允许并行重复任务

## 改造方案（落地实现）

### 1) 移除 allow_same_project_parallel

- 配置中移除 allow_same_project_parallel 字段，并在加载时兼容旧配置（忽略该字段）
- TaskScheduler 入队去重在 `dedup=True` 时始终生效：同项目同 scope 只保留一个任务

涉及文件：

- [generate_concurrency_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/generate_concurrency_config.py)
- [generate_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/generate_routes.py)
- [task_scheduler.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/task_scheduler.py)
- [project_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/project_routes.py)

### 2) 新增 tts scope 并发配置

在生成并发配置中新增 `tts` scope，用于控制配音并发上限：

- 默认值：4
- env 覆盖：`SACV_TTS_MAX_WORKERS`
- 通过接口读取/更新：`/api/generate/concurrency`

涉及文件：

- [generate_concurrency_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/generate_concurrency_config.py)
- [generate_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/generate_routes.py)

### 3) tts_service 全局并发闸门（核心）

在 `tts_service.synthesize` 入口增加模块级 `Semaphore` 限流，所有 provider（edge_tts / qwen3_tts / tencent_tts）统一受控：

- 并发上限来源：`generate_concurrency_config_manager.get_effective("tts")`
- 配置变化后自动生效（内部会在并发数变化时重建 semaphore）

涉及文件：

- [tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/tts_service.py)

### 4) 两阶段流水线：并发 TTS，串行重操作

思路：并发只覆盖“配音合成”，ffmpeg/视频处理等重操作继续串行，保证稳定性。

#### 4.1 剪映草稿（JianyingDraftManager）

- 阶段 1：收集所有需配音片段，并发生成音频（受 tts semaphore 限制），产出每段的 `tts_out` 与 duration 信息
- 阶段 2：按原顺序串行做 normalize + overlay + 对齐 + timeline_items 拼装

涉及文件：

- [jianying_draft_manager.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/services/jianying_draft_manager.py)

#### 4.2 视频生成（VideoGenerationService）

- 阶段 1：串行剪切片段（稳定）
- 阶段 2：并发生成需要配音的音频（受 tts semaphore 限制）
- 阶段 3：串行按配音时长扩/缩片段并替换音轨

涉及文件：

- [video_generation_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/services/video_generation_service.py)

## 配置说明

### API

- 查询并发配置：`GET /api/generate/concurrency`
- 更新并发配置：`PUT /api/generate/concurrency`
- 触发 worker resize：`POST /api/generate/concurrency/resize`

### ENV

- `SACV_GENERATE_VIDEO_MAX_WORKERS`
- `SACV_JY_DRAFT_MAX_WORKERS`
- `SACV_TTS_MAX_WORKERS`

## 验证清单

- 单任务 16 段均需配音：观察日志与 WebSocket 进度，确认配音阶段是并发推进
- `tts.max_workers=1/2/4/8` 分别运行：确认失败率与资源占用在可接受范围
- 取消任务：在配音阶段与后处理阶段均可快速停止

## 回滚方式

- 将 `tts.max_workers` 设置为 1，可快速回到“配音串行”的资源占用行为（但仍保留两阶段结构与闸门）
- 若需彻底回滚：恢复旧版 for 循环内直接 `await tts_service.synthesize(...)` 的串行逻辑，并移除 semaphore 相关代码

