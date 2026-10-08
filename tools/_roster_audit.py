# -*- coding: utf-8 -*-
"""做游戏风关系网的「弹药盘点」：按团统计立绘覆盖、创作者(PL)、角色类型、跨团情况。

用途：设计前先知道哪些团"照片齐全"、哪个维度能当阵营/筛选用。

用法:
    python tools/_roster_audit.py
    python tools/_roster_audit.py --group "我的团"
"""
from __future__ import annotations

import os
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    only = sys.argv[sys.argv.index("--group") + 1] if "--group" in sys.argv else None
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]

    have = lambda c: bool(c.get("avatar")) and (
        DATA / "\u5934\u50cf" / Path(str(c["avatar"]).replace("\\", "/")).name).is_file()

    by_group: dict[str, list[dict]] = defaultdict(list)
    for c in chars:
        for g in (c.get("groups") or ["(无团)"]):
            by_group[g].append(c)

    deg: Counter = Counter()
    for r in rels:
        deg[r["from"]] += 1
        deg[r["to"]] += 1

    print(f"{'团':<30}{'角色':>5}{'有立绘':>7}{'占比':>7}{'有PL':>6}{'PC':>5}{'NPC':>5}{'BOSS':>6}{'关系边':>7}")
    print("-" * 84)
    for g, cs in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        if only and g != only:
            continue
        n = len(cs)
        av = sum(1 for c in cs if have(c))
        pl = sum(1 for c in cs if c.get("played_by"))
        tag = lambda t: sum(1 for c in cs if t in (c.get("tags") or []))
        edges = sum(deg[c["id"]] for c in cs) // 2
        print(f"{g:<30}{n:>5}{av:>7}{av * 100 // max(1, n):>6}%{pl:>6}"
              f"{tag('PC'):>5}{tag('NPC'):>5}{tag('BOSS'):>6}{edges:>7}")

    multi = [c for c in chars if len(c.get("groups") or []) > 1]
    print(f"\n跨团角色（出场 ≥2 个团）：{len(multi)}")
    for c in sorted(multi, key=lambda c: -len(c.get("groups") or []))[:12]:
        print(f"  {c.get('name',''):<22}{len(c.get('groups') or [])} 团："
              f"{'、'.join(c.get('groups') or [])}")

    tags = Counter(t for c in chars for t in (c.get("tags") or []))
    print(f"\n标签分布（Top 20）：")
    for t, n in tags.most_common(20):
        print(f"  {n:>4}  {t}")

    players = Counter(c.get("played_by") for c in chars if c.get("played_by"))
    print(f"\n扮演者（= 创作者视角）{len(players)} 人：")
    for p, n in players.most_common(16):
        print(f"  {n:>4}  {p}")

    noav = [c for c in chars if not have(c)]
    print(f"\n无立绘 {len(noav)} / {len(chars)} 人"
          f"（游戏风关系网对头像很敏感，这批是最大缺口）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
