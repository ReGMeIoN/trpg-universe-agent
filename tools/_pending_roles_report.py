# -*- coding: utf-8 -*-
"""盘点「提炼时被标成待确认、至今没入库」的角色/条目。

这是最直接的「缺角色」证据源：`extract` 当时认出来了，但因为 `confirmed:false`
（铁律：拿不准不写盘）一直躺在补丁里。主人问"老团还有很多角色没入库"时，
先把这份清单摆出来最有用。

用法：
    .venv\\Scripts\\python.exe tools\\_pending_roles_report.py [--out 产出\\未入库待确认.md]
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCHES = WS / ".trpg" / "patches"
DATA = WS / "\u6570\u636e"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WS / "\u4ea7\u51fa" / "\u672a\u5165\u5e93\u5f85\u786e\u8ba4.md"))
    a = ap.parse_args()

    lib = {c.get("id") for c in json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]}

    lines = ["# 待确认 / 未入库清单（按团）", "",
             "> 这些是提炼阶段认出、但因 `confirmed:false` 没写进生产库的条目。",
             "> **角色类**的可以挑着建节点；**设定类**的通常不用管（玩梗不入库是铁律）。", ""]
    total_new = 0
    for p in sorted(PATCHES.glob("*_patch.json")):
        if ".bak" in p.name:
            continue
        group = p.name[: -len("_patch.json")]
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        chars = doc.get("characters") or []
        pend = doc.get("pending") or doc.get("\u5f85\u786e\u8ba4") or []
        pending_chars = [c for c in chars if c.get("confirmed") is False]
        new_chars = [c for c in chars if c.get("id") not in lib]
        if not (pending_chars or new_chars or pend):
            continue
        print(f"\n=== {group} ===")
        if pending_chars:
            print(f"  补丁里 confirmed:false 的角色 {len(pending_chars)} 个：")
            for c in pending_chars:
                print(f"    - {c.get('name','?')}  [{c.get('id','')}]")
        if new_chars:
            print(f"  补丁里有、库里没有的角色 {len(new_chars)} 个：")
            for c in new_chars:
                print(f"    - {c.get('name','?')}  [{c.get('id','')}]")
                total_new += 1
        print(f"  其它待确认条目 {len(pend)} 条")

        lines.append(f"## {group}")
        lines.append("")
        if new_chars:
            lines.append(f"**库里没有的候选角色（{len(new_chars)}）**")
            lines.append("")
            lines.append("| 名字 | id | 身份 | 简介（截断） |")
            lines.append("|---|---|---|---|")
            for c in new_chars:
                lines.append("| {} | `{}` | {} | {} |".format(
                    c.get("name", ""), c.get("id", ""),
                    (c.get("identity") or "")[:30], (c.get("note") or "")[:60].replace("|", "/")))
            lines.append("")
        if pending_chars:
            lines.append(f"**补丁里被标 confirmed:false 的角色（{len(pending_chars)}）**")
            lines.append("")
            for c in pending_chars:
                lines.append(f"- {c.get('name','')} `{c.get('id','')}` — {(c.get('note') or '')[:80]}")
            lines.append("")
        if pend:
            lines.append(f"**其它待确认（{len(pend)} 条）**")
            lines.append("")
            for it in pend[:40]:
                txt = it.get("item") or it.get("reason") or str(it)[:60]
                lines.append(f"- {str(txt)[:100]}")
            lines.append("")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n合计「库里有缺失」的候选角色：{total_new} 个")
    print(f"清单 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
