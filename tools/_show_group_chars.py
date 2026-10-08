# -*- coding: utf-8 -*-
"""List the stored character nodes of one group from a workspace's 数据/characters.json.

Handy after a shadow-store rehearsal: shows exactly what would land in the production library
(ids / names / tags / played_by / aliases), without opening the JSON by hand.

usage:
    python tools/_show_group_chars.py --group "阴阳差事录 超自然怪谈"
    python tools/_show_group_chars.py --ws "<shadow_ws>" --group X --full
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--ws", default=str(WS))
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--prefix", default=None, help="按 id 前缀过滤(如 yy_)")
    args = ap.parse_args()

    ws = Path(args.ws)
    f = ws / "\u6570\u636e" / "characters.json"
    if not f.is_file():
        print(f"!! 没有 {f}")
        return 1
    d = json.loads(f.read_text(encoding="utf-8"))
    chars = d.get("characters") or []
    hits = [c for c in chars if args.group in (c.get("groups") or [])]
    if args.prefix:
        hits = [c for c in hits if (c.get("id") or "").startswith(args.prefix)]
    print(f"{f}  共 {len(chars)} 个节点；团「{args.group}」{len(hits)} 个\n")
    for c in sorted(hits, key=lambda x: x.get("id") or ""):
        al = "\u3001".join(c.get("aliases") or [])
        tags = ",".join(c.get("tags") or [])
        print(f"{c.get('id'):<30} {c.get('name'):<24} [{tags}] played_by={c.get('played_by')}")
        if al:
            print(f"{'':<30} 别名: {al}")
        if args.full:
            print(f"{'':<30} note: {c.get('note')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
