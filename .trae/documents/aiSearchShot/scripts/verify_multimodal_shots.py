#!/usr/bin/env python3
"""
验证 step2 输出的 *_shots_multimodal.json 是否为每个镜头生成了完整的多模态分析数据。

检查项：
- shots 数量是否与 total_shots（或 total_segments_semantic）一致
- shot_id 是否从 1 连续覆盖到 N（无缺失、无重复）
- 每条成功记录是否包含 frame / subtitle / visual / summary / embedding，且 visual 含 schema 要求字段
- 统计含 error 字段或字段不完整的镜头

用法：
  python scripts/verify_multimodal_shots.py
  python scripts/verify_multimodal_shots.py path/to/video_1_shots_multimodal.json
  python scripts/verify_multimodal_shots.py output/video_1_shots_multimodal.json --max-list 50
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

VISUAL_REQUIRED = ("desc", "objects", "action", "scene", "emotion")


def _expected_shot_count(root: Dict[str, Any]) -> Optional[int]:
    for key in ("total_shots", "total_segments_semantic", "total_shots_raw"):
        v = root.get(key)
        if isinstance(v, int) and v > 0:
            return v
    return None


def _check_one_shot(shot: Dict[str, Any]) -> Tuple[bool, List[str]]:
    reasons: List[str] = []
    if shot.get("error"):
        return False, ["error"]

    # 兼容两种字段：
    # - 老格式：frame: "path/to.jpg"
    # - 新格式：frames: ["path/to_q1.jpg", "path/to_q3.jpg", ...]
    frame = shot.get("frame")
    frames = shot.get("frames")
    has_one_frame = isinstance(frame, str) and bool(frame.strip())
    has_frames_list = (
        isinstance(frames, list)
        and len(frames) > 0
        and all(isinstance(p, str) and p.strip() for p in frames)
    )
    if not (has_one_frame or has_frames_list):
        reasons.append("frame/frames")

    sub = shot.get("subtitle")
    if not isinstance(sub, dict):
        reasons.append("subtitle")
    else:
        if "full_text" not in sub or "segments" not in sub:
            reasons.append("subtitle_shape")

    vis = shot.get("visual")
    if not isinstance(vis, dict):
        reasons.append("visual")
    else:
        for k in VISUAL_REQUIRED:
            if k not in vis:
                reasons.append(f"visual.{k}")

    summary = shot.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        reasons.append("summary")

    emb = shot.get("embedding")
    if not isinstance(emb, list) or len(emb) == 0:
        reasons.append("embedding")

    ok = len(reasons) == 0
    return ok, reasons


def main() -> int:
    ap = argparse.ArgumentParser(description="验证 multimodal shots JSON 完整性")
    ap.add_argument(
        "json_path",
        nargs="?",
        default=None,
        help="JSON 路径，默认：项目下 output/video_1_shots_multimodal.json 或 config 中的 result_json",
    )
    ap.add_argument("--max-list", type=int, default=30, help="最多列出多少条不完整镜头 ID（0 表示不列出）")
    args = ap.parse_args()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    json_path = args.json_path
    if not json_path:
        cfg_path = os.path.join(project_root, "config.json")
        if os.path.isfile(cfg_path):
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            json_path = (cfg.get("output") or {}).get("result_json") or "output/video_1_shots_multimodal.json"
        else:
            json_path = "output/video_1_shots_multimodal.json"
        if not os.path.isabs(json_path):
            json_path = os.path.join(project_root, json_path)

    if not os.path.isfile(json_path):
        print(f"文件不存在: {json_path}", file=sys.stderr)
        return 2

    print(f"加载: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        root = json.load(f)

    shots = root.get("shots")
    if not isinstance(shots, list):
        print('根对象缺少 "shots" 数组或类型错误', file=sys.stderr)
        return 1

    expected_n = _expected_shot_count(root)
    actual_n = len(shots)

    print(f"shots 条数: {actual_n}")
    if expected_n is not None:
        print(f"元数据期望镜头数 (total_shots 等): {expected_n}")
        if actual_n != expected_n:
            print(f"  ⚠ 条数不一致：缺 {expected_n - actual_n} 条" if actual_n < expected_n else f"  ⚠ 条数不一致：多 {actual_n - expected_n} 条")

    ids: List[Optional[int]] = []
    dup: List[int] = []
    seen = set()
    for s in shots:
        sid = s.get("shot_id") if isinstance(s, dict) else None
        if isinstance(sid, int):
            ids.append(sid)
            if sid in seen:
                dup.append(sid)
            seen.add(sid)
        else:
            ids.append(None)

    missing_ids: List[int] = []
    extra_ids: List[int] = []
    if expected_n is not None:
        want = set(range(1, expected_n + 1))
        have = {i for i in ids if isinstance(i, int)}
        missing_ids = sorted(want - have)
        extra_ids = sorted(have - want)
        if missing_ids:
            print(f"缺失 shot_id 数量: {len(missing_ids)}")
            if args.max_list > 0:
                preview = missing_ids[: args.max_list]
                print(f"  示例（前 {len(preview)} 个）: {preview}")
        if extra_ids:
            print(f"多余/越界 shot_id 数量: {len(extra_ids)}")
            if args.max_list > 0:
                print(f"  示例: {extra_ids[: args.max_list]}")
        if dup:
            print(f"重复 shot_id 数量: {len(dup)}（示例: {dup[:10]}）")

    incomplete: List[Tuple[Optional[int], List[str]]] = []
    with_error = 0
    for s in shots:
        if not isinstance(s, dict):
            incomplete.append((None, ["not_a_dict"]))
            continue
        sid = s.get("shot_id")
        ok, reasons = _check_one_shot(s)
        if s.get("error"):
            with_error += 1
        if not ok:
            incomplete.append((sid if isinstance(sid, int) else None, reasons))

    print(f"含 error 字段的镜头数: {with_error}")
    print(f"字段不完整或失败的镜头数: {len(incomplete)}")

    if args.max_list > 0 and incomplete:
        print("不完整镜头（shot_id -> 原因）:")
        for i, (sid, reasons) in enumerate(incomplete[: args.max_list]):
            print(f"  {sid}: {', '.join(reasons)}")
        if len(incomplete) > args.max_list:
            print(f"  ... 另有 {len(incomplete) - args.max_list} 条未显示")

    if expected_n is None:
        all_good = len(dup) == 0 and len(incomplete) == 0
    else:
        all_good = (
            actual_n == expected_n
            and len(missing_ids) == 0
            and len(extra_ids) == 0
            and len(dup) == 0
            and len(incomplete) == 0
        )

    if all_good:
        print("结论: 每个镜头均已生成完整多模态分析数据。")
        return 0
    print("结论: 未完全生成，请根据上述缺失/不完整项排查 step2 日志或重跑。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
