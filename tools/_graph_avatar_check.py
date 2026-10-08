# -*- coding: utf-8 -*-
"""关系图立绘核对：关系图 HTML 里还有多少个「? 占位」节点，各自是谁；并抽查指定角色的头像路径。

用法:
    python tools/_graph_avatar_check.py                       # 全库所有 <团>_关系图.html
    python tools/_graph_avatar_check.py --group "我的团" --names 角色甲,角色乙
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
OUT = WS / "\u4ea7\u51fa"                               # 产出

# 缺图节点：<div class="avatar noimg clickable" onclick="openModal('id')" title="...">?</div><div class="name">X</div>
# ⚠️ 引号在 HTML 里可能是实体（&#39;）也可能是裸引号，两种都要认——只认一种会**假报 0 缺图**。
# 名字后面可能还挂徽章 span（KP / 跨团），所以 </div> 前要允许一个 span。
NOIMG = re.compile(
    r'class="avatar noimg[^"]*"[^>]*onclick="openModal\((?:&#39;|\')([^&\']+?)(?:&#39;|\')\)"'
    r'[^>]*>\s*\?\s*</div>\s*<div class="name">([^<]*)')
# 有图节点：<img src="..." class="avatar ..." onclick="openModal('id')" ...><div class="name">X</div>
NODE = re.compile(r'<img src="([^"]+)"[^>]*>\s*<div class="name">([^<]*)')


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    group = argv[argv.index("--group") + 1] if "--group" in argv else None
    names = argv[argv.index("--names") + 1].split(",") if "--names" in argv else []

    files = sorted(OUT.glob("*_\u5173\u7cfb\u56fe.html"))     # *_关系图.html
    bad_total = 0
    for f in files:
        if group and group not in f.name:
            continue
        t = f.read_text(encoding="utf-8")
        miss = NOIMG.findall(t)
        nodes = NODE.findall(t)
        bad_total += len(miss)
        print(f"\n=== {f.name}  节点 {len(nodes)} · 缺图占位 {len(miss)}")
        for cid, nm in miss:
            print(f"    ? {nm}  [{cid}]")
        for nm in names:
            hit = [src for src, n in nodes if n.strip() == nm]
            print(f"    {nm} -> {hit[0] if hit else '(节点里没有)'}")
    print(f"\n合计缺图占位: {bad_total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
