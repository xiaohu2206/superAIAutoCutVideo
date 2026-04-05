# 脚本生成整体算法说明

本文档说明当前项目中“脚本长度规划 + 字幕/镜头拆分 + 并行生成 + 结果合并”的整体算法逻辑，主要对应以下实现：

- `backend/services/script_generation/length_planner.py`
- `backend/services/script_generation/subtitle_utils.py`
- `backend/services/script_generation/service.py`
- `backend/services/script_generation/constants.py`

## 1. 整体流程概览

无论输入来源是字幕还是镜头，当前脚本生成流程都可以概括为下面几步：

1. 读取项目配置中的脚本长度选项 `script_length`
2. 生成目标计划 `ScriptTargetPlan`
  - 得到目标成片条数范围
  - 得到推荐并行分段数 `preferred_calls`
3. 按输入素材数量对字幕/镜头做分段
  - 当前按“条数”拆分，不是按“字数”拆分
  - 每段会增加一定比例的上下文重叠
4. 按分段并行调用脚本生成
5. 将每段结果合并、去重、排序
6. 如果总条数超过目标条数，再做一次全局精修
7. 输出最终脚本 JSON

---

## 2. 关键常量

当前核心常量位于 `backend/services/script_generation/constants.py`：

- `DEFAULT_SCRIPT_LENGTH_SELECTION = "30～40条"`
- `CUSTOM_SCRIPT_LENGTH_MIN = 5`
- `CUSTOM_SCRIPT_LENGTH_MAX = 200`
- `AUTO_SCRIPT_CHARS_PER_20_SEGMENTS = 500`
- `AUTO_SCRIPT_SEGMENT_BASE = 20`
- `MAX_SUBTITLE_ITEMS_PER_CALL = 400`
- `SOFT_INPUT_FACTOR = 1.2`
- `MAX_SUBTITLE_CHARS_PER_CALL = 20000`

其中需要特别注意：

### 2.1 自动长度估算常量

- `AUTO_SCRIPT_CHARS_PER_20_SEGMENTS = 500`
- `AUTO_SCRIPT_SEGMENT_BASE = 20`

这两个常量共同表达一条经验规则：

> 每 500 个非空白字符，大约对应 20 条脚本。

等价理解为：

> 平均每 25 个非空白字符，对应 1 条脚本。

### 2.2 分段拆分常量

- `MAX_SUBTITLE_ITEMS_PER_CALL = 400`
- `SOFT_INPUT_FACTOR = 1.2`

它们共同决定单个分段的软上限：

```text
soft_max = ceil(400 × 1.2) = 480
```

也就是说，单个基础分段理想上不要超过约 480 条输入项。

注意：这里的“条”在不同入口下可以是字幕条，也可以是镜头条。

---

## 3. 脚本长度规划逻辑

对应文件：`backend/services/script_generation/length_planner.py`

### 3.1 输入两种模式

脚本长度规划有两种模式：

#### 模式 A：固定档位 / 自定义范围

例如：

- `15～20条`
- `30～40条`
- `40～60条`
- `60～80条`
- `80～100条`
- 或者用户传入自定义数值 / 范围

在这种模式下，会走：

- `normalize_script_length_selection()`
- `parse_script_length_selection()`

主要作用：

1. 统一各种分隔符格式，如 `~`、`-`、`—` 等都转成 `～`
2. 自动补上 `条`
3. 如果是单个数字，例如 `50`，会扩展为一个范围
4. 最终得到标准化后的目标范围

#### 模式 B：自动模式 `auto`

如果项目里的 `script_length` 为 `auto`，则走：

- `estimate_auto_script_length_plan(copywriting_text)`

### 3.2 自动模式的计算公式

自动模式会先统计文案的非空白字符数：

```text
non_ws_len = len(re.sub(r"\s+", "", text))
```

然后按下面的公式估算目标脚本条数：

```text
target = ceil((non_ws_len / AUTO_SCRIPT_CHARS_PER_20_SEGMENTS) × AUTO_SCRIPT_SEGMENT_BASE)
```

代入当前常量后就是：

```text
target = ceil((non_ws_len / 500) × 20)
```

进一步等价于：

```text
target = ceil(non_ws_len / 25)
```

也就是：

- 文案 500 字 → 约 20 条
- 文案 1000 字 → 约 40 条
- 文案 2500 字 → 约 100 条
- 文案 5000 字 → 约 200 条

然后会做上下界裁剪：

```text
target = clamp(target, 5, 200)
```

所以自动模式下最终目标条数不会小于 5，也不会大于 200。

