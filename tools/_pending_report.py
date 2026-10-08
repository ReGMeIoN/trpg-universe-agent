# -*- coding: utf-8 -*-
"""Dump the COMPLETE open-question set of a group's patch.

Two different buckets hold open questions and people forget the second one:
  1. `pending[]`                       -- 提炼自己标的不确定项
  2. `characters[].confirmed == false` -- store 会「降级不写盘」的条目（= 也没入库）
  3. 悬空端点(端点没入库的关系)        -- store 会跳过这些关系
This prints all three, grouped, with reasons and segment refs.

usage:
    python tools/_pending_report.py --group "阴阳差事录 超自然怪谈"
    python tools/_pending_report.py --all
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCHES = WS / ".trpg" / "patches"
GROUPS = ["\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08",   # 阴阳差事录 超自然怪谈
          "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6"]              # 魔法少女育成计划 6


def roster_ids() -> set[str]:
    p = WS / ".trpg" / "canon" / "roster.json"
    ids = set()
    if p.is_file():
        for c in (json.loads(p.read_text(encoding="utf-8")).get("characters") or []):
            ids.add(c.get("id"))
    return ids


def dump(group: str) -> None:
    p = PATCHES / f"{group}_patch.json"
    if not p.is_file():
        print(f"!! 缺补丁 {p.name}")
        return
    d = json.loads(p.read_text(encoding="utf-8"))
    ids = {c.get("id") for c in (d.get("characters") or [])} | roster_ids()

    print(f"\n{'=' * 78}\n# {group}\n{'=' * 78}")

    pend = d.get("pending") or []
    ans = d.get("resolved_by_owner") or []
    print(f"\n## A. pending（{len(pend)} 条，已答归档 {len(ans)} 条）")
    for i, q in enumerate(pend, 1):
        print(f"\nA{i:02d} [段{q.get('segment')}] {q.get('item')}")
        r = str(q.get("reason") or "")
        if r:
            print(f"     理由: {r}")

    conf = [c for c in (d.get("characters") or []) if not c.get("confirmed", True)]
    print(f"\n## B. confirmed:false（{len(conf)} 条，store 不写盘）")
    for i, c in enumerate(conf, 1):
        print(f"\nB{i:02d} {c.get('id')} {c.get('name')} [{','.join(c.get('tags') or [])}]")
        print(f"     理由: {c.get('pending_reason')}")
        print(f"     概述: {str(c.get('note'))[:160]}")

    dang = []
    for i, r in enumerate(d.get("relations") or []):
        bad = [x for x in (r.get("from"), r.get("to")) if x not in ids]
        if bad:
            dang.append((i, r, bad))
    print(f"\n## C. 悬空端点关系（{len(dang)} 条，store 会跳过）")
    for i, r, bad in dang:
        print(f"\nC{i:02d} [relations[{i}]] {r.get('from')} -> {r.get('to')} | {r.get('type')} | 缺 {bad}")
        print(f"     依据: {str(r.get('event'))[:140]}")

    print(f"\n## D. 已答归档（{len(ans)} 条，仅供回看）")
    for a in ans:
        print(f"  - {str(a.get('item'))[:70]}  <- {a.get('owner_answer')}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default=None)
    ap.add_argument("--all", action="store_true")
    args = ap.parse_args()
    for g in (GROUPS if args.all or not args.group else [args.group]):
        dump(g)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
