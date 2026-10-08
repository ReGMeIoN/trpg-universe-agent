# -*- coding: utf-8 -*-
"""精简站点原声：只保留与 15 张关键 CG 同 key 的片段（其余删除）。

用法: .venv\\Scripts\\python.exe tools\\_trim_audio.py
"""
from __future__ import annotations

import sys
from pathlib import Path

SITE = Path(Path(__file__).resolve().parents[1] / 'site')
KEEP = {
    "段1_003", "段1_006", "段1_007", "段1_008", "段1_009",
    "段2_001", "段2_007", "段2_009",
    "段3_005", "段3_022",
    "段4_005", "段4_007",
    "段5_006", "段5_014",
    "段6_009",
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    d = SITE / "assets" / "audio"
    if not d.is_dir():
        print("没有 audio 目录")
        return 1
    files = sorted(d.glob("*.mp3"))
    before_n, before_b = len(files), sum(p.stat().st_size for p in files)
    removed = 0
    for p in files:
        if p.stem not in KEEP:
            p.unlink()
            removed += 1
    left = sorted(d.glob("*.mp3"))
    after_b = sum(p.stat().st_size for p in left)
    print(f"删除 {removed} 个；{before_n} 个 / {before_b/1e6:.2f} MB -> {len(left)} 个 / {after_b/1e6:.2f} MB")
    print("保留:", "、".join(p.stem for p in left))
    return 0


if __name__ == "__main__":
    sys.exit(main())
