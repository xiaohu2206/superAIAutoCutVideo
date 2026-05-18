# Omni 智能剪辑脚本生成改进方案

## Summary

把当前 `omni_generate_script` 从“按文案分批 + top1/proportional 时间窗”升级为：

**topK 精准召回 + 全局路径约束 + 动态分组时间窗 + 多锚点邻域扩展 + 置信度路由 + 程序化后验校验。**

目标是同时解决：

- 固定/比例窗口与真实剧情位置错位。
- top1 错误导致相邻镜头整体偏移。
- LLM 被迫从过大镜头列表中盲选。
- 解说文本被模型改写、漏用、乱序。
- 镜头时长与配音时长不匹配。

最终项目 `script.segments` 保持兼容，只新增 artifact/debug 诊断信息。

## Key Changes

### 1. 上游镜头匹配增强

在 `omni_shot_match` 暴露并透传调参字段：

- `top_k`: 默认 `30`
- `stage1_top_n`: 默认 `24`
- `stage2_top_n`: 默认 `20`
- `stage2_return_n`: 默认 `8`
- `output_top_k`: 默认 `0`，保留完整候选池
- `weights`: 继续支持 `rerank_score / embedding_score / continuity_score`

`rerank.json` 继续输出 `results[].matches[]`，但保证每个候选包含：

- `shot_id`
- `start / end`
- `summary / visual.brief / subtitle_full_text`
- `embedding_score`
- `rerank_score`
- `continuity_score`
- `final_score`
- `reason`

全链路 `shot_match_options` 也同步支持这些字段。

### 2. 全局路径搜索增强

`global_path_search` 默认质量优先：

- `candidate_top_k`: 默认从 `3` 提升到 `8`
- `keep_all_matches`: `true`
- `output_matches_limit`: `30`
- 保留 `matches[0]` 为全局路径优选镜头。
- 其他候选继续保留，用于生成阶段 topK 候选包。

生成阶段读取优先级保持：

1. 显式 `input_global_path_web_path`
2. 项目 `omni_global_path_search_path`
3. 项目 `omni_shot_match_rerank_path`

### 3. 生成阶段改成动态候选上下文

在 `OmniNarrationParams` 增加质量优先默认参数：

- `candidate_top_k = 5`
- `anchor_neighbor_radius = 2`
- `low_confidence_neighbor_radius = 3`
- `confidence_high_score = 0.78`
- `confidence_medium_score = 0.65`
- `confidence_high_gap = 0.08`
- `confidence_medium_gap = 0.03`
- `confidence_high_spread_sec = 180`
- `confidence_medium_spread_sec = 600`
- `dynamic_window_padding_high_sec = 90`
- `dynamic_window_padding_medium_sec = 180`
- `dynamic_window_padding_low_sec = 300`
- `chunk_target_size = 12`
- `chunk_max_lines = 15`
- `timeline_window_mode = "topk_confidence"`

每段文案计算：

- top1 分数
- top1/top2 分差
- topK 时间跨度
- topK robust 时间范围，使用 P10/P90 或 median fallback
- 置信度：`high / medium / low`
- 候选策略：`anchor_only / anchor_plus_window / wide_window`

分批规则：

- 保持文案原始顺序，不重排。
- 连续文案按 topK 时间分布动态切组。
- 当相邻文案 robust median 时间差大于 `300s`，或本组超过 `chunk_max_lines`，切新组。
- 若 topK 时间明显回跳，不强行重排，标记为低置信并扩大窗口。

每批构造三类镜头上下文：

- `top_candidates`: 每段文案 top5 候选。
- `anchor_neighbor_shots`: topK 每个锚点前后邻域镜头，去重排序。
- `group_window_shots`: 本批 P10/P90 动态时间窗内镜头。

LLM 提示词明确说明：

- top1 只是参考，不是必须选择。
- 必须优先在候选包内选镜头。
- 高置信使用多锚点邻域。
- 中低置信允许从 group window 中兜底。
- OST=0 文案只能拆分，不能改写、增删、换序。

