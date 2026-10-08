# -*- coding: utf-8 -*-
"""体检：绘本正文里混进了哪些"非剧情文本"（时间戳残留 / 元信息 / 编者注 / 场外语）。

用法: .venv\\Scripts\\python.exe tools\\_audit_text.py
"""
from __future__ import annotations

import json
import re
import sys
from collections import Counter
from pathlib import Path

SITE = Path(Path(__file__).resolve().parents[1] / 'site')

PATTERNS = [
    ("方括号时间戳 [123-456]", re.compile(r"\[\s*\d{2,}(?:\.\d+)?\s*[-–—~到至]\s*\d{2,}(?:\.\d+)?\s*\]")),
    ("方括号单点 [3876.08]", re.compile(r"\[\s*\d{2,}\.\d+\s*\]")),
    ("圆括号约数 （约1234）", re.compile(r"[（(]\s*约\s*\d{2,}")),
    ("裸时间范围 （1234-5678）", re.compile(r"[（(]\s*\d{3,}\s*[-–—~]\s*\d{3,}\s*[)）]")),
    ("编者注 （2026-10-03…）", re.compile(r"[（(]\s*20\d\d-\d\d-\d\d")),
    ("段标记 段3：", re.compile(r"段\s*\d+\s*[：:]")),
    ("待确认/存疑", re.compile(r"待确认|存疑|待核")),
    ("角色卡设定字样", re.compile(r"角色卡设定|角色卡原件")),
    ("转写/ASR 字样", re.compile(r"转写|ASR|录音里|音近")),
    ("场外/玩梗提示", re.compile(r"场外|玩梗|桌边梗|玩家胡诌")),
    ("KR/KP 口播提示", re.compile(r"^菌羊描述|KP描述|口播")),
    ("英文残留", re.compile(r"[A-Za-z]{4,}")),
    ("连续空行/分隔", re.compile(r"^---+$")),
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    story = json.loads((SITE / "data" / "story.json").read_text(encoding="utf-8"))
    bodies = [(seg["tag"], s["key"], s["body"]) for seg in story["segments"] for s in seg["sections"]]
    print(f"小节 {len(bodies)} 个 / 正文合计 {sum(len(b[2]) for b in bodies):,} 字\n")
    for name, rx in PATTERNS:
        hits = [(tag, key, rx.findall(body), body) for tag, key, body in bodies if rx.search(body)]
        if not hits:
            continue
        total = sum(len(h[2]) for h in hits)
        print(f"■ {name}: {total} 处 / 涉 {len(hits)} 小节")
        for tag, key, found, body in hits[:3]:
            m = rx.search(body)
            s = max(0, m.start() - 30)
            print(f"    [{key}] …{body[s:m.end() + 30]}…")
        print()
    # 逐页看长度分布，找"明显不是剧情"的短页
    pages = json.loads((SITE / "data" / "pages.json").read_text(encoding="utf-8"))["pages"]
    lens = Counter()
    for p in pages:
        n = len(p["body"])
        lens["<40" if n < 40 else "40-80" if n < 80 else "80-130" if n < 130 else ">130"] += 1
    print("绘本页长度分布:", dict(lens), f"（共 {len(pages)} 页）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
