# -*- coding: utf-8 -*-
"""关系密度体检：每个团有多少节点/边、边/节点比、以及有多少「团内两人却没有任何边」。

用来发现「关系抽少了」的团——extract 只抽角色骨架，**关系靠编年史补**（见
`_extract_relations_sjt.py` / `_merge_relations_sjt.py` 的老做法）。

用法:
    python tools/_relation_stats.py
    python tools/_relation_stats.py --group "魔法少女育成计划 6" --list   # 列出该团全部边
"""
from __future__ import annotations

import os
import json
import re
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    only = argv[argv.index("--group") + 1] if "--group" in argv else None
    show = "--list" in argv

    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    name_of = {c["id"]: c.get("name") or c["id"] for c in chars}

    if "--types" in argv:
        # ⚠️ 别在这里 `from collections import Counter`：函数内 import 会把 Counter 变成**整个函数的局部名**，
        #    下面 `deg: Counter = Counter()` 就会 UnboundLocalError（2026-10-05 踩过一次）。Counter 在模块顶部已导入。
        print(f"关系类型总览（{len(rels)} 条边）")
        types = Counter((r.get("type") or "").strip() for r in rels)
        print(f"  不同的 type 串：{len(types)} 个")
        # 「A/B」式的复合类型单独数一下
        multi = [t for t in types if "/" in t or "、" in t or "／" in t]
        print(f"  其中含「/」等复合写法：{len(multi)} 个（覆盖 {sum(types[t] for t in multi)} 条边）")
        print("\n  出现最多的 40 个 type：")
        for t, n in types.most_common(40):
            print(f"    {n:>4}  {t}")
        # 时间锚：event 里有没有「段N」或 [秒]
        seg = re.compile(r"段\s*\d+|\[\d{2,4}(?:\.\d+)?(?:\s*[-–]\s*\d{2,4}(?:\.\d+)?)?\]")
        timed = [r for r in rels if seg.search(r.get("event") or "")]
        print(f"\n  带时间锚的边：{len(timed)}/{len(rels)}"
              f"（{len(timed) * 100 // max(1, len(rels))}%）—— 有「段N」或 [秒] 可直接抽成 from_ts")
        st = Counter(r.get("strength") or "(空)" for r in rels)
        print(f"  强度分布：{dict(st)}")
        return 0

    by_group: dict[str, set[str]] = defaultdict(set)
    for c in chars:
        for g in (c.get("groups") or []):
            by_group[g].add(c["id"])
    name_of = {c["id"]: c.get("name") or c["id"] for c in chars}

    print(f"{'团':<30}{'节点':>5}{'团内边':>7}{'边/节点':>9}{'孤立节点':>9}")
    print("-" * 62)
    rows = []
    for g, ids in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        inner = [r for r in rels
                 if r.get("from") in ids and r.get("to") in ids]
        deg: Counter = Counter()
        for r in inner:
            deg[r["from"]] += 1
            deg[r["to"]] += 1
        iso = [i for i in ids if deg[i] == 0]
        ratio = len(inner) / max(1, len(ids))
        rows.append((g, ids, inner, iso))
        if only and g != only:
            continue
        print(f"{g:<30}{len(ids):>5}{len(inner):>7}{ratio:>9.2f}{len(iso):>9}")

    if show and only:
        row = next((r for r in rows if r[0] == only), None)
        if row:
            g, ids, inner, iso = row
            print(f"\n=== {g} 的 {len(inner)} 条边 ===")
            for r in inner:
                print(f"  {name_of.get(r['from'], r['from']):<18} —{r.get('type',''):<12}"
                      f"[{r.get('strength','')}]→ {name_of.get(r['to'], r['to']):<18}  "
                      f"{(r.get('event') or '')[:60]}")
            print(f"\n=== 孤立节点（团内一条边都没有，{len(iso)} 个）===")
            for i in sorted(iso, key=lambda x: name_of.get(x, x)):
                c = next((c for c in chars if c["id"] == i), {})
                print(f"  {name_of.get(i, i):<20} {i:<28} {(c.get('identity') or '')[:50]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
