# -*- coding: utf-8 -*-
"""Find relation endpoints that point at non-existent character ids."""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
chars = json.loads((WS / "\u6570\u636e" / "characters.json").read_text(encoding="utf-8"))
rels = json.loads((WS / "\u6570\u636e" / "relations.json").read_text(encoding="utf-8"))
ids = {c.get("id") for c in chars.get("characters", [])}
bad = []
for r in rels.get("relations", []):
    for k in ("from", "to"):
        if r.get(k) not in ids:
            bad.append((r.get("from"), r.get("to"), r.get("type"), k, r.get("event", "")[:60]))
print("dangling edges: %d" % len(bad))
for b in bad:
    print("  %s -> %s [%s] (bad %s)  %s" % b)
