## 运行

### Step 1 镜头分割（保持原逻辑）
名称：`step1_shot_split`

```bash
.\.venv\Scripts\python main.py
```

### Step 2 多模态特征提取（中间帧 + qwen3-vl-flash + embedding）
名称：`step2_multimodal_features`

1) 编辑 `config.json`，填写：
- `yunwu.api_key`
- 确认 `input.shots_json` 指向你的 `output/video_1_shots.json`
- 确认 `video.path` 指向原视频

2) 运行：

```bash
.\.venv\Scripts\python main.py
```

输出：
- 中间帧：`output/frames/shot_###.jpg`
- 结果：`output/video_1_shots_multimodal.json`

### Step 3 解说文案结构化（解说文案 → copywriting_format.json）
名称：`step3_copywriting_structuring`

将原始“解说文案”文本按长度先做安全拆分，再把每个分段送入大模型做“镜头语义拆分 + 结构化输出”，最后把所有结果拼接成 `copywriting_format.json`，供后续文案向量化直接使用。

拆分规则：
- 默认每段目标长度约 `500` 字
- 实际不会直接固定按 `500` 切，而是先根据总字符数动态计算分段起始长度：
  - 先用 `总字符数 / 500` 估算段数并向上取整
  - 再用 `总字符数 / 段数` 得到实际分割起始长度
  - 例如总长 `1800`，则 `1800 / 500 = 3.6`，向上取整为 `4` 段，再按 `1800 / 4 = 450` 字左右作为分割开始数
- 不直接硬切，会在最多向前 `100` 个字符内优先寻找这些断点：
  1. 换行符
  2. 句末符号：`。！？!?；;`
  3. 次优断点：`，,、：:`
- 如果回看范围内仍找不到合适断点，则直接截断

提示词：
- 中文：`copywritingStructuring/prompt_zh.md`
- 英文：`copywritingStructuring/prompt_en.md`

1) 编辑 `config.json`：
- `step`: 设置为 `step3_copywriting_structuring`
- `copywriting_structuring.input_text`: 原始解说文案 txt 文件路径（默认 `inputFile/copywriting.txt`）
- `copywriting_structuring.output_json`: 结构化输出路径（默认 `inputFile/copywriting_format.json`）
- `copywriting_structuring.prompt_language`: `zh` / `en`
- `copywriting_structuring.prompt_path`: 可选，自定义提示词文件路径；为空时按语言选择内置提示词
- `copywriting_structuring.model`: 可选，指定结构化所用模型；为空时自动读取当前 provider 的 `llm_model`，再回退到 `vl_model`
- `copywriting_structuring.chunk_target_chars`: 单段目标长度（默认 `500`）
- `copywriting_structuring.chunk_lookback_chars`: 向前探测长度（默认 `100`）
- `copywriting_structuring.temperature/max_retries/retry_sleep_seconds`: 模型采样与重试参数
- 同时填写当前模型供应商配置，例如 `yunwu.api_key` 或 `custom_openai.api_key`

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`inputFile/copywriting_format.json`

### Step 3.5 结构化解说文案向量化（copywriting_format.json → embedding）
名称：`step3_copywriting_embeddings`

将 Step 3 生成的 `copywriting_format.json`（结构化解说文案数组）按固定格式拼接为字符串后做向量化，输出为 json 文件。

1) 编辑 `config.json`：
- `step`: 设置为 `step3_copywriting_embeddings`
- `copywriting_embeddings.input_json`: 输入（默认 `inputFile/copywriting_format.json`，建议直接使用 Step 3 输出）
- `copywriting_embeddings.output_json`: 输出（默认 `output/copywriting_format_embeddings.json`）
- 填写当前模型供应商配置，例如 `yunwu.api_key` 或 `custom_openai.api_key`

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`output/copywriting_format_embeddings.json`（包含 `meta` 与 `items[]`，每条带 `embedding_input`、`embedding_model`、`embedding`）

### Step 4 用解说文案匹配镜头（embedding 检索 TopK）
名称：`step4_search_shots`

将 Step3 生成的 `output/copywriting_format_embeddings.json`（`items[].embedding`）与 Step2 生成的 `output/video_1_shots_multimodal.json`（`shots[].embedding`）做向量相似度匹配，按每条解说文案输出 TopK 镜头及分数（余弦相似度）。

1) 编辑 `config.json`：
- `step`: 设置为 `step4_search_shots`
- `search_shots.copywriting_embeddings_json`: 文案 embedding 输入（默认 `output/copywriting_format_embeddings.json`）
- `search_shots.shots_multimodal_json`: 镜头 embedding 输入（默认 `output/video_1_shots_multimodal.json`）
- `search_shots.output_json`: 输出（可省略；默认 `output/copywriting_to_shots_top{top_k}.json`）
- `search_shots.top_k`: TopK（默认 20）

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`output/copywriting_to_shots_top{top_k}.json`（`results[]` 为每条文案的 TopK 镜头匹配列表）

