import asyncio
import json
import math
import os
import re
import subprocess
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

import edge_tts


def _read_json(path: str) -> Any:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data: Any) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _abs_path(project_root: str, p: str) -> str:
    root = os.path.abspath(project_root)
    if not p:
        return root
    if os.path.isabs(p):
        return os.path.abspath(p)
    return os.path.abspath(os.path.join(root, p))


def _run_cmd(args: List[str]) -> None:
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if proc.returncode != 0:
        raise RuntimeError(
            "Command failed:\n"
            f"  cmd: {' '.join(args)}\n"
            f"  exit: {proc.returncode}\n"
            f"  stdout:\n{proc.stdout}\n"
            f"  stderr:\n{proc.stderr}\n"
        )


def _ffprobe_json(path: str) -> Dict[str, Any]:
    args = [
        "ffprobe",
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_streams",
        "-show_format",
        path,
    ]
    # ffprobe 在极少数情况下会遇到“文件刚写完/还未落盘完成”的瞬态错误，
    # 例如: moov atom not found / Invalid data found...。这里做一个轻量重试，
    # 同时把 stderr 带上，便于定位真正的坏文件。
    last_err = ""
    for attempt in range(3):
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if proc.returncode == 0:
            return json.loads(proc.stdout or "{}")
        last_err = (proc.stderr or "").strip()
        # 常见的“容器头不完整/文件损坏”错误：通常重试无效，但重试成本极低；
        # 其他错误也可能是短暂 I/O 抖动，因此统一重试 2 次。
        if attempt < 2:
            time.sleep(0.2)
    raise RuntimeError(f"ffprobe failed: {last_err}")


def _media_has_audio_stream(path: str) -> bool:
    try:
        info = _ffprobe_json(path)
        streams = info.get("streams") or []
        if not isinstance(streams, list):
            return False
        return any(isinstance(s, dict) and s.get("codec_type") == "audio" for s in streams)
    except Exception:
        # 兼容坏文件/不完整文件：视作“无音频/不可复用”，交由上层删掉并重建
        return False


def _mtime(path: str) -> float:
    try:
        return os.path.getmtime(path)
    except Exception:
        return 0.0


def _get_media_duration_seconds(path: str) -> float:
    info = _ffprobe_json(path)
    fmt = (info.get("format") or {}) if isinstance(info, dict) else {}
    dur = fmt.get("duration")
    try:
        d = float(dur)
        if math.isfinite(d) and d > 0:
            return d
    except Exception:
        pass

    # fallback: try audio stream duration
    streams = info.get("streams") or []
    if isinstance(streams, list):
        for s in streams:
            if not isinstance(s, dict):
                continue
            d2 = s.get("duration")
            try:
                d = float(d2)
                if math.isfinite(d) and d > 0:
                    return d
            except Exception:
                continue
    raise RuntimeError(f"无法获取媒体时长: {path}")


def _get_video_props(path: str) -> Tuple[int, int, float]:
    info = _ffprobe_json(path)
    streams = info.get("streams") or []
    if not isinstance(streams, list):
        raise RuntimeError("ffprobe streams 解析失败")
    v = None
    for s in streams:
        if isinstance(s, dict) and s.get("codec_type") == "video":
            v = s
            break
    if not v:
        raise RuntimeError("未找到视频流")
    w = int(v.get("width") or 0)
    h = int(v.get("height") or 0)
    r = str(v.get("r_frame_rate") or "0/0")
    m = re.match(r"^\s*(\d+)\s*/\s*(\d+)\s*$", r)
    fps = 0.0
    if m:
        num = float(m.group(1))
        den = float(m.group(2)) if float(m.group(2)) != 0 else 1.0
        fps = num / den
    if w <= 0 or h <= 0:
        raise RuntimeError("无法解析视频分辨率")
    if not (fps > 0):
        fps = 30.0
    return w, h, fps


def _safe_name(i: int) -> str:
    return f"{i:03d}"

def _ffconcat_quote(path: str) -> str:
    # concat demuxer list: single-quoted; escape quote as: '\'' (ffmpeg doc style)
    return "'" + path.replace("'", "'\\''") + "'"


def _ffconcat_file_line(segment_path: str) -> str:
    # 相对路径会按 concat 列表所在目录解析，易与 output/generated 叠加成双路径；用绝对路径。
    # Windows 下 FFmpeg 对 concat 列表中的反斜杠路径偶发解析异常，统一为正斜杠。
    ap = os.path.abspath(os.path.normpath(segment_path))
    return f"file {_ffconcat_quote(ap.replace(chr(92), '/'))}\n"


async def _tts_one(
    sem: asyncio.Semaphore,
    text: str,
    out_path: str,
    voice: str,
    rate: str,
    volume: str,
) -> None:
    async with sem:
        communicate = edge_tts.Communicate(text=text, voice=voice, rate=rate, volume=volume)
        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        await communicate.save(out_path)


