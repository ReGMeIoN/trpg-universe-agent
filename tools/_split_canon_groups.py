# -*- coding: utf-8 -*-
"""Split group-specific blocks out of the workspace-wide canon_rules.md.

Moves "## ... <group> ..." tail sections into <work>/canon/groups/<group>.md so that
per-group rules are injected only for that group (canon.render_canon_block now reads
them). Idempotent-ish: refuses to run when the target file already exists.

usage: python tools/_split_canon_groups.py            # dry-run listing
       python tools/_split_canon_groups.py --apply
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
CANON = WS / ".trpg" / "canon"
RULES = CANON / "canon_rules.md"
SJT = "\u5723\u5251\u82f1\u96c4\u8c2d"          # 圣剑英雄谭 (谭=U+8C2D)
BAK = CANON / "canon_rules.md.bak_groups20261005"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    text = RULES.read_text(encoding="utf-8")
    lines = text.splitlines(keepends=True)

    cut = None
    for i, ln in enumerate(lines):
        if ln.startswith("## ") and SJT in ln:
            cut = i
            break
    if cut is None:
        print("no group section found; nothing to do")
        return 0

    head = "".join(lines[:cut]).rstrip() + "\n"
    body = "".join(lines[cut:]).strip() + "\n"
    target = CANON / "groups" / f"{SJT}.md"
    print(f"global part : {len(head)} chars")
    print(f"group part  : {len(body)} chars -> {target}")
    print("--- first line of group part ---")
    print(body.splitlines()[0])

    if not apply:
        print("\n(dry-run; pass --apply to write)")
        return 0
    if target.exists():
        print(f"!! target exists, refusing to overwrite: {target}")
        return 1
    if not BAK.exists():
        BAK.write_text(text, encoding="utf-8")
        print(f"backup -> {BAK}")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        f"# {SJT} · 本团专用规则\n\n"
        f"> 由 `canon_rules.md` 拆出（2026-10-05），只在本团提炼时注入。\n\n"
        + body,
        encoding="utf-8",
    )
    RULES.write_text(head, encoding="utf-8")
    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
