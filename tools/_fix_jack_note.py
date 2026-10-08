# -*- coding: utf-8 -*-
"""Rewrite the tail of cross_jieke's note after the 2026-10-05 rulings.

The accumulated note ended up self-contradictory:
  「本团未见杰克本人正式出场，多为道具/提及/玩梗」  <- 旧判断（提炼时期）
  「主人确认：算杰克本人出场（非纯玩梗）」          <- 2026-10-05 主人裁决
and the ruling sentence had been appended twice (store's append_note is not idempotent).

This cuts everything from 「本团出现知风牧场…」 to the end and writes one consistent tail.

usage: python tools/_fix_jack_note.py [--apply]
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

DATA = Path(os.environ.get("TRPG_WS", "workspace")) / "\u6570\u636e" / "characters.json"
JACK = "cross_jieke"
ANCHOR = "\u672c\u56e2\u51fa\u73b0\u77e5\u98ce\u7267\u573a"      # 本团出现知风牧场
TAIL = (
    "\u672c\u56e2\u51fa\u73b0\u77e5\u98ce\u7267\u573a\uff08\u6377\u514b\u7684\u5bb6\uff09\u3001\u6770\u514b\u73a9\u5076\u3001"
    "\u6770\u514b\u5531\u7247\u3001\u827e\u4f26\u6770\u514b\u53e3\u7f69\u3001\u6770\u514b\u7f51\u7edc\u3001\u56fe\u4e66\u9986\u5bc6\u5ba4"
    "\u53e3\u4ee4\u8bd5\u8fc7\u300e\u6377\u514b\u300f\u7b49\uff0c\u6309\u97f3\u8fd1\u5f52\u4e00\u5e76\u5165\u6770\u514b\u3002"
    "**\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u8fd9\u4e9b\u7ebf\u7d22\u7b97\u6770\u514b\u672c\u4eba\u51fa\u573a\uff08\u975e\u7eaf\u73a9\u6897\uff09\u3002**"
    "\u540c\u65e5\u4e3b\u4eba\u4ea6\u786e\u8ba4\uff1a\u300c\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08\u300d\u91cc\u73a9\u5bb6\u73a9\u6897\u63d0\u53ca\u6770\u514b"
    "\uff08\u300c\u4f60\u662f\u6770\u514b\u300d\u300c\u5f00\u819b\u624b\u6770\u514b\u300d\uff09**\u4e0d\u8ba1\u4e3a\u6770\u514b\u51fa\u573a**"
    "\uff08\u53ea\u7b97\u300c\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6\u300d\u90a3\u8fb9\uff09\uff0c\u6545\u8be5\u56e2\u4e0d\u5217\u5165\u5176 groups\u3002"
)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    doc = json.loads(DATA.read_text(encoding="utf-8"))
    c = next((x for x in doc.get("characters") or [] if x.get("id") == JACK), None)
    if c is None:
        print("!! 找不到 cross_jieke")
        return 1
    note = c.get("note") or ""
    i = note.find(ANCHOR)
    if i < 0:
        print("!! note 里找不到锚点「本团出现知风牧场」，可能已处理过")
        print("尾部 120 字:", note[-120:])
        return 1
    new = note[:i].rstrip() + TAIL
    print(f"note: {len(note)} -> {len(new)} 字符")
    print("旧尾部:", note[i:i + 120], "...")
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    bak = DATA.with_name(DATA.name + f".bak_jacknote_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(DATA, bak)
    c["note"] = new
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")
    chk = json.loads(DATA.read_text(encoding="utf-8"))
    n = next(x for x in chk["characters"] if x.get("id") == JACK).get("note") or ""
    print(f"复验: 「算杰克本人出场」×{n.count('算杰克本人出场')} · "
          f"「未见杰克本人正式出场」×{n.count('未见杰克本人正式出场')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
