## 目标
- 读取项目脚本 `script.segments`，为非“播放原片X”片段生成腾讯TTS配音并写入对应视频片段。
- 保留“播放原片X”片段的原始音频。
- 解决配音时长与视频时长不一致的两类问题（音频长>视频、视频长>音频）。
- 在现有拼接流程 `video_generation_service.generate_from_script` 基础上插入配音混流步骤，最终仍用现有的稳健拼接输出。

## 代码变更点
1. `backend/modules/video_processor.py`
   - 新增：`async replace_audio_with_narration(video_path: str, narration_path: str, output_path: str) -> bool`
   - 功能：用 TTS 音轨替换指定片段的音轨，含时长对齐策略（见下）。
   - 细节：`ffprobe` 获取视频/音频时长；`ffmpeg -filter_complex` 执行裁剪/补齐/（小幅）变速；`-c:v copy` 保持片段视频不重编码、`-c:a aac -b:a 192k` 重编码音频。

2. `backend/services/video_generation_service.py`
   - 在片段剪切后、拼接前：
     - 遍历 `segments`，判断 `text` 是否以“播放原片”开头；若否：
       - 调用 TTS 合成生成 `mp3/wav` 到 `uploads/audios/tmp/{project_id}_{ts}/seg_{idx}.mp3`。
       - 调用 `video_processor.replace_audio_with_narration(clip_abs, tts_audio_abs, clip_abs)` 将片段音轨替换为旁白（原地覆盖或输出到 `clip_narr.mp4` 再替换路径）。
     - 若是“播放原片X”：保留原片段不处理。
   - 其余流程（收集 `clip_paths` → `concat_videos`）保持不变。

3. `backend/modules/config/tts_config.py`
   - 复用已存在的激活配置：`get_active_config()` 与 `active_voice_id`、`speed_ratio`。

4. 新增最小服务：`backend/modules/tts_service.py`
   - `class TencentTtsService`：`async synthesize(text: str, out_path: str, voice_id: Optional[str], speed_ratio: float) -> Dict`。
   - 实现：使用 `tencentcloud.tts.v20190823` 的 `TextToVoice`；返回 `success, duration, codec, sample_rate`。
   - 说明：仅此单文件，逻辑与配置管理解耦，避免在路由层暴露合成接口（直接由生成服务调用）。

## 时长对齐策略
- 获取 `video_dur` 与 `audio_dur`（秒）。
- 差异阈值：`delta = abs(video_dur - audio_dur)`；相对差 `ratio = audio_dur / video_dur`。
- 规则：
  - 音频更长（`ratio > 1`）：
    - 若 `ratio ≤ 1.15`：轻微加速配音（`atempo = min(max(1/ratio, 0.5), 2.0)`），再 `atrim=0:video_dur` 保障精确对齐。
    - 若 `ratio > 1.15`：直接 `atrim=0:video_dur, asetpts=PTS-STARTPTS` 截断音频。
  - 视频更长（`ratio < 1`）：
    - 若 `1/ratio ≤ 1.15`：轻微减速配音（`atempo = min(max(1/ratio, 0.5), 2.0)`），不足部分用 `apad` 补静音，并 `-shortest`。
    - 若差异较大：`apad` 静音补齐到视频长度，`-shortest` 保证输出与视频一致。
- `ffmpeg` 示例（音频短、静音补齐）：
  - `ffmpeg -i clip.mp4 -i seg.mp3 -filter_complex "[1:a]apad[a1]" -map 0:v:0 -map "[a1]" -c:v copy -c:a aac -b:a 192k -shortest -y out.mp4`
- `ffmpeg` 示例（音频长、裁剪）：
  - `ffmpeg -i clip.mp4 -i seg.mp3 -filter_complex "[1:a]atrim=0:VIDEO_DUR,asetpts=PTS-STARTPTS[a1]" -map 0:v:0 -map "[a1]" -c:v copy -c:a aac -b:a 192k -y out.mp4`
- 小幅变速（可选）：在 `[1:a]atempo=VAL` 后接 `apad/atrim`。

## TTS 合成细节
- 取活动配置：`cfg = tts_engine_config_manager.get_active_config()`；若无或缺凭据→抛错。
- `TextToVoiceRequest` 参数：
  - `Text`: 片段 `text`
  - `VoiceType`: 使用 `cfg.active_voice_id`（若需映射到腾讯枚举，可在 `extra_params` 配置；初期直接填字符串由服务自行映射）
  - `SampleRate`: `16000`
  - `Codec`: `mp3`
  - `Speed`: 由 `cfg.speed_ratio` 映射（或直接保持默认并在后处理用 `atempo`）
- 响应 `Audio`（Base64）落盘到 `out_path`。
- 时长估算：优先 `ffprobe` 读取文件时长，兜底用返回 `Audio` 字节数与采样率估算。

## 目录与命名
- 音频临时目录：`/uploads/audios/tmp/{project_id}_{ts}/`
- 片段命名：`seg_{idx:04d}.mp3`；输出片段若做替换：`clip_{idx:04d}.mp4` 原地覆盖或 `clip_{idx:04d}_nar.mp4`。
- 最终输出仍保存在：`/uploads/videos/outputs/{safe_project_name}/{project_id}_output_{ts}.mp4`（现有逻辑）。

## 调用与流程
- 仍由现有接口触发：`POST /api/projects/{project_id}/generate-video`。
- 服务内部决定是否生成配音（基于脚本内容与 TTS 激活配置）。
- 前端无需改动；如需可选“是否配音”开关，可在请求体增加参数，后端按参数决定是否执行 TTS 步骤。

## 验证
- 单元验证：
  - 针对 3 类片段构建用例：`音频>视频`、`视频>音频`、`播放原片X`；检查输出时长与音频存在性。
- 端到端：
  - 用现有项目 `c4fc...` 执行生成；核对输出无卡顿（现有拼接已重编码）、非旁白片段保留原音，旁白片段替换为清晰配音。

## 交付节奏
- 第一步：新增 `TencentTtsService` 与 `replace_audio_with_narration`。
- 第二步：在 `generate_from_script` 中插入 TTS 与混流。
- 第三步：运行一次并输出日志，若无误再清理临时音频。