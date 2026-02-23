#!/usr/bin/env python
# -*- coding: UTF-8 -*-

def short_drama(language: str = "zh") -> str:
    if language.lower() == "en":
        return """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": "sequence_number",
  "timestamp": "start_time-end_time",
  "narration": "播放原片+序号",
  "OST": 1
}
```

## 输出格式要求示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:0x,000-00:00:0x,x00",
      "narration": "...",
      "OST": 0
    },
    {
      "_id": 2,
      "timestamp": "00:00:0x,x00-00:00:0x,000",
      "narration": "播放原片x",
      "OST": 1
    },
    {
      "_id": 3,
      "timestamp": "00:00:0x,000-00:00:xx,000",
      "narration": "...",
      "OST": 0
    }
  ]
}
"""
    return """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": 序号,
  "timestamp": "开始时间-结束时间",
  "narration": "播放原片+序号",
  "OST": 1
}
```

## 输出格式要求示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:0x,000-00:00:0x,x00",
      "narration": "...",
      "OST": 0
    },
    {
      "_id": 2,
      "timestamp": "00:00:0x,x00-00:00:0x,000",
      "narration": "播放原片x",
      "OST": 1
    },
    {
      "_id": 3,
      "timestamp": "00:00:0x,000-00:00:xx,000",
      "narration": "...",
      "OST": 0
    }
  ]
}
"""


def movie(language: str = "zh") -> str:
    if language.lower() == "en":
        return """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": "sequence_number",
  "timestamp": "start_time-end_time",
  "narration": "播放原片+序号",
  "OST": 1
}
```

## 输出格式要求示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:0x,000-00:00:0x,x00",
        "narration": "...",
        "OST": 0
    },
    {
        "_id": 2,
        "timestamp": "00:00:xx,x00-00:00:xx,000",
        "narration": "播放原片x",
        "OST": 1
    },
    {
        "_id": 3,
        "timestamp": "00:00:xx,000-00:00:xx,000",
        "narration": "...",
        "OST": 0
    }
  ]
}
"""
    return """## 原声片段格式要求
原声片段必须严格按照以下JSON格式：
```json
{
  "_id": 序号,
  "timestamp": "开始时间-结束时间",
  "narration": "播放原片+序号",
  "OST": 1
}
```

## 输出格式要求示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:0x,000-00:00:0x,x00",
        "narration": "……",
        "OST": 0
    },
    {
        "_id": 2,
        "timestamp": "00:00:0x,x00-00:00:0x,000",
        "narration": "播放原片x",
        "OST": 1
    },
    {
        "_id": 3,
        "timestamp": "00:00:0x,000-00:00:xx,000",
        "narration": "xxx",
        "OST": 0
    }
  ]
}
"""

