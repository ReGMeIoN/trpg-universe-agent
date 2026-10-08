# -*- coding: utf-8 -*-
"""Check a clip-quiz keyword list against a transcript before cutting audio clips.

`_clip_quiz.py` silently marks keywords it cannot find as "miss" (no clip), which is
only useful if you learn about it *before* handing the page to the user. This prints a
per-keyword hit count plus a suggested manual time point for the misses.

usage:
    python tools/_quiz_check.py --group "阴阳差事录 超自然怪谈" --quiz <quiz.json>
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
TS_RE = re.compile(r"^\[\s*([\d.]+)\s*->\s*([\d.]+)\s*\]\s?(.*)$")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--quiz", default=None, help="疑问清单 JSON; 不给则用 --terms")
    ap.add_argument("--terms", default=None, help="逗号分隔的候选词, 只打印命中数(用来挑关键词)")
    ap.add_argument("--transcript", default=None)
    args = ap.parse_args()

    tx = Path(args.transcript) if args.transcript else WS / "素材" / f"{args.group}_转写.txt"
    if not tx.is_file():
        print(f"!! 没有转写稿: {tx}")
        return 1
    rows = []
    for ln in tx.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_RE.match(ln.strip())
        if m:
            rows.append((float(m.group(1)), m.group(3)))
    print(f"转写: {tx.name} · {len(rows)} 行" + (f" (至 {rows[-1][0]/60:.1f} 分钟)" if rows else ""))
    if not rows:
        return 1

    if args.terms:
        for kw in [t for t in args.terms.split(",") if t]:
            hits = [(t, txt) for t, txt in rows if kw in txt]
            mark = f"×{len(hits)}@{hits[0][0]:.0f}s" if hits else "×0"
            print(f"  {kw:<16} {mark}")
        return 0

    if not args.quiz:
        print("!! 需要 --quiz 或 --terms")
        return 1
    quiz = json.loads(Path(args.quiz).read_text(encoding="utf-8"))
    missing: list[tuple[str, str]] = []
    for q in quiz:
        if q.get("at"):
            print(f"{q['id']} 手工时间点 {q['at']} —— ok")
            continue
        parts = []
        for kw in q["kws"]:
            hits = [(t, txt) for t, txt in rows if kw in txt]
            if hits:
                parts.append(f"{kw}×{len(hits)}@{hits[0][0]:.0f}s")
            else:
                parts.append(f"{kw}×0")
                missing.append((q["id"], kw))
        flag = "  <= 有关键词 0 命中" if "×0" in " ".join(parts).replace("×0@", "@") else ""
        print(f"{q['id']:<4} " + " | ".join(parts) + flag)
    print(f"\n0 命中关键词 {len(missing)} 个:")
    for qid, kw in missing:
        print(f"  {qid} {kw}")
    print("\n提示: 0 命中的条目要么换关键词, 要么用 {\"at\":[起,止]} 手工给时间点。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
