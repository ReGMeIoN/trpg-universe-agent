# -*- coding: utf-8 -*-
"""夏未眠 的出处更正：主人 2026-10-05 明确她是**本团原创**（不是既有角色）。

节点已入库，所以补丁里改 note 不会再生效 —— 直接改生产数据（备份 + 复验），
同时把补丁里的 note 一起改掉，免得下次入库又写回旧说法。

usage: python tools/_fix_xiaweimian.py [--apply]
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08"
DATA = WS / "\u6570\u636e" / "characters.json"
PATCH = WS / ".trpg" / "patches" / f"{GROUP}_patch.json"
CID = "yy_xiaweimian"
OLD = "\u4e14\u5979\u662f**\u65e2\u6709\u89d2\u8272**"          # 且她是**既有角色**
OLD_TAIL_ANCHOR = "\u5168\u5e93\u68c0\u7d22\u300c\u590f\u672a\u7720\u300d"
NEW = "\u5979\u662f**\u672c\u56e2\u539f\u521b**\u89d2\u8272\uff08\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff09\u3002"


def fix_note(note: str) -> tuple[str, bool]:
    if OLD_TAIL_ANCHOR not in note:
        return note, False
    # 把「且她是**既有角色**（…全库检索…待主人补充…）」整段替换成一句
    i = note.find(OLD)
    if i < 0:
        return note, False
    j = note.find("\u3002", note.find(OLD_TAIL_ANCHOR))
    if j < 0:
        return note, False
    return note[:i] + NEW + note[j + 1:], True


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv

    doc = json.loads(DATA.read_text(encoding="utf-8"))
    c = next((x for x in doc.get("characters") or [] if x.get("id") == CID), None)
    if c is None:
        print(f"!! 生产库没有 {CID}")
        return 1
    new_note, hit = fix_note(c.get("note") or "")
    print("生产库 note:")
    print("  旧:", (c.get("note") or "")[120:300])
    print("  新:", new_note[120:300])
    print(f"  是否命中: {hit}")

    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    pc = next((x for x in (patch.get("characters") or []) if x.get("id") == CID), None)
    p_new, p_hit = (fix_note(pc.get("note") or "") if pc else ("", False))
    print(f"补丁 note 是否命中: {p_hit}")

    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    ts = f"{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(DATA, DATA.with_name(DATA.name + f".bak_xwm_{ts}"))
    c["note"] = new_note
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if pc and p_hit:
        shutil.copy2(PATCH, PATCH.with_name(PATCH.name + f".bak_xwm_{ts}"))
        pc["note"] = p_new
        PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n已写入（含备份）")
    chk = json.loads(DATA.read_text(encoding="utf-8"))
    n = next(x for x in chk["characters"] if x.get("id") == CID).get("note") or ""
    print(f"复验: 「本团原创」×{n.count('本团原创')} · 「既有角色」×{n.count('既有角色')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
