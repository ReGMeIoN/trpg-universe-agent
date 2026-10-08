# -*- coding: utf-8 -*-
"""Literal string replace inside one character's note, in BOTH the patch and the production data.

Needed because `store` can only append notes (its `append_note` is not idempotent), so any
*edit* to an already-stored note must be done on 数据/characters.json directly — with a backup
and a verification, exactly like the other `_fix_*.py` tools.

usage:
    python tools/_note_replace.py --id yy_xiaweimian --old "old text" --new "new text" --group "阴阳差事录 超自然怪谈"
    ... --apply
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e" / "characters.json"
PATCHES = WS / ".trpg" / "patches"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--id", required=True)
    ap.add_argument("--old", required=True)
    ap.add_argument("--new", default="")
    ap.add_argument("--group", default=None, help="同时改这个团的补丁里的同名节点")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    doc = json.loads(DATA.read_text(encoding="utf-8"))
    c = next((x for x in doc.get("characters") or [] if x.get("id") == args.id), None)
    if c is None:
        print(f"!! 生产库没有 {args.id}")
        return 1
    note = c.get("note") or ""
    n_hit = note.count(args.old)
    new_note = note.replace(args.old, args.new)
    print(f"生产库 {args.id}: 命中 {n_hit} 处，note {len(note)} -> {len(new_note)}")

    patch = pnew = None
    if args.group:
        p = PATCHES / f"{args.group}_patch.json"
        if p.is_file():
            patch = json.loads(p.read_text(encoding="utf-8"))
            pc = next((x for x in (patch.get("characters") or []) if x.get("id") == args.id), None)
            if pc:
                p_hit = (pc.get("note") or "").count(args.old)
                pnew = (pc.get("note") or "").replace(args.old, args.new)
                print(f"补丁           : 命中 {p_hit} 处")
            else:
                print("补丁           : 节点不在 characters[] 里（可能只在 updates 里）")
    if not args.apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    if n_hit == 0 and (pnew is None or pnew == (pc.get("note") or "")):
        print("无需改动。")
        return 0
    ts = f"{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(DATA, DATA.with_name(DATA.name + f".bak_noterep_{ts}"))
    c["note"] = new_note
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    if patch is not None and pnew is not None and pc is not None:
        shutil.copy2(PATCHES / f"{args.group}_patch.json",
                     PATCHES / f"{args.group}_patch.json.bak_noterep_{ts}")
        pc["note"] = pnew
        (PATCHES / f"{args.group}_patch.json").write_text(
            json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print("已写入（含备份）")
    chk = json.loads(DATA.read_text(encoding="utf-8"))
    n2 = next(x for x in chk["characters"] if x.get("id") == args.id).get("note") or ""
    print(f"复验: 旧串剩余 {n2.count(args.old)} 处 · note 长度 {len(n2)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