### 3.3 推荐并行段数 `preferred_calls`

无论是固定档位还是自动模式，后面都要计算推荐并行段数：

```text
base_per_call = AUTO_SCRIPT_SEGMENT_BASE = 20
soft = SOFT_INPUT_FACTOR = 1.2
effective_per_call = 20 × 1.2 = 24
preferred_calls = ceil(target_max / 24)
```

这意味着系统的经验判断是：

> 每个并行任务大约负责 24 条目标输出。

示例：

- 目标 40 条 → `ceil(40 / 24) = 2`
- 目标 60 条 → `ceil(60 / 24) = 3`
- 目标 80 条 → `ceil(80 / 24) = 4`
- 目标 100 条 → `ceil(100 / 24) = 5`
- 目标 200 条 → `ceil(200 / 24) = 9`

这也是在自动模式下为什么经常会出现 9 段的原因之一。

---

## 4. 字幕 / 镜头拆分逻辑

对应文件：`backend/services/script_generation/subtitle_utils.py`

核心函数：`compute_subtitle_chunks()`

### 4.1 当前按“条数”拆，不按“字数”拆

当前拆分逻辑依据的是输入项数量：

- 如果入口是字幕生成，则 `subtitles` 是字幕条列表
- 如果入口是镜头生成，则 `subtitles` 实际上传入的是 `scene_items`

因此，`compute_subtitle_chunks()` 里的 `subtitles` 更准确地说是“时间线项目列表”。

### 4.2 先计算至少要分几段

设输入总条数为 `n`：

```text
soft_max = ceil(max_items × soft_factor)
min_calls = ceil(n / soft_max)
```

当前默认值下：

```text
max_items = 400
soft_factor = 1.2
soft_max = ceil(400 × 1.2) = 480
```

因此：

```text
min_calls = ceil(n / 480)
```

含义是：

> 为了不让单个基础分段超过大约 480 条输入项，至少要拆成 `min_calls` 段。

### 4.3 最终采用多少段

最终分段数由下面公式决定：

```text
calls = max(1, desired_calls, min_calls)
```

其中：

- `desired_calls` 来自长度规划阶段计算出的 `preferred_calls`
- `min_calls` 来自输入条数本身的下限约束

所以最终段数同时受两部分影响：

1. 目标输出条数想拆成几段
2. 输入素材量至少要拆成几段

谁更大，就采用谁。

### 4.4 基础均分

得到 `calls` 后，会按索引把输入数据做平均切片：

```text
start = (i * n) // calls
end = ((i + 1) * n) // calls
```

这会让每段大小尽量均匀。

### 4.5 超大分段二次递归拆分

如果某个基础分段仍然超过软上限 `soft_max`，会继续进入：

- `_split_subtitles_if_oversize()`

其策略非常直接：

1. 如果当前段长度不超过 `soft_max`，直接返回
2. 如果超过，则从中间一分为二
3. 对左右两半继续递归
4. 直到所有分段都不超过软上限

这一步的目标是控制每个基础分段的输入规模。

### 4.6 给每个分段补 50% 上下文重叠

在得到基础分段后，算法会再为每段增加上下文：

```text
overlap = floor(length × 0.5)
new_s = max(0, s_idx - overlap)
new_e = min(n, e_idx + overlap)
```

也就是说，每段会向前和向后各扩展自己长度的 50%。

这样做的目的主要是：

- 减少硬切段造成的语义断裂
- 给模型保留前后剧情/镜头上下文
- 提高局部生成结果的连贯性

因此最终送进模型的真实 `chunk["subs"]`，通常会比基础切片更大。

### 4.7 输出 chunk 结构

每个分段最终会包装成：

```json
{
  "idx": 0,
  "start": 0.0,
  "end": 12.3,
  "subs": [...]
}
```

字段含义：

- `idx`：分段序号
- `start`：本段首条的开始时间
- `end`：本段末条的结束时间
- `subs`：本段实际输入的字幕/镜头列表

---

## 5. 服务层如何把长度规划和拆分串起来

对应文件：`backend/services/script_generation/service.py`

服务层的核心串联逻辑如下：

1. 读取项目上的 `script_length`
2. 判断是否为 `auto`
3. 生成 `plan`
4. 根据 `plan.preferred_calls` + 输入条数，计算 chunks
5. 根据目标总条数，把输出额度分配到每个 chunk
6. 并发生成各分段脚本
7. 合并、精修、排序、校验

### 5.1 生成计划

```text
if is_auto:
    plan = estimate_auto_script_length_plan(copywriting_text)
else:
    plan = parse_script_length_selection(sel_length)
```

