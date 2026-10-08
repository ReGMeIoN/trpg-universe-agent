# -*- coding: utf-8 -*-
"""Fix the mechanical double-suffix produced by the 八变场 -> 巴别塔旧址 rewrite."""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
BAD = "\u5df4\u522b\u5854\u65e7\u5740\u65e7\u5740"     # 巴别塔旧址旧址
GOOD = "\u5df4\u522b\u5854\u65e7\u5740"                 # 巴别塔旧址


def walk(node) -> int:
    n = 0
    if isinstance(node, dict):
        for k, v in list(node.items()):
            if isinstance(v, str):
                if BAD in v:
                    n += v.count(BAD)
                    node[k] = v.replace(BAD, GOOD)
            else:
                n += walk(v)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                if BAD in v:
                    n += v.count(BAD)
                    node[i] = v.replace(BAD, GOOD)
            else:
                n += walk(v)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    total = 0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f in [WS / "\u6570\u636e" / "characters.json",
              WS / "\u6570\u636e" / "relations.json",
              WS / ".trpg" / "patches" / ("\u6f6e\u6c50\u76d1\u72f1_patch.json")]:
        doc = json.loads(f.read_text(encoding="utf-8"))
        n = walk(doc)
        if n:
            print("  %s: %d replacement(s)" % (f.name, n))
            total += n
            if a.apply:
                shutil.copyfile(f, f.with_name(f.name + ".bak_suffix_" + stamp))
                f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        else:
            print("  %s: clean" % f.name)
    # 派生文档
    for f in [WS / "\u4ea7\u51fa" / ("\u6f6e\u6c50\u76d1\u72f1_\u5267\u60c5\u7f16\u5e74\u53f2.md"),
              WS / "\u4ea7\u51fa" / "\u6770\u514b\u6863\u6848.md",
              WS / "\u4ea7\u51fa" / "astrbot\u77e5\u8bc6\u5e93\u5bfc\u5165" / "\u6f6e\u6c50\u76d1\u72f1.md",
              WS / "\u4ea7\u51fa" / "astrbot\u77e5\u8bc6\u5e93\u5bfc\u5165" / "00c_\u6770\u514b\u6863\u6848.md"]:
        if not f.is_file():
            continue
        t = f.read_text(encoding="utf-8")
        if BAD in t:
            print("  %s: %d replacement(s)" % (f.name, t.count(BAD)))
            total += t.count(BAD)
            if a.apply:
                f.write_text(t.replace(BAD, GOOD), encoding="utf-8")
    print("total=%d" % total)
    if not a.apply:
        print("[dry-run] add --apply to write")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
