# -*- coding: utf-8 -*-
"""Owner ruling: the 阴阳差事录 杰克 jokes do NOT count as an appearance.

`store` can only ADD (add_groups / add_events), so undoing the earlier write needs a direct
data edit. This removes the group + that group's events from `cross_jieke`, records the ruling
in its note, backs the file up first, and verifies the result.

usage: python tools/_fix_jack_yy.py [--apply]
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e"
GROUP = "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08"     # 阴阳差事录 超自然怪谈
JACK = "cross_jieke"
NOTE = ("\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u300c\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08\u300d\u91cc\u73a9\u5bb6\u73a9\u6897"
        "\u63d0\u53ca\u6770\u514b\uff08\u300c\u4f60\u662f\u6770\u514b\u300d\u300c\u5f00\u819b\u624b\u6770\u514b\u300d\uff09\uff0c**\u4e0d\u8ba1\u4e3a\u6770\u514b\u51fa\u573a**"
        "\uff08\u53ea\u7b97\u300c\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6\u300d\u90a3\u8fb9\uff09\uff0c\u6545\u672c\u56e2\u4e0d\u5217\u5165\u5176 groups\u3002")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    f = DATA / "characters.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    hit = [c for c in doc.get("characters") or [] if c.get("id") == JACK]
    if not hit:
        print(f"!! 没找到 {JACK}")
        return 1
    c = hit[0]
    groups = list(c.get("groups") or [])
    events = list(c.get("events") or [])
    print(f"{JACK} {c.get('name')}")
    print(f"  groups: {groups}")
    print(f"  events: {[e.get('group') for e in events]}")
    print(f"  note  : {str(c.get('note'))[:120]}")

    in_group = GROUP in groups
    ev_hit = [e for e in events if e.get("group") == GROUP]
    print(f"\n将移除: groups 里 {'有' if in_group else '没有'}本团；本团事件 {len(ev_hit)} 段")
    print(f"将追加 note: {NOTE}")

    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    if not in_group and not ev_hit and NOTE in (c.get("note") or ""):
        print("\n已经是目标状态，无需改动。")
        return 0

    bak = f.with_name(f.name + f".bak_jackfix_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(f, bak)
    c["groups"] = [g for g in groups if g != GROUP]
    c["events"] = [e for e in events if e.get("group") != GROUP]
    if NOTE not in (c.get("note") or ""):
        c["note"] = ((c.get("note") or "").rstrip() + " " + NOTE).strip()
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")

    chk = json.loads(f.read_text(encoding="utf-8"))
    c2 = [x for x in chk["characters"] if x.get("id") == JACK][0]
    ok = GROUP not in (c2.get("groups") or []) and not [e for e in (c2.get("events") or [])
                                                        if e.get("group") == GROUP]
    print(f"复验: groups={c2.get('groups')} · 本团事件={len([e for e in (c2.get('events') or []) if e.get('group') == GROUP])} "
          f"-> {'OK' if ok else 'FAIL'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