### Step 4.5 重排序（Re-rank：粗排 + 精排 + 融合评分）
名称：`step4_5_rerank`

在 Step4 召回的 TopK 候选镜头基础上，引入上下文/剧情阶段信息，使用云雾模型进行两阶段重排序：
- 阶段1：`qwen3-rerank` 粗排（Top20 → Top10）
- 阶段2：`glm-4` 精排（Top10 → Top3）
- 最终融合：\(0.55 * rerank + 0.30 * embedding + 0.15 * continuity\)，并将最终分数写回 `matches[].score`（便于 Step5 直接使用）

1) 编辑 `config.json`：
- `step`: 设置为 `step4_5_rerank`
- `step4_5_rerank.input_topk_json`: Step4 输出（推荐新字段；可不填）
  - 若不填：会自动使用 `search_shots.output_json`，再不填则按 `search_shots.top_k` 推导为 `output/copywriting_to_shots_top{top_k}.json`
- `step4_5_rerank.copywriting_embeddings_json`: Step3 输出（默认 `output/copywriting_format_embeddings.json`）
- `step4_5_rerank.copywriting_format_json`: 结构化文案（默认 `inputFile/copywriting_format.json`）
- `step4_5_rerank.output_json`: 输出（默认 `output/copywriting_to_shots_rerank.json`）
- `step4_5_rerank.models.rerank_model / llm_model`: 云雾平台模型名（默认 `qwen3-rerank` / `glm-4`）
- `step4_5_rerank.concurrency`: 并发数（`0` 表示“无限并发”，等价于按文案条数开满；请注意额度与限流）
- `step4_5_rerank.reuse_existing_output`: 若 `output_json` 已存在，则复用其中的粗排结果，直接进入阶段2 LLM（默认 true）
- `step4_5_rerank.output_top_k`: 输出时保留的候选镜头数（`0` 表示不截断，保持 Step4 的 TopK；例如填 `3` 则只输出 Top3）

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`output/copywriting_to_shots_rerank.json`

### Step 4.8 全局路径搜索（Global Path Search）
名称：`step4_8_global_path_search`

在 Step4.5 的逐段重排序结果基础上，增加跨段全局优化：
- 多路径 Beam Search（前宽后窄）避免早期误选导致全局崩塌
- Transition Score 约束镜头衔接（时间轴回退惩罚等）
- Zigzag 惩罚（允许单次跨时间跳；对“前跳→回跳”和“回跳→前跳”两种时间摆动都加罚）
- 时间轴回退惩罚：若当前镜起点早于上一镜终点（时间线往回走），在转场分项中按回退幅度扣分
- 不再对“相邻镜头时长差异过大”单独扣分（移除局部 -0.15 节奏惩罚）
- 全局评分（以时间线 zigzag 等约束为主）+ 可选回溯优化
- 输出仍保持 `results[].matches[]` 结构，但会将全局最优镜头放在每段 `matches[0]`，可直接供 Step5 使用

1) 编辑 `config.json`：

根键 `step` 设为 `step4_8_global_path_search`。字段分两类：**路径与数值参数**、**策略开关**（`true` / `false`）。括号内为代码默认值。

**路径与数值参数**

| 字段 | 含义 |
|------|------|
| `input_rerank_json` | Step4.5 重排序结果 JSON 路径。须含非空 `results` 数组；每段的 `matches` 即候选池。（默认 `output/copywriting_to_shots_rerank.json`） |
| `output_json` | 本步写出路径，供 Step5 等后续使用。（默认 `output/copywriting_to_shots_global_path.json`） |
| `candidate_top_k` | 在开启 `enable_candidate_truncation` 时，每段只取前 K 个候选参与搜索。基础分优先取 `final_score`，否则依次 `score`、`rerank_score`、`embedding_score`。（默认 `3`） |
| `beam_width_early` | 文案段进度前 30%（不含第 0 段初始化）每一步 Beam 扩展后最多保留的路径条数。（默认 `8`） |
| `beam_width_mid` | 进度 30%～70% 段使用的 Beam 保留条数；若关闭 `enable_dynamic_beam_width`，它也会作为全程固定 Beam 宽度。（默认 `5`） |
| `beam_width_late` | 进度 70% 以后使用的 Beam 保留条数。（默认 `3`） |
| `keep_top_paths` | 搜索结束后，在输出 `global_paths` 里写入前几条完整备选路径（含 `rank`、`global_score`、`shot_ids`），便于对比或调试。（默认 `5`） |
| `refine_candidate_top_k` | 开启 `enable_refine` 时，每一段只从前 K 个候选里尝试替换当前选中镜，控制 refine 开销。（默认 `3`） |
| `smooth_candidate_top_k` | 与 `enable_polyline_smoothing` 等字段一并保留在配置中；当前版本已移除折线离群检测，基于离群的平滑替换不再生效。（默认 `12`） |
| `smooth_skip_head_ratio` | 同上，历史参数，当前不参与计算。（默认 `0.05`） |
| `smooth_skip_tail_ratio` | 同上，历史参数，当前不参与计算。（默认 `0.10`） |
| `smooth_outlier_residual_threshold` | 同上，历史参数，当前不参与计算。（默认 `120.0`） |
| `smooth_outlier_neighbor_gap_threshold` | 同上，历史参数，当前不参与计算。（默认 `90.0`） |
| `smooth_residual_penalty_weight` | smoothing 选择替换镜头时，对残差引入的附加惩罚权重；越大越偏向时间折线更平滑的候选。（默认 `0.05`） |
| `smooth_min_score_improve` | smoothing 接受替换所需的最小改进量，避免因为极小浮动频繁替换。（默认 `1e-6`） |

