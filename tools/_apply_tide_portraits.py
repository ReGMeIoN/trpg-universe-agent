# -*- coding: utf-8 -*-
"""Register 潮汐监狱 PC portraits from the in-card images (PC rule: use card art as-is).

Himmel / 失败的 man have no usable portrait inside their cards (only dice/skill
tables, and a live-action Spider-Man still) -> per the owner's ruling they stay EMPTY.

Source images come from tools/_cards_batch.py into
    .trpg/card_images/tide_<group>/<card stem>__imageN.<ext>
The per-character pick is deliberate: every other image in these cards is a stat or
skill table (verified by eye, 2026-10-06).

usage:
    python tools/_apply_tide_portraits.py            # dry-run
    python tools/_apply_tide_portraits.py --apply
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))                                   # TRPG关系网
CARD_IMG = PROJECT / ".trpg" / "card_images" / ("tide_" + "\u6f6e\u6c50\u76d1\u72f1")
AVATAR_DIR = WS / "\u6570\u636e" / "\u5934\u50cf"                                    # 数据/头像
GROUP = "\u6f6e\u6c50\u76d1\u72f1"                                                   # 潮汐监狱

# character name -> image file name inside .trpg/card_images/tide_潮汐监狱
PICKS = {
    "Ace": "\u6b7b\u56da\u6863\u6848-Ace__image1.png",          # 死囚档案-Ace__image1.png
    "\u5fd2\u739b\u841d": "\u6b7b\u56da\u5fd2\u739b\u841d__image2.jpg",  # 死囚忒玛萝__image2.jpg
    "\u8389\u5a1c": "\u8389\u5a1c__image3.jpg",               # 莉娜__image3.jpg
}
SKIP = ["Himmel", "\u5931\u8d25\u7684 man"]                    # 失败的 man


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    if not CARD_IMG.is_dir():
        print("!! missing card image dir: " + str(CARD_IMG))
        return 2

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    plan: dict[str, str] = {}
    for name, src in PICKS.items():
        p = CARD_IMG / src
        if not p.is_file():
            print("  !! missing source: " + src)
            continue
        ext = p.suffix.lstrip(".").lower()
        out = AVATAR_DIR / (GROUP + "_" + name + "." + ext)
        rel = "\u6570\u636e\\\u5934\u50cf\\" + out.name
        plan[name] = rel
        print("  OK %s: %s (%d KB) -> %s" % (name, src, p.stat().st_size // 1024, out.name))
        if a.apply:
            shutil.copyfile(p, out)

    for s in SKIP:
        print("  -- %s: no usable in-card portrait (owner ruled: leave empty)" % s)

    cfile = WS / "\u6570\u636e" / "characters.json"
    doc = json.loads(cfile.read_text(encoding="utf-8"))
    n = 0
    for c in doc.get("characters", []):
        rel = plan.get(c.get("name"))
        if rel and c.get("avatar") != rel:
            print("    %s: %s -> %s" % (c["name"], c.get("avatar"), rel))
            c["avatar"] = rel
            n += 1
    if a.apply and n:
        bak = cfile.with_name(cfile.name + ".bak_tidecard_" + time.strftime("%Y%m%d_%H%M%S"))
        shutil.copyfile(cfile, bak)
        cfile.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print("\ncharacters.json updated %d character(s) (backup %s)" % (n, bak.name))
    elif not a.apply:
        print("\n[dry-run] would update %d character(s); add --apply to write" % n)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
