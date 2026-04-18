"""与 script_generation.copywriting_builder._remove_leading_quoted_subtitle_lines 一致的剪裁逻辑（独立副本，避免反向依赖）。"""

from __future__ import annotations

import re
from typing import List


def remove_leading_quoted_subtitle_lines(text: str) -> str:
    lines = text.splitlines()
    out: List[str] = []

    for ln in lines:
        s = ln.strip()
        if not s:
            out.append("")
            continue

        opening = s[0]
        closing = {"“": "”", "「": "」", '"': '"', "『": "』"}.get(opening)
        if closing:
            idx = s.find(closing, 1)
            if idx != -1:
                after = s[idx + 1 :].lstrip(" \t-—:：，,。.!！?？\"”'」』")
                if after:
                    out.append(after)
                continue

        if re.fullmatch(r"[“「『\"].{1,120}[”」』\"]", s):
            continue

        out.append(s)

    merged = "\n".join(out)
    merged = re.sub(r"\n{3,}", "\n\n", merged).strip()
    return merged
