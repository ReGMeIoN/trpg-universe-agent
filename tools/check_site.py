# -*- coding: utf-8 -*-
"""站点正文/数据自检：找清洗残渣、空页、缺 CG、坏标点等。

用法:
    .venv\\Scripts\\python.exe tools\\check_site.py
"""
from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"

# 不该出现在成品正文里的东西
BAD = [
    (r"\*\*", "未解析的加粗标记"),
    (r"\[\s*\d{2,}", "残留时间戳"),
    (r"（\s*\d{2,}(\.\d+)?\s*[-–—~]\s*\d", "残留时间戳（括号）"),
    (r"主人确认|2026-1\d|修正：|待确认|存疑|不采信|原稿误记", "编者注/元说明"),
    (r"KP\s*描述|转写里|转写中|角色卡设定[：:]", "元说明措辞"),
    (r"(?<!N)PC(?![A-Za-z])", "未替换的 PC"),
    (r"[，,]{2,}", "重复逗号"),
    (r"[（(]\s*[）)]", "空括号"),
    (r"[（(]\s*[，、；]", "括号后紧跟顿号"),
    (r"[\u4e00-\u9fff]\?", "中文后的半角问号（存疑标记残留）"),
    (r"\?\?", "连续问号"),
    (r"^(?:[，、；：]|\s)+", "行首标点"),
    (r"[，、；]\s*[。！？]", "标点连写"),
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    bundle_p = SITE / "data" / "bundle.js"
    raw = bundle_p.read_text(encoding="utf-8")
    data = json.loads(raw[raw.index("{"):raw.rindex(";")])
    pages = data["pages"]
    meta = data["meta"]
    assets = meta.get("assets", {})
    cg, au = set(assets.get("cg", [])), set(assets.get("audio", []))

    print(f"pages={len(pages)}  cg={len(cg)}  audio={len(au)}  "
          f"bgm={len((assets.get('bgm') or {}).get('tracks', {}))}")
    print("-" * 68)

    issues: list[tuple[str, str, str]] = []
    for p in pages:
        txt = p.get("body", "")
        if not txt.strip():
            issues.append((p["key"], "空正文", ""))
        for pat, why in BAD:
            for m in re.finditer(pat, txt, re.M):
                s = max(0, m.start() - 14)
                issues.append((p["key"], why, txt[s:m.end() + 14].replace("\n", "⏎")))
                break

    # CG / 原声 覆盖
    want_cg = [p["key"] for p in pages if p.get("show_cg")]
    missing_cg = sorted({k for k in want_cg if k not in cg})
    have_orphan = sorted(cg - set(want_cg))
    print(f"小节首页 {len(want_cg)} 个（每节首页挂 CG/原声）")
    print(f"存在的 CG {len(cg)} 张；挂载点缺图 {len(missing_cg)} 个")
    print(f"孤立 CG（无对应页）{len(have_orphan)} 个" + (f"  例: {have_orphan[:5]}" if have_orphan else ""))
    # PC 批 CG（22-trpg-sjt-cg-pc）覆盖情况
    pc_dir = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '22-trpg-sjt-cg-pc')
    if pc_dir.is_dir():
        pc_keys = {p.stem[:-2] for p in pc_dir.glob("*_[abc].png")}
        print(f"PC 批候选覆盖 {len(pc_keys)}/15 个场景"
              + (f"；未覆盖: {sorted(set(want_cg) - pc_keys)}" if len(pc_keys) < 15 else " ✅"))
    # 页长分布
    lens = [len(p.get("body", "")) for p in pages]
    print(f"页字数 min={min(lens)} / avg={sum(lens)//len(lens)} / max={max(lens)}")
    over = [p["key"] for p in pages if len(p.get("body", "")) > 260]
    if over:
        print(f"!! 超长页（>260 字）{len(over)} 个: {over[:6]}")
    # 角色 / 关系
    roster = data["roster"]["characters"]
    noav = [c["name"] for c in roster if not c.get("avatar")]
    print(f"角色 {len(roster)}　无立绘 {len(noav)}: {noav}")
    print("-" * 68)
    if issues:
        print(f"发现 {len(issues)} 条正文问题（按类型汇总）:")
        by: dict[str, list] = {}
        for k, why, ctx in issues:
            by.setdefault(why, []).append((k, ctx))
        for why, lst in sorted(by.items(), key=lambda x: -len(x[1])):
            print(f"  [{len(lst):3}] {why}   例: {lst[0][0]}  …{lst[0][1][:44]}…")
        return 1
    print("正文清洗：未发现残渣 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
