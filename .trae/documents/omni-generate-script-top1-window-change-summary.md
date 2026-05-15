# Omni 生成解说脚本改造说明

## 背景

原来的“生成电影解说脚本”步骤会把文案按条数分批，例如 40 条文案拆成每批 20 条。镜头列表窗口则按批次比例切电影时间轴：

| 批次 | 原逻辑 |
|---|---|
| 第 1 批 | 使用电影前半段镜头窗口 |
| 第 2 批 | 使用电影后半段镜头窗口 |

这个假设在文案顺序和电影时间线大体一致时可用，但如果第 21-40 条文案实际仍然对应电影前半段，第 2 批就会拿到无效的后半段镜头窗口，导致大模型选镜头上下文偏离。

本次改造的核心是：文案仍按条数分批，但每批镜头窗口改为由该批文案的 Top1 匹配镜头自动圈定。

## 改造目标

| 目标 | 说明 |
|---|---|
| 保留文案分批 | 继续用 `chunk_target_size` 控制每批文案数量，避免 LLM 上下文过大 |
| 改造镜头窗口 | 不再默认按“第几批”切电影，而是按本批 Top1 镜头时间分布圈定窗口 |
| 最小侵入 | 不改 LLM 调用、prompt 拼装、脚本合并主流程 |
| 可回退 | 保留 `proportional` 和 `legacy_top1` 旧模式 |
| 可调参 | Top1 聚类、pad、主簇比例等参数可通过 `generation_params` 覆盖 |

## 涉及文件

| 文件 | 改动 |
|---|---|
| `backend/modules/omni_generate_script/top1_window.py` | 新增独立 Top1 窗口计算模块 |
| `backend/modules/omni_generate_script/_runner_core.py` | 在 `_compute_chunk_time_windows()` 中接入 `top1_span` 模式 |
| `backend/modules/omni_generate_script/pure.py` | `OmniNarrationParams.timeline_window_mode` 默认改为 `top1_span`，并透传 Top1 参数 |
| `backend/services/omni_generate_script_service.py` | 从 `generation_params` 读取 Top1 窗口参数 |
| `backend/modules/omni_copywriting_struct_embed/segments.py` | 修复结构化模型返回单对象时的解析兼容问题 |

## Top1 窗口模式

新增窗口模式：

```text
timeline_window_mode = "top1_span"
```

默认值已从：

```text
proportional
```

改为：

```text
top1_span
```

仍可通过请求参数回退：

```json
{
  "generation_params": {
    "timeline_window_mode": "proportional"
  }
}
```

或：

```json
{
  "generation_params": {
    "timeline_window_mode": "legacy_top1"
  }
}
```

## Top1 窗口计算流程

| 步骤 | 逻辑 | 目的 |
|---|---|---|
| 1. 收集锚点 | 遍历本批 `chunk_results`，取每条文案的 `matches[0]` | 使用已有精细向量匹配结果 |
| 2. 清洗锚点 | 丢弃没有 `start/end` 或 `end <= start` 的 Top1 | 防止异常数据污染窗口 |
| 3. 无锚点回退 | 如果本批没有有效 Top1，则回退到 proportional 逻辑 | 保证任务不中断 |
| 4. 按时间排序 | 使用 `mid = (start + end) / 2` 排序 | 准备做时间聚类 |
| 5. 时间聚类 | 相邻 Top1 中点间隔超过阈值时切成新簇 | 避免少量远端误匹配拉大窗口 |
| 6. 选择主簇 | 最大簇占比达到阈值时只使用主簇，否则使用全部锚点 | 区分“离群点”和“真实跨段” |
| 7. 计算基础范围 | `raw_min = min(start)`，`raw_max = max(end)` | 覆盖本批主要 Top1 镜头 |
| 8. 增加 pad | 两端按比例补上下文，并限制最小/最大 pad | 给 LLM 足够衔接镜头 |
| 9. 裁剪边界 | 限制在 `[0, video_end]` 内 | 防止越界 |

## 核心参数