**策略开关**

| 字段 | 含义 |
|------|------|
| `enable_candidate_truncation` | `true`：对每段 `matches` 按基础分降序后只取前 `candidate_top_k` 个进入搜索；`false`：不截断，保留该段全部候选。（默认 `true`） |
| `enable_dynamic_beam_width` | `true`：Beam 宽度随进度在 early / mid / late 三档间切换；`false`：全程固定为 `beam_width_mid`。（默认 `true`） |
| `enable_path_expansion` | `true`：正常逐段扩展路径；`false`：不再用新候选扩展，只保留已有路径并按 Beam 截断（调试用）。（默认 `true`） |
| `disallow_repeat_shot` | `true`：Beam、refine、smoothing 换镜时跳过路径中已出现过的 `shot_id`；`false`：允许同镜重复出现。（默认 `true`） |
| `enable_repeat_shot_fallback` | `true`：在 `disallow_repeat_shot=true` 且某步无法扩展时，自动退化为允许重复，保证搜索不断；`false`：不做该兜底。（默认 `true`） |
| `enable_backward_jump_penalty` | `true`：时间线回退（当前镜起点早于上一镜终点）时在转场分项扣分；`false`：关闭该项惩罚。（默认 `true`） |
| `enable_timeline_zigzag_penalty` | `true`：对连续三段的「前跳→回跳 / 回跳→前跳」时间摆动做全局惩罚；`false`：关闭 zigzag 全局项。（默认 `true`） |
| `enable_refine` | `true`：在 Beam 最优路径上再做逐段替换，用全局 `_path_score` 择优；`false`：跳过 refine。（默认 `true`） |
| `enable_polyline_smoothing` | 配置项保留；当前版本已移除折线离群检测，该开关不再改变 Step4.8 结果。（默认 `true`） |
| `keep_all_matches` | `true`：每段 `matches` = 全局选中顶到 `[0]` + 其余原候选（去重同 `shot_id`）；`false`：每段只输出一条选中镜。（默认 `true`） |

2) 推荐调参（减少“中间 item 突然跳到很远时间点”）：
- 优先保持 `enable_candidate_truncation=true`，并将 `candidate_top_k` 设为 `6~10`，扩大可选镜头池
- 保持 `enable_dynamic_beam_width=true`，并适度加宽 `beam_width_early/mid/late`（如 `12/8/5`），降低早期误选影响
- 保持 `enable_refine=true` 且 `refine_candidate_top_k>=5`，加强局部回溯修正能力
- 保持 `enable_backward_jump_penalty=true` 与 `enable_timeline_zigzag_penalty=true`，通常更有利于时间线稳定
- 保持 `disallow_repeat_shot=true`，通常更稳定，避免因重复镜头导致路径异常

**参数组合备选（按需整段替换 `step4_8_global_path_search` 里除路径外的字段）：**

