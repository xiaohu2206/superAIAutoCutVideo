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

## 输出格式要求
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:01,000-00:00:05,500",
      "narration": "The fate of an ordinary girl is about to be completely changed by a cup of coffee! The man she bumped into is actually...",
      "OST": 0
    },
    {
      "_id": 2,
      "timestamp": "00:00:05,500-00:00:08,000",
      "narration": "播放原片2",
      "OST": 1
    },
    {
      "_id": 3,
      "timestamp": "00:00:08,000-00:00:12,000",
      "narration": "A classic opening of a domineering president! A love story triggered by a cup of coffee begins just like this...",
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

## 输出格式要求
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
      "_id": 1,
      "timestamp": "00:00:01,000-00:00:05,500",
      "narration": "一杯咖啡改变命运的瞬间，她撞上的男人竟是……",
      "OST": 0
    },
    {
      "_id": 2,
      "timestamp": "00:00:05,500-00:00:08,000",
      "narration": "播放原片1",
      "OST": 1
    },
    {
      "_id": 3,
      "timestamp": "00:00:08,000-00:00:12,000",
      "narration": "霸总经典开场，一场因咖啡而起的爱情，就此开幕……",
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

## 输出格式要求
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:01,000-00:00:05,500",
        "narration": "A fatal dilemma appears right at the start — this moment rewrites his destiny...",
        "OST": 0
    },
    {
        "_id": 2,
        "timestamp": "00:00:05,500-00:00:08,000",
        "narration": "播放原片1",
        "OST": 1
    },
    {
        "_id": 3,
        "timestamp": "00:00:08,000-00:00:12,000",
        "narration": "And at this moment, the gears of fate begin to turn — the truth draws near...",
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

## 输出格式要求
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{
  "items": [
    {
        "_id": 1,
        "timestamp": "00:00:01,000-00:00:05,500",
        "narration": "开场就抛出致命难题，这一刻改变了他的人生轨迹……",
        "OST": 0
    },
    {
        "_id": 2,
        "timestamp": "00:00:05,500-00:00:08,000",
        "narration": "播放原片1",
        "OST": 1
    },
    {
        "_id": 3,
        "timestamp": "00:00:08,000-00:00:12,000",
        "narration": "而这时，命运的齿轮开始转动，真相正在逼近……",
        "OST": 0
    }
  ]
}
"""

