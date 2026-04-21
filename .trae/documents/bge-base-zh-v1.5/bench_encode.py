#!/usr/bin/env python3
"""对固定条数文本做 encode 计时（不含首次模型加载）。"""

from __future__ import annotations

import argparse
from time import perf_counter

from sentence_transformers import SentenceTransformer

from demo import ensure_model_local


def build_texts(n: int) -> list[str]:
    base = (
        "机器学习与深度学习在自然语言处理、推荐系统与图像识别中的应用正在快速推进；"
        "向量检索可以把语义相近的段落聚在一起。"
    )
    return [f"第{i + 1}段：{base}" for i in range(n)]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("-n", type=int, default=100, help="文本条数")
    p.add_argument("--batch-size", type=int, default=None, help="encode batch_size，默认由库决定")
    args = p.parse_args()

    path = ensure_model_local()
    print("加载模型…")
    t0 = perf_counter()
    model = SentenceTransformer(path, trust_remote_code=True)
    t_load = perf_counter() - t0
    print(f"模型加载耗时: {t_load:.3f} s\n")

    texts = build_texts(args.n)
    kw = {"normalize_embeddings": True, "show_progress_bar": False}
    if args.batch_size is not None:
        kw["batch_size"] = args.batch_size

    t1 = perf_counter()
    _ = model.encode(texts, **kw)
    t_enc = perf_counter() - t1

    print(f"文本条数: {args.n}")
    if args.batch_size is not None:
        print(f"batch_size: {args.batch_size}")
    print(f"纯向量化（encode）耗时: {t_enc:.3f} s")
    print(f"平均每条: {t_enc / args.n * 1000:.2f} ms")


if __name__ == "__main__":
    main()
