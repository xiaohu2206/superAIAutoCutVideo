# 后端依赖安装命令（GPU 版 llama-cpp-python）

适用场景：在新电脑上“直接安装依赖并运行后端（源码）”，并确保 Moondream GGUF 走 GPU offload（而不是 CPU）。

## 0. 前置条件（Windows）

- 安装 Python 3.11（建议用 `py -3.11`）
- 安装 Visual Studio 2022 Build Tools（包含 C++ 编译工具）
- 安装 NVIDIA 驱动（能正常识别 GPU）

## 1. 创建并使用 GPU 虚拟环境

在仓库根目录执行：

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo

# 创建 venv（已存在会跳过）
if (-not (Test-Path .\backend\.venv_pack_gpu)) { py -3.11 -m venv .\backend\.venv_pack_gpu }

$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

# 基础工具
& $py -m pip install -U pip setuptools wheel
```

## 2. 安装后端运行依赖

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

& $py -m pip install -r .\backend\requirements.runtime.txt
```

## 2.0 安装 PyTorch（GPU 版，VoxCPM/Qwen3‑TTS 需要）

说明：GPU 推理需要安装 CUDA 构建的 torch；如果你装的是 CPU 版 torch，会导致 `/api/tts/*/acceleration-status` 显示不支持 GPU，或推理只能走 CPU。

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

& $py -m pip install --no-deps torch==2.7.1+cu128 torchvision==0.22.1+cu128 torchaudio==2.7.1+cu128 --index-url https://download.pytorch.org/whl/cu128
& $py -c "import torch; print('torch', torch.__version__, 'cuda', bool(torch.cuda.is_available()))"
```

## 2.1 安装 Qwen3‑TTS（可选）

说明：为避免 pip 解析依赖时联动升级/降级核心库（如 numpy、torch 等），推荐按项目打包策略使用 `--no-deps` 单独安装。

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

& $py -m pip install qwen-tts --no-deps
& $py -c "import qwen_tts; print('qwen_tts_ok')"
```

补充：
- Qwen3‑TTS 的模型文件不随依赖安装自动下载；需要你把模型放到本地目录（应用内也有模型管理/下载/校验能力）。
- 如果你改用 `requirements.txt`（非 runtime）安装依赖，请遵循项目的 numpy 约束（见 requirements 里的说明），避免与 numba 等库冲突。

## 2.2 安装 VoxCPM（可选）

说明：`requirements.runtime.txt` 里只包含 VoxCPM 的前置依赖（`simplejson`、`sortedcontainers`），主包需要你手动装，并且必须 `--no-deps` 以避免依赖冲突。
如果你使用仓库的一键打包脚本 `scripts/build.ps1 -Variant gpu`，脚本会自动安装 `voxcpm` 并做导入自检。

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

& $py -m pip install --no-deps voxcpm
& $py -c "import voxcpm; from voxcpm import VoxCPM; from modules.vendor.voxcpm_tts import VoxCPMTTSModel; print('voxcpm_ok')"
```

## 3. 安装 CUDA 构建的 llama-cpp-python（关键）

直接运行仓库脚本（它会在 `backend\.venv_pack_gpu` 里强制用 `GGML_CUDA=on` 重新编译安装）：

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
.\backend\scripts\install_llama_gpu_pack.bat
```

## 4. 验证是否真的是 GPU 版（必须）

### 4.1 检查 GPU offload 能力

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo
$py = Resolve-Path .\backend\.venv_pack_gpu\Scripts\python.exe

& $py -c "import llama_cpp; import llama_cpp.llama_cpp as ll; print('llama_cpp', llama_cpp.__version__); print('supports_gpu_offload', bool(ll.llama_supports_gpu_offload()))"
```

期望输出包含：`supports_gpu_offload True`

### 4.2 检查 Moondream 加速状态（代码同 `/api/moondream/acceleration-status`）

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo\backend
$py = Resolve-Path .\.\.venv_pack_gpu\Scripts\python.exe

& $py -c "import json; from modules.moondream_acceleration import get_moondream_acceleration_status; print(json.dumps(get_moondream_acceleration_status(), ensure_ascii=False))"
```

期望输出包含：`"supported": true` 且 `"llama_cpp": {"supports_gpu_offload": true, ...}`

## 5. 用 GPU 环境启动后端（避免装对了但跑错环境）

```powershell
Set-Location C:\Users\Administrator\Documents\superAIAutoCutVideo\backend
& (Resolve-Path .\.venv_pack_gpu\Scripts\python.exe) .\main.py
```

## 常见问题

- `torch.cuda.is_available()==True` 但 `supports_gpu_offload==False`：说明 `llama-cpp-python` 仍是 CPU 构建；请重新执行第 3 步。
- 后端启动后仍显示不支持：大概率是后端进程用的不是 `.venv_pack_gpu`（请用第 5 步的方式启动）。
