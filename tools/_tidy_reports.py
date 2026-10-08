# -*- coding: utf-8 -*-
"""把 `.trpg/reports/` 里的报告分类归档（**移动，不删除**）。

转交/交付时，把「一次性的中间产物」收进子目录，只留「长期有用」的在根上。

分类：
  keep    → 留在 reports 根（正式入库报告、待确认清单、主人答疑结论）
  tmp     → `_tmp/`（我这边的日志/扫描/中间清单）
  bak     → `_bak/`（备份、建议文件、快照）
  test    → `_test/`（守卫测试团等一次性验证产物）

用法:
    python tools/_tidy_reports.py            # dry-run
    python tools/_tidy_reports.py --apply
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

REPORTS = Path(os.environ.get("TRPG_WS", "workspace") / '.trpg' / 'reports')   # TRPG关系网\.trpg\reports

# 明确要收走的（前缀/后缀匹配）
RULES = [
    ("tmp", ["avatar_gap", "gen24.log", "gen25-covers.log", "looks_mg6", "looks_yy",
             "mg6封面提示词", "rel_extract_", "relation_fill_all", "关系类型_原始清单",
             "名称检索_", "wiki同步_", "批量提炼_", "新团转录_会话报告",
             "圣剑英雄谭_三PC戏份核对", "圣剑英雄谭_关系补全草稿", "圣剑英雄谭_角色卡摘要",
             "新团角色卡摘要", "存疑清单_"]),
    ("bak", [".bak", "自动更新建议", "_stale_"]),
    ("test", ["守卫测试团_"]),
]
# 留根上的
KEEP_SUFFIX = ("_入库报告.md", "_待确认.md")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply_ = "--apply" in sys.argv
    if not REPORTS.is_dir():
        print(f"!! 目录不存在: {REPORTS}")
        return 1

    plan: dict[str, list[Path]] = {"tmp": [], "bak": [], "test": []}
    keep: list[Path] = []
    for p in sorted(REPORTS.iterdir()):
        if p.is_dir():
            continue
        name = p.name
        bucket = None
        for b, keys in RULES:
            if any(k in name for k in keys):
                bucket = b
                break
        if bucket:
            plan[bucket].append(p)
        elif name.endswith(KEEP_SUFFIX):
            keep.append(p)
        else:
            keep.append(p)      # 拿不准的一律留着

    for b, items in plan.items():
        if items:
            print(f"[{b}] {len(items)} 个 → _${b}/")
            for p in items:
                print(f"    {p.name}")
    print(f"\n[留根] {len(keep)} 个（入库报告 / 待确认 / 拿不准的）")
    if not apply_:
        print("\n(dry-run; 加 --apply 移动)")
        return 0

    for b, items in plan.items():
        if not items:
            continue
        d = REPORTS / f"_{b}"
        d.mkdir(parents=True, exist_ok=True)
        for p in items:
            shutil.move(str(p), str(d / p.name))
    print("\n已归档。reports 根目录现在有：")
    for p in sorted(REPORTS.iterdir()):
        print(f"  {'DIR ' if p.is_dir() else '    '}{p.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
