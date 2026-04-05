# -*- coding: utf-8 -*-
"""与前端一致的镜头视觉完成判定（vision_status 为主）。"""

from typing import Any, Dict


def scene_vision_success_ok(scene: Dict[str, Any]) -> bool:
    """
    已成功视觉分析以 vision_status == \"ok\" 为准。
    若存在非空的 vision_status，则仅 ok 为成功（error/empty/no_frame 等均视为未成功）。
    若无 vision_status（旧 JSON），则回退为 vision_analyzed。
    """
    vs = scene.get("vision_status")
    if vs is not None and str(vs).strip() != "":
        return str(vs).strip().lower() == "ok"
    return bool(scene.get("vision_analyzed"))
