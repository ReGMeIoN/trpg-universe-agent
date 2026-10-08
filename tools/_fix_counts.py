# -*- coding: utf-8 -*-
"""One-off: align the documented transcript count with the real line count.

The transcribe counter double-counts the batch that is redone after a resume (the output
file is truncated back to the batch start, but `segments` keeps its old value). The real
deliverable is the file, so docs should quote the line count.

usage: python tools/_fix_counts.py [--apply]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))
BAD = "15401"
GOOD = "15015"
NOTE = (
    "\n> 计数说明：转写工具日志报的 `15401 段` 包含了断点续跑时被重做的那一批（产物文件已截断回"
    "该批起点，计数器没有回退），**以产物文件为准 = 15015 行**。\n"
)

FILES = [
    ROOT / "docs" / "\u65b0\u56e2\u8f6c\u5f55-\u4ea4\u4ed8\u8bf4\u660e-2026-10-05.md",
    WS / ".trpg" / "reports" / "\u65b0\u56e2\u8f6c\u5f55_\u4f1a\u8bdd\u62a5\u544a_20261005.md",
    ROOT / "\u9879\u76ee\u72b6\u6001\u4ea4\u63a5.md",
]
ANCHOR = "\u9634\u9633\u5dee\u4e8b\u5f55 超自然怪谈** | ✅ "  # 表格行，仅用于报告插入定位


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    for p in FILES:
        if not p.is_file():
            print(f"!! 缺文件 {p}")
            continue
        text = p.read_text(encoding="utf-8")
        hits = text.count(BAD)
        if not hits:
            print(f"  ok      {p.name}: 没有 {BAD}")
            continue
        new = text.replace(f"{BAD} \u6bb5", f"{GOOD} \u884c").replace(BAD, GOOD)
        if NOTE.strip() not in new and "计数说明" not in new:
            new = new.rstrip() + "\n" + NOTE
        print(f"  {'fix' if apply else 'dry'}     {p.name}: {hits} 处 -> {GOOD}")
        if apply:
            p.write_text(new, encoding="utf-8")
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
