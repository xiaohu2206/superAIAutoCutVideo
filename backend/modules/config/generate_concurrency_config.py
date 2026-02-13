from __future__ import annotations

import json
import math
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal, Optional, Tuple

import psutil
from pydantic import BaseModel, Field


ScopeName = Literal["generate_video", "generate_jianying_draft", "tts"]
SourceName = Literal["user", "env", "recommended"]


class ScopeConcurrencyConfig(BaseModel):
    max_workers: int = Field(default=1, ge=1)
    override: bool = Field(default=False)


class GenerateConcurrencyConfig(BaseModel):
    generate_video: ScopeConcurrencyConfig = Field(default_factory=lambda: ScopeConcurrencyConfig(max_workers=2, override=False))
    generate_jianying_draft: ScopeConcurrencyConfig = Field(default_factory=lambda: ScopeConcurrencyConfig(max_workers=4, override=False))
    tts: ScopeConcurrencyConfig = Field(default_factory=lambda: ScopeConcurrencyConfig(max_workers=4, override=False))


class GenerateConcurrencyConfigManager:
    def __init__(self, config_file: Optional[Path] = None) -> None:
        if config_file is None:
            from modules.app_paths import user_config_dir

            config_file = user_config_dir() / "generate_concurrency.json"
        self.config_file = Path(config_file)
        self.config = GenerateConcurrencyConfig()
        self.load()

    def load(self) -> None:
        try:
            if self.config_file.exists():
                data = json.loads(self.config_file.read_text("utf-8"))
                if isinstance(data, dict):
                    data.pop("allow_same_project_parallel", None)
                    self.config = GenerateConcurrencyConfig(**data)
            else:
                self.save()
        except Exception:
            self.config = GenerateConcurrencyConfig()

    def save(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self.config.model_dump(), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _env_int(self, name: str) -> int:
        try:
            v = int(str(os.environ.get(name) or "").strip())
            if v >= 1:
                return v
        except Exception:
            pass
        return 0

    def recommend_concurrency(self, scope: ScopeName) -> int:
        try:
            st: Dict[str, Any] = {}
            try:
                from modules.qwen3_tts_acceleration.detector import get_qwen3_tts_acceleration_status

                st = get_qwen3_tts_acceleration_status() or {}
            except Exception:
                st = {}
            has_gpu = bool(st.get("supported"))
            vram = int(((st.get("gpu") or {}).get("total_memory_bytes") or 0))

            mem = psutil.virtual_memory()
            ram_avail = int(getattr(mem, "available", 0) or 0)
            cores = max(1, int(os.cpu_count() or 1))

            if scope == "generate_video":
                per_task_ram = 1 * 1024**3
                per_task_vram = 3 * 1024**3
                headroom_ram = 0.5
                headroom_vram = 0.7
                base_default = 2
            elif scope == "generate_jianying_draft":
                per_task_ram = 512 * 1024**2
                per_task_vram = 2 * 1024**3
                headroom_ram = 0.5
                headroom_vram = 0.7
                base_default = 4
            else:
                per_task_ram = 256 * 1024**2
                per_task_vram = 2 * 1024**3
                headroom_ram = 0.5
                headroom_vram = 0.7
                base_default = 4

            if has_gpu and vram > 0:
                by_vram = max(1, math.floor((vram * headroom_vram) / per_task_vram))
                by_ram = max(1, math.floor((ram_avail * headroom_ram) / per_task_ram))
                by_core = max(1, cores // 2)
                return max(1, min(by_vram, by_ram, by_core))

            by_ram = max(1, math.floor((ram_avail * headroom_ram) / per_task_ram))
            by_core = max(1, cores // 2)
            return max(1, min(by_ram, by_core, base_default))
        except Exception:
            if scope == "generate_video":
                return 2
            if scope == "generate_jianying_draft":
                return 4
            return 4

    def get_effective(self, scope: ScopeName) -> Tuple[int, SourceName]:
        cfg = getattr(self.config, scope)
        if cfg.override and int(cfg.max_workers or 0) >= 1:
            return int(cfg.max_workers), "user"

        if scope == "generate_video":
            v = self._env_int("SACV_GENERATE_VIDEO_MAX_WORKERS")
            if v:
                return v, "env"
        elif scope == "generate_jianying_draft":
            v = self._env_int("SACV_JY_DRAFT_MAX_WORKERS")
            if v:
                return v, "env"
        else:
            v = self._env_int("SACV_TTS_MAX_WORKERS")
            if v:
                return v, "env"

        return self.recommend_concurrency(scope), "recommended"

    def snapshot(self) -> Dict[str, Any]:
        eff_video, src_video = self.get_effective("generate_video")
        eff_draft, src_draft = self.get_effective("generate_jianying_draft")
        eff_tts, src_tts = self.get_effective("tts")
        return {
            "config": self.config.model_dump(),
            "effective": {
                "generate_video": {"max_workers": eff_video, "source": src_video},
                "generate_jianying_draft": {"max_workers": eff_draft, "source": src_draft},
                "tts": {"max_workers": eff_tts, "source": src_tts},
            },
            "timestamp": datetime.now().isoformat(),
        }

    def update(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        data = self.config.model_dump()
        for k in ["generate_video", "generate_jianying_draft", "tts"]:
            if k in payload:
                data[k] = payload[k]
        self.config = GenerateConcurrencyConfig(**data)
        self.save()
        return self.snapshot()


generate_concurrency_config_manager = GenerateConcurrencyConfigManager()
