上一步拿到的镜头数据示例：
```json
{
  "shot_id": 1,
  "start": 30,
  "end": 50,
  "frames": [...],
  "subtitles": [
    { "start": 30, "end": 32, "text": "..." },
    { "start": 35, "end": 40, "text": "..." }
  ]
}
```
****
## Step 1：关键帧提取
避免选到“黑帧 / 切换帧”:
```
function extractKeyframes(shot) {
  const frames = shot.frames

  return [
    frames[Math.floor(frames.length * 0.2)],
    frames[Math.floor(frames.length * 0.5)],
    frames[Math.floor(frames.length * 0.8)]
  ]
}
```
👉 原因：
避开镜头边界（容易模糊/过渡）
中间信息更稳定

## Step 2：视觉模型分析帧（模型qwen3-vl-flash）
1张关键帧 + Prompt：
```
你是一个影视镜头分析专家，请根据提供的视频关键帧（按时间顺序）和字幕内容，对该镜头进行语义理解。

【要求】
1. 综合多帧信息，不要只描述单帧
2. 优先识别人物、动作、场景、情绪
3. 如果字幕提供了语义，结合字幕理解（但不要照抄字幕）
4. 输出必须结构化 JSON

【输出字段定义】
- desc：一句话描述这个镜头发生了什么（自然语言）
- objects：画面中主要物体（数组）
- action：核心动作（动词，如：离开/奔跑/对话）
- scene：场景（室内/室外/街道/房间等）
- emotion：整体情绪（如：开心/悲伤/紧张/平静）

字幕：
{{subtitle_text}}

【输出JSON格式】
{
  "desc": "",
  "objects": [],
  "action": "",
  "scene": "",
  "emotion": ""
}
```

## Step 3：字幕合并+构建summary
输入：
```json
[
  { "start": 30, "end": 32, "text": "他终于决定离开" },
  { "start": 35, "end": 40, "text": "这座城市不再属于他" }
]
```
合并逻辑：
```
function mergeSubtitles(subtitles) {
  return {
    full_text: subtitles.map(s => s.text).join(""),
    segments: subtitles
  }
}
```
输出：
```json
{
  "full_text": "他终于决定离开这座城市不再属于他",
  "segments": [
    { "start": 30, "end": 32, "text": "他终于决定离开" },
    { "start": 35, "end": 40, "text": "这座城市不再属于他" }
  ]
}
```
构建summary:
```
function buildSummary(visual, subtitle) {
  return `
画面：${visual.desc}
动作：${visual.action}
情绪：${visual.emotion}
字幕：${subtitle.full_text}
  `.trim()
}
```
输出：
```
画面：刘十三拖着行李走出房间
动作：离开
情绪：低落
字幕：他终于决定离开这座城市不再属于他
```

## Step 4：embedding 向量化
（使用模型text-embedding-3-large）
输入：
```
function buildEmbeddingInput(summary) {
  return summary
}
```

## 最终输出结构
```json
{
  "shot_id": 1,
  "start": 30,
  "end": 50,
  "frames": [...],
  "subtitle": {
    "full_text": "他终于决定离开这座城市不再属于他",
    "segments": [
      { "start": 30, "end": 32, "text": "他终于决定离开" },
      { "start": 35, "end": 40, "text": "这座城市不再属于他" }
    ]
  },
  "visual": {
    "desc": "刘十三拖着行李走出房间",
    "objects": ["人", "行李箱", "房门"],
    "action": "离开",
    "scene": "室内",
    "emotion": "低落"
  },
  "summary": "画面：刘十三拖着行李走出房间，情绪低落，他决定离开这座城市",
  "embedding": [...]
}
```