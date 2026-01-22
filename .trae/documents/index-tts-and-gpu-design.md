# SuperAutoCutVideo：Index TTS 引入与按需安装 + GPU 加速完整设计方案

## 1. 目标与原则
- 组件化与低耦合：新增模块独立、接口统一，逻辑与视图分离，保持高内聚低耦合。
- 按需安装：用户点击“下载并安装”后才解锁 Index TTS；未安装不可用。
- GPU 加速校验：提供统一的检测与压测接口，前端一键校验是否可用，失败清晰回退。
- 安全与可维护性：敏感信息脱敏；错误显式可见；遵循现有路径与缓存约定。
- 环境约定：前端依赖使用 cnpm；Node 版本使用 nvm；尽量提取纯函数与 hooks。

## 2. 架构总览
- 后端
  - 新增服务：index_tts_service（音色列表与合成）、installers/index_tts_installer（按需安装）、gpu_system（GPU 检测与压测）、video_hwaccel（FFmpeg 硬编映射）。
  - 配置层扩展：tts_config 支持 provider=index_tts，默认配置 index_tts_default，启用状态与语音缓存管理。
  - 合成网关：tts_service 新增 provider 分支，统一调度。
  - 路由：复用 TTS 路由；新增安装与 GPU 路由。
  - 数据与缓存：使用 serviceData 与用户数据目录，试听音频与音色缓存统一存放。
- 前端
  - 设置页新增“Index TTS 安装卡片”和“GPU 加速”卡片。
  - hooks：useTtsEngineInstaller、useGpuDiagnostics；服务层统一发起请求，UI 仅负责展示。
- 路径约定与挂载
  - 用户数据目录与配置/数据路径：参考 [app_paths.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/app_paths.py) 与 [main.py:get_app_paths](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/main.py#L320-L395)。
  - 挂载路径：/uploads 与 /backend/serviceData。

## 3. 后端引入 Index TTS
### 3.1 服务模块：index_tts_service
- 能力
  - async list_voices()：获取 Index TTS 音色列表，返回统一结构（兼容 TtsVoice），并写入缓存 backend/serviceData/tts/index_voices_cache.json。
  - async synthesize(text, voice_id, speed_ratio, out_path, proxy_override)：生成 mp3/wav 文件，返回 {success, path, duration, codec, sample_rate}。
- 参数与扩展
  - extra_params 支持：api_key、base_url、ProxyUrl、SampleRate、Codec、Speed、Volume。
  - 代理：优先使用 extra_params.ProxyUrl，其次环境变量；不在代码中硬编码。
- 错误处理
  - 网络错误显式返回，不做系统语音降级或静默回退。
  - 返回统一结构 {success: false, error: "..."}。
- 参考接口与数据结构
  - TtsVoice 与引擎配置管理：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L17-L31)
  - Edge TTS 的服务参考：[edge_tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/edge_tts_service.py#L120-L176)

### 3.2 配置层：tts_config 扩展
- provider 白名单增加 index_tts：
  - 参考校验逻辑：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L45-L50)
- 引擎元数据增加 Index TTS：
  - get_engines_meta() 扩展：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L216-L233)
  - Index TTS 建议 required_fields: ["api_key"]；optional_fields: ["base_url","ProxyUrl"]。
- 默认配置 index_tts_default
  - enabled=false；active_voice_id 可留空或填写常用音色 ID。
  - extra_params 存放 api_key、base_url、ProxyUrl 等。
- 音色列表加载
  - get_voices("index_tts")：优先读取 index_voices_cache.json；若已安装但无缓存，调用 index_tts_service.list_voices() 填充并返回。
  - 参考 Edge TTS 缓存读取逻辑：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L275-L352)
- 连通性测试
  - test_connection("index_tts")：未安装时返回安装提示；已安装则 synthesize 生成 previews/index_test_preview.mp3 并返回时长。
  - 参考现有测试结构（Edge/Tencent）：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L376-L506)

