# -*- coding: utf-8 -*-
"""把挑图页导出的 picks 落成正式立绘：候选 PNG → 数据\\头像\\<团>_<角色>.jpg + 回写 characters.json。

两种用法：
  1) 主人挑完：`--picks <挑图页导出的 _picks_portrait.json>`
  2) 先占位（挑图页还没看）：`--default a` —— 把每个角色的 a 候选先登记上，
     之后主人挑了再跑一次 `--picks ...` 覆盖即可（本工具幂等、每次都备份）。

写法与 `build_site.sync_avatar_pick` 一致（压到最长边 1000、JPEG q90）。

用法:
    python tools/_apply_npc_portraits.py --default a               # dry-run
    python tools/_apply_npc_portraits.py --default a --apply
    python tools/_apply_npc_portraits.py --picks D:\\...\\_picks_portrait.json --apply
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
AVATARS = DATA / "\u5934\u50cf"                         # 头像
CHARS = DATA / "characters.json"
CAND = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '24-trpg-npc-yymg6')

# 跨团同位体由 `_apply_reuse_portraits.py` 负责，**本工具一律跳过**——
# 否则 `--default a` 会把「曼德拉/神前早月/马卡龙」这些复用位又盖回成自己生成的候选图。
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    from _apply_reuse_portraits import REUSE as _REUSE   # noqa: E402
except Exception as _e:  # noqa: BLE001
    _REUSE = {}
    print(f"!! 读不到 _apply_reuse_portraits.REUSE（{type(_e).__name__}: {_e}），不跳过复用位")

MAX_SIDE = 1000


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    apply = "--apply" in argv
    default = argv[argv.index("--default") + 1] if "--default" in argv else None
    picks_file = Path(argv[argv.index("--picks") + 1]) if "--picks" in argv else None

    cand_dir = Path(argv[argv.index("--cand") + 1]) if "--cand" in argv else CAND

    picks: dict[str, str] = {}
    if picks_file:
        raw = json.loads(picks_file.read_text(encoding="utf-8"))
        for k, v in (raw or {}).items():
            if isinstance(v, dict):
                v = v.get("pick") or v.get("tag") or ""
            v = str(v).strip().lstrip("_")
            if v in ("a", "b", "c"):
                picks[str(k)] = v

    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    index = {c.get("id"): c for c in doc.get("characters") or []}

    # 候选目录里出现过的角色 id
    cids = sorted({p.stem[:-2] for p in cand_dir.glob("*_[abc].png")}) if cand_dir.is_dir() else []
    skipped_reuse = [c for c in cids if c in _REUSE]
    if skipped_reuse:
        print(f"跳过 {len(skipped_reuse)} 个跨团复用位（归 _apply_reuse_portraits.py 管）: "
              f"{', '.join(skipped_reuse)}")

    plan = []
    missing = []
    for cid in cids:
        if cid in _REUSE:
            continue
        tag = picks.get(cid) or default
        if not tag:
            continue
        if cid not in index:
            missing.append(f"characters.json 里没有这个 id: {cid}")
            continue
        src = cand_dir / f"{cid}_{tag}.png"
        if not src.is_file():
            missing.append(f"候选缺失: {src}")
            continue
        c = index[cid]
        group = (c.get("groups") or ["未分组"])[0]
        name = c.get("name") or cid
        # 文件名里的 Windows 非法字符要洗掉（角色名里出现过「／」「（）」）
        safe = name.replace("/", "／").replace("\\", "＼")
        dst = AVATARS / f"{group}_{safe}.jpg"
        plan.append((cid, name, tag, src, dst))

    print(f"候选目录: {cand_dir}（{len(cids)} 个角色）")
    print(f"待落地 {len(plan)} 张{'（默认候选 ' + default + '）' if default and not picks_file else ''}")
    for cid, name, tag, src, dst in plan[:8]:
        print(f"  {cid:<28}{name:<20}_{tag}  ->  {dst.name}")
    if len(plan) > 8:
        print(f"  ... 其余 {len(plan) - 8} 张")
    if missing:
        print("\n!! 问题:")
        for m in missing[:20]:
            print("   " + m)
    if not plan:
        print("\n没有可落地的项（是不是还没出图 / 还没挑？）")
        return 1
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0

    AVATARS.mkdir(parents=True, exist_ok=True)
    bak = CHARS.with_name(CHARS.name + f".bak_npcportrait_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(CHARS, bak)
    n = 0
    for cid, name, tag, src, dst in plan:
        try:
            im = Image.open(src).convert("RGB")
        except Exception as e:  # noqa: BLE001
            print(f"  !! 打不开 {src.name}: {type(e).__name__}: {e}")
            continue
        w, h = im.size
        scale = MAX_SIDE / max(w, h)
        if scale < 1:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        im.save(dst, "JPEG", quality=90, optimize=True)
        index[cid]["avatar"] = f"{DATA.name}\\{AVATARS.name}\\{dst.name}"
        n += 1
    CHARS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已落地 {n} 张（备份 {bak.name}）")

    chk = json.loads(CHARS.read_text(encoding="utf-8"))
    ci = {c.get("id"): c for c in chk["characters"]}
    ok = 0
    for cid, name, tag, src, dst in plan:
        av = ci[cid].get("avatar") or ""
        fn = Path(av.replace("\\", "/")).name
        if av and (AVATARS / fn).is_file():
            ok += 1
        else:
            print(f"  !! 复验失败 {cid}: {av}")
    print(f"复验: {ok}/{len(plan)} 张头像可解析")
    return 0 if ok == len(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
