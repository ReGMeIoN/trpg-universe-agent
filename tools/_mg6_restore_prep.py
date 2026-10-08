# -*- coding: utf-8 -*-
"""Trim the already-applied part out of the mg6 patch's cross_jieke append_note.

`store` appends `append_note` unconditionally (merger.py:272-275) -- unlike add_groups /
add_events it does NOT dedupe. The first store already wrote the extract's original note,
so re-storing would duplicate it. This leaves only the sentence that has NOT been applied yet.

usage: python tools/_mg6_restore_prep.py [--apply]
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCH = WS / ".trpg" / "patches" / "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6_patch.json"
KEEP = ("\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u672c\u56e2\u7684\u6770\u514b\u73a9\u5076\uff0f\u5531\u7247\uff0f"
        "\u77e5\u98ce\u7267\u573a\u7b49\u7ebf\u7d22\u7b97\u6770\u514b\u672c\u4eba\u51fa\u573a\uff08\u975e\u7eaf\u73a9\u6897\uff09\u3002")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    doc = json.loads(PATCH.read_text(encoding="utf-8"))
    hit = [u for u in (doc.get("character_updates") or []) if u.get("id") == "cross_jieke"]
    if not hit:
        print("!! 补丁里没有 cross_jieke 更新")
        return 1
    u = hit[0]
    old = u.get("append_note") or ""
    print("原 append_note:")
    print("  " + old[:400])
    print("\n保留（未落盘的那句）:")
    print("  " + KEEP)
    if old.strip() == KEEP:
        print("\n已是目标状态，无需改动。")
        return 0
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    bak = PATCH.with_name(PATCH.name + f".bak_notetrim_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(PATCH, bak)
    u["append_note"] = KEEP
    PATCH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
