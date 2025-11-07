#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
诊断脚本：检查 backend/config/content_model_config.json 加载失败的原因。

功能：
- 显示目标配置文件路径与存在性；
- 读取并打印顶层结构与配置项数量；
- 使用 ContentModelConfig 逐项校验，打印具体的校验/构造异常；
- 使用 ContentModelConfigManager 指定路径加载，打印成功加载的数量与活动配置；
"""

import json
import sys
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
logger = logging.getLogger("debug_content_model_config")


def ensure_backend_on_path():
    root = Path(__file__).resolve().parents[1]
    backend_dir = root / "backend"
    if str(backend_dir) not in sys.path:
        sys.path.insert(0, str(backend_dir))
    return backend_dir


def print_env_info(cfg_path: Path):
    print("=== 环境信息 ===")
    print(f"Python: {sys.executable}")
    print(f"CWD: {Path.cwd()}")
    print(f"目标配置文件: {cfg_path} (存在: {cfg_path.exists()})")
    if cfg_path.exists():
        try:
            print(f"文件大小: {cfg_path.stat().st_size} 字节")
        except Exception:
            pass
    print()


def read_raw_json(cfg_path: Path):
    print("=== 原始JSON检查 ===")
    if not cfg_path.exists():
        print("配置文件不存在！")
        return None
    try:
        with cfg_path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        top_keys = list(data.keys())
        print(f"顶层键: {top_keys}")
        if isinstance(data.get("configs"), dict):
            print(f"configs 项数量: {len(data['configs'])}")
        else:
            print("configs 不是字典，结构异常")
        print()
        return data
    except Exception as e:
        print(f"读取/解析JSON失败: {e}")
        return None


def validate_each_config(data):
    print("=== 逐项校验 ===")
    if not data or not isinstance(data.get("configs"), dict):
        print("无有效 configs 结构，跳过逐项校验。")
        print()
        return

    try:
        # 延迟导入，确保路径已加入
        from modules.config.content_model_config import ContentModelConfig
    except Exception as e:
        print(f"导入 ContentModelConfig 失败: {e}")
        print()
        return

    ok_count = 0
    for cfg_id, cfg in data["configs"].items():
        try:
            ContentModelConfig(**cfg)
            ok_count += 1
        except Exception as e:
            print(f"[校验失败] {cfg_id}: {e}")
    print(f"校验通过数量: {ok_count} / {len(data['configs'])}")
    print()


def test_manager_load(cfg_path: Path):
    print("=== 管理器加载 ===")
    try:
        from modules.config.content_model_config import ContentModelConfigManager
    except Exception as e:
        print(f"导入 ContentModelConfigManager 失败: {e}")
        print()
        return

    try:
        mgr = ContentModelConfigManager(config_file=str(cfg_path))
        all_configs = mgr.get_all_configs()
        active_id = mgr.get_active_config_id()
        print(f"管理器配置数量: {len(all_configs)}")
        print(f"活动配置ID: {active_id}")
        if len(all_configs) == 0:
            print("提示: 管理器为空，可能是部分配置校验失败被忽略，请查看上面的逐项校验错误。")
    except Exception as e:
        print(f"管理器初始化/加载失败: {e}")
    print()


def main():
    backend_dir = ensure_backend_on_path()
    cfg_path = backend_dir / "config" / "content_model_config.json"
    print_env_info(cfg_path)
    data = read_raw_json(cfg_path)
    validate_each_config(data)
    test_manager_load(cfg_path)


if __name__ == "__main__":
    main()