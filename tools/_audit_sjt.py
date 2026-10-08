# -*- coding: utf-8 -*-
"""审计「圣剑英雄谭」的提炼覆盖度：转写 → 段 → 草稿 → 补丁，逐层看有没有漏。

用法: .venv\\Scripts\\python.exe tools\\_audit_sjt.py
"""
from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
TS_RE = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\s*->")


def mmss(sec: float) -> str:
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    tr = WS / "素材" / "圣剑英雄谭_转写.txt"
    lines = tr.read_text(encoding="utf-8", errors="replace").splitlines()
    stamps = []
    for ln in lines:
        m = TS_RE.match(ln.strip())
        if m:
            stamps.append(float(m.group(1)))
    print(f"[转写稿] {tr.name}: {tr.stat().st_size} 字节 / {len(lines)} 行 / 带时间戳 {len(stamps)} 行")
    if stamps:
        print(f"         时间范围 {mmss(stamps[0])} ~ {mmss(stamps[-1])} "
              f"(音频总长 377.4 分钟 = 6:17)")

    segs = sorted((WS / ".trpg" / "segments").glob("圣剑英雄谭_段*.txt"))
    print(f"\n[段] {len(segs)} 个")
    total_seg_lines = 0
    for s in segs:
        txt = s.read_text(encoding="utf-8", errors="replace")
        ss = [float(TS_RE.match(x.strip()).group(1)) for x in txt.splitlines()
              if TS_RE.match(x.strip())]
        total_seg_lines += len(txt.splitlines())
        rng = f"{mmss(ss[0])}~{mmss(ss[-1])}" if ss else "无时间戳"
        print(f"  {s.name:<34} {s.stat().st_size:>7} 字节 / {len(txt.splitlines()):>5} 行 / {rng}")
    print(f"  段行数合计 {total_seg_lines} vs 转写稿 {len(lines)} 行 "
          f"(差 {len(lines) - total_seg_lines}, 正常=段首尾时间戳边界)")

    ex = sorted((WS / ".trpg" / "extracts").glob("圣剑英雄谭_段*_提炼.md"))
    print(f"\n[分段提炼草稿] {len(ex)} 个")
    for e in ex:
        print(f"  {e.name:<34} {e.stat().st_size:>7} 字节")

    pj = WS / ".trpg" / "patches" / "圣剑英雄谭_patch.json"
    doc = json.loads(pj.read_text(encoding="utf-8"))
    chars = doc.get("characters") or []
    rels = doc.get("relations") or []
    ev_total = 0
    print(f"\n[补丁] 角色 {len(chars)} · 关系 {len(rels)} · pending {len(doc.get('pending') or [])}")
    print(f"{'id':<26}{'name':<14}{'事件条':>6}{'事件字数':>8}")
    for c in chars:
        evs = c.get("events") or []
        items = [i for e in evs for i in (e.get("items") or [])]
        n_char = sum(len(i) for i in items)
        ev_total += len(items)
        print(f"  {c.get('id',''):<24}{c.get('name',''):<14}{len(items):>6}{n_char:>8}")
    print(f"  事件条目合计 {ev_total}")
    print(f"\n[关系] {len(rels)} 条")
    for r in rels:
        print(f"  {r.get('from')} --{r.get('type')}({r.get('strength')})--> {r.get('to')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
