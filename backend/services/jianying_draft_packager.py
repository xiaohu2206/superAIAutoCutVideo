from __future__ import annotations

import json
import os
import shutil
import uuid
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from modules.projects_store import projects_store
from modules.config.jianying_config import jianying_config_manager


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _drafts_output_dir(project_id: str) -> Path:
    root = _backend_root_dir()
    d = root / "uploads" / "jianying_drafts" / "outputs" / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _rewrite_json_paths(pack_tmp_dir: Path, info_path: Path, meta_path: Path) -> None:
    try:
        if info_path.exists():
            data = json.loads(info_path.read_text(encoding="utf-8"))

            def _rw(v):
                if isinstance(v, dict):
                    return {k: _rw(v2) for k, v2 in v.items()}
                if isinstance(v, list):
                    return [_rw(x) for x in v]
                if isinstance(v, str):
                    try:
                        pth = Path(v)
                        rel = pth.relative_to(pack_tmp_dir)
                        return str(rel).replace("\\", "/")
                    except Exception:
                        return v
                return v

            data = _rw(data)
            info_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        if meta_path.exists():
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            meta["draft_fold_path"] = "."
            meta["draft_root_path"] = "."
            meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def _zip_dir(src_dir: Path, zip_path: Path) -> None:
    with zipfile.ZipFile(str(zip_path), "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _, files in os.walk(src_dir):
            for fn in files:
                abs_fp = Path(base) / fn
                rel_fp = abs_fp.relative_to(src_dir)
                zf.write(str(abs_fp), str(rel_fp))


def _pack_from_dir(pack_src: Path, drafts_dir: Path) -> Tuple[Path, Path]:
    zip_name = f"{pack_src.name}.zip"
    zip_path = drafts_dir / zip_name
    tmp_name = f"__pack_tmp__{pack_src.name}_{uuid.uuid4().hex[:8]}"
    pack_tmp_dir = drafts_dir / tmp_name
    if pack_tmp_dir.exists():
        shutil.rmtree(pack_tmp_dir, ignore_errors=True)
    shutil.copytree(pack_src, pack_tmp_dir)
    info_path = pack_tmp_dir / "draft_info.json"
    meta_path = pack_tmp_dir / "draft_meta_info.json"
    _rewrite_json_paths(pack_tmp_dir, info_path, meta_path)
    _zip_dir(pack_tmp_dir, zip_path)
    return zip_path, pack_tmp_dir


def pack_jianying_draft(project_id: str, f: Optional[str] = None) -> Tuple[Path, Optional[Path]]:
    p = projects_store.get_project(project_id)
    if not p:
        raise ValueError("项目不存在")
    root = _backend_root_dir()
    drafts_dir = _drafts_output_dir(project_id)
    target: Optional[Path] = None
    pack_tmp_dir: Optional[Path] = None
    if f:
        name = Path(str(f)).name
        candidate_file = drafts_dir / name
        candidate_dir = drafts_dir / name.replace(".zip", "")
        if candidate_dir.exists() and candidate_dir.is_dir():
            try:
                zip_path, pack_tmp_dir = _pack_from_dir(candidate_dir, drafts_dir)
                projects_store.update_project(project_id, {"jianying_draft_last_zip": str(zip_path)})
                target = zip_path
            except Exception as e:
                raise RuntimeError(f"打包草稿失败: {str(e)}")
        else:
            try:
                last_dir_str = (p.model_dump().get("jianying_draft_last_dir") or "").strip()
                base_name = name.replace(".zip", "")
                pack_src: Optional[Path] = None
                if last_dir_str:
                    ld = Path(last_dir_str) if not last_dir_str.startswith("/") else (root / last_dir_str[1:])
                    if ld.exists() and ld.is_dir() and ld.name == base_name:
                        pack_src = ld
                if not pack_src:
                    cfg = jianying_config_manager.get_draft_path()
                    if cfg and cfg.exists():
                        cand = cfg / base_name
                        if cand.exists() and cand.is_dir():
                            pack_src = cand
                if pack_src and pack_src.exists():
                    zip_path, pack_tmp_dir = _pack_from_dir(pack_src, drafts_dir)
                    projects_store.update_project(project_id, {"jianying_draft_last_zip": str(zip_path)})
                    target = zip_path
                elif candidate_file.exists() and candidate_file.is_file():
                    projects_store.update_project(project_id, {"jianying_draft_last_zip": str(candidate_file)})
                    target = candidate_file
            except Exception as e:
                raise RuntimeError(f"打包草稿失败: {str(e)}")
    else:
        dir_candidates = sorted(
            [x for x in drafts_dir.glob("*") if x.is_dir()],
            key=lambda x: x.stat().st_mtime,
            reverse=True,
        )
        if dir_candidates:
            latest_dir = dir_candidates[0]
            try:
                zip_path, pack_tmp_dir = _pack_from_dir(latest_dir, drafts_dir)
                projects_store.update_project(project_id, {"jianying_draft_last_zip": str(zip_path)})
                target = zip_path
            except Exception as e:
                raise RuntimeError(f"打包草稿失败: {str(e)}")
        else:
            try:
                last_dir_str = (p.model_dump().get("jianying_draft_last_dir") or "").strip()
                if last_dir_str:
                    pack_src = Path(last_dir_str) if not last_dir_str.startswith("/") else (root / last_dir_str[1:])
                    if pack_src.exists() and pack_src.is_dir():
                        zip_path, pack_tmp_dir = _pack_from_dir(pack_src, drafts_dir)
                        projects_store.update_project(project_id, {"jianying_draft_last_zip": str(zip_path)})
                        target = zip_path
                    else:
                        zip_candidates = sorted(
                            [x for x in drafts_dir.glob("*.zip") if x.is_file()],
                            key=lambda x: x.stat().st_mtime,
                            reverse=True,
                        )
                        if zip_candidates:
                            projects_store.update_project(project_id, {"jianying_draft_last_zip": str(zip_candidates[0])})
                            target = zip_candidates[0]
            except Exception as e:
                raise RuntimeError(f"打包草稿失败: {str(e)}")
    if not target or not target.exists():
        raise FileNotFoundError("尚未生成剪映草稿")
    return target, pack_tmp_dir

