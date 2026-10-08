# -*- coding: utf-8 -*-
"""把工作区根目录里**过期的会话/过程文档**归档到 `_归档/`（移动，不删除）。

根目录只该留：`README.md`（对外说明书）、`项目状态交接.md`（交接主文档）、
`处理工作流runbook.md`（流程手册）、`agent化-产品化建议.md`（产品方向）。

用法:
    python tools/_tidy_root_docs.py            # dry-run
    python tools/_tidy_root_docs.py --apply
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
# 收走的（过期的会话交接 / 压缩摘要）
ARCHIVE = [
    "\u4f1a\u8bdd\u538b\u7f29\u6458\u8981-20260908.md",                     # 会话压缩摘要-20260908.md
    "\u4ea4\u63a5-20260909-AstrBot\u63a5\u5165\u7eed\u63a5.md",             # 交接-20260909-AstrBot接入续接.md
]
KEEP_NOTE = "保留：README / 项目状态交接 / 处理工作流runbook / agent化-产品化建议"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply_ = "--apply" in sys.argv
    moves = []
    for name in ARCHIVE:
        p = WS / name
        if p.is_file():
            moves.append(p)
    print(f"待归档 {len(moves)} 个：")
    for p in moves:
        print(f"  {p.name}  ({p.stat().st_size / 1024:.1f} KB)")
    print(f"\n{KEEP_NOTE}")
    if not apply_:
        print("\n(dry-run; 加 --apply 移动)")
        return 0
    d = WS / "\u5f52\u6863"      # 归档
    d.mkdir(parents=True, exist_ok=True)
    for p in moves:
        shutil.move(str(p), str(d / p.name))
    print(f"\n已移入 {d.name}\\：")
    for p in sorted(d.iterdir()):
        print(f"  {p.name}")
    print("\n根目录现在有：")
    for p in sorted(WS.iterdir()):
        if p.is_file():
            print(f"  {p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
