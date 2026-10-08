# -*- coding: utf-8 -*-
"""Refresh the shadow workspace so `store --apply` can be rehearsed with zero risk.

The shadow ws is a throwaway copy of the production library: root != production_root, so the
production write gate lets the write through without touching real data. Per the project
handover, the shadow needs `数据/` + `.trpg/{canon,patches,state,extracts}` + `manifest.json`.

usage:
    python tools/_shadow_sync.py            # 只看会同步什么
    python tools/_shadow_sync.py --apply    # 真正重建 shadow_ws
    python tools/_shadow_sync.py --apply --shadow <dir>
"""
from __future__ import annotations

import os
import argparse
import shutil
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DEFAULT_SHADOW = WS / ".trpg" / "shadow_ws"

# 生产库 -> shadow 的映射（目录整个同步；文件单个同步）
DIRS = ["\u6570\u636e", ".trpg/canon", ".trpg/patches", ".trpg/state", ".trpg/extracts"]
FILES = [".trpg/manifest.json"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--shadow", default=str(DEFAULT_SHADOW))
    ap.add_argument("--keep", action="store_true", help="不删旧 shadow，直接覆盖")
    args = ap.parse_args()
    shadow = Path(args.shadow)

    print(f"生产库: {WS}")
    print(f"影子库: {shadow}")
    for d in DIRS:
        src = WS / d
        if not src.is_dir():
            print(f"  !! 缺少 {d}（跳过）")
            continue
        n = sum(1 for p in src.rglob("*") if p.is_file())
        print(f"  dir  {d:<22} {n:>4} 个文件")
    for f in FILES:
        print(f"  file {f:<22} {'OK' if (WS / f).is_file() else '缺失'}")

    if not args.apply:
        print("\n(dry-run; 加 --apply 重建影子库)")
        return 0

    if shadow.exists() and not args.keep:
        shutil.rmtree(shadow, ignore_errors=True)
        print(f"已清空旧影子库: {shadow}")
    shadow.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        src = WS / d
        if not src.is_dir():
            continue
        dst = shadow / d
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
    for f in FILES:
        src = WS / f
        if src.is_file():
            dst = shadow / f
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

    # .bak_* 不进影子库（否则 store 的备份轮转会被历史备份塞满）
    for p in shadow.rglob("*.bak_*"):
        try:
            p.unlink()
        except OSError:
            pass
    total = sum(1 for p in shadow.rglob("*") if p.is_file())
    print(f"\nOK 影子库就绪: {shadow}（{total} 个文件）")
    print("下一步:")
    print(f'  .venv\\Scripts\\python.exe -m trpg_agent store --apply --ws "{shadow}" --group "<团名>"')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
