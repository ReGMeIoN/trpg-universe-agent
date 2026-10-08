# -*- coding: utf-8 -*-
"""把关系草稿合并进「圣剑英雄谭」入库补丁（去重），供 store 消费。

用法:
    .venv\\Scripts\\python.exe tools\\_merge_relations_sjt.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_merge_relations_sjt.py --write
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCH = WS / ".trpg" / "patches" / "圣剑英雄谭_patch.json"
DRAFT = WS / ".trpg" / "patches" / "圣剑英雄谭_relations_draft.json"


def key(r: dict) -> tuple:
    return (r.get("from"), r.get("to"), r.get("type"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    chars = json.loads((WS / "数据" / "characters.json").read_text(encoding="utf-8"))["characters"]
    name = {c["id"]: c["name"] for c in chars}
    ids = {c["id"] for c in chars}

    have = patch.setdefault("relations", [])
    seen = {key(r) for r in have}
    added, skipped, bad = [], [], []
    for r in draft.get("relations") or []:
        if r.get("from") not in ids or r.get("to") not in ids:
            bad.append(r)
            continue
        k = key(r)
        if k in seen:
            skipped.append(r)
            continue
        seen.add(k)
        have.append(r)
        added.append(r)

    print(f"补丁原关系 {len(have) - len(added)} 条 → 合并后 {len(have)} 条"
          f"（新增 {len(added)} / 重复跳过 {len(skipped)} / 端点非法 {len(bad)}）")
    for r in added:
        print(f"  + {name.get(r['from'], r['from'])} --{r.get('type')}--"
              f"({r.get('strength')})--> {name.get(r['to'], r['to'])}")
    for r in skipped:
        print(f"  = 已存在: {r.get('from')} -> {r.get('to')} ({r.get('type')})")
    for r in bad:
        print(f"  !! 端点不在库: {r.get('from')} -> {r.get('to')}")

    if not write:
        print("\n[dry-run] 未落盘。加 --write 生效。")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = PATCH.with_suffix(f".json.bak_rel_{stamp}")
    shutil.copy2(PATCH, bak)
    PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {PATCH}\n备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
