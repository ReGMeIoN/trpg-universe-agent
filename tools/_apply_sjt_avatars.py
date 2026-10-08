# -*- coding: utf-8 -*-
"""把「圣剑英雄谭」角色卡里抽出的立绘登记为角色头像（数据/头像 + characters.json 的 avatar）。

背景：`数据/头像/` 里既有的那批（`木柜子_魔法少女Dollmaker__image1.png` 之类）就是卡内立绘，
关系图 net_html.py 会读 character["avatar"] 渲染 76px 圆头像 + 点击弹窗大图。本次补登记。

用法:
    .venv\\Scripts\\python.exe tools\\_apply_sjt_avatars.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_apply_sjt_avatars.py --write
"""
from __future__ import annotations

import os
import json
import shutil
import struct
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
SRC_DIR = WS / ".trpg" / "refs" / "圣剑英雄谭" / "立绘"
AVATAR_DIR = WS / "数据" / "头像"
CHARS = WS / "数据" / "characters.json"

# 角色 id -> (源图, 输出名)。八重樱的卡里没有图（0 张），只能留空。
PLAN = {
    "sjt_nina": ("妮娜可可__image1.png", "圣剑英雄谭_妮娜可可__image1"),
    "sjt_yashi": ("流星亚什__image1.jpg", "圣剑英雄谭_流星亚什__image1"),
    "sjt_liujia": ("琉珈·深谣__image1.png", "圣剑英雄谭_琉珈深谣__image1"),
    "sjt_liya": ("莉亚·岩心__image1.png", "圣剑英雄谭_莉亚岩心__image1"),
    "sjt_sasami": ("飒飒米__image1.jpg", "圣剑英雄谭_飒飒米__image1"),
}


def sniff(blob: bytes) -> str:
    """按内容判断真实格式（实测：docx 里叫 .png 的其实是 webp）。"""
    if blob[:4] == b"RIFF" and blob[8:12] == b"WEBP":
        return "webp"
    if blob[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if blob[:3] == b"\xff\xd8\xff":
        return "jpg"
    if blob[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    return "bin"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    chars = {c["id"]: c for c in doc["characters"]}
    existing = [c for c in doc["characters"] if c.get("avatar")]
    print(f"现有带头像的角色 {len(existing)} 个，样例: "
          f"{[(c['id'], c['avatar']) for c in existing[:3]]}")

    changes = []
    for cid, (src_name, out_stem) in PLAN.items():
        src = SRC_DIR / src_name
        if not src.is_file():
            print(f"  !! 缺图: {src}")
            continue
        blob = src.read_bytes()
        ext = sniff(blob)
        out_name = f"{out_stem}.{ext}"
        dst = AVATAR_DIR / out_name
        rel = f"数据\\头像\\{out_name}"
        if cid not in chars:
            print(f"  !! characters.json 里没有 {cid}")
            continue
        old = chars[cid].get("avatar")
        changes.append((cid, chars[cid].get("name"), src.name, ext, dst, rel, old))

    print(f"\n计划登记 {len(changes)} 个头像：")
    for cid, name, src, ext, dst, rel, old in changes:
        print(f"  {cid:<22} {name:<10} {src:<28} -> {dst.name:<40} ({ext}) 旧值={old!r}")

    if not write:
        print("\n[dry-run] 未落盘。加 --write 生效。")
        return 0

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    for cid, name, src, ext, dst, rel, old in changes:
        shutil.copy2(SRC_DIR / src, dst)
        chars[cid]["avatar"] = rel
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = CHARS.with_suffix(f".json.bak_avatar_{stamp}")
    shutil.copy2(CHARS, bak)
    CHARS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {CHARS}\n备份 {bak}\n头像目录 {AVATAR_DIR}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
