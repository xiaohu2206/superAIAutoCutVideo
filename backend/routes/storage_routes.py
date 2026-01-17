from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import os
import json
import shutil
import sys
from modules.app_paths import data_base_dir, app_settings_file, uploads_dir

router = APIRouter(prefix="/api/settings", tags=["设置"])

def _data_base_dir() -> Path:
    return data_base_dir()

def _settings_file() -> Path:
    return app_settings_file()

def _current_uploads_dir() -> Path:
    return uploads_dir()

class StorageUpdateRequest(BaseModel):
    uploads_root: str
    migrate: bool = False

@router.get("/storage")
async def get_storage_settings():
    up = _current_uploads_dir()
    exists = up.exists()
    total = free = used = None
    percent = None
    try:
        usage = shutil.disk_usage(str(up if exists else up.parent))
        total = int(usage.total)
        free = int(usage.free)
        used = int(usage.used)
        if total:
            percent = round((used / total) * 100, 2)
    except Exception:
        pass
    return {
        "success": True,
        "data": {
            "uploads_root": str(up),
            "disk": {
                "total_bytes": total,
                "free_bytes": free,
                "used_bytes": used,
                "percent_used": percent,
            }
        }
    }

@router.post("/storage")
async def update_storage_settings(req: StorageUpdateRequest):
    dest = Path(req.uploads_root).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"无法创建目录: {str(e)}")
    cur = _current_uploads_dir()
    if req.migrate:
        try:
            for item in cur.iterdir() if cur.exists() else []:
                src = item
                dst = dest / item.name
                if src.is_dir():
                    if dst.exists():
                        continue
                    shutil.copytree(src, dst)
                else:
                    if not dst.exists():
                        shutil.copy2(src, dst)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"迁移失败: {str(e)}")
    settings_path = _settings_file()
    data = {}
    try:
        if settings_path.exists():
            data = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        data = {}
    data["uploads_root"] = str(dest)
    try:
        settings_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"写入配置失败: {str(e)}")
    return {
        "success": True,
        "message": "uploads 根路径更新成功，重启后端生效",
        "needs_restart": True,
        "data": {
            "uploads_root": str(dest)
        }
    }
