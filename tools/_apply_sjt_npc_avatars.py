# -*- coding: utf-8 -*-
"""把 NAI 生成的 NPC 头像登记进 `数据/头像/` 并写回 characters.json 的 avatar。

来源：`<NAI库>\\archive\\15-trpg-sjt-npc\\`（trpg-gen12.py 生成，832×1216 免费档）

用法:
    .venv\\Scripts\\python.exe tools\\_apply_sjt_npc_avatars.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_apply_sjt_npc_avatars.py --write
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
SRC_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '15-trpg-sjt-npc')
AVATAR_DIR = WS / "数据" / "头像"
CHARS = WS / "数据" / "characters.json"

# 角色 id -> (源图, 输出名)
PLAN = {
    "sjt_huangdi": ("01-emperor-augustus-a.png", "圣剑英雄谭_皇帝奥古斯都__image1"),
    "sjt_shengnv": ("02-saintess-selinstia-a.png", "圣剑英雄谭_圣女赛林斯蒂亚__image1"),
    "sjt_weierna": ("03-wilna-thunder-a.png", "圣剑英雄谭_威尔娜__image1"),
    "sjt_weiketuo": ("04-victor-holyblade-a.png", "圣剑英雄谭_维克托__image1"),
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    chars = {c["id"]: c for c in doc["characters"]}

    plan = []
    for cid, (src_name, stem) in PLAN.items():
        src = SRC_DIR / src_name
        if not src.is_file():
            print(f"  !! 缺图 {src}")
            continue
        if cid not in chars:
            print(f"  !! characters.json 里没有 {cid}")
            continue
        dst = AVATAR_DIR / f"{stem}.png"
        plan.append((cid, chars[cid].get("name"), src, dst, chars[cid].get("avatar")))

    print(f"计划登记 {len(plan)} 个 NPC 头像：")
    for cid, name, src, dst, old in plan:
        print(f"  {cid:<22} {name:<14} {src.name:<32} -> {dst.name}  旧值={old!r}")
    if not write:
        print("\n[dry-run] 未落盘。加 --write 生效。")
        return 0

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    for cid, name, src, dst, old in plan:
        shutil.copy2(src, dst)
        chars[cid]["avatar"] = f"数据\\头像\\{dst.name}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = CHARS.with_suffix(f".json.bak_npcavatar_{stamp}")
    shutil.copy2(CHARS, bak)
    CHARS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {CHARS}\n备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
