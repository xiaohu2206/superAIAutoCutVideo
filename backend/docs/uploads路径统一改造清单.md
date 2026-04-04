# uploads 路径统一改造清单

本文记录本次后端围绕 `uploads` 根目录、路径解析、web 路径映射与历史兼容迁移所做的改动文件清单，以及每个文件的改动目的。

## 改造目标

- 将后端所有与 `uploads` 相关的目录选择逻辑统一收口到 `backend/modules/app_paths.py`
- 统一真实路径与 `/uploads/...` web 路径之间的双向转换
- 统一多种运行环境下的 uploads 根目录选择逻辑
- 保留对历史仓库 `uploads` 目录和旧安装目录数据的兼容/迁移能力
- 降低 Windows / Tauri 重装后上传视频丢失的风险

---

## 核心统一入口

### `backend/modules/app_paths.py`

**改动目的：建立 uploads 路径统一基础设施。**

本次在该文件中集中实现了 uploads 相关的核心能力：

- `uploads_dir()`：统一获取当前 uploads 根目录
- `uploads_roots_for_resolve()`：统一枚举可能的 uploads 根目录
- `to_uploads_web_path()`：统一将物理路径转成 `/uploads/...`
- `resolve_uploads_path()`：统一将 `/uploads/...` 或 uploads 相对路径解析成物理路径
- `app_settings_file()`：作为配置入口，承接设置页对 `uploads_root` 的保存

同时保留以下优先级与兼容能力：

1. `SACV_UPLOADS_DIR`
2. `app_settings.json` 中的 `uploads_root`
3. 用户数据目录默认 uploads
4. 历史仓库根目录 `uploads`（兼容 legacy 数据）

---

## 路由层改动

### `backend/routes/project_routes.py`

**改动目的：统一项目上传/删除/读取等主流程的 uploads 路径逻辑。**

原先该文件内部自带：

- `uploads_dir()`
- `to_web_path()`
- `resolve_abs_path()`

并直接按项目根目录或环境变量推导 uploads 路径。现已改为复用 `app_paths.py`：

- `uploads_dir() -> app_uploads_dir()`
- `to_web_path() -> to_uploads_web_path()`
- `resolve_abs_path() -> resolve_uploads_path()`

影响范围包括但不限于：

- 视频上传
- 字幕上传/保存
- 视频预处理
- 输出视频/合并视频路径生成
- 文案分析结果落盘
- 删除视频/字幕/产物时的路径解析

### `backend/routes/storage_routes.py`

**改动目的：确认设置页修改 uploads 根目录的逻辑继续有效，并与统一入口保持一致。**

该文件本身结构没有大改，但它现在与 `app_paths.py` 的关系更加清晰：

- 读取当前 uploads 根目录时走 `uploads_dir()`
- 保存新目录时写入 `app_settings.json` 的 `uploads_root`
- `migrate` 为真时复制旧目录内容到新目录

注意：该设置仍然是**重启后端后生效**，因为运行中进程会持有当前 uploads 根目录环境。

---

## 服务层改动

### `backend/services/extract_subtitle_service.py`

**改动目的：统一字幕提取流程中的 uploads 目录、web 路径与回读路径。**

原先该文件内部有独立的：

- `_uploads_dir()`
- `_to_web_path()`
- `_uploads_roots_for_resolve()`
- `_resolve_path()`

现已全部收口到 `app_paths.py`，避免字幕提取链路与项目主路由使用不同的 uploads 根目录判断逻辑。

### `backend/services/video_generation_service.py`

**改动目的：统一视频生成过程中的输入路径解析与输出目录选择。**

现已将：

- 输入视频路径解析
- 输出目录 `uploads/videos/outputs/...`
- 临时目录 `uploads/videos/tmp/...`
- 配音临时目录 `uploads/audios/tmp/...`
- 输出 web 路径生成

统一建立在 `app_paths.py` 之上。

### `backend/services/generate_script_service.py`

**改动目的：统一脚本生成过程中视频、字幕、分析结果等路径处理。**

该文件原先也自带 uploads 根目录推导和路径解析逻辑，现在改为统一复用：

- `_uploads_dir()`
- `_to_web_path()`
- `_resolve_path()`

此外还顺手清理了残留日志中的旧路径输出方式，改成打印统一后的 `uploads_root`，避免排查时混淆。

### `backend/services/generate_copywriting_service.py`

**改动目的：统一文案生成依赖的场景文件读取与分析结果保存路径。**

该文件现已改为统一复用 `app_paths.py`，包括：

- 场景 JSON 读取路径
- 文案结果 JSON 落盘目录
- 生成后 web 路径写回项目数据

### `backend/services/jianying_draft_service.py`

**改动目的：统一剪映草稿打包服务的临时目录、输出目录与路径解析。**

包括：

- `jianying_drafts/tmp/...`
- `jianying_drafts/outputs/...`
- 打包 zip / 目录产物的 web 路径
- 输入素材的路径回读

