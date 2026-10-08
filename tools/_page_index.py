# -*- coding: utf-8 -*-
"""列出绘本页索引（找带 CG 的页 / 跨段的页，方便截图核对）。"""
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
ROOT = Path(__file__).resolve().parent.parent
raw = (ROOT / "site" / "data" / "bundle.js").read_text(encoding="utf-8")
d = json.loads(raw[raw.index("{"):raw.rindex(";")])
pages = d["pages"]
cg = set((d["meta"].get("assets") or {}).get("cg", []))

mode = sys.argv[1] if len(sys.argv) > 1 else "cg"
print(f"total={len(pages)}  cg={len(cg)}")
if mode == "cg":
    for i, p in enumerate(pages):
        if p["key"] in cg:
            print(f"  #{i:3}  {p['key']}  part {p['part']+1}/{p['parts']}  {p['title'][:18]}")
elif mode == "seg":
    last = None
    for i, p in enumerate(pages):
        if p["seg"] != last:
            print(f"  #{i:3}  seg={p['seg']}  {p['key']}  part {p['part']+1}/{p['parts']}")
            last = p["seg"]
elif mode == "len":
    order = sorted(range(len(pages)), key=lambda i: len(pages[i]["body"]))
    for i in order[:6]:
        print(f"  shortest #{i}: {len(pages[i]['body'])} 字  {pages[i]['key']}")
    for i in order[-3:]:
        print(f"  longest  #{i}: {len(pages[i]['body'])} 字  {pages[i]['key']}")
