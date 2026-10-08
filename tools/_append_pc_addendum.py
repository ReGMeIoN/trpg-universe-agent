# -*- coding: utf-8 -*-
"""把「三 PC 戏份核对」的 high/medium 条目作为附录追加进《剧情编年史》（幂等）。

为什么要它：妮娜·可可 / 莉亚·岩心 / 飒飒米 的名字在转写里几乎没被点名（转写未分离说话人），
正编里他们的戏份因此偏少。本附录按证据把它们补回编年史。

用法:
    .venv\\Scripts\\python.exe tools\\_append_pc_addendum.py
"""
from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "圣剑英雄谭"
CHRONICLE = WS / "产出" / f"{GROUP}_剧情编年史.md"
OUT_DIR = WS / ".trpg" / "extracts"
MARK = "## 附：三 PC 戏份补录"

TITLES = {
    "飒飒米": "飒飒米（pd）—— 提夫林吟游诗人，音之圣剑「小尤里」",
    "妮娜·可可": "妮娜·可可（往）—— 人造人，炎之圣剑「血」",
    "莉亚·岩心": "莉亚·岩心（ReGMeIoN）—— 半兽人，土之圣剑「无双天下磁场爆破剑」",
}


def fmt(sec: str) -> str:
    try:
        s = float(sec)
    except (TypeError, ValueError):
        return str(sec)
    return f"{int(s)//3600}:{int(s)%3600//60:02d}:{int(s)%60:02d}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    rows: dict[str, list[tuple[str, dict]]] = {k: [] for k in TITLES}
    for f in sorted(OUT_DIR.glob(f"{GROUP}_三PC核对_*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        tag = f.stem.split("_")[-1]
        for x in doc.get("findings") or []:
            who = x.get("who")
            if who in rows and x.get("confidence") in ("high", "medium"):
                rows[who].append((tag, x))

    lines = ["", "---", "", f"{MARK}（专项核对，2026-10-03）", "",
             "> 这三位 PC 的名字在转写里几乎没被点名（录音未分离说话人、且多用昵称），正编里他们的戏份因此偏少。",
             "> 本节由 `tools/_trace_pcs_sjt.py` 逐段回扫原始转写得到，**只收 high/medium 置信度**；",
             "> low 置信度的推测条目仅存档在 `.trpg/extracts/*_三PC核对_*.json`，不入正文。", ""]
    total = 0
    for who, title in TITLES.items():
        items = rows[who]
        lines.append(f"### {title}")
        lines.append("")
        if not items:
            lines.append("(本段无 high/medium 依据)")
            lines.append("")
            continue
        for tag, x in sorted(items, key=lambda t: (t[1].get("at") or 0)):
            total += 1
            conf = "明确" if x.get("confidence") == "high" else "较可能"
            lines.append(f"- **[{fmt(x.get('at'))}]**（{conf}）{x.get('quote')}")
            lines.append(f"  - 依据：{x.get('why')}")
        lines.append("")

    text = CHRONICLE.read_text(encoding="utf-8")
    # 幂等：删掉旧的同一附录
    idx = text.find("\n---\n\n" + MARK)
    if idx >= 0:
        text = text[:idx]
    CHRONICLE.write_text(text.rstrip() + "\n" + "\n".join(lines), encoding="utf-8")
    print(f"OK 已追加附录（{total} 条 high/medium）-> {CHRONICLE}")
    for who in TITLES:
        print(f"  {who}: {len(rows[who])} 条")
    return 0


if __name__ == "__main__":
    sys.exit(main())
