# 一键生成改造说明

日期：2026-06-07

## 改造目标

本次改造新增“是否一键生成”能力，覆盖 `subtitle` 字幕推理、`visual` 视觉推理和 `omni` 全感知推理三类项目。

目标是让用户在上传步骤勾选“是否一键生成”后，可以从原有“提取字幕 / 分析镜头”入口直接提交一条完整流水线任务，自动完成后续生成链路：

- 一键生成草稿
- 一键生成视频

同时补齐任务队列展示与按钮互斥，避免同一项目在排队或运行中时继续提交新任务。

## 支持范围

已支持：

- `project_type = subtitle`
- `project_type = visual`

新增支持：

- `project_type = omni`

Omni 项目不复用 subtitle/visual 的镜头分析流水线，而是单独对接现有 Omni 全感知链路。

## 项目参数改造

新增项目字段：

- `one_click_generate_enabled`
  - 类型：`bool`
  - 默认值：`true`
  - 含义：上传步骤是否默认启用一键生成。

- `one_click_generate_target`
  - 类型：`draft | video`
  - 默认值：`draft`
  - 含义：一键生成目标，生成剪映草稿或直接生成视频。

涉及位置：

- `backend/modules/projects_store.py`
- `backend/routes/project_routes.py`
- `frontend/src/types/project.ts`
- `frontend/src/components/projectManagement/CreateProjectModal.tsx`
- `frontend/src/hooks/useProjectEditUploadStep.ts`

## 后端路由改造

### 新增一键生成路由

新增接口：

```http
POST /api/projects/{project_id}/one-click-generate
```

核心参数：

- `target`: `draft | video`
- `force`: 是否强制覆盖中间结果
- `asr_provider`
- `asr_model_key`
- `asr_language`
- `itn`
- `hotwords`
- `analyzeVision`
- `visionMode`
- `visionKeyFrames`
- `visionAction`

涉及位置：

- `backend/routes/project_ai_routes.py`
- `frontend/src/services/projectService.ts`

### 一键生成流水线

`subtitle` 项目流程：

1. 检查项目存在、视频存在、项目类型合法。
2. 如目标是草稿，检查剪映草稿路径配置。
3. 提取字幕，已有用户上传字幕时跳过。
4. 生成解说文案。
5. 保存 `narration_copywriting`，避免脚本生成阶段报“请先生成并保存解说文案”。
6. 生成解说脚本。
7. 根据 `target` 生成剪映草稿或视频。
8. 写入一键生成任务进度。

`visual` 项目流程：

1. 先执行 subtitle 项目的字幕准备逻辑。
2. 执行镜头分析 / 视觉分析。
3. 等待镜头任务完成。
4. 继续生成文案、脚本、草稿或视频。

`omni` 项目流程：

1. 检查项目存在、视频存在、项目类型合法，并校验 Omni License。
2. 如目标是草稿，检查剪映草稿路径配置。
3. 提取字幕，已有用户上传字幕时跳过。
4. 执行 Omni 全感知推理（多模态镜头表）。
5. 生成解说文案，并保存 `narration_copywriting`。
6. 执行 Omni 全链路脚本编排：文案结构化、镜头匹配、全局路径搜索、Omni 脚本生成。
7. 根据 `target` 生成剪映草稿或视频。
8. 写入一键生成任务进度。

### 提取字幕路由加入项目队列

`POST /api/projects/{project_id}/extract-subtitle` 现在会通过 `project_task_queue.acquire/release` 进入项目级队列，避免和其他项目级任务并发冲突。

## 队列任务改造

本次队列相关改造是重点。

### 新增一键生成 scope

新增：

```python
ONE_CLICK_GENERATE_SCOPE = "one_click_generate"
```

用于：

- 一键生成任务进度
- 队列浮球展示
- 项目运行任务查询
- 项目最新任务查询

### task_scheduler 暴露 pending/running

`task_scheduler` 新增 `list_tasks()`，用于返回 scheduler 内部还没有进入 `task_progress_store` 的排队任务。

原因：

- 之前队列浮球主要依赖 `project_task_queue` 和 `task_progress_store`。
- scheduler 中 `pending` 的任务可能还没有开始执行，也就没有完整进度状态。
- 这会导致用户看不到“正在排队”的任务。

新增数据：

- `scheduler_status = queued`
- `scheduler_status = running`

同时新增 `running_projects` 映射，确保 running 任务也能准确反查 `project_id`。

涉及位置：

- `backend/modules/task_scheduler.py`

### 队列接口合并多路状态

`GET /api/projects/tasks/queue` 现在合并以下来源：

- `project_task_queue.get_queue_status()`
- `task_progress_store`
- `task_scheduler.list_tasks()`

覆盖 scope：

