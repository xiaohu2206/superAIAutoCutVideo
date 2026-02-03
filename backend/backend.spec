# -*- mode: python ; coding: utf-8 -*-

import sys
import os
from PyInstaller.utils.hooks import collect_all

# 基础数据文件：将 serviceData 目录打包进 exe
datas = [
    ('serviceData', 'serviceData'),
]
cache_dir = '../.trae/cache/Qwen3-TTS'
if os.path.isdir(cache_dir):
    datas.append((cache_dir, '.trae/cache/Qwen3-TTS'))
binaries = []
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
for package in ['cv2', 'numpy', 'uvicorn', 'fastapi', 'pydantic', 'transformers', 'huggingface_hub', 'soundfile', 'modelscope']:
    try:
        tmp_ret = collect_all(package)
        datas += tmp_ret[0]
        binaries += tmp_ret[1]
        hiddenimports += tmp_ret[2]
    except Exception as e:
        print(f"Warning: Failed to collect {package}: {e}")

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='superAutoCutVideoBackend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False, # 关闭控制台窗口，避免弹黑框
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
