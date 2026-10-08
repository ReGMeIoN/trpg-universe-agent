# -*- coding: utf-8 -*-
"""把 examples/mini-group 重置回初始态(示例是夹具, 必须可重复跑)。

做法:
  1. 数据/*.json 从最近一次 .bak_store_* 备份还原(备份即覆盖前快照), 然后删掉所有备份;
  2. 清理运行态与派生产物(segments / normalized / staging / reports / state / logs / manifest / plan)。

用法(项目根目录):
    .venv\\Scripts\\python.exe tools\\reset_example.py
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

ROOT = Path(__file__).resolve().parent.parent
WS = ROOT / "examples" / "mini-group"

KINDS = ("characters", "relations", "players", "pl_profiles")
CLEAN_DIRS = (
    "素材/segments",
    ".trpg/normalized",
    ".trpg/staging",
    ".trpg/reports",
    ".trpg/state",
    ".trpg/logs",
    ".trpg/segments_index",
)
CLEAN_FILES = (".trpg/manifest.json",)


def main() -> int:
    if not WS.is_dir():
        print(f"!! 示例工作区不存在: {WS}")
        return 1
    restored: list[str] = []
    for kind in KINDS:
        target = WS / "数据" / f"{kind}.json"
        baks = sorted((WS / "数据").glob(f"{kind}.json.bak_store_*"))
        if not baks:
            continue
        newest = baks[-1]
        shutil.copy2(newest, target)
        restored.append(f"{kind}.json <- {newest.name}")
    for bak in (WS / "数据").glob("*.bak_store_*"):
        bak.unlink()

    for rel in CLEAN_DIRS:
        d = WS / rel
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for rel in CLEAN_FILES:
        f = WS / rel
        if f.is_file():
            f.unlink()
    for plan in WS.glob(".trpg/plan_*.json"):
        plan.unlink()

    # 工作补丁从受保护夹具恢复(extract 会覆盖工作副本, 夹具不能动)
    fixture = WS / "fixtures" / "星海列车_patch.json"
    work_patch = WS / ".trpg" / "patches" / "星海列车_patch.json"
    if fixture.is_file():
        work_patch.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(fixture, work_patch)
        print(f"  工作补丁已从夹具恢复: {work_patch.relative_to(WS)}")

    for line in restored:
        print(f"  还原 {line}")
    if not restored:
        print("  (无备份可还原, 数据目录保持原样)")
    print(f"示例已重置: {WS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