此时 `plan` 中主要有：

- `normalized_selection`
- `target_min`
- `target_max`
- `preferred_calls`
- `final_target_count`

### 5.2 计算分段

```text
chunks = compute_subtitle_chunks(
    subtitles=...,
    desired_calls=plan.preferred_calls,
    max_items=MAX_SUBTITLE_ITEMS_PER_CALL,
    soft_factor=SOFT_INPUT_FACTOR,
)
```

这里的关键点是：

- `plan.preferred_calls` 只是“推荐并行数”
- `compute_subtitle_chunks()` 还会根据输入条数强制抬高段数
- 所以最终 `len(chunks)` 不一定等于 `preferred_calls`

### 5.3 为每个 chunk 分配输出额度

使用：`allocate_output_counts(total_target_count, chunk_count)`

逻辑如下：

- 如果目标总条数为 `t`
- chunk 数为 `c`
- 且 `c <= t`
- 那么先算整除部分 `base = t // c`
- 再把余数 `rem = t % c` 依次分给前面的 chunk

这本质上是一个“尽量平均分配”的策略。

示例：

- 目标总条数 40
- chunk 数 3
- 则结果为 `[14, 13, 13]`

之后服务层还会再做一次边界修正：

```text
per_call_caps = [min(MAX_SUBTITLE_ITEMS_PER_CALL, max(2, x)) for x in per_call_caps]
```

也就是：

- 每段至少要求产出 2 条
- 每段上限不会超过 400

虽然这里的上限值与输入分段上限复用了同一个常量，但语义上它更像是“单段允许输出的条数上限”。

---

## 6. 并行生成与合并

### 6.1 并发执行

服务层会对每个 chunk 创建一个异步任务：

- 字幕入口调用 `_generate_script_chunk()`
- 镜头入口调用 `_generate_visual_script_chunk()`

并通过信号量控制并发数：

```text
sem = asyncio.Semaphore(5)
```

也就是最多 5 个分段任务同时运行。

### 6.2 合并结果

所有 chunk 完成后：

1. 把各段结果拼到一起
2. 调用 `_merge_items()` 做合并
3. 若结果条数多于目标条数，则调用 `_refine_full_script()` 做全局精修
4. 最后按时间戳排序
5. 为每条补 `_id`
6. 调用 `validate_script_items()` 做最终校验

---

## 7. 典型例子

### 例子 1：1152 个镜头，默认 30～40 条

- `target_max = 40`
- `preferred_calls = ceil(40 / 24) = 2`
- 输入条数 `n = 1152`
- `min_calls = ceil(1152 / 480) = 3`
- `calls = max(1, 2, 3) = 3`

所以最终至少拆成 3 段。

基础均分后约为：

- 第 1 段：384
- 第 2 段：384
- 第 3 段：384

再加上 50% overlap 后，实际输入给模型的每段会更大。

### 例子 2：自动模式，文案接近 5000 字

- `non_ws_len ≈ 5000`
- `target = ceil(5000 / 25) = 200`
- 自动模式又会把上限裁到 200
- `preferred_calls = ceil(200 / 24) = 9`

如果输入条数本身没有逼出更高的 `min_calls`，那最终就会看到 **9 段**。

---

## 8. 当前实现的重要特征

### 8.1 优点

1. 同时考虑了“目标输出规模”和“输入素材规模”
2. 分段数可以随目标条数和输入量自动调整
3. 使用 overlap 提高跨段上下文连贯性
4. 并行生成提高整体吞吐
5. 合并后再全局精修，能一定程度改善局部独立生成带来的割裂感

### 8.2 当前局限

1. 当前拆分依据是“条数”，不是“字符数”
  - 即使定义了 `MAX_SUBTITLE_CHARS_PER_CALL = 20000`
  - 当前这套拆分逻辑里也没有真正使用这个字符上限
2. overlap 固定为 50%
  - 对不同类型内容可能并不是最优
3. `MAX_SUBTITLE_ITEMS_PER_CALL` 同时用于输入分段和输出上限限制
  - 常量复用在语义上略混杂
4. 自动模式的经验公式是固定比例
  - `500 字 -> 20 条` 是经验值，不一定适合所有题材

---

## 9. 一句话总结

当前脚本生成的整体算法可以概括为：

> 先根据脚本长度配置或文案字数估算目标输出条数，再根据目标条数与输入素材规模共同决定并行分段数，随后对字幕/镜头按条数均分并增加重叠上下文，最后并行生成、合并去重、全局精修并输出最终脚本。