### `backend/services/jianying_draft_manager.py`

**改动目的：统一剪映草稿管理器中的 uploads 路径推导与 web 路径转换。**

与 `jianying_draft_service.py` 保持一致，确保两处对草稿目录的理解完全统一。

### `backend/services/asr_base.py`

**改动目的：统一 ASR 文件缓存目录。**

原先该基类直接按历史方式推导 `uploads/asr_cache`，现已改为：

- `uploads_dir() / "asr_cache"`

避免 ASR 缓存仍写入旧仓库目录而主业务文件写入新用户目录的问题。

### `backend/services/extract_scene_service.py`

**改动目的：复用已经统一的字幕服务路径工具，确保镜头分析链路与主 uploads 逻辑一致。**

这个文件本身没有独立再造一套 uploads 根目录，而是依赖：

- `services.extract_subtitle_service` 中已统一后的 `_resolve_path`
- `_uploads_dir`
- `_to_web_path`

因此镜头分析相关的：

- 场景缓存
- 原始分析结果
- 最终场景 JSON

也都自然跟随统一后的 uploads 规则。

---

## 模型/语音资产存储改动

### `backend/modules/qwen3_tts_voice_store.py`

**改动目的：统一 Qwen3 TTS 语音资产目录与 web 路径生成。**

改造后：

- 语音参考音频存储目录基于 `uploads_dir()`
- `ref_audio_url` 通过 `to_uploads_web_path()` 生成
- 删除语音素材时也以统一根目录定位

### `backend/modules/qwen_online_tts_voice_store.py`

**改动目的：统一在线 Qwen TTS 语音资产目录与 web 路径生成。**

与 `qwen3_tts_voice_store.py` 一致，不再自行读取 `SACV_UPLOADS_DIR` 并手动拼 `/uploads/...`。

### `backend/modules/voxcpm_tts_voice_store.py`

**改动目的：统一 VoxCPM TTS 语音资产目录与 web 路径生成。**

同样收口到 `app_paths.py`，避免不同 TTS 语音库落到不同 uploads 目录。

---

## 启动与运行时路径改动

### `backend/main.py`

**改动目的：统一后端启动时的 uploads 根目录确定逻辑，并保留历史迁移能力。**

本次重点调整了 `get_app_paths()`：

- 开发环境下改为从 `uploads_roots_for_resolve()` 统一选取 uploads 根目录
- 打包环境下改为从 `uploads_roots_for_resolve(include_legacy_repo_uploads=False)` 统一选取 uploads 根目录
- 保留对旧安装目录 `uploads`、旧仓库目录 `uploads` 的迁移逻辑
- 继续将最终选中的 uploads 根目录写入 `SACV_UPLOADS_DIR`，作为当前运行进程的固定环境

这保证了：

- 设置页写入的 `uploads_root` 会在重启后成为正式生效目录
- Tauri / PyInstaller 场景下优先使用用户数据目录
- 历史版本安装目录内的 uploads 数据可迁移到新目录

---

## 脚本工具改动

### `backend/scripts/mirror_tencent_tts_audio.py`

**改动目的：统一脚本工具使用的 uploads 根目录。**

原先脚本内部也会自己从环境变量或项目根推断 uploads 目录，现在改为直接调用 `uploads_dir()`，确保辅助脚本与正式服务一致。

---

## 本次改动文件总览

以下文件在本次 uploads 路径统一改造中发生了改动：

- `backend/modules/app_paths.py`
- `backend/routes/project_routes.py`
- `backend/routes/storage_routes.py`
- `backend/services/extract_subtitle_service.py`
- `backend/services/video_generation_service.py`
- `backend/services/generate_script_service.py`
- `backend/services/generate_copywriting_service.py`
- `backend/services/jianying_draft_service.py`
- `backend/services/jianying_draft_manager.py`
- `backend/services/asr_base.py`
- `backend/services/extract_scene_service.py`（依赖链路跟随统一）
- `backend/modules/qwen3_tts_voice_store.py`
- `backend/modules/qwen_online_tts_voice_store.py`
- `backend/modules/voxcpm_tts_voice_store.py`
- `backend/main.py`
- `backend/scripts/mirror_tencent_tts_audio.py`

---

## 最终效果

本次改造完成后，后端关于 uploads 的核心行为已经统一：

- **目录选择统一**：由 `app_paths.py` 决定
- **路径解析统一**：由 `resolve_uploads_path()` 决定
- **web 路径映射统一**：由 `to_uploads_web_path()` 决定
- **设置页改目录仍然有效**：写入 `app_settings.json` 后，重启后端生效
- **历史目录兼容保留**：旧仓库 uploads、旧安装目录 uploads 均有兼容/迁移处理

这使得 Windows / Tauri 场景下上传文件的持久化行为更稳定，也显著降低了重装应用导致上传文件丢失的风险。
