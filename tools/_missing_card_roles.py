# -*- coding: utf-8 -*-
"""按「角色卡文件名」盘点缺哪些 PC 还没入库（比词频可靠得多）。

配套 `_missing_roles_scan.py`（那个从转写捞词，噪音大）；
这条直接看**素材目录里的每张角色卡**，清洗出人名后和库内名字/别名比对。

用法：
    .venv\\Scripts\\python.exe tools\\_missing_card_roles.py [--out 产出\\缺卡角色.md]
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
MAT = WS / "\u7d20\u6750"
DATA = WS / "\u6570\u636e"

# 文件名里的前缀/后缀噪音
NOISE = re.compile(
    r"(死囚档案|死囚|囚犯|档案|角色卡|最终版|模板卡|魔法少女校园网|魔法少女|带带后辈|"
    r"第[一二三四五六七八九十\d]+季|周年庆|异世界|coc|ACT\d*|强化|的副本|副本)")
EXTRA = re.compile(r"[（(][^）)]*[）)]|\(\d+\)|\d+$|[·•・_\-—\s]+")


def clean(stem: str) -> str:
    s = NOISE.sub("", stem)
    s = EXTRA.sub("", s)
    return s.strip(" ·•・_—-")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WS / "\u4ea7\u51fa" / "\u7f3a\u5361\u89d2\u8272.md"))
    a = ap.parse_args()

    lib = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    known: set[str] = set()
    for c in lib:
        for k in ("name", "id"):
            if c.get(k):
                known.add(str(c[k]).strip())
        for al in (c.get("aliases") or []):
            known.add(str(al).strip())
    known = {k for k in known if len(k) >= 2}

    def hit(name: str) -> tuple[bool, str]:
        n = name.strip()
        if not n:
            return True, ""
        for k in known:
            if k == n or k in n or n in k:
                return True, k
        return False, ""

    rows: list[tuple[str, str, str, bool, str]] = []   # group, file, probe, ok, matched
    for d in sorted(MAT.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        cards = [f for f in d.iterdir() if f.suffix.lower() in (".doc", ".docx", ".docm")]
        if not cards:
            continue
        for f in sorted(cards):
            probe = clean(f.stem)
            ok, m = hit(probe)
            rows.append((d.name, f.name, probe, ok, m))

    miss = [r for r in rows if not r[3]]
    print(f"角色卡共 {len(rows)} 张：命中库里 {len(rows) - len(miss)} 张 / 疑似缺 {len(miss)} 张\n")
    byg: dict[str, list] = {}
    for r in miss:
        byg.setdefault(r[0], []).append(r)
    for g, lst in byg.items():
        print(f"## {g}")
        for _, fn, probe, _, _ in lst:
            print(f"   - {probe:<18} ← {fn}")
        print()

    lines = ["# 角色卡 vs 生产库：疑似还没入库的", "",
             f"> 素材里一共 {len(rows)} 张角色卡，库里能对上 {len(rows) - len(miss)} 张，"
             f"疑似缺 **{len(miss)}** 张。",
             "> 判定方式：卡文件名清洗后与库内 名字/别名 做包含匹配（包含即算命中）。",
             "> ⚠️ 名单里可能有「模板卡 / 副本 / 已改名」这类噪声，**入库前请主人过一眼**。", ""]
    for g, lst in byg.items():
        lines.append(f"## {g}（{len(lst)}）")
        lines.append("")
        lines.append("| 卡文件名 | 清洗出的名字 |")
        lines.append("|---|---|")
        for _, fn, probe, _, _ in lst:
            lines.append(f"| {fn} | {probe} |")
        lines.append("")
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"清单 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
