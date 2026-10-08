# -*- coding: utf-8 -*-
"""挑图页自检：确认页面能取到、分组/候选数正确、缩略图都在。

用法:
    .venv\\Scripts\\python.exe tools\\check_pickpage.py
    .venv\\Scripts\\python.exe tools\\check_pickpage.py --file     # 不走 HTTP，直接读文件
"""
from __future__ import annotations

import argparse
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / ".trpg" / "pickpage" / "asset-pick.html"
CAND = ROOT / ".trpg" / "pickpage" / "cg-cand"


def report(html: str, base: str | None) -> int:
    groups = re.findall(r'"title": "([^"]+)"', html)
    srcs = re.findall(r'"src": "([^"]+)"', html)
    keys = sorted(set(re.findall(r'"key": "([^"]+)"', html)))
    bad = 0

    print(f"页面大小: {len(html)/1024:.1f} KB")
    print(f"分组 ({len(groups)}):")
    for g in groups:
        print(f"  - {g}")
    print(f"候选图: {len(srcs)} 张")
    print(f"行数（角色/场景）: {len(keys)}")
    print("  " + "、".join(keys))
    for ph in ("__DATA__", "__PICKED__"):
        if ph in html:
            print(f"  !! 残留占位符 {ph}")
            bad += 1

    # 缩略图存在性
    miss = []
    for s in srcs:
        p = CAND / s
        if not p.is_file() or p.stat().st_size < 800:
            miss.append(s)
    print(f"缩略图缺失: {len(miss)}" + (f"  例: {miss[:4]}" if miss else " ✅"))
    bad += len(miss)

    if base:
        try:
            url = base.rstrip("/") + "/.trpg/pickpage/asset-pick.html"
            code = urllib.request.urlopen(url, timeout=10).status
            print(f"HTTP {code}  {url}")
            if code != 200:
                bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"HTTP 取不到: {type(e).__name__}: {e}")
            bad += 1
    print("\n" + ("挑图页 OK ✅" if not bad else f"有 {bad} 项问题 ❌"))
    return 1 if bad else 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", action="store_true", help="不查 HTTP")
    ap.add_argument("--base", default="http://127.0.0.1:8899")
    a = ap.parse_args()
    if not PAGE.is_file():
        print(f"!! 挑图页不存在：{PAGE}（先跑 tools/build_site.py）")
        return 1
    return report(PAGE.read_text(encoding="utf-8"), None if a.file else a.base)


if __name__ == "__main__":
    sys.exit(main())
