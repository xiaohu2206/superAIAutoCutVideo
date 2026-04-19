import os
import sys
import json
import time
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

from utils import ShotSplitter
from utils import extract_quarter_frames, build_model_client
from copywritingStructuring import run_copywriting_structuring
from copywritingEmbeddings import run_copywriting_embeddings
from searchShots import run_search_shots
from reRank import run_rerank
from globalPathSearch import run_global_path_search
from highlightNarrationScript import run_highlight_narration_script


logger = logging.getLogger("AIShotSearch")


def _ensure_logging_configured(level: int = logging.INFO):
    """
    确保 logger 至少有一个 stdout handler。
    场景：当从别的模块/脚本调用本文件函数时，可能不会走到 __main__ 的 basicConfig，导致终端“无状态”。
    """
    root = logging.getLogger()
    if not root.handlers:
        handler = logging.StreamHandler(stream=sys.stdout)
        handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
        root.addHandler(handler)
    root.setLevel(level)


def build_shot_embedding_summary(visual: dict, subtitle_text: str, prompt_language: str = "zh") -> str:
    language = str(prompt_language or "zh").strip().lower()

    raw_objects = visual.get("objects") or []
    if isinstance(raw_objects, (list, tuple)):
        object_items = [str(o).strip() for o in raw_objects if str(o).strip()]
    elif isinstance(raw_objects, str):
        object_items = [s.strip() for s in raw_objects.split(",") if s.strip()]
    else:
        object_items = []
    seen = set()
    deduped_objects: list = []
    for o in object_items:
        if o in seen:
            continue
        seen.add(o)
        deduped_objects.append(o)

    desc = str(visual.get("desc", "") or "").strip()
    brief = str(visual.get("brief", "") or "").strip()
    action = str(visual.get("action", "") or "").strip()
    scene = str(visual.get("scene", "") or "").strip()
    emotion = str(visual.get("emotion", "") or "").strip()
    subtitle = str(subtitle_text or "").strip()

    if language == "en":
        objects_text = ", ".join(deduped_objects)
        lines = [f"Visual: {desc}"]
        if brief and brief != desc:
            lines.append(f"Brief: {brief}")
        lines.extend([
            f"Action: {action}",
            f"Scene: {scene}",
            f"Objects: {objects_text}",
            f"Emotion: {emotion}",
            f"Subtitles: {subtitle}",
        ])
        return "\n".join(lines).strip()

    objects_text = "、".join(deduped_objects)
    lines = [f"画面：{desc}"]
    if brief and brief != desc:
        lines.append(f"简述：{brief}")
    lines.extend([
        f"动作：{action}",
        f"场景：{scene}",
        f"物体：{objects_text}",
        f"情绪：{emotion}",
        f"字幕：{subtitle}",
    ])
    return "\n".join(lines).strip()


def split_shots(
    video_path: str,
    srt_path: str,
    output_path: str = None,
    model_path: str = None,
    merge_shots: bool = True,
    export_clips: bool = True,
    export_raw_clips: bool = True
):
    _ensure_logging_configured()
    if model_path is None:
        model_path = os.path.join(os.path.dirname(__file__), 'models', 'transnetv2-weights')

    if output_path is None:
        video_name = Path(video_path).stem
        output_path = os.path.join(os.path.dirname(__file__), 'output', f'{video_name}_shots.json')

    logger.info(
        "[step1] 开始镜头切分 "
        f"video={video_path} srt={srt_path} output={output_path} model={model_path} "
        f"merge_shots={merge_shots} export_clips={export_clips} export_raw_clips={export_raw_clips}"
    )

    splitter = ShotSplitter(model_path)
    t0 = time.time()
    result = splitter.process(video_path, srt_path, output_path, merge_shots, export_clips, export_raw_clips)
    elapsed = time.time() - t0

    logger.info(
        f"[step1] 镜头切分完成 elapsed={elapsed:.2f}s total_shots={result.get('total_shots')} "
        f"total_shots_raw={result.get('total_shots_raw')} total_segments_semantic={result.get('total_segments_semantic')}"
    )
    return result


