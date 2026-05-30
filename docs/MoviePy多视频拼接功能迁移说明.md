# MoviePy 多视频拼接功能迁移说明

## 1. 目标

本说明用于把 `.cache/moviepy` 中稳定的“多个视频按顺序拼接”能力迁移到当前项目。

分析对象：

- MoviePy 版本：`2.2.0`
- 本地源码提交：`7ffa4f0`
- 源码目录：`.cache/moviepy`
- 源码许可证：MIT，复制源码时需要保留 `LICENCE.txt`

MoviePy 的核心入口是：

```python
from moviepy import VideoFileClip, concatenate_videoclips
```

拼接的完整链路是：

```text
VideoFileClip
  -> FFMPEG_VideoReader / AudioFileClip
  -> concatenate_videoclips
  -> chain 或 compose
  -> CompositeAudioClip
  -> VideoClip.write_videofile
  -> ffmpeg_write_video
  -> FFMPEG_VideoWriter
  -> FFmpeg
```

## 2. 推荐用法

如果允许把 MoviePy 作为 Python 依赖安装，不建议手工复制 MoviePy 内部文件。直接增加依赖并写一层项目适配器，后续维护成本最低。

不同来源的视频可能存在分辨率、画幅和 FPS 差异。为提高成功率，推荐使用 `method="compose"`：

```python
from contextlib import ExitStack
from pathlib import Path
from typing import Iterable

from moviepy import VideoFileClip, concatenate_videoclips


def merge_videos_with_moviepy(
    inputs: Iterable[str],
    output_path: str,
    *,
    fps: int | None = None,
) -> str:
    paths = [str(Path(path)) for path in inputs]
    if not paths:
        raise ValueError("inputs must not be empty")

    with ExitStack() as stack:
        clips = [stack.enter_context(VideoFileClip(path)) for path in paths]
        final_clip = concatenate_videoclips(
            clips,
            method="compose",
            bg_color=(0, 0, 0),
        )
        stack.callback(final_clip.close)
        final_clip.write_videofile(
            output_path,
            fps=fps,
            codec="libx264",
            audio_codec="aac",
            pixel_format="yuv420p",
            ffmpeg_params=["-movflags", "+faststart"],
        )

    return output_path
```

注意：

- `VideoFileClip` 会创建 FFmpeg 子进程并锁定文件，必须关闭每个输入 clip。
- `final_clip.close()` 不会代替输入 clip 的关闭操作。
- 输出 H.264 MP4 时使用 `yuv420p`，兼容性更好。
- 输出宽高最好为偶数。当前项目的 FFmpeg 拼接器已经有偶数对齐逻辑，可以继续保留。
- MoviePy 的 `compose` 采用最大宽高作为画布，小素材居中显示，不会被强制拉伸。

## 3. 核心拼接代码提取版

原始实现位于：

```text
.cache/moviepy/moviepy/video/compositing/CompositeVideoClip.py
```

下面是去掉文档字符串后的核心逻辑提取版。它展示了需要克隆的行为，但不能脱离 MoviePy 的 `VideoClip`、`CompositeVideoClip`、`CompositeAudioClip` 和 `ColorClip` 单独运行。

```python
from functools import reduce

import numpy as np

from moviepy.audio.AudioClip import CompositeAudioClip
from moviepy.video.VideoClip import ColorClip, VideoClip


def concatenate_videoclips(
    clips,
    method="chain",
    transition=None,
    bg_color=None,
    is_mask=False,
    padding=0,
):
    if transition is not None:
        pairs = [[clip, transition] for clip in clips[:-1]]
        clips = reduce(lambda x, y: x + y, pairs) + [clips[-1]]

    timings = np.cumsum([0] + [clip.duration for clip in clips])
    sizes = [clip.size for clip in clips]
    width = max(size[0] for size in sizes)
    height = max(size[1] for size in sizes)

    timings = np.maximum(0, timings + padding * np.arange(len(timings)))
    timings[-1] -= padding

    if method == "chain":
        def frame_function(t):
            index = max(i for i, end in enumerate(timings) if end <= t)
            return clips[index].get_frame(t - timings[index])

        def get_mask(clip):
            mask = clip.mask or ColorClip(clip.size, color=1, is_mask=True)
            if mask.duration is None:
                mask.duration = clip.duration
            return mask

        result = VideoClip(is_mask=is_mask, frame_function=frame_function)
        if any(clip.mask is not None for clip in clips):
            masks = [get_mask(clip) for clip in clips]
            result.mask = concatenate_videoclips(masks, method="chain", is_mask=True)
            result.clips = clips

    elif method == "compose":
        result = CompositeVideoClip(
            [
                clip.with_start(start).with_position("center")
                for clip, start in zip(clips, timings)
            ],
            size=(width, height),
            bg_color=bg_color,
            is_mask=is_mask,
        )
    else:
        raise ValueError("method must be 'chain' or 'compose'")

    result.timings = timings
    result.start_times = timings[:-1]
    result.start = 0
    result.duration = timings[-1]
    result.end = timings[-1]

    audio_timeline = [
        (clip.audio, start)
        for clip, start in zip(clips, timings)
        if clip.audio is not None
    ]
    if audio_timeline:
        result.audio = CompositeAudioClip(
            [audio.with_start(start) for audio, start in audio_timeline]
        ).with_duration(result.duration)

    fps_values = [
        clip.fps
        for clip in clips
        if getattr(clip, "fps", None) is not None
    ]
    result.fps = max(fps_values) if fps_values else None
    return result
```

