from __future__ import annotations

import json
import shutil
import subprocess
import time
import uuid
from pathlib import Path
from typing import Dict, Sequence

DEFAULT_DRAFT_ROOT = Path(r"D:\JianyingPro Drafts")


def probe_video_meta(video_path: Path) -> dict:
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
        fps = float(num) / float(denom)
    else:
        fps = float(rate_str)
    duration = float(stream.get("duration", 0.0))
    return {"width": width, "height": height, "fps": fps, "duration": duration}


def load_or_init_draft(draft_dir: Path) -> dict:
    draft_path = draft_dir / "draft_info.json"
    if draft_path.exists():
        with open(draft_path, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "canvas_config": {"width": 1080, "height": 1920, "ratio": "original"},
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
        "cover": {
            "cover_draft_id": "",
            "cover_template": "",
            "sub_type": "local",
            "type": "image",
            "web_cover_info": "",
        },
        "create_time": 0,
        "duration": 0,
        "extra_info": None,
        "fps": 30,
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
            "os": "mac",
            "os_version": "15.5",
        },
        "materials": {},
        "mutable_config": None,
        "name": "",
        "new_version": "110.0.0",
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "update_time": 0,
        "version": 360000,
        "platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "6.5.0",
            "device_id": "c4ca4238a0b923820dcc509a6f75849b",
            "hard_disk_id": "307563e0192a94465c0e927fbc482942",
            "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
            "os": "mac",
            "os_version": "15.5",
        },
    }


def init_new_draft_dir(draft_root: Path, video_path: Path) -> Path:
    draft_root.mkdir(parents=True, exist_ok=True)
    name = f"auto_{uuid.uuid4().hex[:8]}"
    draft_dir = draft_root / name
    draft_dir.mkdir(parents=True, exist_ok=True)
    print(f"草稿目录: {draft_dir}")
    return draft_dir


def copy_unique(src: Path, dst_dir: Path) -> Path:
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / src.name
    if dst.exists():
        base = src.stem
        ext = src.suffix
        dst = dst_dir / f"{base}_{uuid.uuid4().hex[:6]}{ext}"
    shutil.copy2(src, dst)
    return dst


