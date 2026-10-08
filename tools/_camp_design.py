# -*- coding: utf-8 -*-
"""阵营分类设计辅助：看看每个团里有哪些「可用的分类线索」。

用途：L1 关系网的小队外壳现在是「某个人名 + 组」（贪心按度数选种子），主人要求改成
**有意义的分类**。本工具把各团的 tags 与 identity 关键词统计出来，供设计分类规则。

用法:
    python tools/_camp_design.py [--group "魔法少女育成计划 6"] [--site] [--members "团名"]
"""
from __future__ import annotations

import os
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
SITE_DATA = ROOT / "site" / "data.js"

# identity / note 里的阵营关键词（顺序即优先级）
RULES = [
    ("考核官 / 教职", r"考核官|审核官|考官|导师|老师|教师|院长|校长|馆长|园长|大师|仙人|评委|裁判|主持"),
    ("学生 / 参赛者", r"学生|后辈|参赛|选手|考生|学徒|徒弟"),
    ("魔女 / 反派组织", r"魔女|反派|教主|boss|首领|头目|主祭|邪教"),
    ("异兽 / 灵宠", r"灵宠|魔兽|神兽|异兽|怪物|三头犬|大狗|巨兽|鲨|蛇|龙"),
    ("亲属 / 平民", r"妹妹|哥哥|姐姐|弟弟|父亲|母亲|儿子|女儿|市民|居民|市民|老板|店主"),
]


def classify(c: dict) -> str:
    tags = c.get("tags") or []
    if "KP" in tags:
        return "KP / 主持人"
    if "PC" in tags:
        return "玩家角色 (PC)"
    if "BOSS" in tags:
        return "BOSS / 敌方"
    txt = f"{c.get('identity') or ''} {c.get('note') or ''}"
    for name, pat in RULES:
        if re.search(pat, txt, re.I):
            return name
    if "跨团" in tags:
        return "跨团角色"
    return "其他 NPC"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    only = argv[argv.index("--group") + 1] if "--group" in argv else None
    members_of = argv[argv.index("--members") + 1] if "--members" in argv else None

    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    if "--site" in argv:
        src = SITE_DATA.read_text(encoding="utf-8")
        net = json.loads(src[src.index("=") + 1:].rstrip().rstrip(";"))
        ids = {c["id"] for c in net["chars"]}
        chars = [c for c in chars if c["id"] in ids]

    by_group: dict[str, list[dict]] = defaultdict(list)
    for c in chars:
        for g in (c.get("groups") or []):
            by_group[g].append(c)

    for g, cs in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        if only and g != only:
            continue
        if members_of and g != members_of:
            continue
        print(f"\n{'=' * 72}\n{g}（{len(cs)} 人）\n{'=' * 72}")
        camps = Counter(classify(c) for c in cs)
        print("  按本工具的规则分出来：")
        for k, n in camps.most_common():
            names = [c.get("name") for c in cs if classify(c) == k]
            print(f"    {n:>3}  {k:<16} {'、'.join(names[:6])}{'…' if len(names) > 6 else ''}")
        tags = Counter(t for c in cs for t in (c.get("tags") or []))
        print(f"  可用 tags：{dict(tags.most_common(14))}")
        if members_of:
            print("\n  逐人明细：")
            for c in sorted(cs, key=lambda c: (classify(c), c.get("name") or "")):
                print(f"    {classify(c):<16}{c.get('name',''):<22}"
                      f"{(c.get('identity') or '')[:52]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
