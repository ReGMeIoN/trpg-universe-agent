# -*- coding: utf-8 -*-
"""把 5 名 PC 的**角色卡内立绘**登记为站点头像（严格用卡里的原图，不做重画）。

背景：2026-10-04 主人要求「PC 的立绘要严格使用角色卡里的立绘」——
卡里抽出什么就用什么（不换成 NAI 生成图）。

抽取逻辑复用 `_extract_sheet_images.py`：
    · .docx → zip 里的 word/media/*
    · .doc  → OLE 流里扫 JPEG/PNG 完整块
两张以上时按**像素面积**排序，第 1 张通常就是主立绘（`--list` 可先看清单）。

用法:
    .venv\\Scripts\\python.exe tools\\_apply_card_portraits.py --list
    .venv\\Scripts\\python.exe tools\\_apply_card_portraits.py --apply [--idx N]
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import time
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _doc_text import Ole  # noqa: E402
from _extract_sheet_images import _jpeg_size, _png_size, find_images  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
CARD_DIR = WS / "素材" / "圣剑英雄谭"
AVATAR_DIR = WS / "数据" / "头像"

# 角色名 -> 卡文件名
PC_CARDS = {
    "八重樱": "圣剑英雄传烟雾1.doc",
    "莉亚·岩心": "莉亚·岩心.docx",
    "妮娜·可可": "妮娜可可.doc",
    "飒飒米": "飒飒米.doc",
    "流星亚什": "流星亚什.doc",
}


def extract(p: Path) -> list[tuple[str, bytes, int, int]]:
    """返回 [(ext, bytes, w, h)]，按像素面积降序（第 1 张通常就是主立绘）。

    注意：`find_images()` 返回 4 元组，而 docx 的 word/media 里可能出现
    非图片类型（emf/wmf 等）→ 这里统一成 4 元组，避免 sort 时下标越界。
    """
    found: list[tuple[str, bytes, int, int]] = []
    if p.suffix.lower() == ".docx":
        try:
            with zipfile.ZipFile(p) as z:
                for name in z.namelist():
                    if not name.startswith("word/media/"):
                        continue
                    blob = z.read(name)
                    ext = Path(name).suffix.lstrip(".").lower()
                    w = h = 0
                    if ext in ("jpg", "jpeg"):
                        ext, w, h = "jpg", *_jpeg_size(blob)
                    elif ext == "png":
                        w, h = _png_size(blob)
                    else:
                        continue                      # 非 jpg/png 一律跳过
                    found.append((ext, blob, int(w), int(h)))
        except (zipfile.BadZipFile, OSError) as e:
            print(f"  !! {p.name}: {e}")
    else:
        try:
            ole = Ole(p.read_bytes())
        except Exception as e:  # noqa: BLE001
            print(f"  !! {p.name}: OLE 解析失败 {e}")
            return []
        for st in ole.entries:
            if st["type"] != 2:
                continue
            blob = ole.stream(st["name"])
            if blob:
                found += find_images(blob)
    return sorted(found, key=lambda t: t[2] * t[3], reverse=True)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--idx", type=int, default=1, help="用卡里第几张（按面积降序，默认 1）")
    a = ap.parse_args()

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    plan: dict[str, str] = {}

    for name, card in PC_CARDS.items():
        p = CARD_DIR / card
        if not p.is_file():
            print(f"  !! 缺卡：{card}")
            continue
        imgs = extract(p)
        if a.list:
            print(f"\n{name}  ←  {card}  共 {len(imgs)} 张")
            for i, (ext, blob, w, h) in enumerate(imgs, 1):
                print(f"   {i}. {ext:<4} {len(blob)//1024:>6} KB  {w}x{h}")
            continue
        if not imgs:
            print(f"  -- {name}: 卡内 0 张图（保持现状）")
            continue
        if a.idx > len(imgs):
            print(f"  -- {name}: 卡内只有 {len(imgs)} 张，跳过")
            continue
        ext, blob, w, h = imgs[a.idx - 1]
        out = AVATAR_DIR / f"圣剑英雄谭_{name}_card{a.idx}.{ext}"
        rel = f"数据\\头像\\{out.name}"
        plan[name] = rel
        print(f"  OK {name}: 第{a.idx}张 {ext} {w}x{h} ({len(blob)//1024} KB) -> {out.name}")
        if a.apply:
            out.write_bytes(blob)

    if a.list:
        return 0
    if not plan:
        print("\n没有可登记的卡内立绘。")
        return 1

    cfile = WS / "数据" / "characters.json"
    doc = json.loads(cfile.read_text(encoding="utf-8"))
    n = 0
    for c in doc.get("characters", []):
        rel = plan.get(c.get("name"))
        if rel and c.get("avatar") != rel:
            print(f"    {c['name']}: {c.get('avatar')}  ->  {rel}")
            c["avatar"] = rel
            n += 1
    if a.apply and n:
        bak = cfile.with_name(f"{cfile.name}.bak_card_{time.strftime('%Y%m%d_%H%M%S')}")
        shutil.copyfile(cfile, bak)
        cfile.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\ncharacters.json 更新 {n} 个角色（备份 {bak.name}）")
    elif not a.apply:
        print(f"\n[dry-run] 将更新 {n} 个角色；加 --apply 真正写入")
    return 0


if __name__ == "__main__":
    sys.exit(main())
