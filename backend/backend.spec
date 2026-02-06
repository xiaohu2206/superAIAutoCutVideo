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
]

# 自动收集关键库的所有依赖（数据、二进制、隐式导入）
# 这样比手动写 hiddenimports 更稳健
for package in ['cv2', 'numpy', 'uvicorn', 'fastapi', 'pydantic', 'transformers', 'huggingface_hub', 'soundfile', 'modelscope', 'onnxruntime']:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Failed to collect {package}: {e}")

for package in ['librosa']:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Failed to collect {package}: {e}")

for package in ['torch', 'torchvision', 'torchaudio']:
    try:
        datas += collect_data_files(package, include_py_files=True)
        binaries += collect_dynamic_libs(package)
        hiddenimports += collect_submodules(package)
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        raise RuntimeError(f"Failed to collect required package {package}: {e}")

for package in [
    'nvidia.cublas',
    'nvidia.cudnn',
    'nvidia.cuda_nvrtc',
    'nvidia.cuda_runtime',
    'nvidia.cufft',
    'nvidia.curand',
    'nvidia.cusolver',
    'nvidia.cusparse',
    'nvidia.nvtx',
]:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Failed to collect {package}: {e}")

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
        'torch.distributed._shard.checkpoint',
        'torch.distributed._sharded_tensor',
        'torch.distributed._sharding_spec',
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
