# -*- coding: utf-8 -*-
# 自 aiSearchShot highlightNarrationScript/runner 抽取的纯函数（无 I/O、无 LLM），供 omni_generate_script 使用。
from __future__ import annotations
import math
import re
from typing import Any, Dict, List, Optional, Tuple

from .top1_window import Top1WindowConfig, compute_top1_span_window

DEFAULT_SYSTEM_PROMPT = (
    "你是一位专业的视频脚本时间轴编辑器。"
    "你必须严格按照JSON格式输出，绝不能包含任何其他文字、说明或代码块标记。"
)

DEFAULT_USER_PROMPT_TEMPLATE = """OST=0 为解说（narration 为解说文案）；OST=1 为原声（narration 为「播放原片+序号」）。
你必须仅输出一个JSON对象，键为'items'。每条时间段长度不能低于1秒。每条必须包含'id','timestamp','narration','OST'。不得输出除JSON以外的任何文字。
一次性输出完整脚本，items 不可为空；将全部解说文案对齐到镜头时间轴。
**解说文案铁律（高于一切其他表述）**：输入的解说文案**在任何情况下**均不得增删改——不得增加字句、不得删减句段、不得改写润色或同义替换、不得纠错或调整语序(严令禁止出现文案顺序错乱问题)；仅允许把**原文**拆成多条 items 的 narration（每条为原文的连续片段，拼接后须与原文逐字一致）。OST=1 条目的「播放原片+序号」格式不受此限，但不得夹带额外解说。
**原文顺序与 id（必须同时满足）**：将所有 OST=0 的 narration 按 `id` 从小到大依次拼接，必须与给定解说文案原文逐字完全一致。任意两段 OST=0 解说在原文中的先后，必须与它们在 items 里按 `id` 递增时的先后一致——**禁止**为配合爆点、镜头时间或叙事节奏而调换两段 OST=0 原文的先后顺序；仅允许在相邻 OST=0 段之间插入 OST=1。`timestamp` 与爆点骨架只决定每段落在哪一段时间、是否插原声，**不得**改变 OST=0 文本在全文中的先后。
你必须保证每条'narration'的配音时长与对应timestamp镜头时长匹配。按自然语速估算：中文约3-4字/秒（例如10个字约2.5-3.5秒），英文约2-3词/秒。若文本预计配音时长明显短于或长于镜头时长，必须改变镜头时长，不可以修改解说文案。每条预计配音时长与镜头时长误差尽量控制在±0.5秒内。
以下为必须严格使用的解说文案文本：所有 OST=0 条目的'narration'必须仅为该文案的拆分结果；不得编造或新增任何未在原文出现的字句；上文「解说文案铁律」永久适用。

## 输出格式示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{{
  "items": [
    {{
      "id": 1,
      "timestamp": "00:00:0x,000-00:00:0x,x00",
      "narration": "……",
      "OST": 0
    }},
    {{
      "id": 2,
      "timestamp": "00:00:xx,x00-00:00:xx,000",
      "narration": "播放原片2",
      "OST": 1
    }},
    {{
      "id": 3,
      "timestamp": "00:00:xx,000-00:00:xx,000",
      "narration": "xxx",
      "OST": 0
    }}
  ]
}}

# 解说脚本生成任务（视觉推理）

## 工作流程（必须遵守）
- **第一步（爆点先行）**：
  - **若下方提示词中出现 `<viral_shots_preextract>`**：该块为上游模型基于本批镜头列表预提取的「爆款/爆点镜头」清单。你必须以它为**首要骨架**安排本批节奏与 OST（原声优先落在这些 shot/时间附近）；再与「全片镜头列表」「检索候选摘要」交叉校验——仅当镜头描述或时间戳明显矛盾时，才允许在**同一叙事意图**下微调时间区间或改用相邻镜头合并区间，不得凭空新增与列表无关的爆点。
  - **若未出现 `<viral_shots_preextract>`**：在编排任何解说条目之前，须先通读镜头信息（含 vision、字幕、时间戳）与检索候选，自行在影片中识别并锁定「爆点镜头」——包括但不限于：情绪高潮、剧情反转/揭示、名场面或爽点、强冲突/对峙、高光动作、关键对白或声音驱动的戏剧性瞬间；为每个爆点明确对应的时间戳区间（可合并相邻镜头），作为后续节奏与 OST 取舍的骨架。
- **第二步（撰写脚本）**：在已建立的爆点时间轴框架下，将解说文案按**原文从左到右顺序**拆成 OST=0 条目并对齐到具体镜头时间段，生成下方 JSON（`id` 递增时所有 OST=0 的 narration 依次拼接即原文，见上文「原文顺序与 id」）；可在其间穿插 OST=1。输出中仅包含 items，无需另写爆点清单；`timestamp` 与 OST 取舍须体现「先定爆点、再铺解说」，但**不得**违反 OST=0 的原文先后顺序。

## 任务目标
结合镜头（scene）时间轴将解说文案对齐到对应时间段；视频时间轴上可跳过无关片段，但**输入解说文案须全部使用且无遗漏**（仅拆分，见上文「解说文案铁律」）；**优先围绕已确定的爆点镜头组织叙事节奏**（有 `<viral_shots_preextract>` 时以其为锚，无则依第一步自识别结果），避免平铺直叙忽略高潮。

## 输入说明
1. 解说文案：完整叙述文本，必须整体使用并仅作拆分（不得增删改，见「解说文案铁律」）。
2. 镜头信息：带精确时间戳的全片镜头列表，含字幕（如有）与画面理解（vision）。
3. 检索候选：文案与镜头的检索匹配结果，每条文案仅 Top1 候选，优先参考。
4. （可选）**爆款预提取**：若存在 `<viral_shots_preextract>`，须优先采纳其 shot_id 与时间戳作为爆点锚点，并与第 2、3 项对照校验后再写 items。

## 任务要求
- 按时间顺序抽取镜头（时间戳可大幅跳跃），且须覆盖完整解说文案（仅拆分、不省略）；OST=0 解说在 items 中的先后仍须严格等于原文阅读顺序（见「原文顺序与 id」），不可因镜头跳跃而打乱文案顺序。
- 无字幕镜头：依据 vision 判断剧情/动作/情绪以确定解说拆分位置。
- 有字幕镜头：可结合字幕与 vision 对齐解说。
- 时间戳格式：HH:MM:SS,mmm-HH:MM:SS,mmm。
- 在关键情绪爆发点、重要对白、爽点瞬间保留原声，避免解说太长用户太烦躁。

## 核心规则
优先使用原声（OST=1）的情况：
- 关键剧情对白（反转/伏笔/揭示）
- 强情绪爆发（愤怒/崩溃/告白）
- 经典台词（有传播力）
- 声音驱动场景（枪声/爆炸/哭声等）

必须使用解说（OST=0）的情况：
- 信息压缩（剪辑时间跳跃；**不得**用「总结式改写」代替原文，解说词仍须为原文拆分）
- 背景补充（人物关系/设定等仍须来自原文表述）
- 无有效对白的片段
- 过渡镜头

## 重要约束
- 不允许连续长时间纯解说或纯原声（需要节奏变化）；节奏调整仅通过 timestamp 与 OST 切换实现，**不得**以删改解说文案为代价。
- 非常重要的约束，不允许长时间的纯原声，绝对不允许

{dynamic_sections}
"""

