#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Omni 本地句向量：BAAI/bge-base-zh-v1.5。

仅依赖项目已有的 torch + transformers（与 SentenceTransformer 导出目录布局兼容），
不要求单独安装 sentence-transformers。

默认模型目录：backend/serviceData/models/bge-base-zh-v1.5/
（ModelScope 布局下权重在 …/BAAI/bge-base-zh-v1.5/）

可通过环境变量 OMNI_LOCAL_BGE_MODEL_PATH 覆盖为任意含 config.json / tokenizer 的 BERT 类模型目录。
池化方式与随模型自带的 1_Pooling/config.json 一致（bge-base-zh-v1.5 为 CLS + L2 归一化）。
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional, Tuple

logger = logging.getLogger(__name__)

LOCAL_BGE_MODEL_DISPLAY_NAME = "BAAI/bge-base-zh-v1.5 (local)"

_bundle: Optional["_BgeBundle"] = None
_init_lock = threading.Lock()
_encode_lock = threading.Lock()


def _backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def resolve_bge_model_dir() -> Path:
    override = (os.environ.get("OMNI_LOCAL_BGE_MODEL_PATH") or "").strip()
    if override:
        p = Path(override).expanduser().resolve()
        if not p.is_dir():
            raise FileNotFoundError(f"OMNI_LOCAL_BGE_MODEL_PATH 不是目录: {p}")
        return p

    root = _backend_dir() / "serviceData" / "models" / "bge-base-zh-v1.5"
    candidates = [
        root / "BAAI" / "bge-base-zh-v1.5",
        root,
    ]
    for p in candidates:
        if not p.is_dir():
            continue
        if (p / "config.json").is_file() and (p / "tokenizer_config.json").is_file():
            return p
    raise FileNotFoundError(
        f"未找到本地 bge-base-zh 模型，请确认已下载到 {root} "
        f"或设置环境变量 OMNI_LOCAL_BGE_MODEL_PATH"
    )


def assert_local_bge_model_available() -> Path:
    """启动或任务开始前校验路径存在，便于给出明确错误信息。"""
    return resolve_bge_model_dir()


def _read_pooling_mode(model_dir: Path) -> Tuple[bool, bool]:
    """返回 (use_cls, use_mean)。默认 CLS，与 bge-base-zh-v1.5 随包配置一致。"""
    cfg_path = model_dir / "1_Pooling" / "config.json"
    if not cfg_path.is_file():
        return True, False
    try:
        data = json.loads(cfg_path.read_text(encoding="utf-8"))
        cls_on = bool(data.get("pooling_mode_cls_token"))
        mean_on = bool(data.get("pooling_mode_mean_tokens"))
        return cls_on, mean_on
    except Exception:
        return True, False


@dataclass
class _BgeBundle:
    tokenizer: Any
    torch_model: Any
    device: Any
    max_length: int
    use_cls: bool
    use_mean: bool


def _pick_device() -> Any:
    try:
        import torch

        if torch.cuda.is_available():
            return torch.device("cuda")
    except Exception:
        pass
    try:
        import torch

        return torch.device("cpu")
    except ImportError as e:
        raise RuntimeError("未安装 PyTorch（torch），无法运行本地 BGE。") from e


def _get_bundle() -> _BgeBundle:
    global _bundle
    with _init_lock:
        if _bundle is not None:
            return _bundle
        try:
            import torch
            from transformers import AutoModel, AutoTokenizer
        except ImportError as e:
            raise RuntimeError(
                "未安装 transformers / torch，无法加载本地 BGE。请执行: pip install -r backend/requirements.txt"
            ) from e

        model_dir = resolve_bge_model_dir()
        use_cls, use_mean = _read_pooling_mode(model_dir)
        if not use_cls and not use_mean:
            use_cls = True

        cfg_path = model_dir / "config.json"
        max_len = 512
        try:
            cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
            max_len = int(cfg.get("max_position_embeddings") or 512)
        except Exception:
            pass
        max_len = max(64, min(max_len, 8192))

        logger.info("[omni-local-bge] 加载 transformers 模型: %s (cls=%s mean=%s)", model_dir, use_cls, use_mean)
        tokenizer = AutoTokenizer.from_pretrained(str(model_dir), trust_remote_code=True)
        torch_model = AutoModel.from_pretrained(str(model_dir), trust_remote_code=True)
        device = _pick_device()
        torch_model.to(device)
        torch_model.eval()

        _bundle = _BgeBundle(
            tokenizer=tokenizer,
            torch_model=torch_model,
            device=device,
            max_length=max_len,
            use_cls=use_cls,
            use_mean=use_mean,
        )
        return _bundle


def encode_text_sync(text: str) -> List[float]:
    """
    单条文本编码为 float 列表；L2 归一化，与 sentence-transformers normalize_embeddings=True 对齐用途。
    """
    s = (text or "").strip()
    if not s:
        s = " "

    import torch

    b = _get_bundle()
    with _encode_lock:
        inputs = b.tokenizer(
            s,
            return_tensors="pt",
            padding=True,
            truncation=True,
            max_length=b.max_length,
        )
        inputs = {k: v.to(b.device) for k, v in inputs.items()}
        with torch.no_grad():
            out = b.torch_model(**inputs)
            last_hidden = out.last_hidden_state
            if b.use_cls:
                emb = last_hidden[:, 0, :]
            elif b.use_mean:
                mask = inputs.get("attention_mask")
                if mask is None:
                    emb = last_hidden.mean(dim=1)
                else:
                    mask_exp = mask.unsqueeze(-1).type_as(last_hidden)
                    summed = (last_hidden * mask_exp).sum(dim=1)
                    counts = mask_exp.sum(dim=1).clamp(min=1e-9)
                    emb = summed / counts
            else:
                emb = last_hidden[:, 0, :]
            emb = torch.nn.functional.normalize(emb, p=2, dim=1)
            vec = emb[0].detach().float().cpu()

    out_list = vec.tolist() if hasattr(vec, "tolist") else [float(x) for x in vec]
    if not out_list:
        raise RuntimeError("本地 BGE 返回空向量")
    return out_list


async def encode_text_async(text: str) -> List[float]:
    return await asyncio.to_thread(encode_text_sync, text)
