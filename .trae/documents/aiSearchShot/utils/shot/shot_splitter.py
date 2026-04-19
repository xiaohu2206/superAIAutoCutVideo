import json
import os
import shutil
import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

from .shot_detector import ShotDetector, Shot
from .srt_parser import SRTParser, Subtitle
from .shot_subtitle_mapper import ShotSubtitleMapper


logger = logging.getLogger("AIShotSearch")


class ShotSplitter:
    def __init__(self, model_path: str):
        self.shot_detector = ShotDetector(model_path)
        self.srt_parser = SRTParser()
        self.mapper = ShotSubtitleMapper()
    
    def process(
        self,
        video_path: str,
        srt_path: str,
        output_path: Optional[str] = None,
        merge_shots: bool = False,
        export_clips: bool = True,
        export_raw_clips: bool = True,
        min_overlap_ratio: float = 0.4,
        short_shot_threshold: float = 1.4,
        max_segment_duration: float = 6.0
    ) -> Dict[str, Any]:
        t0 = time.time()
        logger.info(f"[step1] ShotSplitter.process 开始 video={video_path} srt={srt_path} merge_shots={merge_shots}")

        detect_t0 = time.time()
        shots = self.shot_detector.detect_shots(video_path)
        logger.info(f"[step1] 镜头检测完成 shots={len(shots)} elapsed={time.time() - detect_t0:.2f}s")

        srt_t0 = time.time()
        subtitles = self.srt_parser.parse(srt_path)
        logger.info(f"[step1] 字幕解析完成 subtitles={len(subtitles)} elapsed={time.time() - srt_t0:.2f}s")

        map_t0 = time.time()
        shots_raw = self.mapper.map_subtitles_to_shots(shots, subtitles)
        logger.info(f"[step1] 字幕映射完成 shots_raw={len(shots_raw)} elapsed={time.time() - map_t0:.2f}s")

        seg_t0 = time.time()
        segments_semantic = self.mapper.build_semantic_segments(
            shots_raw,
            min_overlap_ratio=min_overlap_ratio,
            short_shot_threshold=short_shot_threshold,
            max_segment_duration=max_segment_duration
        )
        logger.info(
            f"[step1] 语义段构建完成 segments_semantic={len(segments_semantic)} elapsed={time.time() - seg_t0:.2f}s"
        )
        
        shots_for_export = shots_raw
        
        if merge_shots:
            merge_t0 = time.time()
            shots_for_export = self.mapper.merge_shots_by_subtitle(
                shots_raw,
                min_overlap_ratio=min_overlap_ratio,
                short_shot_threshold=short_shot_threshold,
                max_segment_duration=max_segment_duration
            )
            logger.info(
                f"[step1] 合并镜头完成 merged_shots={len(shots_for_export)} elapsed={time.time() - merge_t0:.2f}s"
            )
        
        result = self._build_result(
            shots_raw=shots_raw,
            segments_semantic=segments_semantic,
            video_path=video_path,
            srt_path=srt_path,
            merge_shots=merge_shots
        )
        
        if output_path:
            save_t0 = time.time()
            self._save_result(result, output_path)
            logger.info(f"[step1] JSON 写入完成 elapsed={time.time() - save_t0:.2f}s path={output_path}")
        
        if export_clips:
            base_output_dir = os.path.join(os.path.dirname(__file__), 'output')
            if output_path:
                clip_dir = os.path.join(os.path.dirname(output_path), Path(output_path).stem)
            else:
                video_name = Path(video_path).stem
                clip_dir = os.path.join(base_output_dir, f'{video_name}_shots')
            export_t0 = time.time()
            logger.info(f"[step1] 开始导出 clips count={len(shots_for_export)} dir={clip_dir}")
            self._export_shot_clips(video_path, shots_for_export, clip_dir)
            logger.info(f"[step1] clips 导出完成 elapsed={time.time() - export_t0:.2f}s dir={clip_dir}")
            result['clip_dir'] = clip_dir
            result['clip_files'] = sorted([os.path.join(clip_dir, f) for f in os.listdir(clip_dir)]) if os.path.exists(clip_dir) else []
            
            if export_raw_clips and merge_shots:
                if output_path:
                    raw_dir = os.path.join(os.path.dirname(output_path), f"{Path(output_path).stem}_raw")
                else:
                    video_name = Path(video_path).stem
                    raw_dir = os.path.join(base_output_dir, f"{video_name}_shots_raw")
                raw_t0 = time.time()
                logger.info(f"[step1] 开始导出 raw_clips count={len(shots_raw)} dir={raw_dir}")
                self._export_shot_clips(video_path, shots_raw, raw_dir)
                logger.info(f"[step1] raw_clips 导出完成 elapsed={time.time() - raw_t0:.2f}s dir={raw_dir}")
                result['raw_clip_dir'] = raw_dir
                result['raw_clip_files'] = sorted([os.path.join(raw_dir, f) for f in os.listdir(raw_dir)]) if os.path.exists(raw_dir) else []
        
        logger.info(f"[step1] ShotSplitter.process 完成 elapsed={time.time() - t0:.2f}s")
        return result
    
    def _build_result(
        self,
        shots_raw: List[Shot],
        segments_semantic: List[Dict[str, Any]],
        video_path: str,
        srt_path: str,
        merge_shots: bool
    ) -> Dict[str, Any]:
        shots_raw_data = []
        
        for shot in shots_raw:
            shot_dict = {
                'shot_id': shot.shot_id,
                'start': round(shot.start, 3),
                'end': round(shot.end, 3),
                'duration': round(shot.end - shot.start, 3),
                'subtitles': shot.subtitles,
                'subtitle_full_text': ShotSubtitleMapper.get_full_subtitle_text(shot)
            }
            shots_raw_data.append(shot_dict)

        if merge_shots:
            shots_data = [
                {
                    'shot_id': segment['segment_id'],
                    'start': segment['start'],
                    'end': segment['end'],
                    'duration': segment['duration'],
                    'subtitles': segment['subtitles'],
                    'subtitle_full_text': segment['subtitle_full_text']
                }
                for segment in segments_semantic
            ]
        else:
            shots_data = shots_raw_data
        
        result = {
            'video_path': video_path,
            'srt_path': srt_path,
            'total_shots_raw': len(shots_raw_data),
            'total_segments_semantic': len(segments_semantic),
            'shots_raw': shots_raw_data,
            'segments_semantic': segments_semantic,
            'total_shots': len(shots_data),
            'total_duration': round(shots_raw[-1].end, 3) if shots_raw else 0,
            'shots': shots_data
        }
        
        return result
    
    def _save_result(self, result: Dict[str, Any], output_path: str):
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        logger.info(f"[step1] 结果已保存到: {output_path}")
    
    def _export_shot_clips(self, video_path: str, shots: List[Shot], clip_dir: str):
        import subprocess
        os.makedirs(clip_dir, exist_ok=True)
        ffmpeg_bin = self._get_ffmpeg_bin()
        total = len(shots)
        exported = 0
        failed = 0
        export_t0 = time.time()
        for idx, shot in enumerate(shots, start=1):
            if shot.end <= shot.start:
                continue
            out_path = os.path.join(clip_dir, f'shot_{shot.shot_id:03d}.mp4')
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", video_path,
                "-ss", f"{shot.start:.3f}",
                "-to", f"{shot.end:.3f}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-movflags", "+faststart",
                out_path,
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
                exported += 1
            except Exception as e:
                failed += 1
                err = ""
                try:
                    err = getattr(e, "stderr", b"")[:400].decode("utf-8", "ignore") if getattr(e, "stderr", None) else ""
                except Exception:
                    err = ""
                logger.warning(
                    f"[step1] ffmpeg 导出失败 idx={idx}/{total} shot_id={shot.shot_id} start={shot.start:.3f} end={shot.end:.3f} err={str(e)} {err}".strip()
                )

            # 进度：第 1 个、每 10 个、最后 1 个都打点，避免长视频看起来“卡住”
            if idx == 1 or idx % 10 == 0 or idx == total:
                logger.info(
                    f"[step1] clips 导出进度 {idx}/{total} exported={exported} failed={failed} elapsed={time.time() - export_t0:.2f}s"
                )

    @staticmethod
    def _get_ffmpeg_bin() -> str:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            return get_ffmpeg_exe()
        except ModuleNotFoundError:
            ffmpeg_bin = shutil.which("ffmpeg")
            if ffmpeg_bin:
                return ffmpeg_bin
            raise ModuleNotFoundError(
                "缺少 imageio_ffmpeg 且系统中未找到 ffmpeg。请执行 `pip install imageio-ffmpeg` "
                "或安装系统 ffmpeg（macOS 可用 `brew install ffmpeg`）。"
            )
    
    @staticmethod
    def process_video(
        video_path: str,
        srt_path: str,
        model_path: str,
        output_path: Optional[str] = None,
        merge_shots: bool = False,
        export_clips: bool = True,
        export_raw_clips: bool = True,
        min_overlap_ratio: float = 0.4,
        short_shot_threshold: float = 1.4,
        max_segment_duration: float = 6.0
    ) -> Dict[str, Any]:
        splitter = ShotSplitter(model_path)
        return splitter.process(
            video_path,
            srt_path,
            output_path,
            merge_shots,
            export_clips,
            export_raw_clips,
            min_overlap_ratio,
            short_shot_threshold,
            max_segment_duration
        )