| 参数 | 默认值 | 说明 |
|---|---:|---|
| `top1_cluster_gap_min_seconds` | `60.0` | 时间聚类最小切分间隔 |
| `top1_cluster_gap_median_multiplier` | `4.0` | 使用相邻间隔中位数放大得到动态阈值 |
| `top1_main_cluster_ratio` | `0.7` | 最大簇占比达到 70% 时认为其余是离群点 |
| `top1_window_pad_ratio` | `0.1` | pad 为基础窗口跨度的 10% |
| `top1_window_pad_min_seconds` | `30.0` | 最小 pad |
| `top1_window_pad_max_seconds` | `180.0` | 最大 pad |

## 核心公式

```text
anchors = 本批有效 Top1 镜头

if anchors 为空:
    回退 proportional

clusters = 按 Top1 mid 时间间隔聚类
main_cluster = 数量最多的 cluster

if len(main_cluster) / len(anchors) >= 0.7:
    selected = main_cluster
else:
    selected = anchors

raw_min = min(anchor.start for anchor in selected)
raw_max = max(anchor.end for anchor in selected)
span = max(raw_max - raw_min, 1.0)

pad = clamp(span * 0.1, 30.0, 180.0)

window_start = max(0.0, raw_min - pad)
window_end = min(video_end, raw_max + pad)
```

## 典型效果

| 场景 | 改造前 | 改造后 |
|---|---|---|
| 第 2 批文案都对应电影前半段 | 第 2 批仍拿电影后半段窗口 | 第 2 批窗口跟随 Top1 回到电影前半段 |
| 19 条 Top1 在前半段，1 条误跳到后半段 | 窗口可能被拉大 | 主簇占比 95%，远端点被忽略 |
| 10 条 Top1 在前半段，10 条在后半段 | 很难表达真实跨段 | 最大簇占比不足 70%，使用全部锚点 |
| Top1 全部缺失 | 可能异常或窗口不准 | 自动回退 proportional |

## 结构化解析兼容修复

本次还修复了一个前置步骤报错：

```text
chunk=3 item=1 不是对象
```

原因是结构化模型有时返回单个对象：

```json
{
  "text": "...",
  "event": "...",
  "visual_keywords": ["..."]
}
```

旧解析逻辑只接受数组或包装数组，当对象里找不到 `items/segments` 时，会继续扫描所有 value，并误把 `visual_keywords` 这个字符串数组当成结构化 item 数组，最终报“item 不是对象”。

修复方式：

| 情况 | 新行为 |
|---|---|
| 直接返回数组 | 正常返回 |
| 返回 `{ "items": [...] }` / `{ "segments": [...] }` | 正常返回 |
| 返回 `{ "items": {...} }` / `{ "result": {...} }` | 自动包装成单元素数组 |
| 直接返回单个结构化对象 | 自动包装成单元素数组 |
| 对象里存在 `visual_keywords` 字符串数组 | 不再误判为 item 数组 |

## 验证情况

| 验证项 | 结果 |
|---|---|
| Python 语法检查 | `py_compile` 通过 |
| 40 条文案分两批，Top1 都在前半段 | 两批窗口都圈在前半段 |
| 19 个主簇 Top1 + 1 个远端离群 Top1 | 窗口只围绕主簇 |
| 结构化模型返回单对象 | 可正常解析为 1 个 item |
| 结构化模型返回 `{ "items": [obj] }` | 可正常解析 |

## 回退方式

如果需要临时回退旧窗口逻辑，在调用生成脚本时传：

```json
{
  "generation_params": {
    "timeline_window_mode": "proportional"
  }
}
```

如果需要使用旧 Top1 逻辑：

```json
{
  "generation_params": {
    "timeline_window_mode": "legacy_top1"
  }
}
```

## 总结

这次改造没有改变“文案分批”的策略，只把“每批镜头窗口怎么来”从批次比例切片改成了 Top1 镜头时间自适应圈定。分批仍然服务于 LLM 上下文限制，镜头窗口则跟随已经精细检索出的 Top1 结果走。
