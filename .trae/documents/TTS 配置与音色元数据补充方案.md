## 需求概述

* 将当前“片段替换时对旁白音频做标准化”的做法，改为“整片合成完成后，对最终视频的整轨音频做统一响度标准化”。

* 标准化方式参考 `backend/docs/参考_audio_normalizer.py` 的两遍 loudnorm 流程。

* 统一到标准播放音量，默认目标响度 `-10 LUFS`。

## 修改点

* 在 `modules/audio_normalizer.py` 增加 `normalize_video_loudness(input_video, output_video)`：

  * 第一遍：对输入视频做 `loudnorm` 分析，获取 `measured_I/LRA/TP/thresh`（从 stderr JSON 解析）。

  * 第二遍：对整轨音频应用标准化参数，`-c:v copy` 保留视频码流不重编码；音频设置 `-ar 44100 -ac 2 -c:a aac -b:a 192k`。

  * 失败回退：若分析失败，执行单遍 `loudnorm` 标准化（仍 `-c:v copy`）。

* 在 `services/video_generation_service.py` 的 `generate_from_script`：

  * 在成功拼接后，对 `output_abs` 调用 `normalize_video_loudness` 输出为 `*_normalized.mp4`。

  * 若成功，项目的 `output_video_path` 保存为归一化后文件；失败则回退原始拼接文件。

* 在 `modules/video_processor.py`：

  * 移除 `replace_audio_with_narration` 中对旁白的预标准化（当前 `L172-176`），改为直接使用生成的旁白，避免重复或相互抵消的增益处理。

## 关键实现要点

* 两遍 loudnorm 参数：`I=-20:TP=-1:LRA=7`，与参考实现一致；可提取为 `AudioNormalizer` 可配置字段。

* 第二遍命令示例：

  * `ffmpeg -y -hide_banner -i input.mp4 -af "loudnorm=I=-20:TP=-1:LRA=7:measured_I=...:measured_LRA=...:measured_TP=...:measured_thresh=..." -c:v copy -ar 44100 -ac 2 -c:a aac -b:a 192k output_normalized.mp4`

* 保持容器与视频流不变，仅替换音频，避免对最终视频再次重编码影响画质与效率。

## 验证方案

* 通过路由 `POST /{project_id}/generate-video` 生成成片；查看返回路径是否为 `*_normalized.mp4`。

* 使用 `ffmpeg` 或播放器对合成处的音量跳变进行主观检查；再用第一遍 `loudnorm` 分析确认整片 LUFS 接近 `-20`。

* 边界测试：

  * loudnorm 分析失败时是否正确回退单遍；

  * 超长视频的处理时间是否合理；

  * 维持视频码流不变（`-c:v copy`）。

## 影响评估与兼容

* 与现有拼接流程兼容，不改变分段剪切与拼接逻辑，仅在“成功拼接”后追加

