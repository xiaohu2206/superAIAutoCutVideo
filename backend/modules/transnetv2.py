import math
import os
import sys
import time
from typing import Callable, Optional

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'
os.environ['TF_CPP_MIN_LOG_LEVEL'] = '1'

import numpy as np
import tensorflow as tf

# 更安全地导入moviepy
VideoFileClip = None
try:
    from moviepy.editor import VideoFileClip as _VideoFileClip
    VideoFileClip = _VideoFileClip
except (ImportError, ModuleNotFoundError):
    # print("警告: 无法从moviepy.editor导入VideoFileClip，将尝试备用方案...")
    try:
        import moviepy.video.io.VideoFileClip
        VideoFileClip = moviepy.video.io.VideoFileClip.VideoFileClip
    except (ImportError, ModuleNotFoundError):
        try:
            import importlib
            moviepy_editor = importlib.import_module('moviepy.editor')
            VideoFileClip = getattr(moviepy_editor, 'VideoFileClip', None)
        except (ImportError, ModuleNotFoundError):
            pass

if VideoFileClip is None:
    pass
    # print("错误: 缺少moviepy库或相关组件，请确保已正确安装: pip install moviepy")
    # raise ImportError("无法导入moviepy.editor.VideoFileClip")


class TransNetV2:

    def __init__(self, model_dir=None):
        if model_dir is None:
            base_dir = os.getcwd()
            # 拼接模型文件的运行时路径
            model_dir = os.path.join(base_dir, "transnetv2-weights")
            # model_dir = "transnetv2-weights/"
            if not os.path.isdir(model_dir):
                raise FileNotFoundError(f"[TransNetV2] ERROR: {model_dir} is not a directory.")
            else:
                # print(f"[TransNetV2] Using weights from {model_dir}.")
                pass

        self._input_size = (27, 48, 3)
        try:
            self._model = tf.saved_model.load(model_dir)
        except OSError as exc:
            raise IOError(f"[TransNetV2] It seems that files in {model_dir} are corrupted or missing. "
                          f"Re-download them manually and retry. For more info, see: "
                          f"https://github.com/soCzech/TransNetV2/issues/1#issuecomment-647357796") from exc

    def predict_raw(self, frames: np.ndarray):
        assert len(frames.shape) == 5 and frames.shape[2:] == self._input_size, \
            "[TransNetV2] Input shape must be [batch, frames, height, width, 3]."
        frames = tf.cast(frames, tf.float32)

        logits, dict_ = self._model(frames)
        single_frame_pred = tf.sigmoid(logits)
        all_frames_pred = tf.sigmoid(dict_["many_hot"])

        return single_frame_pred, all_frames_pred

    def predict_frames(self, frames: np.ndarray, progress_callback: Optional[Callable[[float], None]] = None):
        assert len(frames.shape) == 4 and frames.shape[1:] == self._input_size, \
            "[TransNetV2] Input shape must be [frames, height, width, 3]."
        if frames is None or len(frames) == 0:
            empty = np.zeros((0,), dtype=np.float32)
            return empty, empty

        def input_iterator():
            # return windows of size 100 where the first/last 25 frames are from the previous/next batch
            # the first and last window must be padded by copies of the first and last frame of the video
            no_padded_frames_start = 25
            no_padded_frames_end = 25 + 50 - (len(frames) % 50 if len(frames) % 50 != 0 else 50)  # 25 - 74

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

        predictions = []

        total_batches = (len(frames) + 49) // 50  # Approximation
        processed_count = 0
        
        # Use simple count for progress if iterator length is hard to predict exactly without consuming it
        # Actually input_iterator yields batches of 50 frames (step)
        
        for inp in input_iterator():
            single_frame_pred, all_frames_pred = self.predict_raw(inp)
            predictions.append((single_frame_pred.numpy()[0, 25:75, 0],
                                all_frames_pred.numpy()[0, 25:75, 0]))

            processed_count += 50
            if progress_callback:
                current = min(processed_count, len(frames))
                pct = (current / len(frames)) * 100
                progress_callback(pct)

        single_frame_pred = np.concatenate([single_ for single_, all_ in predictions])
        all_frames_pred = np.concatenate([all_ for single_, all_ in predictions])

        return single_frame_pred[:len(frames)], all_frames_pred[:len(frames)]  # remove extra padded frames

    def predict_video(
        self,
        video_fn: str,
        progress_callback: Optional[Callable[[float], None]] = None,
        start_time: Optional[float] = None,
        duration: Optional[float] = None,
    ):
        try:
            import ffmpeg
        except ModuleNotFoundError:
            raise ModuleNotFoundError("For `predict_video` function `ffmpeg` needs to be installed in order to extract "
                                      "individual frames from video file. Install `ffmpeg` command line tool and then "
                                      "install python wrapper by `pip install ffmpeg-python`.")

        # print("[TransNetV2] Extracting frames from {}".format(video_fn))
        start_ts = time.time()
        
        # We can't easily get progress from ffmpeg stdout capture this way without complex parsing
        # So we report 0-10% for ffmpeg extraction, 10-100% for prediction
        if progress_callback:
            progress_callback(1.0)
        inp = ffmpeg.input(video_fn, ss=start_time, t=duration) if (start_time is not None or duration is not None) else ffmpeg.input(video_fn)
        video_stream, err = inp.output(
            "pipe:", format="rawvideo", pix_fmt="rgb24", s="48x27"
        ).run(capture_stdout=True, capture_stderr=True)
        # print("[TransNetV2] Done in {:.2f}s".format(time.time() - start_ts))

        video = np.frombuffer(video_stream, np.uint8).reshape([-1, 27, 48, 3])
        
        def wrapped_callback(pct):
            if progress_callback:
                # Map 0-100 to 10-100
                final_pct = 10.0 + (pct * 0.9)
                progress_callback(final_pct)
                
        return (video, *self.predict_frames(video, progress_callback=wrapped_callback))

    @staticmethod
    def predictions_to_scenes(predictions: np.ndarray, threshold: float = 0.5):
        if predictions is None or len(predictions) == 0:
            return np.zeros((0, 2), dtype=np.int32)
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

        # just fix if all predictions are 1
        if len(scenes) == 0:
            return np.array([[0, len(predictions) - 1]], dtype=np.int32)

        return np.array(scenes, dtype=np.int32)
