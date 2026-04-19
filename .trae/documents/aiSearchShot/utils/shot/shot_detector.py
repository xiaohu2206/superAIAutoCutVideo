import json
import os
import logging
from dataclasses import dataclass
from typing import List
import numpy as np

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'

@dataclass
class Shot:
    start: float
    end: float
    shot_id: int = 0
    subtitles: List[dict] = None
    
    def __post_init__(self):
        if self.subtitles is None:
            self.subtitles = []
    
    def to_dict(self):
        return {
            'shot_id': self.shot_id,
            'start': self.start,
            'end': self.end,
            'subtitles': self.subtitles
        }


logger = logging.getLogger("AIShotSearch")


class ShotDetector:
    def __init__(self, model_path: str, threshold: float = 0.5):
        self.model_path = model_path
        self.model = None
        self.threshold = threshold
        self._input_size = (27, 48, 3)
    
    def load_model(self):
        import tensorflow as tf
        logger.info(f"[step1] 开始加载 TransNetV2 模型: {self.model_path}")
        try:
            self.model = tf.saved_model.load(self.model_path)
        except OSError as exc:
            raise IOError(
                f"[TransNetV2] It seems that files in {self.model_path} are corrupted or missing. "
                f"Re-download them manually and retry. For more info, see: "
                f"https://github.com/soCzech/TransNetV2/issues/1#issuecomment-647357796"
            ) from exc
        logger.info("[step1] TransNetV2 模型加载完成")
        return self.model
    
    def detect_shots(self, video_path: str) -> List[Shot]:
        if self.model is None:
            self.load_model()

        logger.info(f"[step1] 开始抽帧 video={video_path}")
        frames = self._extract_frames(video_path)
        logger.info(f"[step1] 抽帧完成 frame_count={len(frames)}")

        if len(frames) == 0:
            logger.warning("[step1] 未抽取到任何视频帧，返回空镜头结果")
            return []

        logger.info("[step1] 开始进行镜头检测推理")
        single_frame_predictions, _ = self.predict_frames(frames)
        logger.info("[step1] 镜头检测推理完成，开始转换场景")
        scenes = self.predictions_to_scenes(single_frame_predictions, threshold=float(self.threshold))
        logger.info(f"[step1] 场景转换完成 scene_count={len(scenes)}")
        return self._scenes_to_shots(scenes, video_path)
    
    def predict_raw(self, frames: np.ndarray):
        import tensorflow as tf
        assert len(frames.shape) == 5 and frames.shape[2:] == self._input_size, \
            "[TransNetV2] Input shape must be [batch, frames, height, width, 3]."
        frames = tf.cast(frames, tf.float32)
        logits, dict_ = self.model(frames)
        single_frame_pred = tf.sigmoid(logits)
        all_frames_pred = tf.sigmoid(dict_["many_hot"])
        return single_frame_pred, all_frames_pred

    def predict_frames(self, frames: np.ndarray):
        assert len(frames.shape) == 4 and frames.shape[1:] == self._input_size, \
            "[TransNetV2] Input shape must be [frames, height, width, 3]."

        def input_iterator():
            no_padded_frames_start = 25
            no_padded_frames_end = 25 + 50 - (len(frames) % 50 if len(frames) % 50 != 0 else 50)

            start_frame = np.expand_dims(frames[0], 0)
            end_frame = np.expand_dims(frames[-1], 0)
            padded_inputs = np.concatenate(
                [start_frame] * no_padded_frames_start + [frames] + [end_frame] * no_padded_frames_end, 0
            )

            ptr = 0
            while ptr + 100 <= len(padded_inputs):
                out = padded_inputs[ptr:ptr + 100]
                ptr += 50
                yield out[np.newaxis]

        total_windows = max(1, (len(frames) - 1) // 50 + 1)
        logger.info(f"[step1] 开始窗口推理 total_windows={total_windows}")

        predictions = []
        for window_index, inp in enumerate(input_iterator(), start=1):
            single_frame_pred, all_frames_pred = self.predict_raw(inp)
            predictions.append((single_frame_pred.numpy()[0, 25:75, 0], all_frames_pred.numpy()[0, 25:75, 0]))
            if window_index == 1 or window_index % 20 == 0 or window_index == total_windows:
                logger.info(f"[step1] 推理进度 {window_index}/{total_windows}")

        single_frame_pred = np.concatenate([single_ for single_, all_ in predictions])
        all_frames_pred = np.concatenate([all_ for single_, all_ in predictions])
        return single_frame_pred[:len(frames)], all_frames_pred[:len(frames)]

    def _extract_frames(self, video_path: str) -> np.ndarray:
        import cv2
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise ValueError(f"无法打开视频文件: {video_path}")
        frames = []
        while True:
            ret, frame = cap.read()
            if not ret:
                break
            frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame = cv2.resize(frame, (48, 27))
            if len(frame.shape) == 3 and frame.shape[2] == 3:
                frames.append(frame)
        cap.release()
        if len(frames) == 0:
            return np.empty((0, 27, 48, 3), dtype=np.uint8)
        return np.array(frames, dtype=np.uint8)

    def _scenes_to_shots(self, scenes: np.ndarray, video_path: str) -> List[Shot]:
        import cv2
        cap = cv2.VideoCapture(video_path)
        fps = cap.get(cv2.CAP_PROP_FPS)
        if fps == 0:
            fps = 25
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        total_duration = (total_frames / fps) if total_frames > 0 else 0.0
        cap.release()

        shots = []
        for i, scene in enumerate(scenes, 1):
            start_frame = int(scene[0])
            end_frame = int(scene[1])
            start_time = start_frame / fps
            end_time = (end_frame + 1) / fps
            if total_duration > 0:
                end_time = min(end_time, total_duration)
            if end_time > start_time:
                shots.append(Shot(start=start_time, end=end_time, shot_id=i))

        if len(shots) == 0 and total_duration > 0:
            shots.append(Shot(start=0.0, end=total_duration, shot_id=1))
        return shots

    @staticmethod
    def predictions_to_scenes(predictions: np.ndarray, threshold: float = 0.5):
        predictions = (predictions > threshold).astype(np.uint8)
        scenes = []
        t, t_prev, start = -1, 0, 0
        for i, t in enumerate(predictions):
            if t_prev == 1 and t == 0:
                start = i
            if t_prev == 0 and t == 1 and i != 0:
                scenes.append([start, i])
            t_prev = t
        if t == 0:
            scenes.append([start, i])
        if len(scenes) == 0:
            return np.array([[0, len(predictions) - 1]], dtype=np.int32)
        return np.array(scenes, dtype=np.int32)
    
    @staticmethod
    def save_shots_to_json(shots: List[Shot], output_path: str):
        data = {
            'total_shots': len(shots),
            'shots': [shot.to_dict() for shot in shots]
        }
        
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        return output_path
