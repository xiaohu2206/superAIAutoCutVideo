# -*- mode: python ; coding: utf-8 -*-

import sys
import os
import importlib.util
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs, collect_submodules

# 基础数据文件：将 serviceData 目录打包进 exe
datas = [
    ('serviceData', 'serviceData'),
]
cache_dir = '../.trae/cache/Qwen3-TTS'
if os.path.isdir(cache_dir):
    datas.append((cache_dir, '.trae/cache/Qwen3-TTS'))
binaries = []
try:
    _tbb12 = os.path.join(sys.prefix, 'Library', 'bin', 'tbb12.dll')
    if os.path.isfile(_tbb12):
        binaries.append((_tbb12, '.'))
except Exception:
    pass
# 基础隐式导入
hiddenimports = [
    'uvicorn.logging',
    'uvicorn.loops',
    'uvicorn.loops.auto',
    'uvicorn.protocols',
    'uvicorn.protocols.http',
    'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets',
    'uvicorn.protocols.websockets.auto',
    'uvicorn.lifespan',
    'uvicorn.lifespan.on',
    'fastapi',
    'pydantic',
    'starlette',
    'multipart',
    'engineio.async_drivers.aiohttp', # 常见遗漏：Socket.IO 异步驱动
    'qwen_tts',  # 动态导入的第三方包，确保打包后可用
    'llama_cpp',
    'llama_cpp.llama_cpp',
    'torch.distributed',
    'torch.distributed.rpc',
    'funasr.register',
    'funasr.register.tables',
]

# 轻量收集：避免对 transformers/torch 等超大库做 collect_all() 触发超长扫描
# 这里优先保证可运行与打包速度；如后续出现“动态导入缺失”，再按报错补充 hiddenimports/datas/binaries。
_maybe_packages = [
    'cv2',
    'numpy',
    'pandas',
    'pkg_resources',
    'uvicorn',
    'fastapi',
    'pydantic',
    'dashscope',
    'onnxruntime',
    'tensorflow',
    'librosa',
    'soundfile',
    'modelscope',
    'funasr',
    'transformers',
    'huggingface_hub',
    'whisper',
    'tiktoken',
    'torch',
    'torchvision',
    'torchaudio',
]
for package in _maybe_packages:
    hiddenimports.append(package)

# 优化收集策略：避免对 torch/transformers 等超大库做全量扫描
# PyInstaller 已内置 torch hook，通常不需要手动 collect_data_files
for package in ['onnxruntime', 'librosa', 'modelscope']:
    try:
        datas += collect_data_files(package)
    except Exception as e:
        print(f"Warning: Failed to collect data files for {package}: {e}")

try:
    if importlib.util.find_spec("pandas") is not None:
        datas += collect_data_files("pandas")
        binaries += collect_dynamic_libs("pandas")
except Exception as e:
    print(f"Warning: Failed to collect pandas extras: {e}")

# 移除对 torch/torchvision/torchaudio/transformers 的手动收集，依赖内置 hook
# for package in ['transformers', 'torch', 'torchvision', 'torchaudio']: ...

try:
    _funasr_ok = importlib.util.find_spec("funasr") is not None
except Exception:
    _funasr_ok = False
if _funasr_ok:
    try:
        hiddenimports += collect_submodules("funasr")
        datas += collect_data_files("funasr")
    except Exception as e:
        print(f"Warning: Failed to collect funasr extras: {e}")

try:
    _whisper_ok = importlib.util.find_spec("whisper") is not None
except Exception:
    _whisper_ok = False
if _whisper_ok:
    try:
        hiddenimports += collect_submodules("whisper")
        datas += collect_data_files("whisper")
    except Exception as e:
        print(f"Warning: Failed to collect whisper extras: {e}")

# 优化：移除对 torch 系列的手动动态库收集，避免 Windows 下扫描数千个 DLL 导致打包挂起
# PyInstaller 内置 hook 已能很好处理 PyTorch
for package in ['onnxruntime', 'soundfile', 'tiktoken']:
    try:
        binaries += collect_dynamic_libs(package)
    except Exception as e:
        print(f"Warning: Failed to collect dynamic libs for {package}: {e}")

try:
    _modelscope_ok = importlib.util.find_spec("modelscope") is not None
except Exception:
    _modelscope_ok = False
if _modelscope_ok:
    try:
        hiddenimports += [
            "modelscope",
            "modelscope.hub",
            "modelscope.hub.snapshot_download",
            "modelscope.hub.api",
            "modelscope.hub.errors",
            "modelscope.hub.file_download",
            "modelscope.hub.utils",
            "modelscope.utils",
            "modelscope.utils.constant",
            "modelscope.utils.config",
            "modelscope.utils.file_utils",
            "modelscope.utils.import_utils",
            "modelscope.utils.logger",
            "modelscope.utils.device",
            "modelscope.utils.hf_util",
        ]
        datas += collect_data_files("modelscope", includes=["**/*.json", "**/*.yaml", "**/*.yml"])
    except Exception as e:
        print(f"Warning: Failed to collect modelscope extras: {e}")

try:
    if importlib.util.find_spec("llama_cpp") is not None:
        _d, _b, _h = collect_all("llama_cpp")
        datas += _d
        binaries += _b
        hiddenimports += _h
except Exception as e:
    print(f"Warning: Failed to collect llama_cpp extras: {e}")

def _is_importable(mod_name: str) -> bool:
    try:
        return importlib.util.find_spec(mod_name) is not None
    except Exception:
        return False

_exclude_hidden_prefixes = [
    "transformers.kernels.falcon_mamba",
    "torch.distributed._sharding_spec.chunk_sharding_spec_ops.",
]

_filtered_hidden = []
for _m in hiddenimports:
    if any(_m.startswith(p) for p in _exclude_hidden_prefixes):
        continue
    if _m == "funasr" or _m.startswith("funasr."):
        _filtered_hidden.append(_m)
        continue
    if _m == "modelscope" or _m.startswith("modelscope."):
        _filtered_hidden.append(_m)
        continue
    if _m == "whisper" or _m.startswith("whisper."):
        _filtered_hidden.append(_m)
        continue
    if _m == "tiktoken" or _m.startswith("tiktoken."):
        _filtered_hidden.append(_m)
        continue
    if _is_importable(_m):
        _filtered_hidden.append(_m)
hiddenimports = sorted(set(_filtered_hidden))

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'transformers.kernels.falcon_mamba',
        'mamba_ssm',
        'sklearn',
        'torch.utils.tensorboard',
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='superAutoCutVideoBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 关闭控制台窗口，避免弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='superAutoCutVideoBackend',
)
