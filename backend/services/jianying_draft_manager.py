from __future__ import annotations

import asyncio
import json
import shutil
import subprocess
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from modules.projects_store import Project, projects_store
from modules.ws_manager import manager
from modules.config.jianying_config import jianying_config_manager
from modules.tts_service import tts_service
from modules.audio_normalizer import AudioNormalizer


def _now_ts() -> str:
    return datetime.now().isoformat()


async def _to_thread(func, *args, **kwargs):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: func(*args, **kwargs))


def _backend_root_dir() -> Path:
    backend_dir = Path(__file__).resolve().parents[1]
    return backend_dir.parent


def _uploads_dir() -> Path:
    root = _backend_root_dir()
    up = root / "uploads"
    (up / "jianying_drafts").mkdir(parents=True, exist_ok=True)
    return up


def _to_web_path(p: Path) -> str:
    root = _backend_root_dir()
    try:
        rel = p.relative_to(root)
        return "/" + str(rel).replace("\\", "/")
    except Exception:
        return str(p)


def _resolve_path(path_or_web: str) -> Path:
    root = _backend_root_dir()
    path_str = (path_or_web or "").strip()
    if not path_str:
        return Path("")
    if path_str.startswith("/"):
        return root / path_str[1:]
    return Path(path_str)


def _s_to_us(v: float) -> int:
    try:
        return int(round(float(v) * 1_000_000))
    except Exception:
        return 0


def _probe_video_meta(video_path: Path) -> Dict[str, Any]:
    try:
        result = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-select_streams",
                "v:0",
                "-show_entries",
                "stream=width,height,r_frame_rate,duration",
                "-of",
                "json",
                str(video_path),
            ],
            stderr=subprocess.STDOUT,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 ffprobe，请先安装并放到 PATH。") from exc
    data = json.loads(result)
    stream = data["streams"][0]
    width = int(stream["width"])
    height = int(stream["height"])
    rate_str = stream.get("r_frame_rate", "0/1")
    if "/" in rate_str:
        num, denom = rate_str.split("/", 1)
        fps = float(num) / float(denom) if float(denom) != 0 else 0.0
    else:
        fps = float(rate_str)
    duration = float(stream.get("duration", 0.0))
    return {"width": width, "height": height, "fps": fps, "duration": duration}

def _probe_audio_duration(audio_path: Path) -> float:
    try:
        result = subprocess.check_output(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=nk=1:nw=1",
                str(audio_path),
            ],
            stderr=subprocess.STDOUT,
        )
        try:
            return float(result.decode().strip())
        except Exception:
            return 0.0
    except Exception:
        return 0.0

@dataclass
class DraftGenerateFolderResult:
    task_id: str
    dir_abs: Path
    dir_web: str