## 4. `chain` 与 `compose` 的区别

| 模式 | 工作方式 | 优点 | 风险 | 建议 |
| --- | --- | --- | --- | --- |
| `chain` | 按时间点把帧直接转发给输出 | 快，逻辑简单 | 不会修正不同分辨率；直接导出时可能失败 | 仅用于尺寸一致、已经标准化的素材 |
| `compose` | 生成统一画布，按开始时间放置 clip | 能容纳不同尺寸素材；可叠加转场 | 会逐帧合成并重新编码，较慢 | 用户上传的异构素材默认使用 |

MoviePy 对 FPS 的处理：

- 输出 clip 使用输入素材中最高的 FPS。
- 如果调用 `write_videofile(..., fps=...)` 显式指定 FPS，则以显式值为准。

MoviePy 对音频的处理：

- 把每个输入视频的音频放到对应的开始时间。
- 使用 `CompositeAudioClip` 生成最终音轨。
- 导出视频前先生成临时音频文件，然后由 FFmpeg 封装进输出视频。

## 5. 精确源码位置

### 5.1 核心入口

| 功能 | 文件 | 关键位置 |
| --- | --- | --- |
| 多视频顺序拼接 | `.cache/moviepy/moviepy/video/compositing/CompositeVideoClip.py` | `concatenate_videoclips`，约第 298 行 |
| 不同尺寸素材统一画布 | `.cache/moviepy/moviepy/video/compositing/CompositeVideoClip.py` | `CompositeVideoClip`，约第 11 行 |
| 叠加时逐帧合成 | `.cache/moviepy/moviepy/video/compositing/CompositeVideoClip.py` | `CompositeVideoClip.frame_function`，约第 156 行 |
| 对外导出入口 | `.cache/moviepy/moviepy/__init__.py` | 导出 `VideoFileClip`、`concatenate_videoclips` |

### 5.2 视频读取与导出

| 功能 | 文件 | 关键位置 |
| --- | --- | --- |
| 视频文件 Clip | `.cache/moviepy/moviepy/video/io/VideoFileClip.py` | `VideoFileClip` |
| FFmpeg 视频读取器 | `.cache/moviepy/moviepy/video/io/ffmpeg_reader.py` | `FFMPEG_VideoReader` |
| Clip 视频导出 API | `.cache/moviepy/moviepy/video/VideoClip.py` | `write_videofile`，约第 208 行 |
| FFmpeg 视频写入器 | `.cache/moviepy/moviepy/video/io/ffmpeg_writer.py` | `FFMPEG_VideoWriter`、`ffmpeg_write_video` |

### 5.3 音频读取、组合与导出

| 功能 | 文件 | 关键位置 |
| --- | --- | --- |
| 音频 Clip 与音频组合 | `.cache/moviepy/moviepy/audio/AudioClip.py` | `CompositeAudioClip`、`concatenate_audioclips` |
| 音频文件 Clip | `.cache/moviepy/moviepy/audio/io/AudioFileClip.py` | `AudioFileClip` |
| FFmpeg 音频读取器 | `.cache/moviepy/moviepy/audio/io/readers.py` | `FFMPEG_AudioReader` |
| FFmpeg 音频写入器 | `.cache/moviepy/moviepy/audio/io/ffmpeg_audiowriter.py` | `FFMPEG_AudioWriter` |

### 5.4 基础设施

| 功能 | 文件 |
| --- | --- |
| Clip 时间轴、切片、逐帧迭代、资源关闭协议 | `.cache/moviepy/moviepy/Clip.py` |
| 装饰器：时长校验、FPS 默认值、路径转换等 | `.cache/moviepy/moviepy/decorators.py` |
| FFmpeg 可执行文件配置 | `.cache/moviepy/moviepy/config.py` |
| 扩展名、编码器、跨平台子进程辅助函数 | `.cache/moviepy/moviepy/tools.py` |
| 视频损坏异常 | `.cache/moviepy/moviepy/video/io/errors.py` |

## 6. 手工复制源码时的文件清单

### 6.1 最小可用清单：只做多视频拼接并导出 MP4

如果必须 vendor 源码，至少复制：

```text
moviepy/
  __init__.py
  Clip.py
  Effect.py
  config.py
  decorators.py
  tools.py
  audio/
    __init__.py
    AudioClip.py
    io/
      __init__.py
      AudioFileClip.py
      readers.py
      ffmpeg_audiowriter.py
  video/
    __init__.py
    VideoClip.py
    compositing/
      __init__.py
      CompositeVideoClip.py
    io/
      __init__.py
      VideoFileClip.py
      errors.py
      ffmpeg_reader.py
      ffmpeg_writer.py
      ffplay_previewer.py
      gif_writers.py
    fx/
      __init__.py
      Crop.py
      Resize.py
      Rotate.py
```

