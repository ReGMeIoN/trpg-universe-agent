# -*- coding: utf-8 -*-
"""主人确认「结刻?」= 杰克（cross_jieke）→ 把补丁里那条降级的更新改为确定并启用。

用法:
    .venv\\Scripts\\python.exe tools\\_fix_jieke_sjt.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_fix_jieke_sjt.py --write
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

NEW_NOTE = (
    "圣剑英雄谭段6终局：众人被世界意识排斥，台词「（我们）只能化身结刻吧」——"
    "「结刻」经主人 2026-10-03 确认为**杰克**（音近归一），属剧情内收束"
)
NEW_EVENTS = [
    "段6终局：世界被修正后众人遭世界意识排斥，「只能化身结刻」（＝杰克）（约 21976-21979）",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    doc = json.loads(PATCH.read_text(encoding="utf-8"))
    ups = doc.get("character_updates") or []
    hit = next((u for u in ups if u.get("id") == "cross_jieke"), None)
    if not hit:
        print("补丁里没有 cross_jieke 的更新项")
        return 1
    print("原更新:")
    print(json.dumps(hit, ensure_ascii=False, indent=1)[:600])
    old_conf = hit.get("confirmed")
    hit["append_note"] = NEW_NOTE
    hit["add_events"] = [{"group": "圣剑英雄谭", "items": NEW_EVENTS}]
    hit["add_groups"] = ["圣剑英雄谭"]
    hit["confirmed"] = True
    print("\n新更新:")
    print(json.dumps(hit, ensure_ascii=False, indent=1)[:600])
    print(f"\nconfirmed: {old_conf} -> True")
    if not write:
        print("[dry-run] 未落盘。加 --write 生效。")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = PATCH.with_suffix(f".json.bak_jieke_{stamp}")
    shutil.copy2(PATCH, bak)
    PATCH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {PATCH}\n备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