@dataclass
class _SegmentPlan:
    index: int
    text: str
    shot_start: float
    shot_end: float
    shot_id: Any
    score: float
    audio_path: str
    segment_path: str


def run_generate_video(config_path: str = None) -> str:
    """
    根据解说文案生成配音，并合并匹配到的第一个镜头，最终拼接为一个视频。

    依赖 config.json:
      - video.path: inputFile/video_1.mp4
      - generate_video:
          input_match_json: output/copywriting_to_shots_global_path.json
          output_dir: output/generated
          output_video: output/generated/final.mp4
          tts:
            voice: zh-CN-XiaoxiaoNeural
            rate: +0%
            volume: +0%
            concurrency: 8
          top_match_index: 0
          max_items: 0
    """
    project_root = os.path.dirname(os.path.dirname(__file__))
    if config_path is None:
        config_path = os.path.join(project_root, "config.json")

    cfg = _read_json(config_path) if os.path.exists(config_path) else {}
    v_path = (cfg.get("video") or {}).get("path") or "inputFile/video_1.mp4"
    v_abs = _abs_path(project_root, v_path)

    gcfg = cfg.get("generate_video") or {}
    input_match_json = gcfg.get("input_match_json") or "output/copywriting_to_shots_global_path.json"
    out_dir = gcfg.get("output_dir") or "output/generated"
    out_video = gcfg.get("output_video") or os.path.join(out_dir, "final.mp4")
    top_match_index = int(gcfg.get("top_match_index", 0) or 0)
    max_items = int(gcfg.get("max_items", 0) or 0)

    tts_cfg = (gcfg.get("tts") or {}) if isinstance(gcfg.get("tts") or {}, dict) else {}
    voice = tts_cfg.get("voice") or "zh-CN-XiaoxiaoNeural"
    rate = tts_cfg.get("rate") or "+0%"
    volume = tts_cfg.get("volume") or "+0%"
    tts_concurrency = int(tts_cfg.get("concurrency", 8) or 1)
    segment_concurrency = int(gcfg.get("segment_concurrency", 2) or 1)
    reuse_existing = bool(gcfg.get("reuse_existing", True))

    match_abs = _abs_path(project_root, input_match_json)
    out_dir_abs = _abs_path(project_root, out_dir)
    out_video_abs = _abs_path(project_root, out_video)

    os.makedirs(out_dir_abs, exist_ok=True)
    audio_dir = os.path.join(out_dir_abs, "audio")
    seg_dir = os.path.join(out_dir_abs, "segments")
    os.makedirs(audio_dir, exist_ok=True)
    os.makedirs(seg_dir, exist_ok=True)

    match_payload = _read_json(match_abs)
    results = match_payload.get("results") if isinstance(match_payload, dict) else None
    if not isinstance(results, list):
        raise ValueError("input_match_json 格式不正确，必须包含 results 数组")

    if max_items and max_items > 0:
        results = results[:max_items]

    # 统一输出参数，保证 concat 可直接 copy
    w, h, fps = _get_video_props(v_abs)
    target_fps = float(round(fps, 3))

    plans: List[_SegmentPlan] = []
    for r in results:
        if not isinstance(r, dict):
            continue
        idx = int(r.get("item_index") if r.get("item_index") is not None else len(plans))
        text = (r.get("text") or "").strip()
        matches = r.get("matches") or []
        if not text:
            continue
        if not isinstance(matches, list) or len(matches) <= top_match_index:
            continue
        m = matches[top_match_index]
        if not isinstance(m, dict):
            continue
        shot_start = float(m.get("start") or 0.0)
        shot_end = float(m.get("end") or 0.0)
        if not (shot_end > shot_start):
            continue
        shot_id = m.get("shot_id")
        score = float(m.get("score") or 0.0)

        base = _safe_name(len(plans))
        audio_path = os.path.join(audio_dir, f"item_{base}.mp3")
        segment_path = os.path.join(seg_dir, f"seg_{base}.mp4")
        plans.append(
            _SegmentPlan(
                index=idx,
                text=text,
                shot_start=shot_start,
                shot_end=shot_end,
                shot_id=shot_id,
                score=score,
                audio_path=audio_path,
                segment_path=segment_path,
            )
        )

    if not plans:
        raise RuntimeError("没有可生成的片段（results 为空或缺少 matches[0]）")

    # 1) 并发生成配音
    async def _run_tts_all() -> None:
        sem = asyncio.Semaphore(max(1, tts_concurrency))
        tasks = [
            _tts_one(sem, p.text, p.audio_path, voice=voice, rate=rate, volume=volume)
            for p in plans
        ]
        await asyncio.gather(*tasks)

    # Windows 下直接 asyncio.run() 偶发出现 Proactor transport 的 “Event loop is closed” 噪音；
    # 这里显式创建/关闭 event loop，避免输出干扰。
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_run_tts_all())
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        try:
            asyncio.set_event_loop(None)
        finally:
            loop.close()

    # 2) 并发合成片段：截取镜头 -> 按音频时长裁剪/延长 -> 合并音频
    def _build_one_segment(idx_p: int, p: _SegmentPlan) -> Dict[str, Any]:
        if reuse_existing and os.path.exists(p.segment_path):
            # 仅当 segment 已包含音频，且比 mp3 新时才复用；
            # 否则容易复用旧 segment，导致最终视频看起来“没有拼上配音”。
            try:
                # 先做一个极轻量的完整性判断，避免对明显坏文件跑 ffprobe（也能减少噪音报错）。
                # mp4 正常情况下不应该是 0 字节或极小文件（通常是上次中断留下的残骸）。
                seg_size = 0
                try:
                    seg_size = int(os.path.getsize(p.segment_path))
                except Exception:
                    seg_size = 0

                seg_has_audio = seg_size > 1024 and _media_has_audio_stream(p.segment_path)
                seg_new_enough = _mtime(p.segment_path) >= _mtime(p.audio_path)
                if seg_has_audio and seg_new_enough:
                    audio_dur = _get_media_duration_seconds(p.audio_path)
                    clip_dur = p.shot_end - p.shot_start
                    return {
                        "item_index": p.index,
                        "text": p.text,
                        "shot_id": p.shot_id,
                        "score": p.score,
                        "shot_start": p.shot_start,
                        "shot_end": p.shot_end,
                        "audio_path": os.path.relpath(p.audio_path, project_root),
                        "segment_path": os.path.relpath(p.segment_path, project_root),
                        "audio_duration": audio_dur,
                        "shot_duration": clip_dur,
                        "reused": True,
                    }
            finally:
                # 走到这里代表“不满足复用条件”或 segment 已损坏：删掉后重建，避免后续 concat 失败。
                try:
                    os.remove(p.segment_path)
                except Exception:
                    pass

        print(f"[step5] build segment {idx_p+1}/{len(plans)} item_index={p.index} shot_id={p.shot_id} score={p.score:.3f}")
        audio_dur = _get_media_duration_seconds(p.audio_path)
        clip_dur = p.shot_end - p.shot_start
        need_pad = audio_dur > clip_dur
        pad_sec = max(0.0, audio_dur - clip_dur) if need_pad else 0.0

        vf = f"scale={w}:{h},fps={target_fps}"
        if need_pad and pad_sec > 0:
            vf = vf + f",tpad=stop_mode=clone:stop_duration={pad_sec:.3f}"

        args = [
            "ffmpeg",
            "-y",
            "-ss",
            f"{p.shot_start:.3f}",
            "-i",
            v_abs,
            "-i",
            p.audio_path,
            # 显式选择：视频来自输入0，音频来自输入1（配音）
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-t",
            f"{audio_dur:.3f}",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            p.segment_path,
        ]
        _run_cmd(args)

        return {
            "item_index": p.index,
            "text": p.text,
            "shot_id": p.shot_id,
            "score": p.score,
            "shot_start": p.shot_start,
            "shot_end": p.shot_end,
            "audio_path": os.path.relpath(p.audio_path, project_root),
            "segment_path": os.path.relpath(p.segment_path, project_root),
            "audio_duration": audio_dur,
            "shot_duration": clip_dur,
            "reused": False,
        }

    segment_infos: List[Optional[Dict[str, Any]]] = [None] * len(plans)
    with ThreadPoolExecutor(max_workers=max(1, segment_concurrency)) as ex:
        futs = {ex.submit(_build_one_segment, i, p): i for i, p in enumerate(plans)}
        for fut in as_completed(futs):
            i = futs[fut]
            segment_infos[i] = fut.result()

    segment_infos_out = [x for x in segment_infos if x is not None]

    # 3) concat 拼接
    concat_list = os.path.join(out_dir_abs, "concat_list.txt")
    with open(concat_list, "w", encoding="utf-8") as f:
        for p in plans:
            f.write(_ffconcat_file_line(p.segment_path))

    _run_cmd(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            concat_list,
            "-c",
            "copy",
            out_video_abs,
        ]
    )

    meta_out = os.path.join(out_dir_abs, "build_meta.json")
    _write_json(
        meta_out,
        {
            "meta": {
                "video_path": v_path,
                "input_match_json": input_match_json,
                "voice": voice,
                "rate": rate,
                "volume": volume,
                "tts_concurrency": tts_concurrency,
                "segment_concurrency": segment_concurrency,
                "reuse_existing": reuse_existing,
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime()),
            },
            "segments": segment_infos_out,
            "output_video": os.path.relpath(out_video_abs, project_root),
        },
    )

    return out_video_abs


if __name__ == "__main__":
    out = run_generate_video()
    print(out)

