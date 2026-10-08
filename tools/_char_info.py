# -*- coding: utf-8 -*-
"""打印指定 id / 团 的角色详情（跨团复用判断用）。

用法:
    python tools/_char_info.py --ids id1,id2
    python tools/_char_info.py --group "团名"
    python tools/_char_info.py --name 神前早月
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))   # TRPG关系网
DATA = WS / "\u6570\u636e"                            # 数据


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    chars = doc["characters"]

    sel = chars
    if "--ids" in sys.argv:
        want = set(sys.argv[sys.argv.index("--ids") + 1].split(","))
        sel = [c for c in chars if c.get("id") in want]
    elif "--group" in sys.argv:
        g = sys.argv[sys.argv.index("--group") + 1]
        sel = [c for c in chars if g in (c.get("groups") or [])]
    elif "--name" in sys.argv:
        n = sys.argv[sys.argv.index("--name") + 1]
        sel = [c for c in chars if c.get("name") == n]

    for c in sel:
        av = c.get("avatar") or ""
        ok = bool(av) and (DATA / "\u5934\u50cf" / Path(av.replace("\\", "/")).name).is_file()
        print(f"--- {c.get('id')} | {c.get('name')} | avatar={'(无)' if not av else Path(av.replace(chr(92),'/')).name}{'' if ok else ' [缺]'}")
        print(f"    groups : {c.get('groups')}")
        print(f"    aliases: {c.get('aliases')}")
        print(f"    tags   : {c.get('tags')}  in_graph={c.get('in_graph')}")
        print(f"    identity: {c.get('identity')}")
        print(f"    note   : {(c.get('note') or '')[:600]}")
    print(f"\n({len(sel)} 条)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
