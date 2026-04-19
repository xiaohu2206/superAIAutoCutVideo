# Omni 项目：镜头粗筛 / 精筛 / 重排 — 交接说明

本文档面向后续接手的开发/联调同学，说明 **`project_type === "omni"`** 下，在「解说文案向量化」与「多模态镜头 JSON」之上的 **镜头匹配与重排** 后端实现：边界、依赖、接口、落盘与任务标识。实现与 **visual**、**.trae/documents/aiSearchShot** 脚本 demo **无代码 import 耦合**；语义上可对齐 demo 的 Step4（向量召回 TopK）与 Step4.5（粗排 + 精排 + 连续性融合）。

前置链路说明见：`backend/docs/omni_copywriting_struct_embed_交接.md`（结构化+向量）、以及 Omni 多模态管线产出 `omni_multimodal_json_path`。

---

## 1. 本步骤在整体链路里做什么

在以下条件已满足时，对**每条**解说结构化条目（与 `copywriting_embeddings.json` 的 `items` 一一对应）：

1. **粗筛（向量）**：用每条解说上的 `embedding` 与多模态镜头 `shots[].embedding` 做余弦相似度，取 **TopK** 镜头候选（默认 20），写入 `search_topk.json`。
2. **粗排（召回模型）**：调用 **向量模型设置**（`ai_search_shot_model_config`）中的 **rerank** 接口（与设置页「召回模型」测试一致：`model`、`query`、`documents`、`top_n`，可选 `instruct`）。将 TopK 镜头的描述文本作为 `documents`，query 为当前条目的解说主文本。可通过 `skip_stage1_rerank=true` 跳过该接口，阶段1分数退化为向量粗筛分数。
3. **精排（文案生成模型）**：对粗排后的少量候选，使用当前激活的 **content 模型**（`services/ai_service.send_chat`），`response_format` 为 **`{"type": "json_object"}`**（与 `omni_copywriting_struct_embed_service` 调用方式一致；对应 demo 中的「结构化 chat」语义）。提示词模板来自 `backend/modules/reRank/fine_prompt_zh.md` / `fine_prompt_en.md`，占位符为 `{query}`、`{candidates_json}`、`{stage2_return_n}`；运行时会追加一段机器可读输出说明，要求模型输出 `{"items":[{"shot_id", "score", "reason"}, ...]}`。
4. **连续性 + 最终分**：按 `item_index` 顺序，为每条解说的候选镜头计算 `continuity_score`，与 `rerank_score`、`embedding_score` 按权重融合为 `final_score`，并回写 `matches[].score` 为 `final_score`（便于后续步骤直接按 `score` 排序）。融合逻辑在 `backend/modules/omni_shot_match/pure.py` 中实现。

**明确不做的事**：不修改 `visual` 的 `scenes_path`；不从 `.trae` 目录 import 业务代码；不负责前端剪辑时间线 UI（仅产出 JSON）。

---

## 2. 代码与目录边界

| 用途 | 路径 |
|------|------|
| 纯函数：余弦、query/文档拼装、连续性、解析 LLM JSON 等 | `backend/modules/omni_shot_match/`（`pure.py`、`__init__.py`） |
| 异步任务、读盘、rerank HTTP、调用 `ai_service`、写结果、更新项目 | `backend/services/omni_shot_match_service.py` |
| HTTP 路由 | `backend/routes/omni_shot_match_routes.py` |
| 精排用户提示词（与 visual 隔离，仅被本模块读取） | `backend/modules/reRank/fine_prompt_zh.md`、`fine_prompt_en.md` |
| 多模态镜头文件解密/明文兼容 | `services/omni_internal/multimodal_json_crypto.read_multimodal_json`（仅读 Omni 产物，不依赖 visual） |

路由在 `backend/main.py` 中通过 `include_router(omni_shot_match_router)` 注册。

---

## 3. 前置条件与配置

| 条件 | 说明 |
|------|------|
| 项目类型 | `project_type` 必须为 **`omni`**。 |
| 解说向量化 | 项目字段 **`omni_copywriting_embeddings_path`** 非空，且磁盘上存在对应 `copywriting_embeddings.json`（由 copywriting struct-embed 流程产出）。 |
| 多模态镜头 | 项目字段 **`omni_multimodal_json_path`** 非空，且可解析出 `shots` 列表；镜头项需含 **`embedding`**（与管线 Step2 一致）。文件可为 OMMJ1 加密或明文 JSON。 |
| 向量 / 召回 | `ai_search_shot_model_config`：`api_key`、**`embedding_base_url`**（本步粗筛不再次请求 embedding，但配置与同一套「向量模型」设置一致）、未跳过粗排时需 **`rerank_base_url`**、`rerank_model`。 |
| 精排 LLM | 在设置中启用 **文案生成模型**（`content_model_config`）；`ai_service.send_chat` 使用当前激活项；支持按请求传入 **`temperature`**（见 `AIService.send_chat` 可选关键字参数）。 |

