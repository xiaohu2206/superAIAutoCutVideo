#!/usr/bin/env python3
# -*- coding: utf-8 -*-

from typing import Any, Dict, List, Optional
from pathlib import Path
import json
import re

from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel, Field

from modules.prompts.prompt_manager import prompt_manager, PromptTemplate
from modules.projects_store import projects_store
from modules.app_paths import user_data_dir

router = APIRouter(prefix="/api/prompts", tags=["提示词"])


class CreatePromptRequest(BaseModel):
    id: Optional[str] = None
    name: str
    category: str
    description: Optional[str] = None
    template: str
    variables: Optional[List[str]] = None
    system_prompt: Optional[str] = None
    tags: Optional[List[str]] = None
    version: Optional[str] = None
    enabled: bool = True


class ValidateRequest(BaseModel):
    template: str
    required_vars: List[str] = Field(default_factory=list)


class RenderPreviewRequest(BaseModel):
    variables: Optional[Dict[str, Any]] = None


def _store_path() -> Path:
    d = user_data_dir()
    return d / "user_prompts.json"


def _read_store() -> Dict[str, Any]:
    p = _store_path()
    if not p.exists():
        return {"templates": {}}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {"templates": {}}


def _write_store(data: Dict[str, Any]) -> None:
    p = _store_path()
    txt = json.dumps(data, ensure_ascii=False, indent=2)
    p.write_text(txt, encoding="utf-8")


def _normalize_template(s: str) -> str:
    return re.sub(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}", r"${\1}", s or "")


def _extract_vars_from_template(s: str) -> List[str]:
    norm = _normalize_template(s)
    return sorted(set(re.findall(r"\$\{([a-zA-Z0-9_]+)\}", norm)))


@router.get("/categories")
async def list_categories():
    cats = prompt_manager.list_categories()
    return {"data": cats}


@router.get("")
async def list_prompts(category: Optional[str] = None):
    items = prompt_manager.list_summary(category)
    return {"data": items}


@router.get("/{key_or_id}")
async def get_prompt_detail(key_or_id: str):
    try:
        detail = prompt_manager.describe_item(key_or_id)
        return {"data": detail}
    except KeyError:
        raise HTTPException(status_code=404, detail="未找到提示词")


@router.post("/{key_or_id}/render-preview")
async def render_preview(key_or_id: str, req: RenderPreviewRequest):
    detail = prompt_manager.describe_item(key_or_id)
    vars_list = detail.get("variables") or []
    vars_map: Dict[str, Any] = {}
    for v in vars_list:
        vars_map[str(v)] = str(v)
    user_vars = req.variables or {}
    vars_map.update(user_vars)
    try:
        messages = prompt_manager.build_chat_messages(detail["id_or_key"], vars_map)
        return {"data": {"messages": messages}}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("")
async def create_prompt(req: CreatePromptRequest):
    if not req.name or not req.category or not req.template:
        raise HTTPException(status_code=400, detail="缺少必要字段")
    data = _read_store()
    templates = data.get("templates") or {}
    new_id = req.id or f"user_{len(templates) + 1}"
    tpl_text = _normalize_template(req.template)
    vars_list = req.variables or _extract_vars_from_template(tpl_text)
    obj = {
        "id": new_id,
        "name": req.name,
        "category": req.category,
        "description": req.description,
        "template": tpl_text,
        "variables": vars_list,
        "system_prompt": req.system_prompt,
        "tags": req.tags or [],
        "version": req.version,
        "origin": "user",
        "enabled": bool(req.enabled),
    }
    templates[new_id] = obj
    data["templates"] = templates
    _write_store(data)
    try:
        tpl = PromptTemplate(**obj)
        prompt_manager.add_template(tpl)
    except Exception:
        pass
    return {"data": obj}


@router.put("/{template_id}")
async def update_prompt(template_id: str, req: CreatePromptRequest):
    data = _read_store()
    templates = data.get("templates") or {}
    if template_id not in templates:
        raise HTTPException(status_code=404, detail="模板不存在")
    tpl_text = _normalize_template(req.template)
    vars_list = req.variables or _extract_vars_from_template(tpl_text)
    obj = templates[template_id]
    obj.update({
        "name": req.name,
        "category": req.category,
        "description": req.description,
        "template": tpl_text,
        "variables": vars_list,
        "system_prompt": req.system_prompt,
        "tags": req.tags or [],
        "version": req.version,
        "origin": "user",
        "enabled": bool(req.enabled),
    })
    templates[template_id] = obj
    data["templates"] = templates
    _write_store(data)
    try:
        tpl = PromptTemplate(**obj)
        prompt_manager.add_template(tpl)
    except Exception:
        pass
    return {"data": obj}


@router.delete("/{template_id}")
async def delete_prompt(template_id: str):
    data = _read_store()
    templates = data.get("templates") or {}
    if template_id in templates:
        del templates[template_id]
        data["templates"] = templates
        _write_store(data)
    return {"data": {"deleted": True}}


@router.post("/validate")
async def validate_prompt(req: ValidateRequest):
    res = prompt_manager.validate_template_placeholders(req.template, req.required_vars)
    return {"data": res}


@router.post("/projects/{project_id}/prompts/select")
async def set_project_prompt_selection(project_id: str, payload: Dict[str, Any] = Body(...)):
    feature_key = str(payload.get("feature_key") or "")
    selection = payload.get("selection") or {}
    if not feature_key or not isinstance(selection, dict):
        raise HTTPException(status_code=400, detail="参数错误")
    p = projects_store.update_prompt_selection(project_id, feature_key, selection)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"data": p.model_dump()}


@router.get("/projects/{project_id}/prompts/selection")
async def get_project_prompt_selection(project_id: str):
    p = projects_store.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="项目不存在")
    return {"data": p.prompt_selection or {}}
