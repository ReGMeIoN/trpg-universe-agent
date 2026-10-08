# -*- coding: utf-8 -*-
"""立绘缺口盘点：按团列出「有图 / 缺图」角色，附身份与出处提示。

用法:
    python tools/_avatar_gap.py                  # 全库汇总 + 每团缺口
    python tools/_avatar_gap.py --group "团名"    # 只看一个团
    python tools/_avatar_gap.py --json out.json  # 顺便导出机器可读清单
"""
from __future__ import annotations

import os
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "数据"
CHARS = DATA / "characters.json"

# 出处线索：从 note / identity / aliases 里捞这些词，判断是不是「别的团角色 / 网络梗 / 明星」
CLUE_WORDS = [
    "同位体", "跨团", "来自", "出自", "客串", "本人出场", "玩梗", "梗",
    "现实", "真名", "主播", "歌手", "演员", "明星", "联动",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    group_filter = None
    if "--group" in sys.argv:
        group_filter = sys.argv[sys.argv.index("--group") + 1]

    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    chars = doc.get("characters") or []

    per_group_total: Counter = Counter()
    per_group_have: Counter = Counter()
    gaps: dict[str, list[dict]] = defaultdict(list)
    haves: dict[str, list[str]] = defaultdict(list)

    orphans = []
    for c in chars:
        cid = c.get("id")
        name = c.get("name") or cid
        av = c.get("avatar") or ""
        rel = Path(av.replace("\\", "/")).name if av else ""
        ok = bool(rel) and (DATA / "头像" / rel).is_file()
        if av and not ok:
            orphans.append((cid, name, av))
        groups = [g for g in (c.get("groups") or []) if g]
        if not groups:
            groups = ["(无团)"]
        for g in groups:
            per_group_total[g] += 1
            if ok:
                per_group_have[g] += 1
                haves[g].append(name)
            else:
                gaps[g].append({
                    "id": cid,
                    "name": name,
                    "in_graph": c.get("in_graph", True),
                    "identity": (c.get("identity") or "").strip(),
                    "aliases": c.get("aliases") or [],
                    "note": (c.get("note") or "").strip(),
                })

    names = sorted(per_group_total, key=lambda g: -len(gaps.get(g, [])))
    print(f"生产库: {len(chars)} 角色 / 头像目录 {len(list((DATA / '头像').glob('*')))} 文件\n")
    print(f"{'团':<34}{'角色':>5}{'有图':>5}{'缺图':>5}")
    print("-" * 52)
    for g in names:
        if group_filter and g != group_filter:
            continue
        print(f"{g:<34}{per_group_total[g]:>5}{per_group_have.get(g,0):>5}{len(gaps.get(g,[])):>5}")

    if orphans:
        print(f"\n!! avatar 字段指向不存在的文件 ({len(orphans)}):")
        for cid, name, av in orphans:
            print(f"   {cid:<28} {name:<16} -> {av}")

    for g in names:
        if group_filter and g != group_filter:
            continue
        rows = gaps.get(g) or []
        if not rows:
            continue
        print(f"\n=== 缺图 [{g}] {len(rows)} 人 ===")
        for r in sorted(rows, key=lambda r: (r["in_graph"] is False, r["name"])):
            flags = []
            if r["in_graph"] is False:
                flags.append("不入图")
            text = " ".join([r["identity"], r["note"], " ".join(r["aliases"])])
            hit = [w for w in CLUE_WORDS if w in text]
            if hit:
                flags.append("线索:" + "/".join(hit))
            print(f"  {r['name']:<18} {r['id']:<28} {'['+','.join(flags)+']' if flags else ''}")
            if r["identity"]:
                print(f"        身份: {r['identity'][:110]}")
            if r["note"]:
                print(f"        备注: {r['note'][:220]}")

    out = {}
    for g in names:
        out[g] = {
            "total": per_group_total[g],
            "have": per_group_have.get(g, 0),
            "gap": gaps.get(g, []),
        }
    if "--json" in sys.argv:
        dst = Path(sys.argv[sys.argv.index("--json") + 1])
        dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已导出清单 -> {dst}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
