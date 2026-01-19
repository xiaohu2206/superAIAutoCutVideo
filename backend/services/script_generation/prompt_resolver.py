from typing import Optional

from modules.projects_store import projects_store


def _default_prompt_key_for_project(project_id: Optional[str]) -> str:
    category = "short_drama_narration"
    if project_id:
        p = projects_store.get_project(project_id)
        if p:
            t = str(getattr(p, "narration_type", "") or "")
            if t == "电影解说":
                category = "movie_narration"
            else:
                category = "short_drama_narration"
    return f"{category}:script_generation"


def _resolve_prompt_key(project_id: Optional[str], default_key: str) -> str:
    if not project_id:
        return default_key
    p = projects_store.get_project(project_id)
    if not p:
        return default_key
    sel_map = getattr(p, "prompt_selection", {}) or {}
    sel = sel_map.get(default_key)
    if not isinstance(sel, dict):
        return default_key
    t = str(sel.get("type") or "official").lower()
    kid = str(sel.get("key_or_id") or "")
    if t == "user" and kid:
        return kid.split(":", 1)[-1]
    if t == "official" and kid:
        return kid
    return default_key
