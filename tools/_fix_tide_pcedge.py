# -*- coding: utf-8 -*-
"""Remove PC->PL edges: PLs live in players.json, not in the relation graph, so those
edges were dangling (the project's convention is played_by + player.roles)."""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e"
PATCH = WS / ".trpg" / "patches" / ("\u6f6e\u6c50\u76d1\u72f1_patch.json")
TYPE = "\u73a9\u5bb6\u89d2\u8272"          # 玩家角色
PCS = {"td_himmel", "td_shibaideman", "td_temaluo", "td_ace", "td_lina"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()
    rfile = DATA / "relations.json"
    rels = json.loads(rfile.read_text(encoding="utf-8"))
    before = len(rels.get("relations", []))
    rels["relations"] = [r for r in rels.get("relations", [])
                         if not (r.get("from") in PCS and r.get("type") == TYPE)]
    after = len(rels["relations"])
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    pb = len(patch.get("relations", []))
    patch["relations"] = [r for r in patch.get("relations", [])
                          if not (r.get("from") in PCS and r.get("type") == TYPE)]
    pa = len(patch["relations"])
    print("relations.json: %d -> %d (-%d)" % (before, after, before - after))
    print("patch: %d -> %d (-%d)" % (pb, pa, pb - pa))
    if not a.apply:
        print("[dry-run] add --apply to write")
        return 0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f, doc in ((rfile, rels), (PATCH, patch)):
        shutil.copyfile(f, f.with_name(f.name + ".bak_pcedge_" + stamp))
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written (backups *.bak_pcedge_%s)" % stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