### 3.3 合成网关：tts_service 分支
- 新增 provider == "index_tts" 分支，统一调用 index_tts_service.synthesize：
  - 参考现有分支（Edge/Tencent）：[tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/tts_service.py#L54-L90)
- 返回结构与日志风格与现有保持一致。

### 3.4 路由复用与预览
- 引擎列表与配置：复用现有 API
  - 获取引擎列表：[tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L49-L57)
  - 获取音色列表：[tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L59-L82)
  - 试听（预览）：Edge TTS 的预览逻辑参考，可对 Index TTS 复用：[tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L242-L317)
- 安全：路由层对敏感字段脱敏展示
  - 参考 safe_tts_config_dict_hide_secret：[tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L26-L33)

## 4. 用户自行下载模型逻辑（按需安装）
### 4.1 安装器模块：installers/index_tts_installer
- 能力
  - is_installed(): 判断安装状态（SDK 可导入或已存在 installed.json 标记）。
  - install(proxy_url?): 异步安装流程；SDK 方案执行 python -m pip 安装；REST 方案下载语音元数据/示例包；写入 installed.json（含 version/时间）。
  - uninstall(): 清理安装资源与标记；可选清理缓存。
- 并发防护
  - 使用进程级/文件锁，避免重复安装。
- 目录与标记位置
  - 用户数据目录：~/Library/Application Support/SuperAutoCutVideo/data/plugins/index_tts/installed.json（macOS）；Windows 与 Linux 按约定变换。
  - 音色缓存与试听：backend/serviceData/tts/index_voices_cache.json 与 previews/index_*_preview.mp3。
- 代理支持
  - install/synthesize 均支持 proxy override；优先 extra_params.ProxyUrl，其次环境变量。

### 4.2 安装路由（建议）
- 前缀：/api/tts/provider/index_tts
  - GET /status：返回 {installed, version, last_installed_at}
  - POST /install：触发安装，返回 {job_id}；配合 GET /install/status 轮询进度
  - POST /uninstall：卸载并清理标记/缓存
- 与现有 TTS 路由兼容：安装完成后，voices/configs/preview/test 等接口即刻可用。

### 4.3 前端交互
- TTS 设置页新增“Index TTS 安装卡片”
  - 未安装：显示“下载并安装”，点击后调用 /install 并轮询状态；完成后刷新引擎与音色列表。
  - 已安装：显示版本与“卸载/修复”下拉（整合控件，避免按钮堆叠）。
- 引擎选择与凭据表单
  - 引擎下拉包含 Index TTS；未安装时禁用或提示安装。
  - 凭据表单复用 TtsCredentialForm（api_key/base_url/ProxyUrl）；未安装状态下禁用提交。
- 逻辑与视图分离
  - hooks：useTtsEngineInstaller 管理安装流程与状态；组件只做展示。
  - 遵循组件化与代码提取原则（pure functions）。

## 5. GPU 加速完整方案
### 5.1 深度学习推理加速
- 后端设备选择器
  - macOS：PyTorch MPS（Metal）；校验 torch.backends.mps.is_available()。
  - NVIDIA：CUDA；校验 torch.cuda.is_available() 与 nvidia-smi。
  - AMD：ROCm；校验 torch.version.hip 或 ORT ROCm provider。
  - ONNX Runtime：按优先级选择 CUDAExecutionProvider/ROCM/MPS，否则 CPU。
- 策略
  - preferred_dl_backend: auto|cuda|rocm|mps|cpu。
  - dtype：尽可能使用 float16/bfloat16；不可用则回退 float32。
  - 提供统一入口：根据设备选择器返回 torch.device / ORT provider，业务模块透明调用。

### 5.2 视频编解码硬件加速（FFmpeg）
- 后端映射
  - macOS：VideoToolbox（h264_videotoolbox/hevc_videotoolbox）
  - NVIDIA：NVENC/NVDEC（h264_nvenc/hevc_nvenc）
  - Intel：QSV（h264_qsv/hevc_qsv）
  - Linux：VAAPI（h264_vaapi）
  - AMD：AMF（h264_amf/h265_amf）
- 参数模板
  - NVENC：`-c:v h264_nvenc -preset p5 -b:v 6M -maxrate 10M -rc:v vbr`
  - VideoToolbox：`-c:v h264_videotoolbox -b:v 6M -allow_sw 1`
  - VAAPI：`-vaapi_device /dev/dri/renderD128 -vf "format=nv12,hwupload" -c:v h264_vaapi -b:v 6M`
- 自动回退
  - 无硬编后端时回退 libx264/libx265，并在日志与 UI 中明确提示。

### 5.3 路由与报告
- 路由（建议）
  - GET /api/system/gpu/status：返回可用后端列表与环境信息 `{dl_backends:{available:[...]}, video_hwaccels:{available:[...]}, drivers:{...}}`
  - POST /api/system/gpu/test：执行 DL 与视频硬编短压测，返回 `{success, dl:{backend, ms, dtype}, video:{backend, ms, path}, hints:[...]}`，视频样本写入 `/uploads/gpu_tests/`。
  - GET /api/system/gpu/backends：返回支持枚举与说明，供前端渲染。
- 配置持久化
  - `~/Library/Application Support/SuperAutoCutVideo/config/gpu_config.json`，字段：
    - enabled: true|false
    - preferred_dl_backend: auto|cuda|rocm|mps|cpu
    - preferred_video_hwaccel: auto|videotoolbox|nvenc|qsv|vaapi|amf|cpu
    - last_test_result: {timestamp, dl:{...}, video:{...}}
- 目录与挂载
  - 挂载与路径参考：[main.py:get_app_paths](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/main.py#L320-L395)

### 5.4 前端交互
- 设置页“GPU 加速”卡片
  - 显示检测到的 DL 与视频硬编后端；不可用给出原因与修复建议。
  - 开关“启用 GPU 加速”；下拉选择首选 DL 与视频硬编后端。
  - 按钮“运行校验测试”，展示详细报告与样本视频链接。
- hooks 与服务
  - useGpuDiagnostics：拉取状态、发起测试、管理进度与结果。
  - 视图组件仅做展示与交互，避免复杂 useEffect。

### 5.5 校验命令与示例
- macOS
  - FFmpeg 硬件能力：
    ```bash
    ffmpeg -hide_banner -hwaccels
    ffmpeg -hide_banner -encoders | grep videotoolbox
    ```
  - PyTorch MPS：
    ```bash
    python - <<'PY'
    import torch
    print("PyTorch:", torch.__version__)
    print("MPS available:", torch.backends.mps.is_available())
    if torch.backends.mps.is_available():
        x = torch.randn(256,256, device='mps'); y = torch.mm(x, x)
        print("MPS test ok:", y is not None)
    PY
    ```
- Windows/NVIDIA
  - 驱动/CUDA：
    ```bash
    nvidia-smi
    ```
  - PyTorch CUDA：
    ```bash
    python - <<'PY'
    import torch
    print("CUDA available:", torch.cuda.is_available())
    if torch.cuda.is_available():
        print("GPU name:", torch.cuda.get_device_name(0))
        x = torch.randn(256,256, device='cuda'); y = torch.mm(x, x)
        print("CUDA test ok:", y is not None)
    PY
    ```
  - FFmpeg NVENC：
    ```bash
    ffmpeg -hide_banner -encoders | findstr nvenc
    ```
- Linux/VAAPI
    ```bash
    ffmpeg -hide_banner -hwaccels
    vainfo || echo "Install vainfo (VAAPI) to inspect devices"
    ```

## 6. 数据目录与路径约定
- 用户数据目录与 config/data/uploads 约定：参考 [app_paths.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/app_paths.py)。
- 上传目录挂载与后端 serviceData：参考 [main.py:get_app_paths](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/main.py#L320-L395)。
- 相关服务使用 `/uploads` 构建 Web 访问路径（示例参考剪映草稿服务）：[jianying_draft_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/services/jianying_draft_service.py#L31-L44)。

## 7. 安全与错误处理
- 凭据脱敏：接口返回隐藏 secret_id/secret_key/api_key（参考 [safe_tts_config_dict_hide_secret](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L26-L33)）。
- 错误显式：网络错误与不可用状态必须明确返回与提示；不做静默回退。
- 日志与隐私：runtime_log_store 做关键字遮蔽，避免泄露（参考 [runtime_log_store.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/runtime_log_store.py#L1-L25)）。

## 8. 前端工程约定
- 依赖安装：使用 cnpm。
  ```bash
  cnpm install
  ```
- Node 版本：使用 nvm 切换。
  ```bash
  nvm use
  ```
- 组件化设计：将复杂逻辑提取至 hooks 与服务层（useTtsEngineInstaller、useGpuDiagnostics），保持 TTS 设置与 GPU 卡片组件简洁。
- UI 控件合并：“下载/卸载/修复”使用下拉或分组控件，避免按钮堆叠。

## 9. 与 Index TTS 的关系与扩展
- 在线版 Index TTS：后端统一发起 HTTP/SDK 调用；安装仅下载元数据与资源包并写标记。
- 本地版 Index TTS（如需 GPU）：作为“index_tts_local”插件接入；安装后走深度学习设备选择器校验，支持 fp16；不满足条件则回退到在线版或禁用本地版。

## 10. 实施最小改动清单
- 后端
  - 新增模块：`modules/index_tts_service.py`、`modules/installers/index_tts_installer.py`、`modules/gpu_system.py`、`modules/video_hwaccel.py`。
  - 配置层：`modules/config/tts_config.py` 增加 provider=index_tts 的白名单、默认配置与 get_engines_meta/get_voices/test_connection 分支。
  - 合成网关：`modules/tts_service.py` 增加 index_tts 分支调用 index_tts_service。
  - 路由：`routes/tts_routes.py` 复用；新增 `routes/gpu_routes.py`（status/test/backends）与 `routes/index_tts_install_routes.py`（status/install/uninstall）。
- 前端
  - 设置页新增“Index TTS 安装卡片”与“GPU 加速”卡片。
  - 新增 hooks：`useTtsEngineInstaller` 与 `useGpuDiagnostics`。
  - 复用现有服务调用风格：`frontend/src/services/clients.ts`。

## 11. 参考代码位置
- TTS 合成网关与腾讯/Edge 分支：[tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/tts_service.py#L54-L190)
- TTS 配置管理与引擎/音色/测试：[tts_config.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/config/tts_config.py#L1-L509)
- TTS 路由与预览/配置返回脱敏：[tts_routes.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/routes/tts_routes.py#L1-L343)
- Edge TTS 服务实现参考：[edge_tts_service.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/edge_tts_service.py#L1-L337)
- 路径约定与挂载：[app_paths.py](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/modules/app_paths.py)，[main.py:get_app_paths](file:///Users/jiangchao/Documents/江汐瑶/学习/测试/superAIAutoCutVideo/backend/main.py#L320-L395)

