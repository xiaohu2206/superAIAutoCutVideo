# Omni 项目：全局路径搜索 — 交接说明

本文档说明 **`project_type === "omni"`** 下，在 **镜头匹配与重排（`rerank.json`）** 之后的 **全局路径搜索** 后端：边界、依赖、接口、落盘与任务标识。实现与 **visual**、**`omni_shot_match` 服务代码** 无 import 耦合；算法独立放在 `backend/modules/omni_global_path_search/`，语义对齐 `.trae/documents/aiSearchShot` 中 Step4.8（`globalPathSearch`，README「Step 4.8 全局路径搜索」一节）。

**前置步骤**：须先完成 `backend/docs/omni_shot_match_交接.md` 所述流程，使项目存在有效的 **`omni_shot_match_rerank_path`**（磁盘上为 `rerank.json`，含非空 `results[]`，每段含 `matches[]` 候选池）。

---

## 1. 本步骤在整体链路里做什么

在已有逐段重排结果上，做 **跨段全局优化**（多路径 Beam、转场分、时间线回退与 zigzag 惩罚、可选 refine 与平滑/短离群修复等），使整条解说序列对应的镜头路径在 **语义分 + 时间线连贯性** 上更稳。

- **输入**：`rerank.json` 根对象中的 `results`（结构与 shot-match 产出一致）。
- **输出**：`global_path.json`，含 `meta`、`results`（每段 `matches[0]` 为全局优选，并带 `global_path` 等字段）、`global_paths`（备选完整路径摘要）。

**不做的事**：不调用向量 / rerank HTTP / LLM；不读写 `visual` 的 `scenes_path`；不从 `.trae` import 业务代码。

---

## 2. 代码与目录边界

| 用途 | 路径 |
|------|------|
| 纯函数：Beam、评分、refine 等 | `backend/modules/omni_global_path_search/pure.py`（入口 `build_global_path_payload`） |
| 异步任务、读 rerank、写结果、更新项目 | `backend/services/omni_global_path_search_service.py` |
| HTTP 路由 | `backend/routes/omni_global_path_search_routes.py` |

**物理目录（与 `uploads/omni_shot_match/` 隔离）**：`uploads/omni_global_path_search/{project_id}/global_path.json`

路由在 `backend/main.py` 中通过 `include_router(omni_global_path_search_router)` 注册。

---

## 3. 前置条件

| 条件 | 说明 |
|------|------|
| 项目类型 | `project_type` 为 **`omni`**。 |
| 重排结果 | 项目 **`omni_shot_match_rerank_path`** 非空，且文件可读、含非空 **`results`**；或请求里显式传入 **`input_rerank_web_path`** 指向同结构 JSON。 |

---

## 4. HTTP API

路由前缀：`/api/projects`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/{project_id}/omni/global-path-search/run` | 提交异步任务。 |
| `GET` | `/{project_id}/omni/global-path-search/status/{task_id}` | 查询任务进度。 |
| `GET` | `/{project_id}/omni/global-path-search/paths` | 返回全局路径结果路径、更新时间，以及当前项目的 `omni_shot_match_rerank_path`（便于核对输入）。 |

**`POST .../run` Body（可选）**

| 字段 | 说明 |
|------|------|
| `force` | 是否取消同 scope 下运行中任务并重新跑。 |
| `task_id` | 可选自定义任务 ID。 |
| `input_rerank_web_path` | 覆盖项目上的 `omni_shot_match_rerank_path`。 |
| `search_params` | 与 Step4.8 一致的可选参数字典（如 `candidate_top_k`、`beam_width_early` / `mid` / `late`、`enable_refine`、`keep_all_matches` 等）；未传字段使用 `pure.py` 内置默认。 |

**任务进度聚合**：`GET .../tasks/running` 与 `.../tasks/latest` 中键 **`omni_global_path_search`**。

---

## 5. 任务与进度标识

- **scope**：`omni_global_path_search`（`OmniGlobalPathSearchService.SCOPE`）。
- 取消：与 shot-match 相同，`force=true` 时取消同 scope 运行中任务。

---

## 6. 落盘与项目字段

| 文件 / 字段 | 说明 |
|-------------|------|
| `uploads/omni_global_path_search/{project_id}/global_path.json` | 全局路径搜索结果。 |
| `omni_global_path_search_path` | Web 路径（`_to_web_path`）。 |
| `omni_global_path_search_updated_at` | ISO 时间戳。 |

输出 `meta` 中会补充 `project_id`、`input_rerank_web_path`、`output_global_path_web_path`，以及输入 `rerank.json` 的 `meta` 副本（`input_rerank_meta`），便于追溯。

---

## 7. 与 demo / 前序文档的对应关系

| 概念 | 本实现 |
|------|--------|
| aiSearchShot Step4.8 | `build_global_path_payload` + 独立落盘目录 |
| Step4.5 输出 `copywriting_to_shots_rerank.json` | 本项目的 **`rerank.json`**（`omni_shot_match_rerank_path`） |

调参说明可参考 `.trae/documents/aiSearchShot/README.md` 中 **Step 4.8** 表格；请求里通过 **`search_params`** 传入同名键即可。

---

## 8. 快速自检

1. Omni 项目已成功生成 **`omni_shot_match_rerank_path`**。  
2. `POST .../omni/global-path-search/run`，记录 `task_id`。  
3. `GET .../global-path-search/status/{task_id}` 直至 `completed`。  
4. `GET .../global-path-search/paths` 或打开 uploads 下 **`global_path.json`**，核对 `results` 与 `global_paths`。

---

*文档版本：与 `backend/modules/omni_global_path_search`、`backend/services/omni_global_path_search_service.py`、`backend/routes/omni_global_path_search_routes.py` 及 `projects_store` 中 `omni_global_path_search_*` 字段同步维护。*
