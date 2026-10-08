# -*- coding: utf-8 -*-
"""整理 `产出/`：把「我看过就完事」的临时件收进子目录（移动，不删除）。

留根上的是**交付物**：每团的 `_剧情编年史.md` / `_关系图.html` / `_关系网.md`、
疑问核对页、PL/杰克档案、宇宙总览、收尾清单、关系类型画像、角色网、挑图相关的成品。

收走的：
  _tmp/   → 我这边扫描/清点出来的中间清单（缺口清单、候选表、检索结果）
  _bak/   → 各种 .bak 快照、过期的旧命名图（伪人杀/雪山狼人杀/异世界大逃杀 的旧图）
  _核对/  → 疑问核对页（历史轮次归档，最新一轮留在根上）

用法:
    python tools/_tidy_outputs.py            # dry-run
    python tools/_tidy_outputs.py --apply
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

OUT = Path(os.environ.get("TRPG_WS", "workspace") / '产出')   # TRPG关系网\产出

TMP = ["\u7acb\u7ed8\u7f3a\u53e3\u6e05\u5355.md", "\u7f3a\u5361\u89d2\u8272.md",
       "\u7f3a\u5931\u89d2\u8272\u5019\u9009.md", "QQ\u56e2\u7f3a\u89d2\u8272.md",
       "\u672a\u5165\u5e93\u5f85\u786e\u8ba4.md"]
#     立绘缺口清单.md / 缺卡角色.md / 缺失角色候选.md / QQ团缺角色.md / 未入库待确认.md
LEGACY_GRAPHS = ["\u4f2a\u4eba\u6740_\u5173\u7cfb\u56fe.html",
                 "\u96ea\u5c71\u72fc\u4eba\u6740_\u5173\u7cfb\u56fe.html",
                 "\u5f02\u4e16\u754c\u5927\u9003\u6740_\u5173\u7cfb\u56fe.html"]
#     旧命名（现在的正式名带「卧槽是伪人群·」前缀）
BAK_SUFFIX = ".bak_"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply_ = "--apply" in sys.argv
    if not OUT.is_dir():
        print(f"!! 不存在: {OUT}")
        return 1

    plan = {"_tmp": [], "_bak": [], "_旧图": []}
    for p in sorted(OUT.iterdir()):
        if p.is_dir():
            continue
        if p.name in TMP:
            plan["_tmp"].append(p)
        elif BAK_SUFFIX in p.name or p.suffix == ".mmd":
            plan["_bak"].append(p)
        elif p.name in LEGACY_GRAPHS:
            plan["_旧图"].append(p)

    for b, items in plan.items():
        print(f"[{b}] {len(items)} 个")
        for p in items:
            print(f"    {p.name}")
    keep = [p.name for p in OUT.iterdir() if p.is_file() and
            not any(p in v for v in plan.values())]
    print(f"\n[留根] {len(keep)} 个交付物")
    if not apply_:
        print("\n(dry-run; 加 --apply 移动)")
        return 0
    for b, items in plan.items():
        if not items:
            continue
        d = OUT / b
        d.mkdir(parents=True, exist_ok=True)
        for p in items:
            shutil.move(str(p), str(d / p.name))
    print("\n已归档。产出\\ 根目录：")
    print(f"  {len([p for p in OUT.iterdir() if p.is_file()])} 个文件 + "
          f"{len([p for p in OUT.iterdir() if p.is_dir()])} 个子目录")
    for p in sorted(OUT.iterdir()):
        if p.is_dir():
            print(f"  DIR {p.name}（{len(list(p.iterdir()))} 项）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
