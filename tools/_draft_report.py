# -*- coding: utf-8 -*-
"""把关系草稿 JSON 渲染成人看的 Markdown（给主人过目用）。"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DRAFT = WS / ".trpg" / "patches" / "圣剑英雄谭_relations_draft.json"
OUT = WS / ".trpg" / "reports" / "圣剑英雄谭_关系补全草稿.md"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    doc = json.loads(DRAFT.read_text(encoding="utf-8"))
    chars = json.loads((WS / "数据" / "characters.json").read_text(encoding="utf-8"))["characters"]
    name = {c["id"]: c["name"] for c in chars}
    rels = doc.get("relations") or []

    lines = ["# 圣剑英雄谭 · 关系补全草稿（**未入库，待主人确认**）\n",
             f"- 来源：《剧情编年史》+ 现有 25 个角色节点；由 `tools/_extract_relations_sjt.py` 抽取",
             f"- 草稿 JSON：`.trpg/patches/圣剑英雄谭_relations_draft.json`",
             f"- 现有已入库关系：6 条；本草稿：**{len(rels)} 条**\n",
             "| # | from | 关系 | 强 | to | 剧情依据 |",
             "|---|---|---|---|---|---|"]
    for i, r in enumerate(rels, 1):
        lines.append(
            f"| {i} | {name.get(r['from'], r['from'])} | {r.get('type')} | {r.get('strength')} "
            f"| {name.get(r['to'], r['to'])} | {(r.get('event') or '').replace('|', '/')} |"
        )
    lines.append("")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"OK {OUT} ({OUT.stat().st_size} 字节, {len(rels)} 条)")

    # 顺带统计出现频次，便于主人挑
    from collections import Counter

    cnt = Counter()
    for r in rels:
        cnt[name.get(r["from"], r["from"])] += 1
        cnt[name.get(r["to"], r["to"])] += 1
    print("涉及角色频次:", ", ".join(f"{k}×{v}" for k, v in cnt.most_common()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
