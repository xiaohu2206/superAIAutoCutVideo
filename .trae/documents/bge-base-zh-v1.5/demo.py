#!/usr/bin/env python3
"""
本地中文句向量 Demo：从 ModelScope 下载 BAAI/bge-base-zh-v1.5 到 ./models，再本地编码与相似度检索。
模型页：https://www.modelscope.cn/models/BAAI/bge-base-zh-v1.5/summary
"""

from __future__ import annotations

import math
from pathlib import Path

from modelscope import snapshot_download
from sentence_transformers import SentenceTransformer, util

# 模型固定放在项目目录下的 models 里
PROJECT_ROOT = Path(__file__).resolve().parent
MODEL_CACHE = PROJECT_ROOT / "models"
MODEL_ID = "BAAI/bge-base-zh-v1.5"


def cosine_sim(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0


def ensure_model_local() -> str:
    MODEL_CACHE.mkdir(parents=True, exist_ok=True)
    print(f"检查/下载模型到: {MODEL_CACHE}")
    path = snapshot_download(MODEL_ID, cache_dir=str(MODEL_CACHE))
    print(f"模型目录: {path}")
    return path


def main() -> None:
    model_path = ensure_model_local()
    print("加载 SentenceTransformer（首次会编译/缓存 tokenizer）…")
    model = SentenceTransformer(model_path, trust_remote_code=True)

    corpus = [
        "机器学习是人工智能的一个分支",
        "今天北京天气晴朗适合出门",
        "深度学习使用多层神经网络进行表示学习",
        "红烧牛肉面是一道常见的中式面食",
    ]
    query = "神经网络与表示学习"

    print("\n=== 批量编码语料 ===")
    corpus_emb = model.encode(corpus, normalize_embeddings=True, show_progress_bar=False)
    query_emb = model.encode(query, normalize_embeddings=True, show_progress_bar=False)

    print("\n=== 与查询句的相似度（越高越相关）===")
    scores = util.cos_sim(query_emb, corpus_emb)[0]
    ranked = sorted(zip(corpus, scores.tolist()), key=lambda x: x[1], reverse=True)
    for text, score in ranked:
        print(f"  {score:.4f}  {text}")

    # 与手写余弦一致性抽查
    q0, c0 = query_emb.tolist(), corpus_emb[0].tolist()
    print(f"\n手写余弦(query, corpus[0]) = {cosine_sim(q0, c0):.6f}")
    print("Demo 运行完成。")


if __name__ == "__main__":
    main()
