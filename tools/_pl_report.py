# -*- coding: utf-8 -*-
"""Print the player roster (uid / qq_name / real_alias / groups played) and profile coverage.

The patch contract wants `player_updates[].add_roles` and `profile_updates[]` to be keyed by
**uid**, and the extract keeps complaining it cannot build pl_profiles without them — so this
is the lookup table for writing those entries by hand.

usage:
    python tools/_pl_report.py                 # 生产库
    python tools/_pl_report.py --ws <shadow>
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=str(WS))
    ap.add_argument("--pl", default=None, help="只详看这名 PL 的画像（支持 uid 或名字）")
    args = ap.parse_args()
    ws = Path(args.ws)
    data = ws / "\u6570\u636e"

    players = json.loads((data / "players.json").read_text(encoding="utf-8")).get("players") or []
    prof = json.loads((data / "pl_profiles.json").read_text(encoding="utf-8")).get("profiles") or []
    by_uid = {p.get("uid"): p for p in prof}

    if args.pl:
        hit = [p for p in prof if args.pl in ((p.get("name") or ""), p.get("uid") or "")]
        if not hit:
            print(f"!! 没找到画像: {args.pl}")
            return 1
        p = hit[0]
        print(f"== {p.get('name')} ({p.get('uid')}) ==")
        print(f"aliases: {'、'.join(p.get('aliases') or [])}")
        for k in ("speaking_style", "rp_style"):
            print(f"\n[{k}]\n{p.get(k) or '(空)'}")
        print(f"\n[impressions] {len(p.get('impressions') or [])} 条")
        for x in (p.get("impressions") or []):
            print(f"  - {x}")
        print(f"\n[highlights] {len(p.get('highlights') or [])} 条")
        for x in (p.get("highlights") or []):
            print(f"  - {x}")
        return 0

    print(f"{ws}\n玩家 {len(players)} 人 · 画像 {len(prof)} 份\n")
    for p in players:
        uid = p.get("uid")
        pr = by_uid.get(uid) or {}
        groups = [str(g).split("(")[0] for g in (pr.get("groups_played") or [])]
        print(f"{uid}")
        print(f"  qq_name={p.get('qq_name')}  real_alias={p.get('real_alias')}  uin={p.get('uin')}")
        print(f"  roles({len(p.get('roles') or [])}): " + "; ".join(
            f"{r.get('group')}={r.get('role')}" for r in (p.get("roles") or [])))
        print(f"  画像: {'有' if pr else '缺'} | groups_played={len(groups)} | cards={len(pr.get('cards') or [])}")
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
