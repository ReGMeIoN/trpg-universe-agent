# -*- coding: utf-8 -*-
"""看看本机 venv 里现成了哪些网络分析 / 数据处理轮子（用来决定推荐什么方案）。"""
from __future__ import annotations

import importlib
import sys

MODS = [
    # 图 / 网络分析
    "networkx", "igraph", "community", "leidenalg", "graph_tool",
    # 数据
    "pandas", "numpy", "scipy", "sklearn", "polars", "duckdb",
    # 可视化
    "matplotlib", "pyvis", "graphviz", "pygraphviz", "plotly", "seaborn",
    # 图数据库 / 查询
    "neo4j", "rdflib", "kuzu",
    # 文本 / NLP
    "spacy", "jieba", "transformers",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ok, miss = [], []
    for m in MODS:
        try:
            mod = importlib.import_module(m)
            ok.append((m, getattr(mod, "__version__", "?")))
        except Exception as e:  # noqa: BLE001
            miss.append((m, type(e).__name__))
    print("已装：")
    for m, v in ok:
        print(f"  ✔ {m:<12} {v}")
    print("\n没装：")
    for m, e in miss:
        print(f"  ✘ {m:<12} {e}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
