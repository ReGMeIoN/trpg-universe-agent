# -*- coding: utf-8 -*-
"""登记第二批 NPC 头像（NAI `archive/16-trpg-sjt-npc2`，15 个）到 数据/头像 + characters.json。

用法:
    .venv\\Scripts\\python.exe tools\\_apply_sjt_npc_avatars2.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_apply_sjt_npc_avatars2.py --write
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
SRC_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '16-trpg-sjt-npc2')
AVATAR_DIR = WS / "数据" / "头像"
CHARS = WS / "数据" / "characters.json"

# 源文件名前缀 -> (角色 id, 输出名)
PLAN = [
    ("05-pope", "sjt_jiaohuang", "圣剑英雄谭_教皇"),
    ("06-lancelot", "sjt_lansiluote", "圣剑英雄谭_兰斯洛特"),
    ("07-veteran", "sjt_laobing", "圣剑英雄谭_老兵"),
    ("08-blind-king", "sjt_laoxiayan", "圣剑英雄谭_老瞎眼"),
    ("09-viper-mouth", "sjt_laoshazui", "圣剑英雄谭_老沙嘴"),
    ("10-dwarf-master", "sjt_airen_dashi", "圣剑英雄谭_矮人大师"),
    ("11-flame-elder", "sjt_yanshu_zhanglao", "圣剑英雄谭_艳术长老"),
    ("12-crimson-knight", "sjt_hongse_qishi", "圣剑英雄谭_红色骑士"),
    ("13-famine", "sjt_jihuang", "圣剑英雄谭_饥荒"),
    ("14-war-knight", "sjt_zhanzheng_qishi", "圣剑英雄谭_战争骑士"),
    ("15-plague-knight", "sjt_wenyi_qishi", "圣剑英雄谭_瘟疫骑士"),
    ("16-apocalypse-knight", "sjt_tianqi_qishi", "圣剑英雄谭_天启骑士"),
    ("17-ice-beast", "sjt_bingjing_shengshou", "圣剑英雄谭_冰晶圣兽"),
    ("18-twelfth-sage", "sjt_xianzhe_shier", "圣剑英雄谭_第十二位贤者"),
    ("19-druid-monkey", "sjt_druid_houzi", "圣剑英雄谭_德鲁伊猴子"),
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    chars = {c["id"]: c for c in doc["characters"]}

    plan = []
    for prefix, cid, stem in PLAN:
        src = SRC_DIR / f"{prefix}-a.png"
        if not src.is_file():
            print(f"  !! 缺图 {src.name}")
            continue
        if cid not in chars:
            print(f"  !! characters.json 里没有 {cid}")
            continue
        plan.append((cid, chars[cid].get("name"), src, AVATAR_DIR / f"{stem}__image1.png",
                     chars[cid].get("avatar")))

    print(f"计划登记 {len(plan)} 个 NPC 头像：")
    for cid, name, src, dst, old in plan:
        print(f"  {cid:<24} {name:<16} {src.name:<26} -> {dst.name}  旧值={old!r}")
    if not write:
        print("\n[dry-run] 未落盘。加 --write 生效。")
        return 0

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    for cid, name, src, dst, old in plan:
        shutil.copy2(src, dst)
        chars[cid]["avatar"] = f"数据\\头像\\{dst.name}"
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = CHARS.with_suffix(f".json.bak_npcavatar2_{stamp}")
    shutil.copy2(CHARS, bak)
    CHARS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {CHARS}\n备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
