# Step1 镜头切分与字幕对齐（升级版）

本文档用于解决一个高频问题：**同一句字幕出现在多个镜头，导致“重复多、语义碎”**。

---

## 1. 问题定义

你当前策略是正确的基础策略：

- 镜头由 TransNetV2 切分，作为时间主轴（不可拆）
- 字幕按镜头边界拆分（可拆）

这会天然产生现象：

- 同一条原字幕可能出现在多个相邻镜头
- 如“坏人把我的饺子抢走了”“怎么这么没礼貌”会跨 2~3 个镜头

这不是错误，而是**时间精确对齐的代价**。

---

## 2. 总体方案（推荐）

采用**双层输出**，把“时间精确”和“语义完整”分层：

- `shots_raw`：严格镜头层（不丢时间精度）
- `segments_semantic`：语义段层（减少重复，给 AI 用）

一句话：**底层不动镜头，上层做语义合并**。

---

## 3. Step A：镜头切分（不变）

```ts
shots = [
  { shot_id: 1, start: 20.040, end: 21.580 },
  { shot_id: 2, start: 21.580, end: 22.700 },
  ...
];
```

规则：

- 镜头连续、无重叠
- 每个时间点只属于一个镜头

---

## 4. Step B：字幕按镜头拆分（不变）

```ts
function splitSubtitleByShots(sub, shots) {
  const result = [];
  for (const shot of shots) {
    const overlapStart = Math.max(sub.start, shot.start);
    const overlapEnd = Math.min(sub.end, shot.end);
    if (overlapStart < overlapEnd) {
      result.push({
        start: overlapStart,
        end: overlapEnd,
        text: sub.text,
        original_subtitle_index: sub.index
      });
    }
  }
  return result;
}
```

规则：

- 字幕可拆，镜头不可拆
- 每个拆分片段仅归属一个镜头

---

## 5. Step C：构建 `shots_raw`（严格层）

```ts
for (const shot of shots) shot.subtitles = [];

for (const sub of subtitles) {
  const splitSubs = splitSubtitleByShots(sub, shots);
  for (const s of splitSubs) {
    const shot = findShotByRange(shots, s.start, s.end);
    shot.subtitles.push(s);
  }
}
```

输出目标：

- 保留每段时间精度
- 允许同一 `original_subtitle_index` 出现在多个相邻 shot

---

## 6. Step D：构建 `segments_semantic`（新增，关键）

### 6.1 合并锚点

优先使用 `original_subtitle_index`，不要只用 `text`。

原因：

- 同文案可能在不同位置重复（如“那地上是什么”）
- `text` 合并容易误并

### 6.2 合并条件（推荐）

对相邻镜头 `A`、`B`，若满足以下条件则可合并到同一语义段：

```ts
const shareIndex = intersection(A.subtitle_indices, B.subtitle_indices).size > 0;
const shortShot = (A.duration < 1.4) || (B.duration < 1.4);
const maxSegmentDuration = currentSegment.end - currentSegment.start <= 6.0;

if (shareIndex && shortShot && maxSegmentDuration) {
  merge();
}
```

推荐阈值：

- `shortShotThreshold = 1.2 ~ 1.5s`（默认 1.4）
- `maxSegmentDuration = 4 ~ 6s`（默认 6.0）

### 6.3 语义去重

在语义段中构建完整文本时，按 `original_subtitle_index` 去重再拼接：

```ts
subtitle_full_text = uniqueByOriginalIndex(subtitles)
  .sort(byStart)
  .map(s => s.text)
  .join(" ");
```

---

## 7. 最终输出结构（推荐）

```json
{
  "video_path": "...",
  "srt_path": "...",
  "shots_raw": [
    {
      "shot_id": 12,
      "start": 20.04,
      "end": 21.58,
      "duration": 1.54,
      "subtitles": [
        { "start": 20.26, "end": 21.26, "text": "妈妈妈妈", "original_subtitle_index": 1 },
        { "start": 21.26, "end": 21.58, "text": "坏人把我的饺子抢走了", "original_subtitle_index": 2 }
      ]
    }
  ],
  "segments_semantic": [
    {
      "segment_id": 1,
      "start": 20.04,
      "end": 24.10,
      "duration": 4.06,
      "shot_ids": [12, 13, 14],
      "subtitles": [
        { "start": 20.26, "end": 21.26, "text": "妈妈妈妈", "original_subtitle_index": 1 },
        { "start": 21.26, "end": 23.00, "text": "坏人把我的饺子抢走了", "original_subtitle_index": 2 },
        { "start": 23.00, "end": 24.10, "text": "你是谁家的孩子", "original_subtitle_index": 3 }
      ],
      "subtitle_full_text": "妈妈妈妈 坏人把我的饺子抢走了 你是谁家的孩子"
    }
  ]
}
```

---

## 8. 规则总表

```text
1. 镜头是时间主轴，不可拆分
2. 字幕必须按镜头边界拆分
3. 每个字幕片段只属于一个镜头（无跨镜头片段）
4. shots_raw 保证时间精度，不做语义去重
5. segments_semantic 用于降重复与语义表达
6. 语义合并锚点使用 original_subtitle_index
7. 合并只在相邻镜头间进行，并受短镜头阈值与最长段时长约束
8. subtitle_full_text 在语义层按 original_subtitle_index 去重拼接
```

---

## 9. 实施建议（落地顺序）

```text
第1步：保留现有拆分逻辑，输出 shots_raw
第2步：新增语义段构建器，输出 segments_semantic
第3步：检索/Embedding 改用 segments_semantic.subtitle_full_text
第4步：最终剪辑仍回溯到 shots_raw 的时间区间
```

---

## 10. 一句话结论

**镜头不能动；字幕先拆分做时间对齐，再在上层做语义合并。**
