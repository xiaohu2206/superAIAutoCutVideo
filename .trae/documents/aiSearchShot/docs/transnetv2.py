import math
import os
import sys
import time

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
    print("警告: 无法从moviepy.editor导入VideoFileClip，将尝试备用方案...")
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
    print("错误: 缺少moviepy库或相关组件，请确保已正确安装: pip install moviepy")
    raise ImportError("无法导入moviepy.editor.VideoFileClip")


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

    def predict_frames(self, frames: np.ndarray):
        assert len(frames.shape) == 4 and frames.shape[1:] == self._input_size, \
            "[TransNetV2] Input shape must be [frames, height, width, 3]."

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

        for inp in input_iterator():
            single_frame_pred, all_frames_pred = self.predict_raw(inp)
            predictions.append((single_frame_pred.numpy()[0, 25:75, 0],
                                all_frames_pred.numpy()[0, 25:75, 0]))

            print("当前进度: {}/{} ({:.2f}%)".format(
                min(len(predictions) * 50, len(frames)), len(frames), (min(len(predictions) * 50, len(frames)) / len(frames)) * 100
            ))

        single_frame_pred = np.concatenate([single_ for single_, all_ in predictions])
        all_frames_pred = np.concatenate([all_ for single_, all_ in predictions])

        return single_frame_pred[:len(frames)], all_frames_pred[:len(frames)]  # remove extra padded frames

    def predict_video(self, video_fn: str):
        try:
            import ffmpeg
        except ModuleNotFoundError:
            raise ModuleNotFoundError("For `predict_video` function `ffmpeg` needs to be installed in order to extract "
                                      "individual frames from video file. Install `ffmpeg` command line tool and then "
                                      "install python wrapper by `pip install ffmpeg-python`.")

        # print("[TransNetV2] Extracting frames from {}".format(video_fn))
        start_time = time.time()
        video_stream, err = ffmpeg.input(video_fn).output(
            "pipe:", format="rawvideo", pix_fmt="rgb24", s="48x27"
        ).run(capture_stdout=True, capture_stderr=True)
        print("[TransNetV2] Done in {:.2f}s".format(time.time() - start_time))

        video = np.frombuffer(video_stream, np.uint8).reshape([-1, 27, 48, 3])
        return (video, *self.predict_frames(video))

    def predict_video_2(self, video_fn: str):
        # print("[TransNetV2] Extracting frames from {}".format(video_fn))
        clip = VideoFileClip(video_fn, target_resolution=(27, 48))
        duration = math.floor(clip.duration * 10) / 10
        fps = clip.fps  # 视频的帧率
        frames = []
        for t in range(0, int(duration * fps)):
            # 输出进度
            if t % 9 == 0 or t >= int(duration * fps) - 1:
                percent = 100.0 if t >= int(duration * fps) - 1 else (t / (duration * fps)) * 100
                print("当前进度: {}/{} ({:.2f}%)".format(
                    t+1, int(duration * fps), percent
                ))

            frame = clip.get_frame(t / fps)  # 获取当前时间点的帧
            if len(frame) != 0:  # 如果帧的长度不为零
                # 确保帧的形状正确
                if len(frame.shape) == 3 and frame.shape[2] == 3:
                    frames.append(frame)  # 将帧添加到 frames 列表中
                else:
                    # 如果帧不是正确的形状，尝试调整
                    if len(frame.shape) == 2:
                        # 灰度图转RGB
                        frame = np.stack([frame, frame, frame], axis=-1)
                        frames.append(frame)
        print("====================")
        video = np.array(frames)
        # 确保视频帧的形状正确，如果高度和宽度颠倒了，则进行转置
        if len(video.shape) == 4:
            if video.shape[1:3] == (48, 27):  # 如果是(48, 27)，则转置为(27, 48)
                video = np.transpose(video, (0, 2, 1, 3))
            elif video.shape[1:3] == (27, 48):  # 正确的形状
                pass
            else:
                # 其他情况尝试调整
                print(f"警告: 视频帧空间维度不标准: {video.shape}")
        
        # 确保视频帧的形状正确
        if len(video.shape) == 4 and video.shape[1:] == (27, 48, 3):
            return video, *self.predict_frames(video)
        else:
            raise ValueError(f"[TransNetV2] 视频帧形状不正确: {video.shape}, 需要: (N, 27, 48, 3)")

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

        # just fix if all predictions are 1
        if len(scenes) == 0:
            return np.array([[0, len(predictions) - 1]], dtype=np.int32)

        return np.array(scenes, dtype=np.int32)

    def save_scene_clips(self, video_fn: str, scenes: np.ndarray, output_dir: str):
        clip_small = VideoFileClip(video_fn)
        fps = clip_small.fps
        clip_small.close()
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)
        import subprocess
        from imageio_ffmpeg import get_ffmpeg_exe
        ffmpeg_bin = get_ffmpeg_exe()
        for idx, pair in enumerate(scenes):
            start_frame = int(pair[0])
            end_frame = int(pair[1])
            if end_frame <= start_frame:
                continue
            start_t = start_frame / fps
            end_t = (end_frame + 1) / fps
            out_path = os.path.join(output_dir, f"scene_{idx + 1:04d}.mp4")
            cmd = [
                ffmpeg_bin,
                "-y",
                "-i", video_fn,
                "-ss", f"{start_t:.3f}",
                "-to", f"{end_t:.3f}",
                "-c:v", "libx264",
                "-pix_fmt", "yuv420p",
                "-preset", "fast",
                "-crf", "20",
                "-c:a", "aac",
                "-movflags", "+faststart",
                out_path,
            ]
            try:
                subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            except Exception:
                pass

    @staticmethod
    def visualize_predictions(frames: np.ndarray, predictions):
        from PIL import Image, ImageDraw

        if isinstance(predictions, np.ndarray):
            predictions = [predictions]

        ih, iw, ic = frames.shape[1:]
        width = 25

        # pad frames so that length of the video is divisible by width
        # pad frames also by len(predictions) pixels in width in order to show predictions
        pad_with = width - len(frames) % width if len(frames) % width != 0 else 0
        frames = np.pad(frames, [(0, pad_with), (0, 1), (0, len(predictions)), (0, 0)])

        predictions = [np.pad(x, (0, pad_with)) for x in predictions]
        height = len(frames) // width

        img = frames.reshape([height, width, ih + 1, iw + len(predictions), ic])
        img = np.concatenate(np.split(
            np.concatenate(np.split(img, height), axis=2)[0], width
        ), axis=2)[0, :-1]

        img = Image.fromarray(img)
        draw = ImageDraw.Draw(img)

        # iterate over all frames
        for i, pred in enumerate(zip(*predictions)):
            x, y = i % width, i // width
            x, y = x * (iw + len(predictions)) + iw, y * (ih + 1) + ih - 1

            # we can visualize multiple predictions per single frame
            for j, p in enumerate(pred):
                color = [0, 0, 0]
                color[(j + 1) % 3] = 255

                value = round(p * (ih - 1))
                if value != 0:
                    draw.line((x + j, y, x + j, y - value), fill=tuple(color), width=1)
        return img


