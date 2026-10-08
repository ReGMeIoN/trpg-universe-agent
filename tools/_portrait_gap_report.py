# -*- coding: utf-8 -*-
"""生成立绘缺口清单（谁还没图），按团分组输出 markdown。

站点现在是全量口径：**没有立绘的角色也在页面上**（显示「未解封」剪影卡），
谁都可以在门户的「新增条目」页或档案页点「上传立绘」补一张。
这份清单就是给主人/朋友们按图索骥用的。

用法：
    .venv\\Scripts\\python.exe tools\\_portrait_gap_report.py [--out 产出\\立绘缺口清单.md]
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e"
OUT_DEFAULT = WS / "\u4ea7\u51fa" / "\u7acb\u7ed8\u7f3a\u53e3\u6e05\u5355.md"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--ws", default="")
    a = ap.parse_args()
    data_dir = Path(a.ws) / "\u6570\u636e" if a.ws else DATA
    chars = json.loads((data_dir / "characters.json").read_text(encoding="utf-8"))["characters"]

    have, miss = [], []
    for c in chars:
        (have if c.get("avatar") else miss).append(c)

    by_group: dict[str, list] = defaultdict(list)
    for c in miss:
        for g in (c.get("groups") or ["(无团)"]):
            by_group[g].append(c)

    lines: list[str] = []
    lines.append("# 立绘缺口清单")
    lines.append("")
    lines.append(f"> 生成时间：{__import__('datetime').datetime.now():%Y-%m-%d %H:%M}　·　"
                 f"全库 **{len(chars)}** 角色：**有图 {len(have)}** / **缺图 {len(miss)}**")
    lines.append(">")
    lines.append("> 站点是全量口径 —— **缺图的角色也已经在页面上**（显示「未解封」剪影卡）。")
    lines.append("> 补图方式：门户页（`#/portal`）→「新增条目」→ 建角色时选图；"
                 "或直接调 `POST /api/upload/portrait`（免口令）。")
    lines.append("")
    lines.append("| 排序 | 团 | 缺图人数 |")
    lines.append("|---|---|---|")
    for i, (g, lst) in enumerate(sorted(by_group.items(), key=lambda kv: -len(kv[1])), 1):
        lines.append(f"| {i} | {g} | {len(lst)} |")
    lines.append("")
    for g, lst in sorted(by_group.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"## {g}（{len(lst)} 人缺图）")
        lines.append("")
        lines.append("| id | 名字 | 身份 | 扮演 |")
        lines.append("|---|---|---|---|")
        for c in sorted(lst, key=lambda x: x.get("name") or x.get("id") or ""):
            lines.append("| `{}` | {} | {} | {} |".format(
                c.get("id", ""), c.get("name", ""),
                (c.get("identity") or "")[:40], c.get("played_by") or ""))
        lines.append("")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"全库 {len(chars)} · 有图 {len(have)} · 缺图 {len(miss)}")
    print(f"清单 -> {out}")
    for g, lst in sorted(by_group.items(), key=lambda kv: -len(kv[1]))[:8]:
        print(f"  {len(lst):>3}  {g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
