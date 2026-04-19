from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Subtitle:
    index: int
    start: float
    end: float
    text: str


@dataclass
class Shot:
    start: float
    end: float
    shot_id: int = 0
    subtitles: Optional[List[Dict[str, Any]]] = None

    def __post_init__(self) -> None:
        if self.subtitles is None:
            self.subtitles = []

    def to_dict(self) -> Dict[str, Any]:
        return {
            "shot_id": self.shot_id,
            "start": round(float(self.start), 3),
            "end": round(float(self.end), 3),
            "subtitles": list(self.subtitles or []),
        }