| 场景 | 关键开关与参数建议 | 说明 |
|------|--------------------|------|
| 轻量 / 冒烟 | `enable_candidate_truncation=true`，`candidate_top_k=3`，`enable_dynamic_beam_width=true`，`beam_width_early/mid/late=5/3/2`，`enable_refine=false`，`keep_all_matches=true` | 最快；池子小、不 refine，适合先跑通流程或文案段很多时试参数 |
| 平衡（常用） | `enable_candidate_truncation=true`，`candidate_top_k=6~8`，`enable_dynamic_beam_width=true`，`beam_width_early/mid/late=10/6/4`，`enable_refine=true`，`refine_candidate_top_k=6~8`，`enable_backward_jump_penalty=true`，`enable_timeline_zigzag_penalty=true` | 质量与速度较均衡，适合作为默认组合 |
| 质量 / 难剪素材 | `enable_candidate_truncation=true`，`candidate_top_k=8~12`，`beam_width_early/mid/late=12/8/5` 或更宽，`enable_refine=true`，`refine_candidate_top_k` 与 `candidate_top_k` 接近 | 扩大每段候选与 Beam，时间线更稳但更慢；段数极多时慎用 |
| 只看原始搜索、不做后处理 | `enable_refine=false`，`enable_polyline_smoothing=false` | 便于观察 Beam 搜索本身效果，不受 refine / smoothing 干预 |
| 仅对比路径、减小 JSON | `keep_all_matches=false` | 每段只保留全局选中的一条 `matches[0]`，文件更小 |

单字段经验：`keep_top_paths` 只影响输出里 `global_paths` 条数，**不参与**选优，一般 3～5 够用、调试时可加大。`input_rerank_json` / `output_json` 通常保持默认即可。

3) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`output/copywriting_to_shots_global_path.json`

### Step 4.9 精彩片段解说脚本（LLM 时间轴对齐）
名称：`step4_9_highlight_narration_script`

这个步骤会把两类数据一起喂给云雾 LLM：
- Step4.8 输出的文案-镜头全局路径结果（默认 `output/copywriting_to_shots_global_path.json`）
- 整部影片的镜头时间线数据（默认 `output/video_1_shots_multimodal.json`）

目标：
- 从整部影片中只挑“值得解说的精彩片段”
- 结合候选匹配与全片时间轴，让模型一次性输出完整的带时间戳解说脚本 JSON

输出 JSON 结构：
- 顶层 `items[]`：最终完整时间轴脚本
- 顶层 `prompt_preview`：本次请求喂给模型的摘要内容，便于排查

1) 编辑 `config.json`：
- `step`: 设置为 `step4_9_highlight_narration_script`
- `step4_9_highlight_narration_script.input_match_json`: Step4.8 输出（默认 `output/copywriting_to_shots_global_path.json`）
- `step4_9_highlight_narration_script.shots_multimodal_json`: 全片镜头数据（默认 `output/video_1_shots_multimodal.json`）
- `step4_9_highlight_narration_script.output_json`: 输出（默认 `output/highlight_narration_script.json`）
- `step4_9_highlight_narration_script.model`: 使用的 LLM
- `step4_9_highlight_narration_script.max_items_for_retrieval`: 最多向模型展示多少条文案的 Top1 候选摘要；默认全部
- `step4_9_highlight_narration_script.temperature/max_retries/retry_sleep_seconds`: 模型采样与重试参数

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 结果：`output/highlight_narration_script.json`

说明：
- 这一步会把全部解说文案一次性提交给模型，不再按 chunk 分段生成。
- 为减少上下文长度，不会直接把整份 `video_1_shots_multimodal.json` 原样塞给模型，而是提供每条文案的 Top1 检索候选摘要，再补充按时间线压缩后的全片镜头摘要。
- Step4.8 结果中已不再包含折线离群字段（如历史版本中的 `is_polyline_outlier`）；本步仅依赖检索候选与全片镜头时间轴。
- 模型必须输出严格 JSON，并在代码里做了时间戳格式、片段时长（不少于 1 秒）、`OST` 值等校验。

### Step 5 生成成片（Edge 配音 + 镜头合成 + 拼接）
名称：`step5_generate_video`

根据 Step4.8 的全局路径结果（默认每条文案取 `matches[0]`），并发用 Edge TTS 生成配音，然后用 ffmpeg 截取镜头、按配音时长自动延长/裁剪镜头，最后把所有片段拼接成一个视频。

前置：
- 系统已安装 `ffmpeg`（命令行可用）
- 已生成 `output/copywriting_to_shots_global_path.json`

1) 编辑 `config.json`：
- `step`: 设置为 `step5_generate_video`
- `video.path`: 你的原视频（如 `inputFile/video_1.mp4`）
- `generate_video.input_match_json`: Step4.8 输出（默认 `output/copywriting_to_shots_global_path.json`）
- `generate_video.output_video`: 最终视频输出（默认 `output/generated/final.mp4`）
- `generate_video.segment_concurrency`: 片段合成并发数（默认 2，越大越占 CPU）
- `generate_video.reuse_existing`: 若音频/片段已存在则复用（默认 true，便于断点续跑）
- `generate_video.tts.voice/rate/volume`: Edge 配音参数
- `generate_video.tts.concurrency`: 配音并发数

2) 运行：

```bash
.\.venv\Scripts\python -X utf8 main.py
```

输出：
- 最终视频：`output/generated/final.mp4`
- 构建明细：`output/generated/build_meta.json`