def main():
    import sys
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("files", type=str, nargs="+", help="path to video files to process")
    parser.add_argument("--weights", type=str, default=None,
                        help="path to TransNet V2 weights, tries to infer the location if not specified")
    parser.add_argument('--visualize', action="store_true",
                        help="save a png file with prediction visualization for each extracted video")
    args = parser.parse_args()

    model = TransNetV2(args.weights)
    for file in args.files:
        if os.path.exists(file + ".predictions.txt") or os.path.exists(file + ".scenes.txt"):
            print(f"[TransNetV2] {file}.predictions.txt or {file}.scenes.txt already exists. "
                  f"Skipping video {file}.", file=sys.stderr)
            continue

        video_frames, single_frame_predictions, all_frame_predictions = \
            model.predict_video(file)

        predictions = np.stack([single_frame_predictions, all_frame_predictions], 1)
        np.savetxt(file + ".predictions.txt", predictions, fmt="%.6f")

        scenes = model.predictions_to_scenes(single_frame_predictions)
        np.savetxt(file + ".scenes.txt", scenes, fmt="%d")

        if args.visualize:
            if os.path.exists(file + ".vis.png"):
                print(f"[TransNetV2] {file}.vis.png already exists. "
                      f"Skipping visualization of video {file}.", file=sys.stderr)
                continue

            pil_image = model.visualize_predictions(
                video_frames, predictions=(single_frame_predictions, all_frame_predictions))
            pil_image.save(file + ".vis.png")


if __name__ == "__main__":
    main()
