# -*- coding: utf-8 -*-
"""Two tidies after the second mg6 store.

1. 杰克's note got the same sentence twice: `store` appends `append_note` unconditionally, and
   the sentence had already been applied by the first store -- my note-trim kept the wrong side.
   -> dedupe repeated sentences (order-preserving).
2. 「阿尔弗雷德」 was BOTH an alias of 析芝花田 AND a separate (confirmed:false) node -- that
   asserts an identity the owner has not confirmed. -> drop the alias, keep the node pending.

Touches 数据/characters.json (backup first) and the patch (so a re-store cannot re-add the alias).

usage: python tools/_fix_mg6_tidy.py [--apply]
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e" / "characters.json"
PATCH = WS / ".trpg" / "patches" / "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6_patch.json"
JACK = "cross_jieke"
HUATIAN = "mg6_xizhi_huatian"
BAD_ALIAS = "\u963f\u5c14\u5f17\u96f7\u5fb7"      # 阿尔弗雷德


def dedupe_sentences(text: str) -> tuple[str, int]:
    """按句号/换行切句，去重复（保序）。"""
    import re

    parts = re.split(r"(?<=[\u3002\uff01\uff1f!?.])", text)
    seen, out, dropped = set(), [], 0
    for p in parts:
        key = p.strip()
        if not key:
            continue
        if key in seen:
            dropped += 1
            continue
        seen.add(key)
        out.append(p)
    return "".join(out), dropped


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv

    doc = json.loads(DATA.read_text(encoding="utf-8"))
    chars = doc.get("characters") or []
    jack = next((c for c in chars if c.get("id") == JACK), None)
    ht = next((c for c in chars if c.get("id") == HUATIAN), None)
    if jack is None or ht is None:
        print("!! 找不到目标节点")
        return 1

    new_note, dropped = dedupe_sentences(jack.get("note") or "")
    has_alias = BAD_ALIAS in (ht.get("aliases") or [])
    print(f"1) {JACK} note: {len(jack.get('note') or '')} -> {len(new_note)} 字符（去掉 {dropped} 个重复句）")
    print(f"2) {HUATIAN} 别名里的「{BAD_ALIAS}」: {'有' if has_alias else '没有'}"
          f"（节点 mg6_alfred 仍保持 confirmed:false 待确认）")
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    pc = next((c for c in (patch.get("characters") or []) if c.get("id") == HUATIAN), None)
    p_alias = bool(pc) and BAD_ALIAS in (pc.get("aliases") or [])
    print(f"   补丁里同样处理: {'是' if p_alias else '无需'}")

    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    ts = f"{datetime.now():%Y%m%d_%H%M%S}"
    bak = DATA.with_name(DATA.name + f".bak_tidy_{ts}")
    shutil.copy2(DATA, bak)
    jack["note"] = new_note
    if has_alias:
        ht["aliases"] = [a for a in ht["aliases"] if a != BAD_ALIAS]
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(PATCH, PATCH.with_name(PATCH.name + f".bak_tidy_{ts}"))
    if pc and p_alias:
        pc["aliases"] = [a for a in pc["aliases"] if a != BAD_ALIAS]
        PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")

    chk = json.loads(DATA.read_text(encoding="utf-8"))
    j2 = next(c for c in chk["characters"] if c.get("id") == JACK)
    h2 = next(c for c in chk["characters"] if c.get("id") == HUATIAN)
    ok_note = (j2.get("note") or "").count("\u672c\u56e2\u7684\u6770\u514b\u73a9\u5076") <= 1
    ok_alias = BAD_ALIAS not in (h2.get("aliases") or [])
    print(f"复验: 杰克 note 重复句={not ok_note and '仍有' or '已清'} · 花田无该别名={ok_alias}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