CHUNK_TASK_SUFFIX = """

## 分批任务说明（必须遵守）
- 本批为第 {batch_cur} / {batch_total} 批。
- 本批解说文案对应全剧序号：第 {line_start}～{line_end} 条（共 {line_count} 条），请完整处理本批全部文案，不得遗漏；对这批文案同样遵守上文「解说文案铁律」与「原文顺序与 id」（仅拆分、不得增删改；本批内 OST=0 仍按该批给定文案从左到右对应 `id` 递增顺序）。
- 本批时间轴窗口为 {win_start_fmt} - {win_end_fmt}（约 {win_start_sec:.1f}s～{win_end_sec:.1f}s），请主要从下方「全片镜头列表」中落在该时间范围内的镜头选取画面；允许少量超出以衔接叙事。
- 仍须遵守「先定本批爆点骨架，再撰写本批解说脚本」：若本批提示中含 `<viral_shots_preextract>`，则以其中预提取结果为爆点骨架；否则在本批时间窗口内自行识别爆点。爆点分析不落盘，仅体现在本批 items 的时间轴与 OST 取舍上。
- 输出的 items **仅包含本批**解说内容，id 从 1 起连续编号。
"""

ORIGINAL_INTERLEAVE_USER_PROMPT_TEMPLATE = """OST=0 为解说（narration 为解说文案）；OST=1 为原声（narration 为「播放原片N」，N从1递增）。
你必须仅输出一个JSON对象，键为'items'。每条时间段长度不能低于1秒。每条必须包含'id','timestamp','narration','OST'。不得输出除JSON以外的任何文字。
一次性输出完整脚本，items 不可为空；将全部解说文案对齐到镜头时间轴。
**解说文案铁律（高于一切其他表述）**：输入的解说文案**在任何情况下**均不得增删改——不得增加字句、不得删减句段、不得改写润色或同义替换、不得纠错或调整语序(严令禁止出现文案顺序错乱问题)；仅允许把**原文**拆成多条 items 的 narration（每条为原文的连续片段，拼接后须与原文逐字一致）。OST=1 条目的「播放原片N」格式不受此限，但不得夹带额外解说。
**原文顺序与 id（必须同时满足）**：将所有 OST=0 的 narration 按 `id` 从小到大依次拼接，必须与给定解说文案原文逐字完全一致。任意两段 OST=0 解说在原文中的先后，必须与它们在 items 里按 `id` 递增时的先后一致——**禁止**为配合爆点、镜头时间或叙事节奏而调换两段 OST=0 原文的先后顺序。
**穿插规则（原片穿插模式）**：每段 OST=0 解说之后必须紧跟一段 OST=1 原声片段（narration 为「播放原片N」，N从1依次递增）。即输出格式为：解说1 → 播放原片1 → 解说2 → 播放原片2 → ... 严禁连续两段 OST=0 或连续两段 OST=1。`timestamp` 与爆点骨架只决定每段落在哪一段时间。
你必须保证每条'narration'的配音时长与对应timestamp镜头时长匹配。按自然语速估算：中文约3-4字/秒（例如10个字约2.5-3.5秒），英文约2-3词/秒。若文本预计配音时长明显短于或长于镜头时长，必须改变镜头时长，不可以修改解说文案。每条预计配音时长与镜头时长误差尽量控制在±0.5秒内。
以下为必须严格使用的解说文案文本：所有 OST=0 条目的'narration'必须仅为该文案的拆分结果；不得编造或新增任何未在原文出现的字句；上文「解说文案铁律」永久适用。

## 输出格式示例
请严格按照以下JSON格式输出，绝不添加任何其他文字、说明或代码块标记：
{{
  "items": [
    {{
      "id": 1,
      "timestamp": "00:00:0x,000-00:00:0x,x00",
      "narration": "……",
      "OST": 0
    }},
    {{
      "id": 2,
      "timestamp": "00:00:xx,x00-00:00:xx,000",
      "narration": "播放原片1",
      "OST": 1
    }},
    {{
      "id": 3,
      "timestamp": "00:00:xx,000-00:00:xx,000",
      "narration": "xxx",
      "OST": 0
    }},
    {{
      "id": 4,
      "timestamp": "00:00:xx,x00-00:00:xx,000",
      "narration": "播放原片2",
      "OST": 1
    }}
  ]
}}

# 解说脚本生成任务（视觉推理）

## 工作流程（必须遵守）
- **第一步（爆点先行）**：
  - **若下方提示词中出现 `<viral_shots_preextract>`**：该块为上游模型基于本批镜头列表预提取的「爆款/爆点镜头」清单。你必须以它为**首要骨架**安排本批节奏与 OST 取舍；再与「全片镜头列表」「检索候选摘要」交叉校验——仅当镜头描述或时间戳明显矛盾时，才允许在**同一叙事意图**下微调时间区间或改用相邻镜头合并区间，不得凭空新增与列表无关的爆点。
  - **若未出现 `<viral_shots_preextract>`**：在编排任何解说条目之前，须先通读镜头信息（含 vision、字幕、时间戳）与检索候选，自行在影片中识别并锁定「爆点镜头」——包括但不限于：情绪高潮、剧情反转/揭示、名场面或爽点、强冲突/对峙、高光动作、关键对白或声音驱动的戏剧性瞬间；为每个爆点明确对应的时间戳区间（可合并相邻镜头），作为后续节奏与 OST 取舍的骨架。
- **第二步（撰写脚本）**：在已建立的爆点时间轴框架下，将解说文案按**原文从左到右顺序**拆成 OST=0 条目并对齐到具体镜头时间段，生成下方 JSON（`id` 递增时所有 OST=0 的 narration 依次拼接即原文，见上文「原文顺序与 id」）；每条 OST=0 后紧跟 OST=1。输出中仅包含 items，无需另写爆点清单；`timestamp` 与 OST 取舍须体现「先定爆点、再铺解说」，但**不得**违反 OST=0 的原文先后顺序。

## 任务目标
结合镜头（scene）时间轴将解说文案对齐到对应时间段；视频时间轴上可跳过无关片段，但**输入解说文案须全部使用且无遗漏**（仅拆分，见上文「解说文案铁律」）；**优先围绕已确定的爆点镜头组织叙事节奏**（有 `<viral_shots_preextract>` 时以其为锚，无则依第一步自识别结果），避免平铺直叙忽略高潮。

## 输入说明
1. 解说文案：完整叙述文本，必须整体使用并仅作拆分（不得增删改，见「解说文案铁律」）。
2. 镜头信息：带精确时间戳的全片镜头列表，含字幕（如有）与画面理解（vision）。
3. 检索候选：文案与镜头的检索匹配结果，每条文案仅 Top1 候选，优先参考。
4. （可选）**爆款预提取**：若存在 `<viral_shots_preextract>`，须优先采纳其 shot_id 与时间戳作为爆点锚点，并与第 2、3 项对照校验后再写 items。

## 任务要求
- 按时间顺序抽取镜头（时间戳可大幅跳跃），且须覆盖完整解说文案（仅拆分、不省略）；OST=0 解说在 items 中的先后仍须严格等于原文阅读顺序（见「原文顺序与 id」），不可因镜头跳跃而打乱文案顺序。
- 无字幕镜头：依据 vision 判断剧情/动作/情绪以确定解说拆分位置。
- 有字幕镜头：可结合字幕与 vision 对齐解说。
- 时间戳格式：HH:MM:SS,mmm-HH:MM:SS,mmm。
- 在关键情绪爆发点、重要对白、爽点瞬间保留原声。

## 核心规则
优先使用原声（OST=1）的情况：
- 关键剧情对白（反转/伏笔/揭示）
- 强情绪爆发（愤怒/崩溃/告白）
- 经典台词（有传播力）
- 声音驱动场景（枪声/爆炸/哭声等）

必须使用解说（OST=0）的情况：
- 信息压缩（剪辑时间跳跃；**不得**用「总结式改写」代替原文，解说词仍须为原文拆分）
- 背景补充（人物关系/设定等仍须来自原文表述）
- 无有效对白的片段
- 过渡镜头

## 重要约束
- 必须严格遵循解说-原片-解说-原片的交替节奏；节奏调整仅通过 timestamp 与 OST 切换实现，**不得**以删改解说文案为代价。
- 非常重要的约束，不允许长时间的纯原声，绝对不允许

{dynamic_sections}
"""
def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return default


