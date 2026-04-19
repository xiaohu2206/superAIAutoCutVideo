# 🚀 Step 4.5：重排序（Re-rank，完整版）

---

# 一、输入数据定义（统一标准）

---

## ✅ 1. 文案结构（输入）

```json
{
  "id": 0,
  "text": "故事开始于2017年的春天,城市清晨的光照进合租房",
  "event": "阳光照进房间",
  "subject": "环境/光线",
  "emotion": "平静",
  "scene_type": "室内-清晨-静态",
  "visual_keywords": ["阳光", "合租房", "窗户", "清晨"],
  "action": "照入",
  "camera_hint": "远景"
}
```

---

## ✅ 2. 检索结果（embedding召回）

```json
{
  "item_index": 0,
  "text": "...",
  "embedding_model": "text-embedding-3-large",
  "matches": [
    {
      "shot_id": 106,
      "start": 438.571,
      "end": 449.857,
      "duration": 11.286,
      "frame": "...",
      "summary": "...",
      "score": 0.59
    }
  ]
}
```

---

## ✅ 3. 上下文结构（新增🔥）

```ts
context = {
  prev: "上一段文案",
  next: "下一段文案"
}
```

---

## ✅ 4. 全局信息（新增🔥）

```ts
meta = {
  index: 3,
  total: 20,
  prevShot: 105   // 上一个已选镜头（用于连续性）
}
```

---

# 二、Query 构造（核心升级🔥）

---

## ✅ 剧情阶段函数（优化版）

```ts
function getStage(i, total) {
  const ratio = i / total

  if (ratio < 0.15) return "开头-建立世界观"
  if (ratio < 0.4) return "发展-人物展开"
  if (ratio < 0.7) return "冲突-矛盾激化"
  if (ratio < 0.9) return "高潮-情绪爆发"
  return "结尾-收束"
}
```

---

## ✅ Query 构造（增强版🔥）

```ts
function buildQuery(narration, context, meta) {
  return `
【当前文案】
${narration.text}

【语义信息】
事件：${narration.event}
主体：${narration.subject}
情绪：${narration.emotion}
动作：${narration.action}
场景：${narration.scene_type}
镜头建议：${narration.camera_hint}

【上下文】
前文：${context.prev || "无"}
后文：${context.next || "无"}

【剧情位置】
第 ${meta.index} 段 / 共 ${meta.total} 段
阶段：${getStage(meta.index, meta.total)}

【剪辑目标】
选择最符合语义、情绪，并且适合当前剧情阶段的镜头
`.trim()
}
```

---

# 三、候选镜头构造（标准化🔥）

---

## ❗ 核心优化点：结构化 > 拼接字符串

```ts
function buildDocs(matches) {
  return matches.map(m => ({
    shot_id: m.shot_id,
    text: `
画面：${m.summary}
时间：${m.start}-${m.end}
`.trim(),
    embedding_score: m.score
  }))
}
```

---

# 四、Re-rank 双阶段设计（关键升级🔥）

---

# ✅ 阶段1：粗排（云雾 qwen3-rerank）

---

## 🎯 目标

```text
从 Top20 → 筛到 Top5 ～ top10
```

---

## ✅ 输入

```ts
query = narration.text（或简化版）
docs = buildDocs(matches)
```

---

## ✅ 输出

```ts
topCandidates = top5 ～ top10
```

---

---

# ✅ 阶段2：精排（LLM，例如 云雾 glm-4）

---

## 🎯 Prompt（强化版，防跑偏🔥）

```text
你是一个专业电影剪辑师。

你的任务是：从候选镜头中选出“最适合当前文案”的镜头。

---

【当前文案信息】
{query}

---

【候选镜头】
{docs}

---

【评分维度】

1. 语义匹配（权重最高）
- 是否表达相同事件和动作

2. 情绪匹配
- 情绪是否一致（平静/悲伤/紧张）

3. 场景匹配
- 室内/室外、时间（清晨/夜晚）

4. 剧情阶段匹配（非常关键）
- 开头 → 建立环境（空镜/远景）
- 发展 → 人物行为
- 冲突 → 强动作/对抗
- 高潮 → 情绪爆发
- 结尾 → 情绪收束

5. 镜头语言匹配
- 是否符合 camera_hint（远景/特写）

6. 连续性（重要）
- 是否适合接在前一个镜头之后
- 避免时间跳跃过大

---

【输出要求】

返回 JSON：

[
  {
    "shot_id": number,
    "score": 0-1,
    "reason": "必须说明匹配原因（语义/情绪/阶段）"
  }
]

按 score 从高到低排序
只返回前3个
```

---

# 五、最终评分融合（工程关键🔥）

---

## ✅ 推荐公式

```ts
finalScore =
  0.55 * rerank_score +
  0.30 * embedding_score +
  0.15 * continuity_score
```

---

## ✅ continuity_score（新增🔥）

```ts
function continuityScore(prevShot, currentShot) {
  let score = 1

  if (!prevShot) return score

  // 时间跳跃惩罚
  if (Math.abs(currentShot.start - prevShot.end) > 30) {
    score -= 0.3
  }

  // 场景突变
  if (scene不同) {
    score -= 0.2
  }

  return score
}
```

---

# 六、完整执行流程（最终版）

---

```ts
// Step1: 构造 query
query = buildQuery(narration, context, meta)

// Step2: 构造 docs
docs = buildDocs(matches)

// Step3: 粗排（embedding + rerank）
top10 = qwen3_rerank(query, docs)

// Step4: 精排（LLM）
top3 = glm4_rerank(query, top10)

// Step5: 融合评分
finalScores = top3.map(item => ({
  ...item,
  finalScore:
    0.55 * item.score +
    0.30 * item.embedding_score +
    0.15 * continuityScore(prevShot, item)
}))

// Step6: 选最优
bestShot = sort(finalScores)[0]
```

