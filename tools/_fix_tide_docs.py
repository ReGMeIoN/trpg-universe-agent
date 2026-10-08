# -*- coding: utf-8 -*-
"""Round-2 answer normalisation across derived docs (not the raw transcript)."""
from __future__ import annotations

import os
import argparse
import shutil
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
OUT = WS / "\u4ea7\u51fa"
KB = OUT / "astrbot\u77e5\u8bc6\u5e93\u5bfc\u5165"
REPORTS = WS / ".trpg" / "reports"

RULES = [
    ("\u5929\u773c\u9738\u6740", "\u5929\u5143\u5927\u4eba"),        # 天眼霸杀 -> 天元大人
    ("\u516b\u53d8\u573a", "\u5df4\u522b\u5854\u65e7\u5740"),        # 八变场 -> 巴别塔旧址
    ("\u94c1\u5976\u9f99", "\u5178\u72f1\u957f\u9636\u5976\u9f99"),  # 铁奶龙 -> 典狱长阶奶龙
]

TARGETS = [
    OUT / ("\u6f6e\u6c50\u76d1\u72f1_\u5267\u60c5\u7f16\u5e74\u53f2.md"),
    OUT / "\u6770\u514b\u6863\u6848.md",
    KB / "\u6f6e\u6c50\u76d1\u72f1.md",
    KB / "00c_\u6770\u514b\u6863\u6848.md",
    KB / "00b_\u6770\u514b\u6863\u6848.md",
    REPORTS / "\u6770\u514b\u6863\u6848_\u81ea\u52a8\u66f4\u65b0\u5efa\u8bae.md",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f in TARGETS:
        if not f.is_file():
            print("  !! missing: %s" % f.name)
            continue
        txt = f.read_text(encoding="utf-8")
        hits = {old: txt.count(old) for old, _ in RULES if old in txt}
        if not hits:
            print("  == %s: no change" % f.name)
            continue
        for old, new in RULES:
            txt = txt.replace(old, new)
        print("  OK %s: %s" % (f.name, hits))
        if a.apply:
            shutil.copyfile(f, f.with_name(f.name + ".bak_tideqa_" + stamp))
            f.write_text(txt, encoding="utf-8")
    if not a.apply:
        print("\n[dry-run] add --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
