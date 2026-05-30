from __future__ import annotations

import re


_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}


def safe_filename_component(name: str, fallback: str = "project", max_length: int = 48) -> str:
    """Return a readable cross-platform filename component while preserving Chinese text."""
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or "").strip())
    safe = re.sub(r"_+", "_", safe).rstrip(" .")
    if safe.upper() in _WINDOWS_RESERVED_NAMES:
        safe = f"_{safe}"
    if not safe:
        safe = str(fallback or "project").strip() or "project"
        safe = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", safe).rstrip(" .") or "project"
    return safe[:max(1, int(max_length))].rstrip(" .") or "project"
