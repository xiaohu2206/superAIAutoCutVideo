# Omni 项目：解说文案结构化 + 向量化 — 交接说明

本文档面向后续接手的开发/联调同学，说明 **`project_type === "omni"`** 下「文案结构化 → 向量化」这一步的后端实现边界、依赖、接口与产物路径。**不涉及前端**（前端若要做按钮，可再单独开需求）。

---

## 1. 这一步在整体链路里做什么

1. **输入**：从项目里读取已保存的解说全文，字段路径与「生成解说脚本」一致：`narration_copywriting`（对象）里的 **`content`**（字符串）。若为空或未保存，任务会直接失败并提示。
2. **结构化**：按配置将长文拆成多段，对每段调用当前激活的 **文案生成模型（content 模型）**，使用 OpenAI 兼容的 **`response_format.type = json_schema`**，得到结构化 JSON 数组（每条含 `text`、`event`、`subject` 等字段；英文模式下额外要求 `translation`）。
3. **向量化**：对结构化后的每一条，拼接成用于 embedding 的文本（与 aiSearchShot demo 中 `buildNarrationEmbeddingInput` 语义一致，实现位于独立模块），调用 **「向量模型」设置**（`ai_search_shot_model_config`）里的 embeddings 接口。

**明确不做的事**：不写解说脚本、不跑镜头提取、不碰 `visual` 的 `scenes_path`、不依赖 `omni_multimodal` 管线里的 Step1/Step2 逻辑。仅依赖「已有解说文案 + 两套模型配置」。

---

## 2. 代码与目录边界（避免和 visual 搅在一起）

| 用途 | 路径 |
|------|------|
| 拆段、schema、校验、embedding 输入拼装、读提示词 | `backend/modules/omni_copywriting_struct_embed/` |
| 异步任务编排、写盘、更新项目字段 | `backend/services/omni_copywriting_struct_embed_service.py` |
| HTTP 路由 | `backend/routes/omni_copywriting_embed_routes.py` |
| 结构化提示词（用户已迁入，本流程只读） | `backend/modules/copywriting_structuring_embedding/prompt/prompt_zh.md`、`prompt_en.md` |

提示词中占位符为 **`{copywriting}`**，运行时会替换为当前 chunk 的原文片段。

参考 demo 时以 **语义对齐** 为准，**不要**从 `.trae/documents/aiSearchShot` 直接 import 业务代码，避免与桌面/脚本 demo 耦合。

---

## 3. 前置条件与配置

| 条件 | 说明 |
|------|------|
| 项目类型 | `project_type` 必须为 **`omni`**，否则接口返回 400。 |
| 解说文案 | 需已生成并保存，`narration_copywriting.content` 非空。 |
| 结构化模型 | 在设置中启用并配置 **文案生成模型**（`content_model_config`）；运行时通过 `services/ai_service.py` 的 `send_chat` + `json_schema` 调用。 |
| 向量模型 | 在 **向量模型** 配置中填写 `api_key`、`embedding_base_url`、`embedding_model` 等；请求形态与 `omni_multimodal_pipeline_service` 内 `_embed_one` 一致（Bearer + JSON body）。 |

若某提供商对 `json_schema` 支持不完整，需换用支持结构化输出的 content 配置（与现有「连接测试」行为一致）。

---

## 4. HTTP API（后端已完成）

路由前缀：`/api/projects`

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/{project_id}/omni/copywriting-struct-embed/run` | 提交异步任务；Body 可选见下表。 |
| `GET` | `/{project_id}/omni/copywriting-struct-embed/status/{task_id}` | 查询任务进度。 |
| `GET` | `/{project_id}/omni/copywriting-struct-embed/paths` | 返回项目里记录的结构化/向量结果 **Web 路径**（若尚未跑过则为 null）。 |

**`POST .../run` 可选 Body 字段（均有默认值）**

- `force`：是否取消同 scope 下正在跑的任务并重新跑。
- `chunk_target_chars` / `chunk_lookback_chars`：拆段策略（与 demo 思路一致）。
- `structuring_concurrency` / `embedding_concurrency`：并发上限。
- `prompt_language`：`zh` 或 `en`，决定读哪个 prompt 文件及是否校验 `translation`。
- `continue_on_embedding_error`：单条向量失败时是否写入 `error` 字段并继续（默认 true）。

**任务进度聚合**：`GET /api/projects/{project_id}/tasks/running` 与 `.../tasks/latest` 中已增加键 **`omni_copywriting_embed`**，与其它长任务一致，便于前端统一轮询（当前前端未接此步）。

---

## 5. 任务与进度标识

- **scope**：`omni_copywriting_embed`（常量见 `OmniCopywritingStructEmbedService.SCOPE`）。
- 与 `omni_multimodal`、生成文案等 scope **相互独立**，互不覆盖状态键。

取消行为：若 `force=true` 且存在运行中任务，会调用 `task_cancel_store.cancel`；任务体内在关键点检查 `is_cancelled`。

---

## 6. 落盘与项目字段

**物理目录（相对 uploads 根）**

`uploads/omni_copywriting_embed/{project_id}/`

| 文件 | 内容 |
|------|------|
| `copywriting_structured.json` | 结构化结果：**JSON 数组**，元素为各条结构化字段。 |
| `copywriting_embeddings.json` | `{ "meta": {...}, "items": [...] }`；成功项含 `embedding`、`embedding_input`、`embedding_model`；失败项可含 `error`（当 `continue_on_embedding_error=true` 时）。 |

**写入 `projects.json` 的 Project 字段**

- `omni_copywriting_structured_path`
- `omni_copywriting_embeddings_path`
- `omni_copywriting_embed_updated_at`

值为通过 `_to_web_path` 转换后的 **Web 路径字符串**，便于前端或静态资源规则解析（与 Omni 多模态管线写路径方式一致）。

---

## 7. 后续可衔接工作（未在本步实现）

- 前端：在 Omni 项目编辑页增加「结构化 + 向量化」按钮，调用 `POST .../run` 后轮询 `status` 与/或 `tasks/latest` 中的 `omni_copywriting_embed`。
- 业务：基于 `copywriting_embeddings.json` 做镜头召回、排序、与 `omni_multimodal` 结果对齐等（需单独设计数据契约）。
- 观测：如需 WebSocket 进度推送，可参考 `generate_script_service` 的 `manager.broadcast` 模式单独加 scope，避免塞进本服务核心逻辑。

---

## 8. 快速自检清单

1. 创建或选用 **omni** 项目，并确认已保存解说文案。
2. 文案模型、向量模型在设置页均可连通。
3. `POST .../omni/copywriting-struct-embed/run`，记下返回的 `task_id`。
4. `GET .../status/{task_id}` 直至 `status === "completed"`。
5. `GET .../omni/copywriting-struct-embed/paths` 或直读 uploads 下两个 JSON 文件核对内容。

---

*文档版本：与实现目录 `omni_copywriting_struct_embed` 及路由 `omni_copywriting_embed_routes` 同步维护；若改 API 或字段名，请同步更新本节。*
