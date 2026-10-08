# -*- coding: utf-8 -*-
"""列出「有 CG 的小节」及其正文，用于判断该场景是哪些 PC 的戏。

用法:
    .venv\\Scripts\\python.exe tools\\_cg_scene_report.py
    .venv\\Scripts\\python.exe tools\\_cg_scene_report.py --full    # 打印正文全文
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PC = ["八重樱", "莉亚·岩心", "妮娜·可可", "飒飒米", "流星亚什"]
# 常见简称/别名，用于粗判"这一节是不是某 PC 的戏"
ALIAS = ["八重樱", "宽", "莉亚", "妮娜", "可可", "飒飒米", "撒撒米", "流星亚什", "亚什", "雪人"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    raw = (ROOT / "site" / "data" / "bundle.js").read_text(encoding="utf-8")
    d = json.loads(raw[raw.index("{"):raw.rindex(";")])
    pages = d["pages"]
    cg = set((d["meta"].get("assets") or {}).get("cg", []))

    # 小节首页（正好是挂 CG 的那页）
    sections = [p for p in pages if p.get("part") == 0]
    print(f"小节数 {len(sections)}　有 CG 的 {len(cg)}\n")
    for p in sections:
        hit = [x for x in ALIAS if x in (p.get("body") or "") or x in (p.get("title") or "")]
        mark = "★有CG" if p["key"] in cg else "      "
        who = "/".join(dict.fromkeys(hit)) if hit else "-"
        print(f"{mark} {p['key']}  {p['time']:>7}  {p['title'][:26]:<28} PC: {who}")
        if a.full and p["key"] in cg:
            print("      " + (p.get("body") or "")[:400].replace("\n", " "))
    return 0


if __name__ == "__main__":
    sys.exit(main())
