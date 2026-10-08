# -*- coding: utf-8 -*-
"""给某个角色追加/替换一句备注（定向修正，带备份 + 复验）。幂等：同一句不会写两遍。

用法:
    python tools/_note_line.py --id yy_liulong_meimei --append "主人 2026-10-06 确认：…"
    ... 加 --apply 落盘
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    a = sys.argv
    if "--id" not in a or "--append" not in a:
        print(__doc__)
        return 1
    cid = a[a.index("--id") + 1]
    line = a[a.index("--append") + 1]
    apply_ = "--apply" in a

    f = DATA / "characters.json"
    doc = json.loads(f.read_text(encoding="utf-8"))
    c = next((x for x in doc["characters"] if x.get("id") == cid), None)
    if not c:
        print(f"!! 找不到 {cid}")
        return 1
    old = (c.get("note") or "").strip()
    if line in old:
        print(f"{cid} 已有这句，跳过（幂等）")
        return 0
    c["note"] = (old + "\n" + line).strip()
    print(f"{cid} 备注 {len(old)} → {len(c['note'])} 字")
    print("  追加: " + line)
    if not apply_:
        print("\n(dry-run; 加 --apply 落盘)")
        return 0
    bak = f.with_name(f"{f.name}.bak_noteline_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(f, bak)
    f.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    chk = json.loads(f.read_text(encoding="utf-8"))
    n = next(x for x in chk["characters"] if x["id"] == cid)
    print(f"\n已写入（备份 {bak.name}）；复验：{'通过' if line in n['note'] else '失败'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