def _format_ts(seconds: float) -> str:
    total_ms = int(round(max(0.0, seconds) * 1000.0))
    h = total_ms // 3600000
    m = (total_ms % 3600000) // 60000
    s = (total_ms % 60000) // 1000
    ms = total_ms % 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _truncate_text(text: str, max_len: int) -> str:
    text = _normalize_spaces(text)
    if len(text) <= max_len:
        return text
    if max_len <= 1:
        return text[:max_len]
    return text[: max_len - 1] + "…"


def _pick_scene_text(shot: Dict[str, Any]) -> str:
    visual = shot.get("visual") or {}
    brief = _normalize_spaces(visual.get("brief") or "")
    sub = _normalize_spaces(shot.get("subtitle_full_text") or "")
    parts: List[str] = []
    if brief:
        parts.append(brief)
    if sub:
        parts.append(f"字幕：{sub}")
    return _normalize_spaces(" | ".join(parts))


def _parse_summary_subtitle_from_blob(blob: str) -> Tuple[str, str]:
    """从检索 match 的 summary 长文本中拆出「摘要」「字幕」段落。"""
    blob = (blob or "").strip()
    if not blob:
        return "", ""
    m_sub = re.search(r"(?:^|\r?\n)\s*字幕：\s*(.+)$", blob, re.MULTILINE | re.DOTALL)
    sub_from_blob = _normalize_spaces(m_sub.group(1)) if m_sub else ""
    m_abs = re.search(
        r"(?:^|\r?\n)\s*摘要：\s*(.+?)(?=\r?\n\s*字幕：|\Z)", blob, re.MULTILINE | re.DOTALL
    )
    abstract = _normalize_spaces(m_abs.group(1)) if m_abs else ""
    if not abstract and not sub_from_blob:
        abstract = _normalize_spaces(re.sub(r"^详细：\s*", "", blob, flags=re.MULTILINE))
        return abstract, ""
    if not abstract and sub_from_blob:
        before = re.split(r"\r?\n\s*字幕：", blob, maxsplit=1)[0]
        abstract = _normalize_spaces(re.sub(r"^详细：\s*", "", before.strip()))
    return abstract, sub_from_blob


