# -*- coding: utf-8 -*-
"""从 QQ 聊天记录里盘点「群里出现过、但库里没有」的角色。

QQ 导出的纯文本里有两种金矿：
  1. `[系统] XX邀请<角色名>加入了群聊。` —— **开局点名**，最全的角色清单；
  2. `[时间] <昵称>: 消息` —— 发言人昵称（PL 或角色名），可交叉验证。
这条比从转写里捞词可靠得多（转写里全是"对啊/哈哈哈"这种口语）。

用法：
    .venv\\Scripts\\python.exe tools\\_missing_qq_roles.py [--out 产出\\QQ团缺角色.md]
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
MAT = WS / "\u7d20\u6750"
DATA = WS / "\u6570\u636e"

INVITE = re.compile(r"\u9080\u8bf7(.+?)\u52a0\u5165\u4e86\u7fa4\u804a")     # 邀请…加入了群聊
SPEAK = re.compile(r"^\[[\d\-: ]+\]\s*(?:\[[\u7cfb\u7edf]+\]\s*)?([^:：]{2,20})[:\uff1a]")  # 发言人

# 昵称/角色名尾巴上的状态噪声
TAIL = re.compile(r"(hp|HP|san|SAN|\u5f53\u524d|\u5269\u4f59|\d+\s*/?\s*\d*|\uff08[^\uff09]*\uff09|\([^)]*\)|[:\uff1a].*)$")


def clean_name(s: str) -> str:
    s = s.strip()
    s = re.sub(r"^(?:\u9080\u8bf7|\u62c9)", "", s)
    s = re.sub(r"[\s\d]+$", "", s)
    s = TAIL.sub("", s).strip()
    s = s.strip("\u3002\uff0c,\u3001 ")
    return s


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(WS / "\u4ea7\u51fa" / "QQ\u56e2\u7f3a\u89d2\u8272.md"))
    a = ap.parse_args()

    lib = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    known: set[str] = set()
    for c in lib:
        for k in ("name", "id"):
            if c.get(k):
                known.add(str(c[k]).strip())
        for al in (c.get("aliases") or []):
            known.add(str(al).strip())
        nm = str(c.get("name") or "")
        m = re.match(r"^([^\uff08(]+)", nm)
        if m:
            known.add(m.group(1).strip())
    known = {k for k in known if len(k) >= 2}

    def known_hit(n: str) -> str:
        for k in known:
            if k == n or (len(n) >= 2 and (k in n or n in k)):
                return k
        return ""

    files = sorted(MAT.glob("*\u804a\u5929\u8bb0\u5f55\u7eaf\u6587\u672c.txt"))
    lines = ["# QQ 团：群里点名过、库里没有的角色", "",
             "> 证据源：`[系统] XX邀请<名字>加入了群聊` 与发言人昵称。",
             "> ⚠️ 列表里可能有 KP / 骰娘 / PL 昵称 / 场地玩家，**入库前请主人认一下**。", ""]
    grand_miss: dict[str, set] = {}
    for f in files:
        txt = f.read_text(encoding="utf-8", errors="replace")
        group = f.name.split("_")[0]
        invited = Counter()
        for m in INVITE.finditer(txt):
            nm = clean_name(m.group(1))
            if len(nm) >= 2:
                invited[nm] += 1
        speakers = Counter()
        for line in txt.splitlines():
            m = SPEAK.match(line)
            if m:
                nm = clean_name(m.group(1))
                if len(nm) >= 2 and nm not in ("\u7cfb\u7edf",):
                    speakers[nm] += 1
        miss_inv = {n: c for n, c in invited.items() if not known_hit(n)}
        miss_spk = {n: c for n, c in speakers.items() if not known_hit(n) and c >= 5}
        grand_miss[group] = set(miss_inv) | set(miss_spk)

        print(f"\n=== {group} ===")
        print(f"  群里被邀请过 {len(invited)} 个名字；发言昵称 {len(speakers)} 个")
        print(f"  库里对不上的（邀请名单）：{'、'.join(miss_inv) or '（无）'}")
        print(f"  库里对不上的（高频发言≥5）：{'、'.join(miss_spk) or '（无）'}")

        lines.append(f"## {group}")
        lines.append("")
        if miss_inv:
            lines.append("**🎯 开局被点名邀请、库里没有（最可能就是缺的角色）**")
            lines.append("")
            lines.append("| 名字 | 被邀请次数 |")
            lines.append("|---|---|")
            for n, c in sorted(miss_inv.items(), key=lambda kv: -kv[1]):
                lines.append(f"| {n} | {c} |")
            lines.append("")
        if miss_spk:
            lines.append("**高频发言人昵称（可能是 PL 昵称，也可能是角色）**")
            lines.append("")
            lines.append("| 昵称 | 发言条数 |")
            lines.append("|---|---|")
            for n, c in sorted(miss_spk.items(), key=lambda kv: -kv[1])[:30]:
                lines.append(f"| {n} | {c} |")
            lines.append("")

    # 全库合并
    allmiss: Counter = Counter()
    for s in grand_miss.values():
        allmiss.update(s)
    lines.append("## 全库合并")
    lines.append("")
    for n, _ in allmiss.most_common(80):
        lines.append(f"- {n}")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n清单 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
