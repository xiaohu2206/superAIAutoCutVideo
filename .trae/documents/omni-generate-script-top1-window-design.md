# Omni 生成解说脚本：基于 Top1 镜头圈定分批窗口改造方案

## 背景

当前「生成电影解说脚本」步骤会将文案按固定条数分批，例如 40 段文案分成两批，每批 20 段。由于大模型上下文限制，文案分批是必要的。

现有默认时间窗口逻辑偏向按文案批次比例映射电影时间轴：

- 第 1 批文案约对应电影前半段
- 第 2 批文案约对应电影后半段

这会导致一个问题：如果第 21-40 段文案实际都对应电影前半段，那么第 2 批收到的「镜头列表窗口」会落到电影后半段，窗口对大模型无效。

补充前提：每段文案已经有 `matches[0]`，这是基于全片做过向量检索和精细化召回后的 Top1 镜头结果，因此 Top1 镜头应作为本批时间窗口的主要锚点。

## 改造目标

| 目标 | 说明 |
|---|---|
| 保留文案分批 | 文案仍按 `chunk_target_size` 分批，解决 LLM 输入输出限制 |
| 改造镜头窗口 | 每批镜头窗口不再按“第几批”推断电影位置，而是由本批文案 Top1 镜头自动圈定 |
| 最小改动 | 尽量只改窗口计算逻辑，后续 prompt、LLM 调用、合并脚本逻辑保持不变 |
| 可回退 | Top1 缺失或异常时保留旧逻辑兜底 |

## 核心原则

| 原则 | 说明 |
|---|---|
| Top1 是锚点 | 本批文案的 `matches[0].start/end/shot_id` 是圈窗口的主要依据 |
| 分批不等于时间切片 | 文案第 2 批不天然等于电影后半段 |
| 窗口只提供上下文 | 窗口的作用是给大模型提供 Top1 附近可选镜头，不负责重新推断剧情位置 |
| 简单优先 | 先用 Top1 时间跨度 + 少量冗余，不引入复杂全局规划 |

## 推荐新增模式

建议新增或明确使用一个窗口模式：

```text
timeline_window_mode = "top1_span"
```

含义：按本批文案 Top1 镜头的时间跨度圈定镜头列表窗口。

## 窗口圈定流程

| 步骤 | 逻辑 | 目的 |
|---|---|---|
| 1. 收集锚点 | 遍历本批 `chunk_results`，取每条文案的 `matches[0]` | 使用已有精细检索结果 |
| 2. 清洗锚点 | 丢弃无 `matches`、无 `start/end`、`end <= start` 的项 | 避免脏数据污染窗口 |
| 3. 无锚点兜底 | 如果本批没有有效 Top1，回退旧窗口逻辑 | 保证异常数据仍可执行 |
| 4. 时间聚类 | 按 Top1 中点时间排序，按大时间间隔切成多个簇 | 避免少数远端误匹配拉大窗口 |
| 5. 选择主簇 | 如果最大簇覆盖本批有效锚点的比例达到阈值，则只用最大簇；否则使用全部锚点 | 区分“异常离群点”和“真实跨剧情段” |
| 6. 计算基础窗口 | `raw_start = min(selected.start)`，`raw_end = max(selected.end)` | 覆盖本批主要命中镜头 |
| 7. 增加冗余 | 两端加 `pad`，给大模型前后衔接镜头 | 避免窗口过窄 |
| 8. 边界裁剪 | `window_start >= 0`，`window_end <= video_end` | 防止越界 |
| 9. 过滤镜头列表 | 继续使用现有 `_filter_shots_by_time_window()` | 后续逻辑无需大改 |

## 参数建议

| 参数 | 推荐值 | 说明 |
|---|---:|---|
| `top1_cluster_gap_min_seconds` | `60` | 小于 60 秒的间隔通常仍视为同一剧情区域 |
| `top1_cluster_gap_median_multiplier` | `4.0` | 大间隔阈值 = 相邻正向间隔中位数 * 4 |
| `top1_main_cluster_ratio` | `0.7` | 最大簇覆盖 70% 以上有效锚点时，认为其它簇是离群点 |
| `top1_window_pad_ratio` | `0.1` | 窗口两端冗余为基础跨度的 10% |
| `top1_window_pad_min_seconds` | `30` | 最少补 30 秒上下文 |
| `top1_window_pad_max_seconds` | `180` | 最多补 180 秒，避免窗口过大 |

## 核心公式

```text
anchors = 本批有效 Top1 镜头

if anchors 为空:
    回退旧逻辑

sorted_anchors = 按 mid=(start+end)/2 排序
clusters = 按大时间间隔切分 sorted_anchors

main_cluster = 数量最多的 cluster

if len(main_cluster) / len(anchors) >= 0.7:
    selected = main_cluster
else:
    selected = anchors

raw_start = min(anchor.start for anchor in selected)
raw_end = max(anchor.end for anchor in selected)
span = max(raw_end - raw_start, 1.0)

pad = clamp(span * 0.1, 30, 180)

window_start = max(0, raw_start - pad)
window_end = min(video_end, raw_end + pad)
```

## 时间聚类细节