说明：

- 这是按当前 MoviePy 文件级导入关系整理的最小清单。
- 即使只调用拼接功能，`VideoClip.py` 在模块加载时仍会导入预览、GIF、裁剪、缩放和旋转相关模块。
- 继续裁剪依赖需要改写 MoviePy 内部 import，维护成本会明显增加。
- 需要保留 `.cache/moviepy/LICENCE.txt`。

### 6.2 Python 包依赖

MoviePy `2.2.0` 的 `pyproject.toml` 声明了：

```text
decorator>=4.0.2,<6.0
imageio>=2.5,<3.0
imageio_ffmpeg>=0.2.0
numpy>=1.25.0
proglog<=1.0.0
python-dotenv>=0.10
pillow>=9.2.0
opencv-python-headless>=4.0.0
```

当前项目已经使用 `numpy`、`Pillow`、`opencv-python` 和自己的 FFmpeg 路径解析逻辑。引入 MoviePy 时仍应显式补充：

```text
moviepy==2.2.0
```

如果采用 vendor 方式，则需要逐项检查缺失依赖，至少关注：

```text
decorator
imageio
imageio_ffmpeg
proglog
python-dotenv
```

## 7. 与当前项目的接入位置

当前项目已有拼接入口：

```text
backend/modules/video_processor.py
  -> VideoProcessor.concat_videos
```

当前实现已经包含：

- 同编码参数素材优先 `-c copy`
- MP4 H.264/H.265 转 MPEG-TS 后快速拼接
- 不一致素材通过 `scale + pad + setsar + fps + concat` 重新编码
- 无音频素材补静音轨
- Windows 命令行过长时分批拼接
- 进度回调、取消任务、编码器回退

因此，不建议直接删除现有 `concat_videos`。推荐增加一个 MoviePy 回退路径：

```text
快速无损拼接成功
  -> 直接返回

快速无损拼接失败
  -> 现有 FFmpeg filter_complex 标准化拼接

仍然失败
  -> MoviePy compose 回退
  -> 统一画布逐帧导出
```

MoviePy 回退路径适合解决：

- 输入尺寸不同
- 输入 FPS 不同
- 输入时间戳不规整
- 快速 remux 拼接失败
- FFmpeg `concat` filter 对复杂输入不稳定

MoviePy 不应替代当前实现中的：

- 异步任务取消
- WebSocket 进度推送
- FFmpeg 路径解析
- GPU 编码器优先级
- Windows 无窗口子进程参数
- 大量片段的分批处理

## 8. 建议新增的项目文件

建议增加一层轻量适配器：

```text
backend/modules/moviepy_concat_adapter.py
```

职责：

- 接收输入路径和输出路径。
- 用 `VideoFileClip` 打开输入。
- 默认使用 `concatenate_videoclips(..., method="compose")`。
- 统一使用 `libx264 + aac + yuv420p + faststart` 输出 MP4。
- 在 `finally` 或 `ExitStack` 中可靠关闭所有 clip。
- 捕获异常并返回可诊断的错误文本。
- 由 `VideoProcessor.concat_videos` 在现有 FFmpeg 路径失败后调用。

## 9. 建议补充的测试

至少覆盖：

| 场景 | 预期 |
| --- | --- |
| 两个同尺寸、同 FPS、都有音频的视频 | 成功拼接，时长接近输入时长之和 |
| 横屏视频加竖屏视频 | 成功拼接，画布为最大宽高，小素材居中且不拉伸 |
| 24 FPS 加 30 FPS 视频 | 成功拼接，输出 FPS 明确且播放连续 |
| 有音频视频加无音频视频 | 成功拼接，无音频片段不导致整体失败 |
| 单个输入视频 | 成功输出或直接重封装 |
| 空输入列表 | 返回明确错误 |
| 损坏视频 | 返回包含输入文件路径的错误 |
| 输出路径含中文和空格 | 成功输出 |
| 拼接结束后删除或改名输入文件 | 能成功操作，确认 FFmpeg 子进程已释放 |

MoviePy 仓库内可参考：

```text
.cache/moviepy/tests/test_compositing.py
.cache/moviepy/tests/test_issues.py
.cache/moviepy/tests/test_AudioClips.py
.cache/moviepy/tests/test_ffmpeg_writer.py
.cache/moviepy/tests/test_VideoFileClip.py
```

## 10. 结论

优先选择：

```text
安装 moviepy==2.2.0
  + 新增 moviepy_concat_adapter.py
  + 保留现有 FFmpeg 快速路径
  + 把 MoviePy compose 作为最终兼容性回退
```

如果必须完全克隆源码，则使用第 6 节的 vendor 文件清单，并保留 MIT 许可证。不要只复制 `concatenate_videoclips` 一个函数，因为它依赖 MoviePy 的 Clip 时间轴、视频和音频读取、逐帧合成、FFmpeg 导出及资源关闭机制。