`copywriting_embeddings.json` 的 **`meta.prompt_language`**（`zh` / `en`）用于选择精排模板与是否使用 `translation` 等上下文逻辑；若缺失则默认 `zh`。

---

## 4. HTTP API

路由前缀：`/api/projects`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/{project_id}/omni/shot-match/run` | 提交异步任务；Body 见下表。 |
| `GET` | `/{project_id}/omni/shot-match/status/{task_id}` | 查询任务进度。 |
| `GET` | `/{project_id}/omni/shot-match/paths` | 返回 `omni_shot_match_*` 相关 Web 路径与时间戳。 |

**`POST .../run` 可选 Body（均有默认值）**

| 字段 | 说明 |
|------|------|
| `force` | 是否取消同 scope 下运行中任务并重新跑。 |
| `task_id` | 可选自定义任务 ID；不传则服务端生成。 |
| `top_k` | 向量粗筛每条解说保留的候选镜头数（默认 20）。 |
| `stage1_top_n` | 粗排参与排序/截断的上限（与 demo stage1 语义一致）。 |
| `stage2_top_n` | 送入精排 LLM 的候选条数上限。 |
| `stage2_return_n` | 精排期望返回的条数上限。 |
| `output_top_k` | **0** 表示每条解说输出全部候选的最终分与连续性；**>0** 时按 `final_score` 截断为前 N 条。 |
| `concurrency` | 每条解说并行处理的上限（异步 Semaphore）。 |
| `skip_stage1_rerank` | 为 `true` 时跳过 rerank HTTP，粗排分数用 embedding 分数。 |
| `rerank_instruct` | 覆盖默认的 stage1 `instruct` 文案（中英默认与 demo 思路一致）。 |
| `temperature` | 精排 LLM 温度，传入 `send_chat(..., temperature=...)`。 |
| `weights` | 可选对象：`rerank_score`、`embedding_score`、`continuity_score`（默认 0.55 / 0.30 / 0.15）。 |

**任务进度聚合**：`GET /api/projects/{project_id}/tasks/running` 与 `.../tasks/latest` 中键 **`omni_shot_match`**，与 `omni_copywriting_embed`、`omni_multimodal` 等并列。

---

## 5. 任务与进度标识

- **scope**：`omni_shot_match`（`OmniShotMatchService.SCOPE`）。
- 取消：`force=true` 时对运行中任务调用 `task_cancel_store.cancel`；任务循环中检查 `is_cancelled`。

---

## 6. 落盘与项目字段

**物理目录（相对 uploads 根）**

`uploads/omni_shot_match/{project_id}/`

| 文件 | 内容 |
|------|------|
| `search_topk.json` | 向量粗筛结果：`meta` + `results[]`（每条含 `item_index`、`text`、`matches[]`（`shot_id`、`start`、`end`、`summary`、`score` 为 embedding 相似度）等）。 |
| `rerank.json` | 完整重排结果：`meta` + `results[]`，每条 `matches[]` 在粗筛字段基础上增加 `embedding_score`、`coarse_rerank_score`、`rerank_score`、`reason`（可选）、`continuity_score`、`final_score`，且 **`score` 已写为 `final_score`**。 |

**写入 `projects.json` 的 Project 字段**

- `omni_shot_match_topk_path`
- `omni_shot_match_rerank_path`
- `omni_shot_match_updated_at`

路径均为 **`_to_web_path`** 后的 Web 路径字符串。

---

## 7. 与 demo / 前序文档的对应关系

| 概念 | 本实现 |
|------|--------|
| aiSearchShot Step4 向量召回 | `build_embedding_search_results` → `search_topk.json` |
| Step4.5 粗排 rerank API | `httpx` POST `rerank_base_url`，解析 `results` / `data` / 顶层 list |
| Step4.5 精排 LLM | `ai_service.send_chat` + `json_object`，解析 `items` 或顶层数组 |
| 连续性 + final | `merge_fine_scores_and_continuity` |

若调整权重或 TopK，优先改请求 Body 或 `pure.py` 中的默认策略，避免与 visual 共用配置键。

---

## 9. 快速自检清单

1. Omni 项目已跑通 **copywriting struct-embed**（`paths` 里 embeddings 非空）。
2. 已跑通 **Omni 多模态管线**（`omni_multimodal_json_path` 有效且 `shots` 含 `embedding`）。
3. 向量设置中 **rerank** 可连通（或显式 `skip_stage1_rerank=true` 做联调）。
4. 文案生成模型（content）已激活且支持 **`response_format: json_object`** 的稳定输出。
5. `POST .../omni/shot-match/run`，记录 `task_id`。
6. `GET .../omni/shot-match/status/{task_id}` 直至 `completed`。
7. `GET .../omni/shot-match/paths` 或直接打开 uploads 下 `search_topk.json`、`rerank.json` 核对字段。

---

*文档版本：与 `backend/modules/omni_shot_match`、`backend/services/omni_shot_match_service.py`、`backend/routes/omni_shot_match_routes.py` 及 `projects_store` 中 `omni_shot_match_*` 字段同步维护；若改 API 或文件名，请同步更新本文档。*