def build_draft(video_path: Path, timeline_items: Sequence[dict], draft_dir: Path):
    draft_dir.mkdir(parents=True, exist_ok=True)
    draft = load_or_init_draft(draft_dir)
    now_us = int(time.time() * 1_000_000)

    assets_video_dir = draft_dir / "assets" / "video"
    copied_video = copy_unique(video_path, assets_video_dir)

    asset_map: Dict[str, Path] = {"__source__": copied_video}
    for item in timeline_items:
        if item["kind"] == "generated":
            src = Path(item["generated_video_path"])
            key = item["asset_key"]
            asset_map[key] = copy_unique(src, assets_video_dir)

    original_meta = probe_video_meta(copied_video)
    vid_id = uuid.uuid4().hex
    speed_id = uuid.uuid4().hex

    video_materials = []

    def make_video_material(material_id: str, path: Path) -> dict:
        meta = probe_video_meta(path)
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

    video_materials.append(make_video_material(vid_id, copied_video))

    generated_material_ids: Dict[str, str] = {}
    for key, path in asset_map.items():
        if key == "__source__":
            continue
        mat_id = uuid.uuid4().hex
        generated_material_ids[key] = mat_id
        video_materials.append(make_video_material(mat_id, path))

    speed_materials = [
        {
            "curve_speed": None,
            "id": speed_id,
            "mode": 0,
            "speed": 1,
            "type": "speed",
        }
    ]

    segments = []
    timeline_cursor_us = 0
    for item in timeline_items:
        duration_us = int(item["duration_us"])
        if duration_us <= 0:
            continue
        if item["kind"] == "generated":
            material_id = generated_material_ids[item["asset_key"]]
            source_start_us = 0
        else:
            material_id = vid_id
            source_start_us = int(item["source_start_us"])
        segments.append(
            {
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
                "volume": 1,
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
        )
        timeline_cursor_us += duration_us

    materials = draft.get("materials", {})
    materials.update(
        {
            "videos": video_materials,
            "speeds": speed_materials,
            "ai_translates": [],
            "audio_balances": [],
            "audio_effects": [],
            "audio_fades": [],
            "audio_track_indexes": [],
            "audios": [],
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
    )
    draft["materials"] = materials

    draft["tracks"] = [
        {"attribute": 0, "flag": 0, "id": uuid.uuid4().hex, "is_default_name": False, "name": "main", "segments": [], "type": "video"},
        {"attribute": 0, "flag": 0, "id": uuid.uuid4().hex, "is_default_name": False, "name": "video_main", "segments": segments, "type": "video"},
    ]

    video_meta = original_meta
    draft["duration"] = timeline_cursor_us
    draft["fps"] = int(round(video_meta["fps"]))
    draft["canvas_config"] = {"width": video_meta["width"], "height": video_meta["height"], "ratio": "original"}
    draft["name"] = f"{video_path.stem}_auto"
    draft["update_time"] = now_us
    draft["create_time"] = draft.get("create_time", now_us)
    draft["id"] = draft.get("id") or str(uuid.uuid4()).upper()
    draft["extra_info"] = draft.get("extra_info", None)
    draft["free_render_index_mode_on"] = draft.get("free_render_index_mode_on", False)
    draft["group_container"] = draft.get("group_container", None)
    draft["keyframe_graph_list"] = draft.get("keyframe_graph_list", [])
    draft["keyframes"] = draft.get("keyframes", {k: [] for k in ["adjusts", "audios", "effects", "filters", "handwrites", "stickers", "texts", "videos"]})
    draft["last_modified_platform"] = draft.get(
        "last_modified_platform",
        {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "6.5.0",
            "device_id": "c4ca4238a0b923820dcc509a6f75849b",
            "hard_disk_id": "307563e0192a94465c0e927fbc482942",
            "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
            "os": "mac",
            "os_version": "15.5",
        },
    )
    draft["render_index_track_mode_on"] = draft.get("render_index_track_mode_on", True)
    draft["source"] = draft.get("source", "default")
    draft["static_cover_image_path"] = draft.get("static_cover_image_path", "")
    draft["time_marks"] = draft.get("time_marks", None)
    draft["platform"] = draft.get(
        "platform",
        {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "6.5.0",
            "device_id": "c4ca4238a0b923820dcc509a6f75849b",
            "hard_disk_id": "307563e0192a94465c0e927fbc482942",
            "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
            "os": "mac",
            "os_version": "15.5",
        },
    )

    draft_path = draft_dir / "draft_info.json"
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
        "draft_enterprise_info": {
            "draft_enterprise_extra": "",
            "draft_enterprise_id": "",
            "draft_enterprise_name": "",
            "enterprise_material": [],
        },
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
        "draft_name": video_path.stem,
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
        "reference_lines_config": {
            "horizontal_lines": [],
            "is_lock": False,
            "is_visible": False,
            "vertical_lines": [],
        },
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
            "is_open_expand_player": False,
            "is_use_adjust": False,
            "is_use_edit_multi_camera": False,
            "is_use_lock_object": False,
            "is_use_loudness_unify": False,
            "is_use_retouch_face": False,
            "is_use_smart_adjust_color": False,
            "is_use_smart_motion": False,
            "is_use_text_to_audio": False,
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

    with open(draft_dir / "performance_opt_info.json", "w", encoding="utf-8") as f:
        json.dump({"manual_cancle_precombine_segs": None}, f, ensure_ascii=False)

    base_template = {
        "canvas_config": {"background": None, "height": original_meta["height"], "ratio": "original", "width": original_meta["width"]},
        "color_space": -1,
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
            "use_float_render": False,
            "video_mute": False,
            "zoom_info_params": None,
        },
        "cover": None,
        "create_time": 0,
        "duration": 0,
        "extra_info": None,
        "fps": float(int(round(original_meta["fps"]))),
        "free_render_index_mode_on": False,
        "group_container": None,
        "id": str(uuid.uuid4()).upper(),
        "is_drop_frame_timecode": False,
        "keyframe_graph_list": [],
        "keyframes": {k: [] for k in ["adjusts", "audios", "effects", "filters", "handwrites", "stickers", "texts", "videos"]},
        "last_modified_platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "6.5.0",
            "device_id": "c4ca4238a0b923820dcc509a6f75849b",
            "hard_disk_id": "307563e0192a94465c0e927fbc482942",
            "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
            "os": "mac",
            "os_version": "15.5",
        },
        "lyrics_effects": [],
        "materials": {k: [] for k in [
            "ai_translates","audio_balances","audio_effects","audio_fades","audio_track_indexes","audios","beats","canvases","chromas",
            "color_curves","common_mask","digital_human_model_dressing","digital_humans","drafts","effects","flowers","green_screens",
            "handwrites","hsl","images","log_color_wheels","loudnesses","manual_beautys","manual_deformations","material_animations",
            "material_colors","multi_language_refs","placeholder_infos","placeholders","plugin_effects","primary_color_wheels",
            "realtime_denoises","shapes","smart_crops","smart_relights","sound_channel_mappings","speeds","stickers","tail_leaders",
            "text_templates","texts","time_marks","transitions","video_effects","video_trackings","videos","vocal_beautifys","vocal_separations"
        ]},
        "mutable_config": None,
        "name": "",
        "new_version": "138.0.0",
        "path": "",
        "platform": {
            "app_id": 359289,
            "app_source": "cc",
            "app_version": "6.5.0",
            "device_id": "c4ca4238a0b923820dcc509a6f75849b",
            "hard_disk_id": "307563e0192a94465c0e927fbc482942",
            "mac_address": "c3371f2d4fb02791c067ce44d8fb4ed5",
            "os": "mac",
            "os_version": "15.5",
        },
        "relationships": [],
        "render_index_track_mode_on": True,
        "retouch_cover": None,
        "source": "default",
        "static_cover_image_path": "",
        "time_marks": None,
        "tracks": [],
        "uneven_animation_template_info": {"composition": "", "content": "", "order": "", "sub_template_info_list": []},
        "update_time": 0,
        "version": 360000,
    }
    with open(draft_dir / "template.tmp", "w", encoding="utf-8") as f:
        json.dump(base_template, f, ensure_ascii=False)
    with open(draft_dir / "template-2.tmp", "w", encoding="utf-8") as f:
        json.dump(base_template, f, ensure_ascii=False)

    settings_path = draft_dir / "draft_settings"
    now_sec = int(time.time())
    settings_content = [
        "[General]",
        "cloud_last_modify_platform=pc",
        f"draft_create_time={now_sec}",
        f"draft_last_edit_time={now_sec}",
        "real_edit_keys=1",
        "real_edit_seconds=0",
        "",
    ]
    with open(settings_path, "w", encoding="utf-8") as f:
        f.write("\n".join(settings_content))

    print(f"已写入草稿: {draft_path}")
    print(f"片段共 {len(segments)} 个，总时长 {timeline_cursor_us/1e6:.2f}s")