class JianyingDraftManager:
    SCOPE = "generate_jianying_draft"

    @staticmethod
    async def _broadcast(payload: Dict[str, Any]) -> None:
        try:
            await manager.broadcast(json.dumps(payload, ensure_ascii=False))
        except Exception:
            pass

    @staticmethod
    def _normalize_segments(project: Project, video_dur: float) -> List[Dict[str, Any]]:
        segs: List[Dict[str, Any]] = []
        raw = (project.script or {}).get("segments") if isinstance(project.script, dict) else None
        if isinstance(raw, list) and raw:
            for seg in raw:
                if not isinstance(seg, dict):
                    continue
                st = float(seg.get("start_time") or 0.0)
                et = float(seg.get("end_time") or 0.0)
                if video_dur and et > video_dur:
                    et = float(video_dur)
                if st < 0:
                    st = 0.0
                if et <= st:
                    continue
                segs.append({
                    "start_time": st,
                    "end_time": et,
                    "text": str(seg.get("text") or ""),
                    "subtitle": str(seg.get("subtitle") or ""),
                })
        if segs:
            return segs
        if video_dur and video_dur > 0:
            return [{
                "start_time": 0.0,
                "end_time": float(video_dur),
                "text": "",
                "subtitle": "",
            }]
        return []

    @staticmethod
    def _init_new_draft_dir(base_dir: Path) -> Path:
        base_dir.mkdir(parents=True, exist_ok=True)
        name = f"auto_{uuid.uuid4().hex[:8]}"
        draft_dir = base_dir / name
        draft_dir.mkdir(parents=True, exist_ok=True)
        return draft_dir

    @staticmethod
    def _copy_unique(src: Path, dst_dir: Path) -> Path:
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / src.name
        if dst.exists():
            base = src.stem
            ext = src.suffix
            dst = dst_dir / f"{base}_{uuid.uuid4().hex[:6]}{ext}"
        shutil.copy2(src, dst)
        return dst

    @staticmethod
    def _build_timeline_items_from_segments(segments: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        items: List[Dict[str, Any]] = []
        for seg in segments:
            st = float(seg.get("start_time") or 0.0)
            et = float(seg.get("end_time") or 0.0)
            dur = max(0.0, et - st)
            if dur <= 0:
                continue
            items.append({
                "kind": "original",
                "duration_us": _s_to_us(dur),
                "source_start_us": _s_to_us(st),
                "text": str(seg.get("text") or ""),
                "subtitle": str(seg.get("subtitle") or ""),
                "mute": False,
                "narration_path": None,
                "narration_duration_us": 0,
            })
        return items

    @staticmethod
    def _make_video_material(material_id: str, path: Path) -> dict:
        meta = _probe_video_meta(path)
        duration_us_total = int(round(meta["duration"] * 1_000_000))
        return {
            "audio_fade": None,
            "category_id": "",
            "category_name": "local",
            "check_flag": 63487,
            "crop": {
                "upper_left_x": 0,
                "upper_left_y": 0,
                "upper_right_x": 1,
                "upper_right_y": 0,
                "lower_left_x": 0,
                "lower_left_y": 1,
                "lower_right_x": 1,
                "lower_right_y": 1,
            },
            "crop_ratio": "free",
            "crop_scale": 1,
            "duration": duration_us_total,
            "height": meta["height"],
            "id": material_id,
            "local_material_id": "",
            "material_id": material_id,
            "material_name": path.name,
            "media_path": "",
            "path": str(path),
            "remote_url": "",
            "type": "video",
            "width": meta["width"],
        }

    @staticmethod
    def _build_draft_info(draft_dir: Path, source_video: Path, timeline_items: Sequence[Dict[str, Any]]) -> None:
        draft_path = draft_dir / "draft_info.json"
        now_us = int(time.time() * 1_000_000)
        original_meta = _probe_video_meta(source_video)
        vid_id = uuid.uuid4().hex
        speed_id = uuid.uuid4().hex
        video_materials: List[dict] = []
        video_materials.append(JianyingDraftManager._make_video_material(vid_id, source_video))
        audio_materials: List[dict] = []
        audio_track_segments: List[dict] = []
        speed_materials = [{"curve_speed": None, "id": speed_id, "mode": 0, "speed": 1, "type": "speed"}]
        segments: List[dict] = []
        timeline_cursor_us = 0
        for item in timeline_items:
            duration_us = int(item["duration_us"])
            if duration_us <= 0:
                continue
            material_id = vid_id
            source_start_us = int(item["source_start_us"])
            text = str(item.get("subtitle") or item.get("text") or "").strip()
            seg_obj = {
                "enable_adjust": True,
                "enable_color_correct_adjust": False,
                "enable_color_curves": True,
                "enable_color_match_adjust": False,
                "enable_color_wheels": True,
                "enable_lut": True,
                "enable_smart_color_adjust": False,
                "last_nonzero_volume": 1,
                "reverse": False,
                "track_attribute": 0,
                "track_render_index": 0,
                "visible": True,
                "id": uuid.uuid4().hex,
                "material_id": material_id,
                "target_timerange": {"start": timeline_cursor_us, "duration": duration_us},
                "common_keyframes": [],
                "keyframe_refs": [],
                "source_timerange": {"start": source_start_us, "duration": duration_us},
                "speed": 1,
                "volume": 0 if bool(item.get("mute")) else 1,
                "extra_material_refs": [speed_id],
                "clip": {
                    "alpha": 1,
                    "flip": {"horizontal": False, "vertical": False},
                    "rotation": 0,
                    "scale": {"x": 1, "y": 1},
                    "transform": {"x": 0, "y": 0},
                },
                "uniform_scale": {"on": True, "value": 1},
                "hdr_settings": {"intensity": 1, "mode": 1, "nits": 1000},
                "render_index": 0,
            }
            segments.append(seg_obj)
            narr_path = item.get("narration_path")
            narr_dur_us = int(item.get("narration_duration_us") or 0)
            if narr_path and narr_dur_us > 0:
                aud_id = uuid.uuid4().hex
                audio_materials.append({
                    "audio_fade": None,
                    "category_id": "",
                    "category_name": "local",
                    "check_flag": 63487,
                    "duration": narr_dur_us,
                    "id": aud_id,
                    "local_material_id": "",
                    "material_id": aud_id,
                    "material_name": Path(str(narr_path)).name,
                    "media_path": "",
                    "path": str(narr_path),
                    "remote_url": "",
                    "type": "audio",
                })
                audio_track_segments.append({
                    "enable_adjust": True,
                    "last_nonzero_volume": 1,
                    "reverse": False,
                    "track_attribute": 0,
                    "track_render_index": 0,
                    "visible": True,
                    "id": uuid.uuid4().hex,
                    "material_id": aud_id,
                    "target_timerange": {"start": timeline_cursor_us, "duration": narr_dur_us},
                    "common_keyframes": [],
                    "keyframe_refs": [],
                    "source_timerange": {"start": 0, "duration": narr_dur_us},
                    "speed": 1,
                    "volume": 1,
                    "clip": {
                        "alpha": 1,
                        "rotation": 0,
                        "scale": {"x": 1, "y": 1},
                        "transform": {"x": 0, "y": 0},
                    },
                    "render_index": 0,
                })
            timeline_cursor_us += duration_us
        materials = {
            "videos": video_materials,
            "speeds": speed_materials,
            "ai_translates": [],
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_track_indexes": [],
            "audios": audio_materials,
            "beats": [],
            "canvases": [],
            "chromas": [],
            "color_curves": [],
            "digital_humans": [],
            "drafts": [],
            "effects": [],
            "flowers": [],
            "green_screens": [],
            "handwrites": [],
            "hsl": [],
            "images": [],
            "log_color_wheels": [],
            "loudnesses": [],
            "manual_deformations": [],
            "material_animations": [],
            "material_colors": [],
            "multi_language_refs": [],
            "placeholders": [],
            "plugin_effects": [],
            "primary_color_wheels": [],
            "realtime_denoises": [],
            "shapes": [],
            "smart_crops": [],
            "smart_relights": [],
            "sound_channel_mappings": [],
            "stickers": [],
            "tail_leaders": [],
            "text_templates": [],
            "texts": [],
            "time_marks": [],
            "transitions": [],
            "video_effects": [],
            "video_trackings": [],
            "vocal_beautifys": [],
            "vocal_separations": [],
            "masks": [],
        }
        draft = {
            "canvas_config": {"width": original_meta["width"], "height": original_meta["height"], "ratio": "original"},
            "color_space": 0,
            "config": {
                "adjust_max_index": 1,
                "attachment_info": [],
                "combination_max_index": 1,
                "export_range": None,
                "extract_audio_last_index": 1,
                "lyrics_recognition_id": "",
                "lyrics_sync": True,
                "lyrics_taskinfo": [],
                "maintrack_adsorb": True,
                "material_save_mode": 0,
                "multi_language_current": "none",
                "multi_language_list": [],
                "multi_language_main": "none",
                "multi_language_mode": "none",
                "original_sound_last_index": 1,
                "record_audio_last_index": 1,
                "sticker_max_index": 1,
                "subtitle_keywords_config": None,
                "subtitle_recognition_id": "",
                "subtitle_sync": True,
                "subtitle_taskinfo": [],
                "system_font_list": [],
                "video_mute": False,
                "zoom_info_params": None,
            },
            "cover": {"cover_draft_id": "", "cover_template": "", "sub_type": "local", "type": "image", "web_cover_info": ""},
            "create_time": now_us,
            "duration": timeline_cursor_us,
            "extra_info": None,
            "fps": int(round(original_meta["fps"])) if original_meta["fps"] else 30,
            "free_render_index_mode_on": False,
            "group_container": None,
            "id": str(uuid.uuid4()).upper(),
            "keyframe_graph_list": [],
            "keyframes": {k: [] for k in ["adjusts", "audios", "effects", "filters", "handwrites", "stickers", "texts", "videos"]},
            "last_modified_platform": {
                "app_id": 359289,
                "app_source": "cc",
                "app_version": "6.5.0",
                "device_id": "c4ca4238a0b923820dcc509a6f75849b",
                "hard_disk_id": "307563e0192a94465c0e927fbc482942",
                "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
                "os": "windows",
                "os_version": "10",
            },
            "materials": materials,
            "mutable_config": None,
            "name": source_video.stem,
            "new_version": "110.0.0",
            "relationships": [],
            "render_index_track_mode_on": True,
            "retouch_cover": None,
            "source": "default",
            "static_cover_image_path": "",
            "time_marks": None,
            "tracks": [],
            "update_time": now_us,
            "version": 360000,
            "platform": {
                "app_id": 359289,
                "app_source": "cc",
                "app_version": "6.5.0",
                "device_id": "c4ca4238a0b923820dcc509a6f75849b",
                "hard_disk_id": "307563e0192a94465c0e927fbc482942",
                "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
                "os": "windows",
                "os_version": "10",
            },
        }
        # 先生成轨道并收集音频轨道ID，便于 materials.audio_track_indexes 显示控制
        track_main_id = uuid.uuid4().hex
        track_video_id = uuid.uuid4().hex
        track_audio_id = uuid.uuid4().hex
        draft["tracks"] = [
            {"attribute": 0, "flag": 0, "id": track_main_id, "is_default_name": False, "name": "main", "segments": [], "type": "video"},
            {"attribute": 0, "flag": 0, "id": track_video_id, "is_default_name": False, "name": "video_main", "segments": segments, "type": "video"},
            {"attribute": 0, "flag": 0, "id": track_audio_id, "is_default_name": False, "name": "audio_main", "segments": audio_track_segments, "type": "audio"},
        ]
        mats = draft.get("materials", {})
        mats["audio_track_indexes"] = [2]
        draft["materials"] = mats
        try:
            cfg = draft.get("config", {})
            cfg["record_audio_last_index"] = 2
            draft["config"] = cfg
            draft["render_index_track_mode_on"] = False
        except Exception:
            pass
        if draft_path.exists():
            shutil.copy2(draft_path, draft_dir / "draft_info.json.bak")
        with open(draft_path, "w", encoding="utf-8") as f:
            json.dump(draft, f, ensure_ascii=False, indent=2)
        meta_info = {
            "cloud_draft_cover": True,
            "cloud_draft_sync": True,
            "cloud_package_completed_time": "",
            "draft_cloud_capcut_purchase_info": "",
            "draft_cloud_last_action_download": False,
            "draft_cloud_package_type": "",
            "draft_cloud_purchase_info": "",
            "draft_cloud_template_id": "",
            "draft_cloud_tutorial_info": "",
            "draft_cloud_videocut_purchase_info": "",
            "draft_cover": "draft_cover.jpg",
            "draft_deeplink_url": "",
            "draft_enterprise_info": {"draft_enterprise_extra": "", "draft_enterprise_id": "", "draft_enterprise_name": "", "enterprise_material": []},
            "draft_fold_path": str(draft_dir),
            "draft_id": str(uuid.uuid4()).upper(),
            "draft_is_ae_produce": False,
            "draft_is_ai_packaging_used": False,
            "draft_is_ai_shorts": False,
            "draft_is_ai_translate": False,
            "draft_is_article_video_draft": False,
            "draft_is_cloud_temp_draft": False,
            "draft_is_from_deeplink": "false",
            "draft_is_invisible": False,
            "draft_materials": [{"type": t, "value": []} for t in [0, 1, 2, 3, 6, 7, 8]],
            "draft_materials_copied_info": [],
            "draft_name": source_video.stem,
            "draft_need_rename_folder": False,
            "draft_new_version": "",
            "draft_removable_storage_device": "",
            "draft_root_path": str(draft_dir.parent),
            "draft_segment_extra_info": [],
            "draft_timeline_materials_size_": 0,
            "draft_type": "",
            "tm_draft_cloud_completed": "",
            "tm_draft_cloud_entry_id": -1,
            "tm_draft_cloud_modified": 0,
            "tm_draft_cloud_parent_entry_id": -1,
            "tm_draft_cloud_space_id": -1,
            "tm_draft_cloud_user_id": -1,
            "tm_draft_create": now_us,
            "tm_draft_modified": now_us,
            "tm_draft_removed": 0,
            "tm_duration": 0,
        }
        meta_path = draft_dir / "draft_meta_info.json"
        if meta_path.exists():
            shutil.copy2(meta_path, draft_dir / "draft_meta_info.json.bak")
        with open(meta_path, "w", encoding="utf-8") as f:
            json.dump(meta_info, f, ensure_ascii=False, indent=2)
        agency_path = draft_dir / "draft_agency_config.json"
        agency_data = {
            "is_auto_agency_enabled": False,
            "is_auto_agency_popup": False,
            "is_single_agency_mode": False,
            "marterials": None,
            "use_converter": False,
            "video_resolution": original_meta["height"],
        }
        if agency_path.exists():
            shutil.copy2(agency_path, draft_dir / "draft_agency_config.json.bak")
        with open(agency_path, "w", encoding="utf-8") as f:
            json.dump(agency_data, f, ensure_ascii=False)
        biz_path = draft_dir / "draft_biz_config.json"
        biz_data = {
            "ai_packaging_infos": [],
            "ai_packaging_report_info": {
                "caption_id_list": [],
                "commercial_material": "",
                "material_source": "",
                "method": "",
                "page_from": "",
                "style": "",
                "task_id": "",
                "text_style": "",
                "tos_id": "",
                "video_category": "",
            },
            "broll": {
                "ai_packaging_infos": [],
                "ai_packaging_report_info": {
                    "caption_id_list": [],
                    "commercial_material": "",
                    "material_source": "",
                    "method": "",
                    "page_from": "",
                    "style": "",
                    "task_id": "",
                    "text_style": "",
                    "tos_id": "",
                    "video_category": "",
                },
            },
            "commercial_music_category_ids": [],
            "pc_feature_flag": 0,
            "recognize_tasks": [],
            "reference_lines_config": {"horizontal_lines": [], "is_lock": False, "is_visible": False, "vertical_lines": []},
            "safe_area_type": 0,
            "template_item_infos": [],
            "unlock_template_ids": [],
        }
        if biz_path.exists():
            shutil.copy2(biz_path, draft_dir / "draft_biz_config.json.bak")
        with open(biz_path, "w", encoding="utf-8") as f:
            json.dump(biz_data, f, ensure_ascii=False)
        attach_path = draft_dir / "attachment_pc_common.json"
        if attach_path.exists():
            shutil.copy2(attach_path, draft_dir / "attachment_pc_common.json.bak")
        with open(attach_path, "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False)
        attach_edit_path = draft_dir / "attachment_editing.json"
        attach_edit_data = {
            "editing_draft": {
                "ai_remove_filter_words": {"enter_source": "", "right_id": ""},
                "ai_shorts_info": {"report_params": "", "type": 0},
                "digital_human_template_to_video_info": {"has_upload_material": False, "template_type": 0},
                "draft_used_recommend_function": "",
                "edit_type": 0,
                "eye_correct_enabled_multi_face_time": 0,
                "has_adjusted_render_layer": False,
                "is_open_expand_player": True,
                "is_use_adjust": False,
                "is_use_edit_multi_camera": False,
                "is_use_lock_object": False,
                "is_use_loudness_unify": False,
                "is_use_retouch_face": False,
                "is_use_smart_adjust_color": False,
                "is_use_smart_motion": False,
                "is_use_text_to_audio": True,
                "material_edit_session": {"material_edit_info": [], "session_id": "", "session_time": 0},
                "profile_entrance_type": "",
                "publish_enter_from": "",
                "publish_type": "",
                "single_function_type": 0,
                "text_convert_case_types": [],
                "version": "1.0.0",
                "video_recording_create_draft": "",
            }
        }
        if attach_edit_path.exists():
            shutil.copy2(attach_edit_path, draft_dir / "attachment_editing.json.bak")
        with open(attach_edit_path, "w", encoding="utf-8") as f:
            json.dump(attach_edit_data, f, ensure_ascii=False)
        common_dir = draft_dir / "common_attachment"
        common_dir.mkdir(parents=True, exist_ok=True)
        with open(common_dir / "aigc_aigc_generate.json", "w", encoding="utf-8") as f:
            json.dump({"aigc_aigc_generate": {"aigc_generate_segment_list": [], "version": "1.0.0"}}, f, ensure_ascii=False)
        with open(common_dir / "attachment_script_video.json", "w", encoding="utf-8") as f:
            json.dump(
                {
                    "script_video": {
                        "attachment_valid": False,
                        "language": "",
                        "overdub_recover": [],
                        "overdub_sentence_ids": [],
                        "parts": [],
                        "sync_subtitle": False,
                        "translate_segments": [],
                        "translate_type": "",
                        "version": "1.0.0",
                    }
                },
                f,
                ensure_ascii=False,
            )

    @staticmethod
    async def generate_draft_folder(project_id: str, task_id: str) -> DraftGenerateFolderResult:
        p: Optional[Project] = projects_store.get_project(project_id)
        if not p:
            raise ValueError("项目不存在")
        tmp_dir: Optional[Path] = None
        audio_norm = AudioNormalizer()
        try:
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "start",
                "message": "开始生成剪映草稿",
                "progress": 1,
                "timestamp": _now_ts(),
            })
            input_abs = _resolve_path(p.video_path or "")
            if not input_abs.exists():
                raise ValueError("原始视频文件不存在")
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "prepare",
                "message": "读取素材信息",
                "progress": 8,
                "timestamp": _now_ts(),
            })
            meta = _probe_video_meta(input_abs)
            video_dur = float(meta.get("duration") or 0.0)
            segments = JianyingDraftManager._normalize_segments(p, video_dur)
            if not segments:
                raise ValueError("没有可用片段生成草稿")
            timeline_items: List[Dict[str, Any]] = []
            uploads_root = _uploads_dir()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            tmp_dir = uploads_root / "jianying_drafts" / "tmp" / f"{project_id}_{ts}_{task_id[:8]}"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            target_dir_cfg = jianying_config_manager.ensure_default_draft_path()
            if target_dir_cfg:
                out_base = Path(target_dir_cfg)
            else:
                out_base = uploads_root / "jianying_drafts" / "outputs" / project_id
                out_base.mkdir(parents=True, exist_ok=True)
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "copy_materials",
                "message": "复制素材文件",
                "progress": 20,
                "timestamp": _now_ts(),
            })
            draft_dir = JianyingDraftManager._init_new_draft_dir(tmp_dir)
            assets_video_dir = draft_dir / "assets" / "video"
            copied_video = await _to_thread(JianyingDraftManager._copy_unique, input_abs, assets_video_dir)
            assets_audio_dir = draft_dir / "assets" / "audio"
            assets_audio_dir.mkdir(parents=True, exist_ok=True)
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "tts",
                "message": "生成配音并对齐片段",
                "progress": 40,
                "timestamp": _now_ts(),
            })
            total_segments = len(segments)
            for idx, seg in enumerate(segments, start=1):
                st = float(seg.get("start_time") or 0.0)
                et = float(seg.get("end_time") or 0.0)
                if et <= st:
                    continue
                dur = max(0.0, et - st)
                text = str(seg.get("text") or "").strip()
                subtitle = str(seg.get("subtitle") or "").strip()
                if text.startswith("播放原片"):
                    timeline_items.append({
                        "kind": "original",
                        "duration_us": _s_to_us(dur),
                        "source_start_us": _s_to_us(st),
                        "text": text,
                        "subtitle": subtitle,
                        "mute": False,
                        "narration_path": None,
                        "narration_duration_us": 0,
                    })
                else:
                    tts_out = assets_audio_dir / f"seg_{idx:04d}.mp3"
                    res = await tts_service.synthesize(text, str(tts_out), None)
                    if not res.get("success"):
                        raise RuntimeError(f"TTS合成失败: {idx} - {res.get('error')}")
                    adur = float(res.get("duration") or 0.0)
                    if adur <= 0.0:
                        adur = _probe_audio_duration(tts_out) or 0.0
                    if adur <= 0.0:
                        raise RuntimeError(f"无法获取配音时长: {idx}")
                    norm_out = assets_audio_dir / f"seg_{idx:04d}_norm.mp3"
                    ok_norm = await audio_norm.normalize_audio_loudness(str(tts_out), str(norm_out))
                    narr_used = norm_out if ok_norm else tts_out
                    # 对齐视频片段时长到配音
                    if adur > dur:
                        ext = adur - dur
                        fwd = max(0.0, video_dur - et)
                        if fwd >= ext:
                            new_start = st
                            new_dur = dur + ext
                        else:
                            shortage = ext - fwd
                            new_start = max(0.0, st - shortage)
                            new_dur = max(0.0, video_dur - new_start)
                    elif (adur + 0.05) < dur:
                        new_start = st
                        new_dur = adur
                    else:
                        new_start = st
                        new_dur = dur
                    timeline_items.append({
                        "kind": "original",
                        "duration_us": _s_to_us(new_dur),
                        "source_start_us": _s_to_us(new_start),
                        "text": text,
                        "subtitle": subtitle,
                        "mute": True,
                        "narration_path": str(narr_used),
                        "narration_duration_us": _s_to_us(adur),
                    })
                try:
                    base = 40
                    span = 25
                    progress = base + int((idx / max(1, total_segments)) * span)
                    await JianyingDraftManager._broadcast({
                        "type": "progress",
                        "scope": JianyingDraftManager.SCOPE,
                        "project_id": project_id,
                        "task_id": task_id,
                        "phase": "tts_progress",
                        "message": f"已处理配音 {idx}/{total_segments}",
                        "progress": min(65, progress),
                        "timestamp": _now_ts(),
                    })
                except Exception:
                    pass
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "write_json",
                "message": "生成草稿 JSON",
                "progress": 65,
                "timestamp": _now_ts(),
            })
            await _to_thread(JianyingDraftManager._build_draft_info, draft_dir, copied_video, timeline_items)
            await JianyingDraftManager._broadcast({
                "type": "progress",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "output",
                "message": "生成草稿目录",
                "progress": 90,
                "timestamp": _now_ts(),
            })
            dest_dir = out_base / draft_dir.name
            if dest_dir.exists():
                try:
                    shutil.rmtree(dest_dir, ignore_errors=True)
                except Exception:
                    pass
            await _to_thread(shutil.copytree, draft_dir, dest_dir)
            try:
                info_path = dest_dir / "draft_info.json"
                if info_path.exists():
                    data = json.loads(info_path.read_text(encoding="utf-8"))
                    mats = (data.get("materials") or {})
                    vids = list(mats.get("videos") or [])
                    for v in vids:
                        try:
                            name = Path(str(v.get("path") or "")).name
                            new_p = dest_dir / "assets" / "video" / name
                            v["path"] = str(new_p)
                        except Exception:
                            pass
                    auds = list(mats.get("audios") or [])
                    for a in auds:
                        try:
                            name = Path(str(a.get("path") or "")).name
                            new_p = dest_dir / "assets" / "audio" / name
                            a["path"] = str(new_p)
                        except Exception:
                            pass
                    data["materials"] = mats
                    info_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
                meta_path = dest_dir / "draft_meta_info.json"
                if meta_path.exists():
                    meta = json.loads(meta_path.read_text(encoding="utf-8"))
                    now_us = int(time.time() * 1_000_000)
                    meta["draft_fold_path"] = str(dest_dir)
                    meta["draft_root_path"] = str(dest_dir.parent)
                    meta["tm_draft_modified"] = now_us
                    if not meta.get("tm_draft_create"):
                        meta["tm_draft_create"] = now_us
                    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            try:
                dir_web = _to_web_path(dest_dir)
            except Exception:
                dir_web = str(dest_dir)
            await JianyingDraftManager._broadcast({
                "type": "completed",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "completed",
                "message": "剪映草稿生成完成",
                "progress": 100,
                "file_path": dir_web,
                "timestamp": _now_ts(),
            })
            return DraftGenerateFolderResult(task_id=task_id, dir_abs=dest_dir, dir_web=dir_web)
        except Exception as e:
            await JianyingDraftManager._broadcast({
                "type": "error",
                "scope": JianyingDraftManager.SCOPE,
                "project_id": project_id,
                "task_id": task_id,
                "phase": "failed",
                "message": f"剪映草稿生成失败: {str(e)}",
                "progress": 0,
                "timestamp": _now_ts(),
            })
            raise
        finally:
            try:
                if tmp_dir and tmp_dir.exists():
                    shutil.rmtree(tmp_dir, ignore_errors=True)
            except Exception:
                pass


jianying_draft_manager = JianyingDraftManager()
