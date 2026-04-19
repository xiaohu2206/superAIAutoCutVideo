#!/usr/bin/env python3
"""
将单张图片按 step2 与 analyze_shot_frame 相同的规则做长边缩放 + JPEG 重编码，输出文件便于与原图对比。

与 utils.aiModels.openai_compatible_base.OpenAICompatibleClientBase._image_path_to_vl_data_url 一致。

用法：
  python scripts/preview_vl_frame_resize.py E:\\learn\\AIShotSearch\\output\\frames\\shot_012_q3.jpg
  python scripts/preview_vl_frame_resize.py path/to.jpg --max-long-edge 1024 --jpeg-quality 80
  python scripts/preview_vl_frame_resize.py path/to.jpg --out E:\\tmp\\preview.jpg
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from typing import Tuple

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from utils.aiModels.openai_compatible_base import OpenAICompatibleClientBase  # noqa: E402


def _read_json(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _data_url_to_bytes(data_url: str) -> Tuple[bytes, str]:
    if not data_url.startswith("data:") or "," not in data_url:
        raise ValueError("非 data URL")
    head, b64 = data_url.split(",", 1)
    b64 = b64.strip()
    raw = base64.b64decode(b64)
    if "image/png" in head:
        return raw, ".png"
    if "image/webp" in head:
        return raw, ".webp"
    return raw, ".jpg"


def main() -> int:
    p = argparse.ArgumentParser(description="预览 VL 送模前的帧缩放/JPEG 效果")
    p.add_argument(
        "image_path",
        help="输入图片路径",
    )
    p.add_argument(
        "--config",
        default=os.path.join(PROJECT_ROOT, "config.json"),
        help="读取 step2_multimodal_features.vl_image_max_long_edge / vl_jpeg_quality（可被命令行覆盖）",
    )
    p.add_argument("--max-long-edge", type=int, default=None, help="长边上限，0 表示不缩放（直读原文件进 base64）")
    p.add_argument("--jpeg-quality", type=int, default=None, help="JPEG 质量 1–100（仅缩放分支有效）")
    p.add_argument(
        "--out",
        default=None,
        help="输出路径，默认在输入同目录生成 *_vl_preview.jpg",
    )
    args = p.parse_args()

    image_path = os.path.abspath(args.image_path)
    if not os.path.isfile(image_path):
        print(f"文件不存在: {image_path}", file=sys.stderr)
        return 1

    max_edge = args.max_long_edge
    jpeg_q = args.jpeg_quality
    if max_edge is None or jpeg_q is None:
        cfg_path = os.path.abspath(args.config)
        if os.path.isfile(cfg_path):
            cfg = _read_json(cfg_path)
            step2 = cfg.get("step2_multimodal_features") or {}
            if max_edge is None:
                max_edge = int(step2.get("vl_image_max_long_edge", 1280) or 0)
            if jpeg_q is None:
                jpeg_q = int(step2.get("vl_jpeg_quality", 85) or 85)
        else:
            if max_edge is None:
                max_edge = 1280
            if jpeg_q is None:
                jpeg_q = 85

    data_url = OpenAICompatibleClientBase._image_path_to_vl_data_url(
        image_path,
        max_long_edge=max_edge,
        jpeg_quality=jpeg_q,
    )
    out_bytes, out_ext = _data_url_to_bytes(data_url)

    if args.out:
        out_path = os.path.abspath(args.out)
    else:
        root, _ = os.path.splitext(image_path)
        out_path = f"{root}_vl_preview{out_ext}"

    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with open(out_path, "wb") as f:
        f.write(out_bytes)

    in_size = os.path.getsize(image_path)
    out_size = len(out_bytes)
    try:
        import cv2
        import numpy as np

        im = cv2.imdecode(np.frombuffer(out_bytes, dtype=np.uint8), cv2.IMREAD_COLOR)
        oh, ow = (im.shape[0], im.shape[1]) if im is not None else (0, 0)
    except Exception:
        ow = oh = 0

    print(f"输入: {image_path}")
    print(f"  文件大小: {in_size} bytes")
    print(f"参数: vl_image_max_long_edge={max_edge} vl_jpeg_quality={jpeg_q}")
    print(f"输出: {out_path}")
    print(f"  文件大小: {out_size} bytes ({100.0 * out_size / max(in_size, 1):.1f}% of 原文件)")
    if ow and oh:
        print(f"  解码尺寸: {ow}x{oh}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
