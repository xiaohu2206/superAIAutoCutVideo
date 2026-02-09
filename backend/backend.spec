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
    'torch.distributed',
    'torch.distributed.rpc',
]

# 轻量收集：避免对 transformers/torch 等超大库做 collect_all() 触发超长扫描
# 这里优先保证可运行与打包速度；如后续出现“动态导入缺失”，再按报错补充 hiddenimports/datas/binaries。
_maybe_packages = [
    'cv2',
    'numpy',
    'uvicorn',
    'fastapi',
    'pydantic',
    'onnxruntime',
    'librosa',
    'soundfile',
    'modelscope',
    'transformers',
    'huggingface_hub',
    'torch',
    'torchvision',
    'torchaudio',
]
for package in _maybe_packages:
    hiddenimports.append(package)

for package in ['onnxruntime', 'librosa', 'transformers', 'modelscope', 'torch', 'torchvision', 'torchaudio']:
    try:
        datas += collect_data_files(package)
    except Exception as e:
        print(f"Warning: Failed to collect data files for {package}: {e}")

for package in ['onnxruntime', 'torch', 'torchvision', 'torchaudio', 'soundfile']:
    try:
        binaries += collect_dynamic_libs(package)
    except Exception as e:
        print(f"Warning: Failed to collect dynamic libs for {package}: {e}")

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
        'pandas',
        'sklearn',
        'torch.distributed',
        'torch.distributed._shard.checkpoint',
        'torch.distributed._sharded_tensor',
        'torch.distributed._sharding_spec',
        'torch.testing',
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