### 4. 后处理和重试

增强 `post_check_chunk_items`，新增校验：

- timestamp 格式合法。
- 每段时长不少于 1 秒。
- OST 只能是 `0/1`。
- `OST=1` narration 必须为 `播放原片N`。
- 每批所有 `OST=0` 拼接后必须等于本批原始文案。
- 合并后全局 `OST=0` 拼接必须等于完整原始文案。
- timestamp 大体不允许严重回跳，除非重叠很小且仍在候选窗口内。
- 同一 shot 连续覆盖超过 2 次写入诊断，必要时扩大相邻镜头自动修正时间段。
- 若解说估算配音时长大于镜头时长，程序自动向后扩展相邻镜头，不改文案。

LLM 单批失败时继续走现有 retry；若失败原因是文案守恒或 JSON 结构问题，追加一次“修复提示词”重试，只要求修复 JSON，不重新生成创意内容。

### 5. Artifact 和兼容性

最终 `projects_store.save_script(project_id, script)` 输出不变。

`narration_script_artifact.json` 新增：

- `meta.params`
- `meta.input_candidate_source`
- `chunk_debug[]`
- `candidate_context_stats`
- `confidence_distribution`
- `post_check_warnings`
- `text_conservation_report`
- `prompt_preview`

下游剪辑、前端读取 `script.segments` 不需要改。

## Public APIs / Interfaces

### `POST /omni/shot-match/run`

新增可选字段：

- `top_k`
- `stage1_top_n`
- `stage2_top_n`
- `stage2_return_n`
- `output_top_k`
- `concurrency`

已有字段保持兼容。

### `POST /omni/generate-script/run`

`generation_params` 新增可选字段：

- `candidate_top_k`
- `anchor_neighbor_radius`
- `low_confidence_neighbor_radius`
- `timeline_window_mode = "topk_confidence"`
- `confidence_*`
- `dynamic_window_padding_*`
- `chunk_max_lines`

未传时使用质量优先默认值。

### Full Pipeline

`shot_match_options`、`global_path_search_options`、`generate_script_options` 透传上述字段。

## Test Plan

- 单元测试 `_runner_core`：
  - topK 置信度分档。
  - P10/P90 动态窗口。
  - 多锚点邻域去重排序。
  - 文案顺序保持，不因时间跳跃重排。
  - top1 错误但 top3 正确时候选包仍包含正确镜头。
  - 低置信抽象文案触发大窗口兜底。

- 单元测试 `pure.py`：
  - `build_chunk_metas_and_prompts` 生成新的候选上下文。
  - prompt 中包含 top candidates、neighbor shots、group window。
  - 保持 `DEFAULT_USER_PROMPT_TEMPLATE` 和 `ORIGINAL_INTERLEAVE_USER_PROMPT_TEMPLATE` 兼容。

- 服务测试：
  - 使用 `rerank.json` 输入。
  - 使用 `global_path.json` 输入。
  - 跳过 global path 时仍可生成。
  - `generation_params` 覆盖默认值生效。
  - artifact 包含 debug 信息。
  - 最终 `script.segments` 结构不变。

- 回归测试：
  - 文案 40 段都集中在前半部时，后续批次不再拿后半部固定窗口。
  - top1/top2 分数接近时，不只围绕 top1 扩邻域。
  - topK 时间分散时，触发大剧情窗口。
  - 模型改写或漏写 OST=0 文案时任务重试或失败报清晰错误。
  - 原片穿插模式仍满足“解说-原片-解说-原片”。

## Assumptions

- 默认走质量优先配置，接受更大的 prompt token 和略高成本。
- 最终项目脚本结构保持兼容，诊断信息只写入 artifact。
- 文案顺序永远以原始文案为准，不允许为了镜头时间线重排 OST=0。
- top1/global_path_selected 是强参考，不是最终唯一锚点。
- 若 token 压力过大，优先减少 `group_window_shots`，不减少 `top_candidates`。
