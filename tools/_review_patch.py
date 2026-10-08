# -*- coding: utf-8 -*-
"""One-screen review of a group's extract patch (characters / updates / relations / pending).

Why: `store` consumes `<work>/patches/<团>_patch.json`, and the review step needs to see
exactly what the model claims — especially the pending list — without opening 100 KB of JSON.

usage:
    python tools/_review_patch.py --group "阴阳差事录 超自然怪谈"
    python tools/_review_patch.py --group X --full      # 打印完整 note/event 正文
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCHES = WS / ".trpg" / "patches"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--dangling", action="store_true",
                    help="只列端点不存在的关系（store 会跳过这些）+ 需要补的节点")
    ap.add_argument("--ids", action="store_true",
                    help="只列 id | 名字 | 标签 | played_by | confirmed | 别名（一行一个）")
    args = ap.parse_args()

    p = PATCHES / f"{args.group}_patch.json"
    if not p.is_file():
        print(f"!! 没有补丁: {p}")
        return 1
    d = json.loads(p.read_text(encoding="utf-8"))

    if args.ids:
        for c in d.get("characters") or []:
            al = "\u3001".join(c.get("aliases") or [])
            print(f"{c.get('id'):<30} {c.get('name'):<24} {','.join(c.get('tags') or []):<18} "
                  f"pb={c.get('played_by'):<10} conf={c.get('confirmed', True)}"
                  + (f" | {al}" if al else ""))
        return 0

    if args.dangling:
        ids = {c.get("id") for c in (d.get("characters") or [])}
        roster = WS / ".trpg" / "canon" / "roster.json"
        if roster.is_file():
            ids |= {c.get("id") for c in (json.loads(roster.read_text(encoding="utf-8")).get("characters") or [])}
        missing: dict[str, list[str]] = {}
        print(f"== 悬空端点的关系 (团 {args.group}) ==")
        for i, r in enumerate(d.get("relations") or []):
            bad = [x for x in (r.get("from"), r.get("to")) if x not in ids]
            if bad:
                for x in bad:
                    missing.setdefault(x, []).append(f"[{i}] {r.get('from')} -> {r.get('to')} | {r.get('type')}")
                print(f"  [{i}] {r.get('from')} -> {r.get('to')} | {r.get('type')} | 缺: {bad}")
                print(f"      事件: {str(r.get('event'))[:120]}")
        if not missing:
            print("  （没有悬空端点）")
        print("\n== 需要补的节点 ==")
        for k, uses in missing.items():
            print(f"  {k}（被 {len(uses)} 条关系引用）")
        return 0

    meta = d.get("_meta") or {}
    print(f"补丁: {p.name}")
    print(f"生成: {meta.get('generated')} · {meta.get('generator')} · 段数 {len(meta.get('source_segments') or [])}")
    print(f"id 前缀: {d.get('id_prefix')}")

    chars = d.get("characters") or []
    print(f"\n== 新增角色 {len(chars)} ==")
    for c in chars:
        flags = []
        if not c.get("confirmed", True):
            flags.append("待确认")
        print(f"  {c.get('id'):<28} {c.get('name'):<16} {','.join(c.get('tags') or []):<14} "
              f"played_by={c.get('played_by')} {'/'.join(flags)}")
        note = c.get("note") or ""
        if note:
            print(f"      {note if args.full else note[:150]}")

    ups = d.get("character_updates") or []
    print(f"\n== 更新既有角色 {len(ups)} ==")
    for u in ups:
        print(f"  {u.get('id')}: {json.dumps({k: v for k, v in u.items() if k != 'id'}, ensure_ascii=False)[:300]}")

    rels = d.get("relations") or []
    print(f"\n== 关系 {len(rels)} ==")
    for r in rels:
        print(f"  {r.get('from')} -> {r.get('to')} | {r.get('type')} | {r.get('strength')} | {str(r.get('event'))[:120]}")

    for key in ("players", "pl_profiles", "profile_updates", "player_updates"):
        v = d.get(key) or []
        if v:
            print(f"\n== {key} {len(v)} ==")
            for x in v:
                print(f"  {json.dumps(x, ensure_ascii=False)[:300]}")

    pend = d.get("pending") or []
    print(f"\n== 待确认 {len(pend)} ==")
    for i, q in enumerate(pend, 1):
        print(f"  {i:02d} [段{q.get('segment')}] {q.get('item')}")
        reason = str(q.get("reason") or "")
        if reason:
            print(f"      理由: {reason if args.full else reason[:160]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