def _read_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _write_json(path: str, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def run_step2_multimodal_features(config_path: str = None):
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")

    cfg = _read_json(config_path)
    shots_json = cfg["input"]["shots_json"]
    video_path = cfg["video"]["path"]
    out_frames_dir = cfg["output"]["frames_dir"]
    out_result_json = cfg["output"]["result_json"]

    data = _read_json(os.path.join(os.path.dirname(__file__), shots_json) if not os.path.isabs(shots_json) else shots_json)
    video_path_abs = os.path.join(os.path.dirname(__file__), video_path) if not os.path.isabs(video_path) else video_path

    step2_cfg = cfg.get("step2_multimodal_features") or {}
    prompt_language = str((cfg.get("copywriting_structuring") or {}).get("prompt_language") or "zh").strip().lower()
    client = build_model_client(cfg)
    model_cfg = cfg.get("custom_openai") if str((cfg.get("model_provider") or "yunwu")).strip().lower() in {"custom", "custom_openai", "openai_compatible"} else cfg.get("yunwu")
    model_cfg = model_cfg or {}
    vl_model = model_cfg.get("vl_model", "qwen3-vl-flash")
    emb_model = model_cfg.get("embedding_model", "text-embedding-3-large")

    shots = data.get("shots") or []
    enriched = [None] * len(shots)
    continue_on_error = bool(step2_cfg.get("continue_on_error", True))
    save_every_n = int(step2_cfg.get("save_every_n", 5) or 0)
    max_retries = int(step2_cfg.get("max_retries", 2) or 0)
    retry_sleep_seconds = float(step2_cfg.get("retry_sleep_seconds", 2) or 0)
    max_image_long_edge = int(step2_cfg.get("vl_image_max_long_edge", 1280) or 0)
    vl_jpeg_quality = int(step2_cfg.get("vl_jpeg_quality", 85) or 85)
    concurrency = int(step2_cfg.get("concurrency", 8) or 1)
    frame_concurrency = int(step2_cfg.get("frame_concurrency", concurrency) or 1)
    model_concurrency = int(step2_cfg.get("model_concurrency", concurrency) or 1)
    dispatch_sleep_seconds = float(step2_cfg.get("dispatch_sleep_seconds", 1.0) or 0)

    provider = str((cfg.get("model_provider") or "yunwu")).strip().lower()
    provider_cfg = (
        cfg.get("custom_openai")
        if provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}
    embedding_provider = str(provider_cfg.get("embedding_provider") or provider).strip().lower()
    embedding_cfg = (
        cfg.get("custom_openai")
        if embedding_provider in {"custom", "custom_openai", "openai_compatible"}
        else cfg.get("yunwu")
    ) or {}

    out_path_abs = os.path.join(os.path.dirname(__file__), out_result_json) if not os.path.isabs(out_result_json) else out_result_json

    out_frames_abs = os.path.join(os.path.dirname(__file__), out_frames_dir) if not os.path.isabs(out_frames_dir) else out_frames_dir

    logger.info(
        f"[step2] 配置加载完成 total_shots={len(shots)} frame_concurrency={frame_concurrency} model_concurrency={model_concurrency} dispatch_sleep_seconds={dispatch_sleep_seconds} continue_on_error={continue_on_error} save_every_n={save_every_n} max_retries={max_retries} retry_sleep_seconds={retry_sleep_seconds} vl_image_max_long_edge={max_image_long_edge} vl_jpeg_quality={vl_jpeg_quality} vl_model={vl_model} emb_model={emb_model}"
    )

    completed = 0
    success_count = 0
    fail_count = 0
    lock = threading.Lock()
    frame_map = [None] * len(shots)

    def _extract_one_frame(shot_index: int, shot_obj: dict):
        t0 = time.time()
        shot_id = shot_obj.get("shot_id")
        try:
            frame_paths = extract_quarter_frames(video_path_abs, shot_obj, out_frames_abs)
            elapsed = time.time() - t0
            return shot_index, True, frame_paths, elapsed, None, shot_id
        except Exception as e:
            elapsed = time.time() - t0
            if not continue_on_error:
                raise
            return shot_index, False, None, elapsed, str(e), shot_id

    def _process_one(shot_index: int, shot_obj: dict, frame_paths: list):
        t0 = time.time()
        shot_id = shot_obj.get("shot_id")
        try:
            subtitle_text = shot_obj.get("subtitle_full_text", "") or ""
            logger.info(
                f"[step2] shot_id={shot_id} shot_index={shot_index} 开始多模态处理 frames={frame_paths} subtitle_len={len(subtitle_text)}"
            )

            visual_start = time.time()
            visual = client.analyze_shot_frame(
                model=vl_model,
                image_paths=list(frame_paths or []),
                subtitle_text=subtitle_text,
                prompt_language=prompt_language,
                max_retries=max_retries,
                retry_sleep_seconds=retry_sleep_seconds,
                max_image_long_edge=max_image_long_edge,
                vl_jpeg_quality=vl_jpeg_quality,
                log_context={
                    "shot_id": shot_id,
                    "shot_index": shot_index,
                    "frame_paths": frame_paths,
                },
            )
            visual_elapsed = time.time() - visual_start
            logger.info(
                f"[step2] shot_id={shot_id} shot_index={shot_index} 视觉分析完成 elapsed={visual_elapsed:.2f}s action={visual.get('action', '')!r} scene={visual.get('scene', '')!r} emotion={visual.get('emotion', '')!r}"
            )

            subtitle = {
                "full_text": subtitle_text,
                "segments": shot_obj.get("subtitles", []) or [],
            }
            summary = build_shot_embedding_summary(visual, subtitle_text, prompt_language)
            logger.info(
                f"[step2] shot_id={shot_id} shot_index={shot_index} summary已生成 summary_len={len(summary)}"
            )

            embedding_start = time.time()
            embedding = client.embed_text(
                model=emb_model,
                text=summary,
                max_retries=max_retries,
                retry_sleep_seconds=retry_sleep_seconds,
                provider_override=(embedding_provider, embedding_cfg),
            )
            embedding_elapsed = time.time() - embedding_start
            logger.info(
                f"[step2] shot_id={shot_id} shot_index={shot_index} 向量生成完成 elapsed={embedding_elapsed:.2f}s dim={len(embedding) if isinstance(embedding, list) else 0}"
            )

            item = dict(shot_obj)
            item["frames"] = list(frame_paths or [])
            item["subtitle"] = subtitle
            item["visual"] = visual
            item["summary"] = summary
            item["embedding"] = embedding

            elapsed = time.time() - t0
            return shot_index, True, item, elapsed, None, shot_id
        except Exception as e:
            elapsed = time.time() - t0
            logger.exception(
                f"[step2] shot_id={shot_id} shot_index={shot_index} 多模态处理异常 elapsed={elapsed:.2f}s"
            )
            if not continue_on_error:
                raise
            item = dict(shot_obj)
            item["frames"] = list(frame_paths or [])
            item["error"] = str(e)
            return shot_index, False, item, elapsed, str(e), shot_id

    with ThreadPoolExecutor(max_workers=max(1, frame_concurrency)) as ex:
        frame_futures = {
            ex.submit(_extract_one_frame, i, shot): i
            for i, shot in enumerate(shots)
        }
        frame_completed = 0
        frame_success_count = 0
        frame_fail_count = 0
        for fut in as_completed(frame_futures):
            shot_index, ok, frame_paths, elapsed, err, shot_id = fut.result()
            frame_completed += 1
            if ok:
                frame_success_count += 1
                frame_map[shot_index] = frame_paths
                logger.info(f"[step2] shot_id={shot_id} 抽帧成功 elapsed={elapsed:.2f}s ({frame_completed}/{len(shots)})")
            else:
                frame_fail_count += 1
                item = dict(shots[shot_index])
                item["error"] = err
                enriched[shot_index] = item
                logger.error(f"[step2] shot_id={shot_id} 抽帧失败 elapsed={elapsed:.2f}s err={err} ({frame_completed}/{len(shots)})")

        logger.info(
            f"[step2] 抽帧阶段完成 total={len(shots)} success={frame_success_count} fail={frame_fail_count}"
        )

    model_tasks = [
        (i, shot, frame_paths)
        for i, (shot, frame_paths) in enumerate(zip(shots, frame_map))
        if frame_paths
    ]
    logger.info(
        f"[step2] 模型阶段任务已准备 ready={len(model_tasks)} skipped={len(shots) - len(model_tasks)} dispatch_sleep_seconds={dispatch_sleep_seconds}"
    )

    with ThreadPoolExecutor(max_workers=max(1, model_concurrency)) as ex:
        futures = {}
        for i, shot, frame_paths in model_tasks:
            if futures:
                time.sleep(dispatch_sleep_seconds)
            futures[ex.submit(_process_one, i, shot, frame_paths)] = i
        for fut in as_completed(futures):
            shot_index, ok, item, elapsed, err, shot_id = fut.result()
            with lock:
                enriched[shot_index] = item
                completed += 1
                if ok:
                    success_count += 1
                    logger.info(f"[step2] shot_id={shot_id} 多模态特征提取成功： elapsed={elapsed:.2f}s ({completed}/{len(shots)})")
                else:
                    fail_count += 1
                    logger.error(f"[step2] shot_id={shot_id} 多模态特征提取失败 elapsed={elapsed:.2f}s err={err} ({completed}/{len(shots)})")

                if save_every_n > 0 and (completed % save_every_n == 0):
                    result = dict(data)
                    result["shots"] = [x for x in enriched if x is not None]
                    _write_json(out_path_abs, result)

    logger.info(
        f"[step2] 处理完成 total={len(shots)} success={success_count} fail={fail_count}"
    )

    result = dict(data)
    result["shots"] = [x for x in enriched if x is not None]

    _write_json(out_path_abs, result)
    return out_path_abs


def run_step1_shot_split(config_path: str = None):
    _ensure_logging_configured()
    if config_path is None:
        config_path = os.path.join(os.path.dirname(__file__), "config.json")
    cfg = _read_json(config_path)

    video_path = cfg["video"]["path"]
    video_path_abs = os.path.join(os.path.dirname(__file__), video_path) if not os.path.isabs(video_path) else video_path

    srt_path = cfg.get("srt", {}).get("path") or cfg.get("input", {}).get("srt_path") or "inputFile/video_1.srt"
    srt_path_abs = os.path.join(os.path.dirname(__file__), srt_path) if not os.path.isabs(srt_path) else srt_path

    step1 = cfg.get("step1_shot_split") or {}
    output_path = step1.get("output_shots_json") or "output/video_1_shots.json"
    output_path_abs = os.path.join(os.path.dirname(__file__), output_path) if not os.path.isabs(output_path) else output_path
    model_path = step1.get("model_path")
    model_path_abs = (
        os.path.join(os.path.dirname(__file__), model_path)
        if (model_path and not os.path.isabs(model_path))
        else model_path
    )

    merge_shots = bool(step1.get("merge_shots", True))
    export_clips = bool(step1.get("export_clips_to_output_video_1_shots", False))
    export_raw_clips = bool(step1.get("export_raw_clips_to_output_video_1_shots_raw", False))

    logger.info(
        "[step1] 配置解析完成 "
        f"config={config_path} video={video_path_abs} srt={srt_path_abs} output={output_path_abs} model={model_path_abs} "
        f"merge_shots={merge_shots} export_clips={export_clips} export_raw_clips={export_raw_clips}"
    )
    result = split_shots(
        video_path=video_path_abs,
        srt_path=srt_path_abs,
        output_path=output_path_abs,
        model_path=model_path_abs,
        merge_shots=merge_shots,
        export_clips=export_clips,
        export_raw_clips=export_raw_clips,
    )
    return output_path_abs, result


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    config_path = os.path.join(os.path.dirname(__file__), "config.json")
    cfg = _read_json(config_path) if os.path.exists(config_path) else {}
    step = cfg.get("step")

    if step == "step2_multimodal_features":
        out_path = run_step2_multimodal_features(config_path)
        print(f"Step2 完成！结果已保存到: {out_path}")
    elif step == "step1_shot_split":
        out_path, result = run_step1_shot_split(config_path)
        print(f"Step1 完成！共输出 {result['total_shots']} 个语义段（原始镜头 {result.get('total_shots_raw', result['total_shots'])}）")
        print(f"结果已保存到: {out_path}")
    elif step == "step3_copywriting_structuring":
        out_path = run_copywriting_structuring(config_path)
        print(f"Step3 完成！结构化文案已保存到: {out_path}")
    elif step == "step3_copywriting_embeddings":
        out_path = run_copywriting_embeddings(config_path)
        print(f"Step3 完成！结果已保存到: {out_path}")
    elif step == "step4_search_shots":
        out_path = run_search_shots(config_path)
        print(f"Step4 完成！结果已保存到: {out_path}")
    elif step == "step4_5_rerank":
        out_path = run_rerank(config_path)
        print(f"Step4.5 完成！结果已保存到: {out_path}")
    elif step == "step4_8_global_path_search":
        out_path = run_global_path_search(config_path)
        print(f"Step4.8 完成！结果已保存到: {out_path}")
    elif step == "step4_9_highlight_narration_script":
        out_path = run_highlight_narration_script(config_path)
        print(f"Step4.9 完成！结果已保存到: {out_path}")
    elif step == "step5_generate_video":
        from generateVideo import run_generate_video
        out_path = run_generate_video(config_path)
        print(f"Step5 完成！视频已保存到: {out_path}")
    else:
        video_path = os.path.join(os.path.dirname(__file__), 'inputFile', 'video_1.mp4')
        srt_path = os.path.join(os.path.dirname(__file__), 'inputFile', 'video_1.srt')
        output_path = os.path.join(os.path.dirname(__file__), 'output', 'video_1_shots.json')
        
        result = split_shots(
            video_path=video_path,
            srt_path=srt_path,
            output_path=output_path,
            merge_shots=True,
            export_clips=True,
            export_raw_clips=True
        )
        
        print(f"处理完成！共输出 {result['total_shots']} 个语义段（原始镜头 {result.get('total_shots_raw', result['total_shots'])}）")
        print(f"结果已保存到: {output_path}")