def _pick_retrieval_candidate_scene_text(match: Dict[str, Any]) -> str:
    """检索候选展示用：优先 brief+字幕；为空则用 summary 中的摘要/字幕。"""
    primary = _pick_scene_text(match)
    if primary:
        return primary
    sub = _normalize_spaces(match.get("subtitle_full_text") or "")
    abstract, sub_blob = _parse_summary_subtitle_from_blob(match.get("summary") or "")
    sub = sub or sub_blob
    parts: List[str] = []
    if abstract:
        parts.append(f"摘要：{abstract}")
    if sub:
        parts.append(f"字幕：{sub}")
    return _normalize_spaces(" | ".join(parts))


def _build_copywriting_outline(results: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for idx, item in enumerate(results, start=1):
        text = _truncate_text(item.get("text", ""), 80)
        lines.append(f"{idx}. {text}")
    return "\n".join(lines)


def _build_retrieval_candidates(results: List[Dict[str, Any]], item_limit: int) -> str:
    lines: List[str] = []
    for item in results[:item_limit]:
        item_index = item.get("item_index")
        lines.append(f"\n - 文案{item_index}: {_truncate_text(item.get('text', ''), 90)}")
        matches = item.get("matches") or []
        if not matches:
            continue
        match = matches[0]
        start = _format_ts(_safe_float(match.get("start")))
        end = _format_ts(_safe_float(match.get("end")))
        score = _safe_float(match.get("final_score", match.get("score", 0.0)))
        reason = _truncate_text(match.get("reason", ""), 72)
        scene = _truncate_text(_pick_retrieval_candidate_scene_text(match), 120)
        lines.append(
            f"  候选1 | shot_id={match.get('shot_id')} | {start}-{end} | score={score:.3f} | {scene} "  # | 匹配原因:{reason}
        )
    return "\n".join(lines)


def _build_timeline_scenes(shots: List[Dict[str, Any]], max_scenes: int, step: int) -> str:
    if not shots:
        return ""
    step = max(1, step)
    sampled = shots[::step]
    if len(sampled) > max_scenes:
        sampled = sampled[:max_scenes]
    lines: List[str] = []
    for shot in sampled:
        start = _format_ts(_safe_float(shot.get("start")))
        end = _format_ts(_safe_float(shot.get("end")))
        scene = _normalize_spaces(_pick_scene_text(shot))
        lines.append(f"\n [{start}-{end}] 镜头shot_id={shot.get('shot_id')} {scene}")
    return "\n".join(lines)


def _extract_relevant_shot_ids(results: List[Dict[str, Any]], candidate_limit: int) -> List[Any]:
    shot_ids: List[Any] = []
    seen = set()
    for item in results:
        matches = item.get("matches") or []
        for match in matches[:candidate_limit]:
            sid = match.get("shot_id")
            if sid in seen:
                continue
            seen.add(sid)
            shot_ids.append(sid)
    return shot_ids


def _build_timeline_samples_for_gap(all_shots: List[Dict[str, Any]], max_scenes: int) -> List[Dict[str, Any]]:
    if not all_shots or max_scenes <= 0:
        return []
    step = max(1, math.ceil(len(all_shots) / max_scenes))
    sampled = all_shots[::step]
    return sampled[:max_scenes]


def _build_global_timeline(
    all_shots: List[Dict[str, Any]],
    results: List[Dict[str, Any]],
    max_scenes: int,
) -> str:
    sorted_shots = sorted(all_shots, key=lambda x: _safe_float(x.get("start")))
    return _build_timeline_scenes(sorted_shots, max_scenes=len(sorted_shots), step=1)


def _compute_copywriting_chunk_ranges(n: int, target_per_chunk: int = 20) -> List[Tuple[int, int]]:
    """按顺序切分文案下标区间 [start, end)，平均每组约 target_per_chunk 条。"""
    if n <= 0:
        return []
    chunk_count = max(1, math.ceil(n / float(target_per_chunk)))
    chunk_size = math.ceil(n / float(chunk_count))
    ranges: List[Tuple[int, int]] = []
    i = 0
    while i < n:
        j = min(i + chunk_size, n)
        ranges.append((i, j))
        i = j
    return ranges


def _count_shots_overlapping_window(
    all_shots: List[Dict[str, Any]],
    w_start: float,
    w_end: float,
) -> int:
    """与半开时间窗 [w_start, w_end) 有重叠的镜头数量（与 _filter_shots_by_time_window 一致）。"""
    n = 0
    for shot in all_shots:
        s = _safe_float(shot.get("start"))
        e = _safe_float(shot.get("end"))
        if e <= w_start or s >= w_end:
            continue
        n += 1
    return n


def _shot_count_for_proportional_line_range(
    all_shots: List[Dict[str, Any]],
    n_lines: int,
    line_a: int,
    line_b: int,
    video_end: float,
) -> int:
    """
    文案下标半开区间 [line_a, line_b) 在 proportional 模式下对应影片时间
    [line_a/n*T, line_b/n*T)，统计该时间窗内与 all_shots 重叠的镜头数。
    """
    ve = max(0.0, video_end)
    if ve <= 0 or n_lines <= 0 or line_a >= line_b:
        return 0
    w0 = (line_a / float(n_lines)) * ve
    w1 = (line_b / float(n_lines)) * ve
    return _count_shots_overlapping_window(all_shots, w0, w1)


def _compute_copywriting_chunk_ranges_balanced_shots(
    n: int,
    target_per_chunk: int,
    video_end: float,
    all_shots: List[Dict[str, Any]],
    min_chunk_lines: int,
) -> List[Tuple[int, int]]:
    """
    在保持顺序的前提下划分 [0,n)，组数与 equal_lines 相同（ceil(n/target)），
    但断点位置通过搜索使得各组在 proportional 时间窗内的镜头重叠数量方差最小（更均匀）。

    旧实现用 DFS 枚举全部切分，在 n、k 稍大时组合数爆炸（如 C(129,6)≈5.7e9）。
    现改为：以 equal_lines 为初值，对相邻断点做 ±1 的局部搜索（爬山），目标与原先一致
    （先最小化镜头数方差，再最小化各组文案条数方差）。
    """
    if n <= 0:
        return []
    k = max(1, math.ceil(n / float(target_per_chunk)))
    if k <= 1:
        return [(0, n)]

    ve = max(0.0, video_end)
    min_c = max(1, min_chunk_lines)
    if n < k * min_c:
        return _compute_copywriting_chunk_ranges(n, target_per_chunk)

    cache: Dict[Tuple[int, int], int] = {}

    def shots_for(a: int, b: int) -> int:
        key = (a, b)
        if key in cache:
            return cache[key]
        c = _shot_count_for_proportional_line_range(all_shots, n, a, b, ve)
        cache[key] = c
        return c

    def shot_var(counts: List[int]) -> float:
        if not counts:
            return 0.0
        m = sum(counts) / len(counts)
        return sum((c - m) ** 2 for c in counts)

    def line_var(ranges: List[Tuple[int, int]]) -> float:
        lens = [b - a for a, b in ranges]
        if not lens:
            return 0.0
        m = sum(lens) / len(lens)
        return sum((x - m) ** 2 for x in lens)

    def _ranges_from_boundaries(boundaries: List[int]) -> List[Tuple[int, int]]:
        return [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    def _score_boundaries(boundaries: List[int]) -> Tuple[float, float]:
        ranges = _ranges_from_boundaries(boundaries)
        counts = [shots_for(a, b) for a, b in ranges]
        return shot_var(counts), line_var(ranges)

    def _is_better_score(sv: float, lv: float, sv2: float, lv2: float) -> bool:
        if sv < sv2 - 1e-6:
            return True
        if abs(sv - sv2) <= 1e-6 and lv < lv2 - 1e-6:
            return True
        return False

    eq_ranges = _compute_copywriting_chunk_ranges(n, target_per_chunk)
    boundaries = [0]
    for _a, b in eq_ranges:
        boundaries.append(b)
    if boundaries[-1] != n or len(boundaries) != k + 1:
        return eq_ranges

    best_sv, best_lv = _score_boundaries(boundaries)
    max_iters = max(64, k * n * 4)
    it = 0
    while it < max_iters:
        it += 1
        best_nb: Optional[List[int]] = None
        best_nsv, best_nlv = best_sv, best_lv
        for i in range(1, k):
            for delta in (-1, 1):
                nb = boundaries[:]
                nb[i] += delta
                if nb[i] <= nb[i - 1] or nb[i] >= nb[i + 1]:
                    continue
                if nb[i] - nb[i - 1] < min_c or nb[i + 1] - nb[i] < min_c:
                    continue
                nsv, nlv = _score_boundaries(nb)
                if not _is_better_score(nsv, nlv, best_sv, best_lv):
                    continue
                if best_nb is None or _is_better_score(nsv, nlv, best_nsv, best_nlv):
                    best_nb = nb
                    best_nsv, best_nlv = nsv, nlv
        if best_nb is None:
            break
        boundaries = best_nb
        best_sv, best_lv = best_nsv, best_nlv

    return _ranges_from_boundaries(boundaries)


def _video_end_seconds(all_shots: List[Dict[str, Any]]) -> float:
    if not all_shots:
        return 0.0
    return max(_safe_float(s.get("end")) for s in all_shots)


def _top1_intervals_from_chunk(chunk_results: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    out: List[Tuple[float, float]] = []
    for item in chunk_results:
        matches = item.get("matches") or []
        if not matches:
            continue
        m = matches[0]
        s = _safe_float(m.get("start"))
        e = _safe_float(m.get("end"))
        if e > s:
            out.append((s, e))
    return out


def _median_float(values: List[float]) -> float:
    if not values:
        return 0.0
    xs = sorted(values)
    m = len(xs) // 2
    if len(xs) % 2 == 1:
        return float(xs[m])
    return (xs[m - 1] + xs[m]) / 2.0


def _interval_overlaps_window(s: float, e: float, w_start: float, w_end: float) -> bool:
    return not (e <= w_start or s >= w_end)


def _top1_entries_line_order(
    chunk_results: List[Dict[str, Any]],
    global_start_idx: int,
) -> List[Dict[str, Any]]:
    """每条文案一行，按文案顺序附带 top1 镜头时间与 shot_id（用于单调时间线过滤）。"""
    out: List[Dict[str, Any]] = []
    for i, item in enumerate(chunk_results):
        matches = item.get("matches") or []
        if not matches:
            continue
        m = matches[0]
        s = _safe_float(m.get("start"))
        e = _safe_float(m.get("end"))
        if e <= s:
            continue
        out.append(
            {
                "line_1based": global_start_idx + i + 1,
                "start": s,
                "end": e,
                "mid": (s + e) * 0.5,
                "shot_id": m.get("shot_id"),
            }
        )
    return out


def _monotonic_top1_by_mid_gap_filter(
    entries: List[Dict[str, Any]],
    w_start: float,
    w_end: float,
    gap_median_mult: float,
    gap_min_seconds: float,
) -> Tuple[List[Dict[str, Any]], float, int]:
    """
    在 [w_start, w_end] 内与 top1 区间有交集的条目中，按文案顺序构造非递减时间线（以区间中点为刻度）：
    - 若中点相对上一保留点回跳，丢弃该条；
    - 若向前跨度大于阈值，丢弃该条（剔除异常大跳跃）。
    阈值：本组内相邻正向跨度的中位数 × gap_median_mult，且不低于 gap_min_seconds（无正向跨度时用窗口长度比例兜底）。
    """
    ov = [
        e
        for e in entries
        if _interval_overlaps_window(e["start"], e["end"], w_start, w_end)
    ]
    overlap_n = len(ov)
    win_span = max(w_end - w_start, 0.0)
    fallback_thr = max(gap_min_seconds, win_span * 0.05) if win_span > 0 else gap_min_seconds

    if len(ov) <= 1:
        return ov, fallback_thr, overlap_n

    mids = [e["mid"] for e in ov]
    pos_gaps = [mids[i] - mids[i - 1] for i in range(1, len(mids)) if mids[i] >= mids[i - 1]]
    if pos_gaps:
        thr = max(gap_min_seconds, _median_float(pos_gaps) * float(gap_median_mult))
    else:
        thr = fallback_thr

    kept: List[Dict[str, Any]] = []
    last: Optional[float] = None
    for e in ov:
        t = e["mid"]
        if last is None:
            kept.append(e)
            last = t
            continue
        if t < last:
            continue
        if t - last > thr:
            continue
        kept.append(e)
        last = t
    return kept, thr, overlap_n


def _compute_chunk_time_windows(
    results: List[Dict[str, Any]],
    chunk_ranges: List[Tuple[int, int]],
    overlap_ratio: float,
    video_end: float,
    window_mode: str = "proportional",
    gap_median_mult: float = 4.0,
    gap_min_seconds: float = 30.0,
    top1_cluster_gap_min_seconds: float = 60.0,
    top1_cluster_gap_median_multiplier: float = 4.0,
    top1_main_cluster_ratio: float = 0.7,
    top1_window_pad_ratio: float = 0.1,
    top1_window_pad_min_seconds: float = 30.0,
    top1_window_pad_max_seconds: float = 180.0,
) -> List[Dict[str, Any]]:
    """
    估计本批用于挑选镜头的影片时间窗口。

    - proportional（默认）：按文案在全剧中的序号占比映射到影片时长占比。
      文案切片为半开区间 [a,b)（0-based 下标），全剧共 N 条时，影片窗口约为
      [a/N * T, b/N * T]（T 为片长秒数）。再对本组 top1 构造单调递增时间线，剔除过大跨度。

    - legacy_top1：沿用旧逻辑——由本组 top1 时间范围与组间 overlap 回退共同决定窗口。
    """
    metas: List[Dict[str, Any]] = []
    prev_window_end = 0.0
    ve = max(0.0, video_end)
    n = len(results)
    mode = (window_mode or "proportional").strip().lower()
    top1_config = Top1WindowConfig(
        cluster_gap_min_seconds=top1_cluster_gap_min_seconds,
        cluster_gap_median_multiplier=top1_cluster_gap_median_multiplier,
        main_cluster_ratio=top1_main_cluster_ratio,
        pad_ratio=top1_window_pad_ratio,
        pad_min_seconds=top1_window_pad_min_seconds,
        pad_max_seconds=top1_window_pad_max_seconds,
    )

    for ci, (a, b) in enumerate(chunk_ranges):
        chunk_results = results[a:b]
        intervals = _top1_intervals_from_chunk(chunk_results)
        if intervals:
            raw_min = min(x[0] for x in intervals)
            raw_max = max(x[1] for x in intervals)
            span = max(raw_max - raw_min, 1.0)
        else:
            raw_min = 0.0
            raw_max = ve if ve > 0 else 600.0
            span = max(120.0, 1.0)

        ratio_a = (a / float(n)) if n > 0 else 0.0
        ratio_b = (b / float(n)) if n > 0 else 1.0

        if mode == "top1_span":
            top1_window = compute_top1_span_window(chunk_results, ve, top1_config)
            if top1_window is not None:
                w_start = top1_window.window_start
                w_end = top1_window.window_end
                prev_window_end = w_end

                metas.append(
                    {
                        "chunk_index": ci,
                        "slice": (a, b),
                        "line_start_1based": a + 1,
                        "line_end_1based": b,
                        "line_count": b - a,
                        "window_start": w_start,
                        "window_end": w_end,
                        "raw_min": top1_window.raw_min,
                        "raw_max": top1_window.raw_max,
                        "top1_span": top1_window.top1_span,
                        "window_mode": mode,
                        "copy_film_ratio_start": None,
                        "copy_film_ratio_end": None,
                        "timeline_gap_threshold": top1_window.gap_threshold,
                        "monotonic_top1_overlap": top1_window.anchor_count,
                        "monotonic_top1_kept": top1_window.selected_anchor_count,
                        "top1_window_pad_seconds": top1_window.pad_seconds,
                        "top1_anchor_count": top1_window.anchor_count,
                        "top1_selected_anchor_count": top1_window.selected_anchor_count,
                        "top1_cluster_count": top1_window.cluster_count,
                        "top1_selected_cluster_ratio": top1_window.selected_cluster_ratio,
                    }
                )
                continue

        if mode == "legacy_top1":
            if ci == 0:
                w_start = 0.0
                if intervals:
                    w_end = max(raw_max, w_start + 1.0)
                else:
                    w_end = min(ve if ve > 0 else raw_max, max(raw_max, 600.0))
                    w_end = max(w_end, w_start + 60.0)
            else:
                if intervals:
                    w_start = max(0.0, prev_window_end - overlap_ratio * span)
                    w_end = max(raw_max, w_start + 1.0)
                else:
                    w_start = max(0.0, prev_window_end - overlap_ratio * span)
                    w_end = min(ve if ve > 0 else w_start + 600.0, max(w_start + 120.0, prev_window_end + 180.0))

            if ve > 0:
                w_end = min(w_end, ve)
            w_end = max(w_end, w_start + 1.0)
            prev_window_end = w_end

            metas.append(
                {
                    "chunk_index": ci,
                    "slice": (a, b),
                    "line_start_1based": a + 1,
                    "line_end_1based": b,
                    "line_count": b - a,
                    "window_start": w_start,
                    "window_end": w_end,
                    "raw_min": raw_min if intervals else w_start,
                    "raw_max": raw_max if intervals else w_end,
                    "top1_span": span,
                    "window_mode": mode,
                    "copy_film_ratio_start": None,
                    "copy_film_ratio_end": None,
                    "timeline_gap_threshold": None,
                    "monotonic_top1_overlap": None,
                    "monotonic_top1_kept": None,
                }
            )
            continue

        effective_window_mode = (
            "top1_span_fallback_proportional" if mode == "top1_span" else mode
        )

        # proportional：文案占比 ↔ 影片时间占比
        if n > 0 and ve > 0:
            w_start = ratio_a * ve
            w_end = ratio_b * ve
        elif intervals and ve <= 0:
            w_start = raw_min
            w_end = max(raw_max, raw_min + 1.0)
        else:
            w_start = 0.0
            w_end = max(raw_max, w_start + 60.0)

        if ve > 0:
            w_end = min(w_end, ve)
            w_start = max(0.0, min(w_start, w_end - 1.0))
        w_end = max(w_end, w_start + 1.0)
        prev_window_end = w_end

        entries = _top1_entries_line_order(chunk_results, a)
        _kept_mono, gap_thr, overlap_n = _monotonic_top1_by_mid_gap_filter(
            entries,
            w_start,
            w_end,
            gap_median_mult,
            gap_min_seconds,
        )

        metas.append(
            {
                "chunk_index": ci,
                "slice": (a, b),
                "line_start_1based": a + 1,
                "line_end_1based": b,
                "line_count": b - a,
                "window_start": w_start,
                "window_end": w_end,
                "raw_min": raw_min if intervals else w_start,
                "raw_max": raw_max if intervals else w_end,
                "top1_span": span,
                "window_mode": effective_window_mode,
                "copy_film_ratio_start": ratio_a,
                "copy_film_ratio_end": ratio_b,
                "timeline_gap_threshold": gap_thr,
                "monotonic_top1_overlap": overlap_n,
                "monotonic_top1_kept": len(_kept_mono),
            }
        )
    return metas


def _filter_shots_by_time_window(
    all_shots: List[Dict[str, Any]],
    w_start: float,
    w_end: float,
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for shot in all_shots:
        s = _safe_float(shot.get("start"))
        e = _safe_float(shot.get("end"))
        if e <= w_start or s >= w_end:
            continue
        out.append(shot)
    return sorted(out, key=lambda x: _safe_float(x.get("start")))


def _shot_id_to_int(shot: Dict[str, Any]) -> Optional[int]:
    sid = shot.get("shot_id")
    if sid is None:
        return None
    try:
        return int(sid)
    except (TypeError, ValueError):
        return None


def _expand_timeline_shots_by_shot_id_redundancy(
    all_shots: List[Dict[str, Any]],
    window_filtered: List[Dict[str, Any]],
    redundancy_ratio: float,
) -> List[Dict[str, Any]]:
    """
    在时间窗口筛出的镜头基础上：
    - 下界：在窗口内 min～max shot_id 的跨度上向前推 5%（并裁剪到全片已有 id），例如 30～330 → 约 15～330。
    - 上界：按本批镜头数量 N 将 shot_id 上界扩展约 ceil(N * ratio)（并裁剪到全片已有 id），
      例如窗口内 shot_id 约 1～304、N=304、ratio=0.1 时上界约 334。
    """
    if redundancy_ratio <= 0 or not window_filtered:
        return window_filtered
    ids = [_shot_id_to_int(s) for s in window_filtered]
    ids = [x for x in ids if x is not None]
    if not ids:
        return window_filtered
    min_sid = min(ids)
    max_sid = max(ids)
    n = len(window_filtered)
    extra = max(0, math.ceil(n * float(redundancy_ratio)))
    if extra == 0:
        return window_filtered

    gids = [_shot_id_to_int(s) for s in all_shots]
    gids = [x for x in gids if x is not None]
    if not gids:
        return window_filtered
    g_min, g_max = min(gids), max(gids)

    span_sid = max(max_sid - min_sid, 0)
    pad_low = math.ceil(span_sid * 0.05) if span_sid > 0 else 0
    target_min = max(g_min, min_sid - pad_low)
    target_max = min(g_max, max_sid + extra)

    out: List[Dict[str, Any]] = []
    for shot in all_shots:
        x = _shot_id_to_int(shot)
        if x is None:
            continue
        if target_min <= x <= target_max:
            out.append(shot)
    return sorted(out, key=lambda x: _safe_float(x.get("start")))


def _validate_timestamp(timestamp: str) -> bool:
    return bool(re.match(r"^\d{2}:\d{2}:\d{2},\d{3}-\d{2}:\d{2}:\d{2},\d{3}$", timestamp or ""))


def _parse_timestamp_range(timestamp: str) -> Tuple[Optional[float], Optional[float]]:
    if not _validate_timestamp(timestamp):
        return None, None
    start_str, end_str = timestamp.split("-", 1)
    return _parse_single_ts(start_str), _parse_single_ts(end_str)


def _parse_single_ts(ts: str) -> float:
    hh, mm, rest = ts.split(":")
    ss, ms = rest.split(",")
    return int(hh) * 3600 + int(mm) * 60 + int(ss) + int(ms) / 1000.0


# 与 prompt「每条时间段长度不能低于1秒」一致；模型偶发略短时将结束时间顺延至满 1 秒
MIN_SEGMENT_DURATION_SECONDS = 1.0


def _post_check_items(items: List[Dict[str, Any]]) -> None:
    if not items:
        raise ValueError("模型输出 items 为空")
    for i, item in enumerate(items, start=1):
        if int(item.get("id", 0)) != i:
            item["id"] = i
        timestamp = item.get("timestamp", "")
        if not _validate_timestamp(timestamp):
            raise ValueError(f"模型输出 timestamp 格式不合法: {timestamp}")
        start, end = _parse_timestamp_range(timestamp)
        if start is None or end is None:
            raise ValueError(f"模型输出 timestamp 无法解析: {timestamp}")
        if end <= start:
            raise ValueError(f"模型输出片段时间顺序不合法: {timestamp}")
        if end - start < MIN_SEGMENT_DURATION_SECONDS:
            end = start + MIN_SEGMENT_DURATION_SECONDS
            item["timestamp"] = f"{_format_ts(start)}-{_format_ts(end)}"
        narration = _normalize_spaces(item.get("narration", ""))
        if not narration:
            raise ValueError("模型输出 narration 不能为空")
        item["narration"] = narration
        if item.get("OST") not in (0, 1):
            raise ValueError("模型输出 OST 只能为 0 或 1")
        if item.get("OST") == 1 and not narration.startswith("播放原片"):
            raise ValueError("OST=1 时 narration 必须为 播放原片X 格式")

