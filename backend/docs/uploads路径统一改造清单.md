# uploads 路径统一改造清单

本文记录后端围绕 `uploads` 根目录、路径解析、web 路径映射与历史兼容迁移所做的改动文件清单，以及每个文件的改动目的。**主使用场景为 Windows（含 Tauri / PyInstaller 打包）**；macOS / Linux 仍按各自惯例落盘，但实现与测试以 Windows 为优先。

## 改造目标

- 将后端所有与 `uploads` 相关的目录选择逻辑统一收口到 `backend/modules/app_paths.py`
- 统一真实路径与 `/uploads/...` web 路径之间的双向转换
- 统一多种运行环境下的 uploads 根目录选择逻辑
- **Windows**：正确处理盘符路径、UNC、`%VAR%` 展开，以及设置页传入的路径字符串
- 保留对历史仓库 `uploads` 目录和旧安装目录数据的兼容/迁移能力
- 降低 Windows / Tauri 重装后上传视频丢失的风险

---

## 核心统一入口

### `backend/modules/app_paths.py`

**改动目的：建立 uploads 路径统一基础设施，并以 Windows 行为为主。**

集中实现的能力包括：

| 函数 | 作用 |
|------|------|
| `uploads_dir()` | 选取当前进程应使用的 uploads 根目录（对候选列表依次 `mkdir`，第一个成功即返回） |
| `uploads_roots_for_resolve()` | 枚举可能的 uploads 根目录，供解析 `/uploads/...` 时按存在性回退 |
| `to_uploads_web_path()` | 物理路径 → `/uploads/...` |
| `resolve_uploads_path()` | `/uploads/...`、uploads 相对片段、或（非 web）路径字符串 → 物理路径 |
| `normalize_path_str()` | Windows 下 URL 解码、盘符修补、`os.path.expandvars`（如 `%LOCALAPPDATA%\...`） |
| `_is_windows_abs_path_str()` | 识别 `C:\...`、UNC，**排除** `C:相对` 误当绝对路径 |
| `app_settings_file()` | 承接设置页写入的 `uploads_root`（`app_settings.json`） |

**候选根目录优先级（`uploads_roots_for_resolve` 顺序）**

1. `SACV_UPLOADS_DIR`（由 `main.py` 在启动时设为当前生效根目录）
2. `app_settings.json` 中的 `uploads_root`
3. `data_base_dir() / "uploads"` → Windows 下通常为 `%LOCALAPPDATA%\SuperAutoCutVideo\uploads`
4. `user_data_dir() / "uploads"` → `...\SuperAutoCutVideo\data\uploads`
5. （可选）仓库根目录下的 `uploads`：`include_legacy_repo_uploads=False` 时省略，用于打包启动避免误用临时解包路径

**Windows 专项行为**

- `resolve_uploads_path()`：若判定为 Windows 绝对路径（盘符+根或 UNC），直接 `Path(s)`，不再走「以 `/` 拼项目根」的分支。
- `to_uploads_web_path()`：对根目录做 `resolve` 时尽量使用 `strict=False`（兼容 Python 版本差异），减少目标尚未存在时的异常。

---

## 路由层改动

### `backend/routes/project_routes.py`

**改动目的：统一项目上传/删除/读取等主流程的 uploads 路径逻辑。**

原先该文件内部自带 `uploads_dir()` / `to_web_path()` / `resolve_abs_path()` 并直接按项目根或环境变量推导。现已改为复用 `app_paths.py`：

- `uploads_dir()` → `app_uploads_dir()`（即 `app_paths.uploads_dir`）
- `to_web_path()` → `to_uploads_web_path()`
- `resolve_abs_path()` → `resolve_uploads_path()`

影响范围包括但不限于：视频上传、字幕上传/保存、视频预处理、合并/输出路径、文案落盘、删除资源时的路径解析。

### `backend/routes/storage_routes.py`

**改动目的：设置页与统一入口一致；** **`POST /storage` 传入的路径经 Windows 规范化后再落盘。**

- `GET`：当前根目录仍通过 `uploads_dir()`。
- `POST`：`uploads_root` 先经 **`normalize_path_str()`** 再 `Path(...).expanduser()`，便于用户填写 `%LOCALAPPDATA%\...` 或含异常分隔符的字符串。
- 写入 `app_settings.json` 的 `uploads_root`、可选 `migrate` 复制逻辑不变；**仍需重启后端后全局生效**（与进程内 `SACV_UPLOADS_DIR` 一致）。

---

## 服务层改动

### `backend/services/extract_subtitle_service.py`

**改动目的：统一字幕提取中的 uploads 目录、web 路径与回读路径。**

原独立的 `_uploads_dir` / `_to_web_path` / `_uploads_roots_for_resolve` / `_resolve_path` 已收口为调用 `app_paths` 的等价能力。

### `backend/services/video_generation_service.py`

**改动目的：统一视频生成中的输入解析与输出/临时目录（均在统一 uploads 根下）。**

### `backend/services/generate_script_service.py`

**改动目的：统一脚本生成中的路径处理；日志中改为输出统一后的 uploads 根（如 `_uploads_dir()`），避免仍打印裸 `SACV_UPLOADS_DIR` 造成误解。**

