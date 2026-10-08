# -*- coding: utf-8 -*-
"""按时间段打印转写稿原文（核对时用来给人看某一段到底说了什么）。

用法:
    .venv\\Scripts\\python.exe tools\\_dump_ts.py <transcript> <start_s> <end_s>
    .venv\\Scripts\\python.exe tools\\_dump_ts.py 素材\\圣剑英雄谭_转写.txt 18620 18700
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

TS_RE = re.compile(r"^\[\s*([\d.]+)\s*->\s*([\d.]+)\s*\]\s?(.*)$")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    if len(sys.argv) < 4:
        print(__doc__)
        return 1
    path, a, b = Path(sys.argv[1]), float(sys.argv[2]), float(sys.argv[3])
    if not path.is_file():
        print(f"找不到 {path}")
        return 1
    n = 0
    for raw in path.read_text(encoding="utf-8", errors="replace").splitlines():
        m = TS_RE.match(raw.strip())
        if not m:
            continue
        t = float(m.group(1))
        if a <= t <= b:
            n += 1
            print(f"[{int(t)//60}:{int(t)%60:02d}] {m.group(3)}")
    print(f"--- {n} 行 (窗口 {int(a)}~{int(b)}s) ---")
    return 0


if __name__ == "__main__":
    sys.exit(main())
