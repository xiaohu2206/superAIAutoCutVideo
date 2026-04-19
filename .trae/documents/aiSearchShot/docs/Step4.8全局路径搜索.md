
# 🚀 Step 4.8：全局路径搜索（最终完整版）

---

# 一、输入定义（标准化）

---

## ✅ 输入1：Step4.5 输出（每段 TopK）

```ts
rerankResults = [
  {
    narration_id: 0,
    candidates: [s1, s2, s3]  // 已包含 finalScore（Step5）
  },
  ...
]
```

---

## ✅ 输入2：全局信息

```ts
meta = {
  totalSegments: N
}
```

---

# 二、整体流程（总览）

---

```ts
globalSearchPlus():

  1. 构建候选矩阵
  2. 多路径 Beam Search（宽搜索）
  3. 动态 Beam 控制（前宽后窄）
  4. 路径扩展（带 transition score）
  5. 保留 TopN 路径（不是1条）
  6. 路径级回溯优化（Refine）
  7. 全局评分（Global Score）
  8. 最终路径选择
```

---

# 三、Step 4.8.1 构建候选矩阵

---

```ts
function buildCandidateMatrix(rerankResults) {
  return rerankResults.map(r => r.candidates)
}
```

---

# 四、Step 4.8.2 路径结构定义（升级版🔥）

---

```ts
path = {
  shots: [],              // 镜头序列
  score: 0,               // 累计分
  lastShot: null,         
  usedShotIds: Set(),     // 防重复
  timeline: [],           // 时间序列（用于检测跳跃）
}
```

---

# 五、Step 4.8.3 动态 Beam 初始化（关键🔥）

---

```ts
function getBeamWidth(i, total) {
  const ratio = i / total

  if (ratio < 0.3) return 8   // 前期：探索
  if (ratio < 0.7) return 5   // 中期：平衡
  return 3                    // 后期：收敛
}
```

---

# 六、Step 4.8.4 路径初始化

---

```ts
function initPaths(firstCandidates) {
  return firstCandidates.map(shot => ({
    shots: [shot],
    score: shot.finalScore,
    lastShot: shot,
    usedShotIds: new Set([shot.shot_id]),
    timeline: [[shot.start, shot.end]]
  }))
}
```

---

# 七、Step 4.8.5 路径扩展（核心🔥）

---

```ts
function expandPaths(paths, candidates, i, total) {

  beamWidth = getBeamWidth(i, total)

  newPaths = []

  for (path of paths) {
    for (shot of candidates) {

      // 1. 防重复
      if (path.usedShotIds.has(shot.shot_id)) continue

      // 2. 计算 transition
      tScore = calcTransitionScore(path.lastShot, shot)

      // 3. 计算局部增量分
      incrementalScore = shot.finalScore + tScore

      newPaths.push({
        shots: [...path.shots, shot],
        score: path.score + incrementalScore,
        lastShot: shot,
        usedShotIds: new Set([...path.usedShotIds, shot.shot_id]),
        timeline: [...path.timeline, [shot.start, shot.end]]
      })
    }
  }

  return topK(newPaths, beamWidth)
}
```

---

# 八、Step 4.8.6 Transition Score（关键模块🔥）

---

```ts
function calcTransitionScore(prev, curr) {

  let score = 0

  // 1. 时间连续性（最重要）
  if (curr.start >= prev.end) score += 1
  else score -= 1.5

  // 2. 时间间隔惩罚
  gap = curr.start - prev.end
  if (gap > 30) score -= 0.5

  // 3. 场景一致性
  if (sameScene(prev, curr)) score += 0.5
  else score -= 0.3

  // 4. 人物一致性
  if (sameSubject(prev, curr)) score += 0.5

  // 5. 动作衔接
  if (isActionFlow(prev, curr)) score += 0.5

  // 6. 镜头语言（高级）
  if (isShotProgression(prev, curr)) score += 0.3

  return score
}
```

---

# 九、Step 4.8.7 主搜索流程（多路径🔥）

---

```ts
function multiPathSearch(matrix, total) {

  paths = initPaths(matrix[0])

  for (i = 1; i < matrix.length; i++) {
    paths = expandPaths(paths, matrix[i], i, total)
  }

  return paths   // ⭐ 返回多条路径
}
```

---

# 十、Step 4.8.8 路径回溯优化（修错🔥）

---

```ts
function refinePath(path, matrix) {

  for (i = 0; i < path.shots.length; i++) {

    current = path.shots[i]
    alternatives = matrix[i]

    for (alt of alternatives) {

      if (alt.shot_id === current.shot_id) continue

      newPath = replaceShot(path, i, alt)

      if (globalScore(newPath) > globalScore(path)) {
        path = newPath
      }
    }
  }

  return path
}
```

---

# 十一、Step 4.8.9 全局评分（终极裁决🔥）

---

```ts
function globalScore(path) {

  score = path.score

  // 1. 时间单调性（强约束）
  if (!isTimelineValid(path.timeline)) {
    score -= 3
  }

  // 2. 场景稳定性
  if (tooManySceneCuts(path)) {
    score -= 1
  }

  // 3. 节奏控制（关键🔥）
  if (!isRhythmBalanced(path)) {
    score -= 1
  }

  // 4. 情绪曲线（高级🔥）
  if (!isEmotionCurveValid(path)) {
    score -= 1
  }

  return score
}
```

---

# 十二、Step 4.8.10 最终选择

---

```ts
function selectBestPath(paths, matrix) {

  // 1. 回溯优化
  refined = paths.map(p => refinePath(p, matrix))

  // 2. 全局评分
  scored = refined.map(p => ({
    path: p,
    score: globalScore(p)
  }))

  // 3. 排序选最优
  return sort(scored)[0]
}
```

---

# 十三、Step 4.8 总入口（最终版🔥）

---

```ts
function globalSearchPlus(rerankResults, meta) {

  // Step1: 构建候选矩阵
  matrix = buildCandidateMatrix(rerankResults)

  // Step2: 多路径搜索（防止早期误杀）
  paths = multiPathSearch(matrix, meta.totalSegments)

  // Step3: 全局优化 + 回溯修正
  best = selectBestPath(paths, matrix)

  return best
}
```

---

# 十四、关键设计总结（你必须掌握）

---

## ✅ 1. 多路径而不是单路径

```text
避免：一步错 → 全盘崩
```

---

## ✅ 2. 前期宽搜索，后期收敛

```text
探索 vs 利用
```

---

## ✅ 3. 允许“推翻过去选择”（回溯）

```text
这是你系统从80分 → 90分的关键
```

---

## ✅ 4. 引入“全局评分”

```text
让系统具备“导演判断”
```

---

# 🔥 一句话本质

```text
Step6 = 在“多个可能的剪辑版本”中，选出最像电影的一条
```