### `backend/services/generate_copywriting_service.py`

**改动目的：统一文案生成依赖的场景文件与输出 JSON 路径。**

### `backend/services/jianying_draft_service.py` / `backend/services/jianying_draft_manager.py`

**改动目的：统一剪映草稿临时目录、输出与 web 路径转换。**

### `backend/services/asr_base.py`

**改动目的：ASR 缓存目录统一为 `uploads_dir() / "asr_cache"`，不再手写「项目根/uploads」。**

### `backend/services/extract_scene_service.py`

**改动目的：通过已统一的 `extract_subtitle_service`（`_resolve_path`、`_uploads_dir`、`_to_web_path`）保持镜头分析与主链路一致。**  
本文件未再单独实现一套 uploads 根目录推导。

---

## 模型/语音资产存储改动

### `backend/modules/qwen3_tts_voice_store.py`
### `backend/modules/qwen_online_tts_voice_store.py`
### `backend/modules/voxcpm_tts_voice_store.py`

**改动目的：语音参考音与 `ref_audio_url` 均基于 `uploads_dir()` 与 `to_uploads_web_path()`，删除文件时亦按统一根定位。**

内部可保留轻量封装名 `_uploads_root()` / `_to_uploads_web_path()`，实现上委托 `app_paths`。

---

## 启动与运行时路径改动

### `backend/main.py`

**改动目的：启动时确定 `service_data_dir` 与 `uploads_dir`，并写入 `SACV_UPLOADS_DIR`；打包场景下 legacy 迁移路径与 Windows 安装布局对齐。**

- **开发**：`service_data_dir = backend/serviceData`，`uploads_dir` 来自 `uploads_roots_for_resolve()`（含仓库下 legacy `uploads` 候选）。
- **打包（frozen）**：`uploads_dir` 来自 `uploads_roots_for_resolve(include_legacy_repo_uploads=False)`，**不再**用「`__file__` 推导的 `project_root/uploads`」做迁移来源（避免指向 PyInstaller 解包临时目录）。
- **Legacy 迁移（frozen）**：优先 `install_dir/uploads`（`SACV_INSTALL_DIR` 或 exe 推导）；**Windows 额外尝试 `exe_dir/uploads`**（便携或安装器把数据放在 exe 旁的情况）。
- 最终将选定目录写入 **`os.environ["SACV_UPLOADS_DIR"]`**，与 `app_paths` 内读取顺序一致。

---

## 脚本工具改动

### `backend/scripts/mirror_tencent_tts_audio.py`

**改动目的：与线上一致地使用 `uploads_dir()`，不再手写 `SACV_UPLOADS_DIR` 或仓库根 `uploads`。**

---

## 本次改动文件总览

| 文件 | 备注 |
|------|------|
| `backend/modules/app_paths.py` | 统一入口 + Windows 路径增强 |
| `backend/main.py` | `get_app_paths()` 与 frozen legacy |
| `backend/routes/project_routes.py` | 委托 `app_paths` |
| `backend/routes/storage_routes.py` | `POST` 路径 `normalize_path_str` |
| `backend/services/extract_subtitle_service.py` | 委托 `app_paths` |
| `backend/services/video_generation_service.py` | 同上 |
| `backend/services/generate_script_service.py` | 同上 + 日志 |
| `backend/services/generate_copywriting_service.py` | 同上 |
| `backend/services/jianying_draft_service.py` | 同上 |
| `backend/services/jianying_draft_manager.py` | 同上 |
| `backend/services/asr_base.py` | `asr_cache` 根目录 |
| `backend/services/extract_scene_service.py` | 依赖统一后的 subtitle 工具 |
| `backend/modules/qwen3_tts_voice_store.py` | 同上 |
| `backend/modules/qwen_online_tts_voice_store.py` | 同上 |
| `backend/modules/voxcpm_tts_voice_store.py` | 同上 |
| `backend/scripts/mirror_tencent_tts_audio.py` | 脚本与线上一致 |

---

## 最终效果

- **目录选择**：由 `app_paths.uploads_dir()` / `uploads_roots_for_resolve()` 统一。
- **解析**：由 `resolve_uploads_path()` 统一；Windows 绝对路径/UNC 优先短路。
- **Web 路径**：由 `to_uploads_web_path()` 统一。
- **设置改目录**：写入 `app_settings.json` 后**重启后端**生效；`POST` 路径经规范化，减少 Windows 下手工输入错误。
- **历史数据**：开发环境仍可解析仓库 legacy `uploads`；打包环境从安装目录/exe 旁迁移，避免误用临时解包路径。
- **Windows / Tauri**：默认持久化在 `%LOCALAPPDATA%\SuperAutoCutVideo\...`，重装应用一般不删除该目录，有利于上传与项目数据保留。

---

## 相关说明（未改代码处）

- `backend/routes/tts_routes.py` 等错误文案中仍可能出现 `SACV_UPLOADS_DIR` 字样，仅为用户提示，路径实现已以 `app_paths` 为准。
- 若 Tauri 侧需固定安装目录，可通过启动参数或环境变量设置 **`SACV_INSTALL_DIR`**，以便 legacy 迁移命中旧数据路径。