| 项目 | 逻辑 |
|---|---|
| 排序字段 | `mid = (start + end) / 2` |
| 相邻间隔 | `gap = current.mid - previous.mid` |
| 正常间隔样本 | 只统计 `gap >= 0` 的间隔 |
| 间隔中位数 | `median_gap = median(positive_gaps)` |
| 大间隔阈值 | `gap_threshold = max(60, median_gap * 4.0)` |
| 切簇条件 | 如果 `gap > gap_threshold`，开启新簇 |
| 单锚点情况 | 不聚类，直接用该锚点加 pad |

## 典型场景

| 场景 | Top1 分布 | 结果 |
|---|---|---|
| 40 段文案都在电影前半段 | 第 2 批 Top1 也集中在前半段 | 第 2 批窗口仍圈在前半段，不会跑到后半段 |
| 19 条在前半段，1 条误跳到后半段 | 最大簇占比 95% | 使用前半段主簇，丢弃远端离群锚点 |
| 10 条在前半段，10 条在后半段 | 最大簇占比 50% | 使用全部锚点，认为该批真实跨段 |
| 本批 Top1 全部缺失 | 无有效锚点 | 回退旧窗口逻辑 |

## 建议改动点

| 文件 | 位置 | 改动 |
|---|---|---|
| `backend/modules/omni_generate_script/pure.py` | `OmniNarrationParams` | 将 `timeline_window_mode` 默认值改为 `"top1_span"` |
| `backend/modules/omni_generate_script/_runner_core.py` | `_compute_chunk_time_windows()` | 增加 `top1_span` 分支 |
| `backend/modules/omni_generate_script/_runner_core.py` | 可新增内部 helper | 增加 Top1 锚点收集、聚类、pad 计算函数 |
| `backend/modules/omni_generate_script/_runner_core.py` | `CHUNK_TASK_SUFFIX` | 可选：补一句“本批时间轴窗口以 Top1 检索候选时间范围为准” |
| `backend/services/omni_generate_script_service.py` | `_params_from_request_and_project()` | 如需暴露新参数，可增加 generation_params 读取；也可先用默认常量 |

## 最小落地版本

如果希望第一版改动尽量少，可以先不暴露新参数，只写死推荐值：

| 项目 | 值 |
|---|---:|
| 主簇占比 | `0.7` |
| 最小 gap | `60s` |
| gap 倍数 | `4.0` |
| pad 比例 | `0.1` |
| 最小 pad | `30s` |
| 最大 pad | `180s` |

后续如果需要调参，再把这些值放入 `OmniNarrationParams` 和 `generation_params`。

## 伪代码

```python
def compute_top1_span_window(chunk_results, video_end):
    anchors = []
    for item in chunk_results:
        matches = item.get("matches") or []
        if not matches:
            continue

        m = matches[0]
        s = safe_float(m.get("start"))
        e = safe_float(m.get("end"))
        if e <= s:
            continue

        anchors.append({
            "start": s,
            "end": e,
            "mid": (s + e) * 0.5,
            "shot_id": m.get("shot_id"),
        })

    if not anchors:
        return None

    anchors.sort(key=lambda x: x["mid"])

    clusters = split_by_large_gap(anchors)
    main_cluster = max(clusters, key=len)

    if len(main_cluster) / len(anchors) >= 0.7:
        selected = main_cluster
    else:
        selected = anchors

    raw_start = min(x["start"] for x in selected)
    raw_end = max(x["end"] for x in selected)
    span = max(raw_end - raw_start, 1.0)

    pad = clamp(span * 0.1, 30.0, 180.0)

    window_start = max(0.0, raw_start - pad)
    window_end = raw_end + pad
    if video_end > 0:
        window_end = min(video_end, window_end)

    if window_end <= window_start:
        window_end = window_start + 1.0

    return window_start, window_end
```

## 与现有逻辑的关系

| 现有模式 | 保留方式 |
|---|---|
| `proportional` | 保留，作为手动配置或无 Top1 兜底 |
| `legacy_top1` | 可保留，用于对比测试 |
| `top1_span` | 推荐设为默认 |

## 验收标准

| 验收项 | 预期 |
|---|---|
| 文案分批数量不变 | 仍按原来的 `chunk_target_size` 分批 |
| 第 2 批文案 Top1 全在前半段 | 第 2 批 prompt 里的镜头列表也来自前半段 |
| 少数 Top1 离群 | 主簇占比达到阈值时，窗口不会被离群点拉大 |
| Top1 缺失 | 任务不失败，回退旧窗口 |
| LLM 输出合并 | `merge_chunk_items()` 等后续逻辑不受影响 |

## 推荐实施顺序

| 阶段 | 内容 | 风险 |
|---|---|---|
| 1 | 新增 `top1_span` 模式，不改其它流程 | 低 |
| 2 | 将默认 `timeline_window_mode` 改为 `top1_span` | 低 |
| 3 | 用已有 LLM message log 检查每批 prompt 的窗口范围 | 低 |
| 4 | 对比同一项目下 `proportional` 与 `top1_span` 输出质量 | 中 |

## 一句话总结

文案可以按 20 条分批，但镜头窗口必须跟着这 20 条文案已经检索到的 Top1 镜头走；分批只是模型上下文策略，不应该决定电影时间位置。
