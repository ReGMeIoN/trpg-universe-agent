# -*- coding: utf-8 -*-
"""复验「picks 真的落地了」：把 characters.json 里的立绘，跟候选图逐张比对缩略指纹，
确认落地的那张 = 主人挑的那张（而不是上一轮 `--default a` 留下的）。

做法：注册图是 JPEG 重压过的，不能直接比字节 → 统一缩到 48×48 灰度比平均绝对差，
取最接近的那张候选，看它是否等于 picks 里的字母。

用法:
    python tools/_verify_picks_landed.py --picks "<用户目录>\\Downloads\\_picks_portrait.json"
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

from PIL import Image

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
AVATARS = WS / "\u6570\u636e" / "\u5934\u50cf"          # 数据/头像
CHARS = WS / "\u6570\u636e" / "characters.json"
CAND = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '24-trpg-npc-yymg6')
SIZE = 48


def fp(p: Path) -> list[float]:
    im = Image.open(p).convert("L").resize((SIZE, SIZE), Image.LANCZOS)
    return list(im.getdata())


def dist(a: list[float], b: list[float]) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    pf = Path(sys.argv[sys.argv.index("--picks") + 1]) if "--picks" in sys.argv else None
    if not pf:
        print(__doc__)
        return 1
    picks = json.loads(pf.read_text(encoding="utf-8"))
    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    index = {c.get("id"): c for c in doc.get("characters") or []}

    ok = bad = skip = 0
    for cid, tag in sorted(picks.items()):
        c = index.get(cid)
        if not c:
            print(f"!! {cid}: characters.json 里没有这个节点")
            bad += 1
            continue
        av = c.get("avatar") or ""
        reg = AVATARS / Path(av.replace("\\", "/")).name
        if not reg.is_file():
            print(f"!! {cid}: avatar 指向的文件不存在 {av}")
            bad += 1
            continue
        cands = {t: CAND / f"{cid}_{t}.png" for t in "abc"}
        cands = {t: p for t, p in cands.items() if p.is_file()}
        if not cands:
            print(f"-- {cid} {c.get('name')}: 候选已移走（复用位），跳过")
            skip += 1
            continue
        f0 = fp(reg)
        ranked = sorted(((dist(f0, fp(p)), t) for t, p in cands.items()))
        best = ranked[0][1]
        if best == tag:
            ok += 1
            print(f"OK {cid:<28}{c.get('name',''):<20}挑={tag} 落地={best}"
                  f"  (次近 {ranked[1][1] if len(ranked) > 1 else '-'} 差 {ranked[0][0]:.1f})")
        else:
            bad += 1
            print(f"!! {cid:<28}{c.get('name',''):<20}挑={tag} 但落地最像 {best}"
                  f"  (差 {ranked[0][0]:.1f})")
    print(f"\n复验: {ok} 对上 / {bad} 不一致 / {skip} 跳过（复用位）")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