- `one_click_generate`
- `generate_copywriting`
- `generate_script`
- `generate_video`
- `generate_jianying_draft`
- `extract_scene`
- `extract_subtitle`
- Omni 现有全链路相关 scope

目的：

- 浮球能看到正在运行任务。
- 浮球能看到 scheduler 中正在排队任务。
- 当前项目忙碌态判断能覆盖排队和运行两种状态。

涉及位置：

- `backend/routes/project_ai_routes.py`
- `frontend/src/components/projectEdit/TaskQueueFloatingBall.tsx`

## 前端上传步骤改造

### 新增“是否一键生成”

在 subtitle 和 visual 上传步骤中新增：

- “是否一键生成”勾选框，默认勾选。
- 目标切换：`草稿 / 视频`。

当勾选开启时：

- subtitle 项目的“提取字幕”按钮文案变为“一键生成草稿 / 一键生成视频”。
- visual 项目的“分析镜头”按钮文案变为“一键生成草稿 / 一键生成视频”。

当取消勾选时：

- subtitle 仍走原来的提取字幕。
- visual 仍走原来的分析镜头。

涉及位置：

- `frontend/src/components/projectEdit/ProjectEditUploadStep.tsx`
- `frontend/src/hooks/useProjectEditUploadStep.ts`

## 前端服务层改造

新增服务方法：

- `startOneClickGenerate(projectId, payload)`
- `getTaskQueue()`

涉及位置：

- `frontend/src/services/projectService.ts`

## 前端任务状态改造

### useProjects 任务 scope 增加一键生成

前端项目任务状态轮询增加：

- `one_click_generate`

涉及位置：

- `frontend/src/hooks/useProjects.ts`
- `frontend/src/types/project.ts`

### 项目编辑页增加 projectTaskBusy

`ProjectEditPage` 增加 `projectTaskBusy` 状态，每 1.5 秒请求：

```http
GET /api/projects/tasks/queue
```

判断当前项目是否：

- 出现在 `active_tasks`
- 出现在 `waiting_projects`
- 是 `active_project`

如果命中，则认为当前项目已有任务排队或运行。

涉及位置：

- `frontend/src/pages/ProjectEditPage.tsx`

## 按钮互斥与禁用提示

当当前项目已有任务在队列中或运行中时，以下按钮不允许继续提交：

- 一键生成
- 提取字幕
- 分析镜头
- 生成文案
- 生成解说脚本
- 生成视频
- 生成剪映草稿

为了避免原生 `disabled` 按钮无法响应点击，本次将关键按钮改为：

- 使用 `aria-disabled` 表达禁用语义。
- 保留禁用视觉样式。
- 点击时先判断禁用原因。
- 如不可操作，则弹出提示，例如：
  - 当前项目已有任务在队列中，请等待完成后再操作
  - 请先上传视频文件
  - 字幕提取中，请等待完成
  - 请先生成并保存解说脚本

涉及位置：

- `frontend/src/components/projectEdit/ProjectEditUploadStep.tsx`
- `frontend/src/components/projectEdit/ProjectEditCopywritingStep.tsx`
- `frontend/src/components/projectEdit/ProjectOperations.tsx`
- `frontend/src/components/ui/Dropdown.tsx`

## 任务浮球改造

任务浮球新增一键生成标签：

```ts
one_click_generate: "一键生成"
```

浮球现在可以展示：

- 运行中任务
- 项目级排队任务
- scheduler pending 任务

涉及位置：

- `frontend/src/components/projectEdit/TaskQueueFloatingBall.tsx`

## 取消与进度

一键生成父任务写入 `one_click_generate` 进度。

子任务使用各自 scope：

- 字幕提取：`extract_subtitle`
- 镜头分析：`extract_scene`
- 文案生成：`generate_copywriting`
- 脚本生成：`generate_script`
- 草稿生成：`generate_jianying_draft`
- 视频生成：`generate_video`

父任务取消时会尽量取消已记录的子任务。

## 已验证项

后端编译通过：

```bash
python -m py_compile backend/modules/task_scheduler.py backend/modules/projects_store.py backend/routes/project_routes.py backend/routes/project_ai_routes.py
```

Diff 检查通过：

```bash
git diff --check
```

前端类型检查：

```bash
cd frontend
npm run type-check
```

当前仍失败，但失败项为既有未使用变量和既有类型问题，本次一键生成改造未引入新的相关类型错误。

## Omni 阶段说明

Omni 一键生成没有直接复用 subtitle/visual 流水线，而是单独对接 Omni 现有全链路：

- multimodal
- copywriting struct embed
- shot match
- global path search
- generate script
- full narration pipeline

已继续复用本次沉淀的能力：

- `one_click_generate` 父任务 scope
- `projectTaskBusy` 前端互斥
- `/tasks/queue` 多来源合并
- 禁用按钮点击提示
- 子任务 scope 进度聚合

