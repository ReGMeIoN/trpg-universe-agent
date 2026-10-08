# -*- coding: utf-8 -*-
"""Batch-extract character-sheet text + embedded images for one or more groups.

Handles .doc (OLE2), .docx and .docm (both are OOXML zips) in one pass so a group
directory can be processed in a single command.

Pure-ASCII source on purpose: PowerShell 5.1 mangles inline CJK, so group names /
paths are built from unicode escapes.

usage:
    python tools/_cards_batch.py                 # all groups below
    python tools/_cards_batch.py <group-key>     # one group
"""
from __future__ import annotations

import os
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from _doc_text import Ole, extract_docx  # noqa: E402
from _extract_sheet_images import (  # noqa: E402
    _jpeg_size,
    _png_size,
    find_images,
    read_zip_member_nocrc,
)

PROJECT = Path(__file__).resolve().parent.parent
MATERIAL = Path(os.environ.get("TRPG_WS", "workspace") / '素材')           # 素材
OUT_TEXT = PROJECT / "\u4ea7\u51fa" / "\u5361\u9762\u6b63\u6587"                 # 产出/卡面正文
OUT_IMG = PROJECT / ".trpg" / "card_images"

GROUPS: dict[str, str] = {
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08": "yin-yang",   # 阴阳差事录 超自然怪谈
    "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6": "mahou6",                  # 魔法少女育成计划 6
    "\u6f6e\u6c50\u76d1\u72f1": "tide",                                            # 潮汐监狱
}

EXTS = (".doc", ".docx", ".docm")


def extract_text(path: Path) -> tuple[str, dict]:
    if path.suffix.lower() in (".docx", ".docm"):
        return extract_docx(path)
    ole = Ole(path.read_bytes())
    # _doc_text.main() has the stream logic; reuse its reader
    from _doc_text import extract_doc  # type: ignore

    return extract_doc(path)


def run(group: str) -> int:
    src = MATERIAL / group
    if not src.is_dir():
        print(f"!! missing dir: {src}")
        return 2
    tag = GROUPS[group]
    tdir = OUT_TEXT / f"{tag}_{group}".replace(" ", "_")
    idir = OUT_IMG / f"{tag}_{group}".replace(" ", "_")
    tdir.mkdir(parents=True, exist_ok=True)
    idir.mkdir(parents=True, exist_ok=True)

    files = sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS)
    print(f"[{group}] {len(files)} cards")
    for p in files:
        try:
            text, meta = extract_text(p)
        except Exception as e:  # noqa: BLE001
            print(f"  !! {p.name}: text failed {type(e).__name__}: {e}")
            text, meta = "", {"source": "failed"}
        out = tdir / f"{p.stem}.txt"
        out.write_text(text, encoding="utf-8")
        print(f"  text  {p.name:<44} {len(text):>7} chars  ({meta.get('source')})")

        found: list[tuple[str, bytes, int, int]] = []
        if p.suffix.lower() in (".docx", ".docm"):
            try:
                with zipfile.ZipFile(p) as z:
                    for name in z.namelist():
                        if not name.startswith("word/media/"):
                            continue
                        try:
                            blob = z.read(name)
                        except zipfile.BadZipFile as e:
                            # 目录里的 CRC 写错但数据完好（阴阳差事录-牛 就是这么被误判"图损坏"的）
                            print(f"     ~ {name}: {e} -> 绕过 CRC 校验重读")
                            blob = read_zip_member_nocrc(z, name)
                        ext = Path(name).suffix.lstrip(".").lower() or "bin"
                        w, h = (0, 0)
                        if ext in ("jpg", "jpeg"):
                            ext, w, h = "jpg", *_jpeg_size(blob)
                        elif ext == "png":
                            w, h = _png_size(blob)
                        found.append((ext, blob, w, h))
            except (zipfile.BadZipFile, OSError) as e:
                print(f"     !! images: {e}")
        else:
            try:
                ole = Ole(p.read_bytes())
                for st in ole.entries:
                    if st["type"] != 2:
                        continue
                    blob = ole.stream(st["name"])
                    if blob:
                        found += find_images(blob)
            except Exception as e:  # noqa: BLE001
                print(f"     !! images: {e}")
        found.sort(key=lambda t: len(t[1]), reverse=True)
        for idx, (ext, blob, w, h) in enumerate(found, 1):
            o = idir / f"{p.stem}__image{idx}.{ext}"
            o.write_bytes(blob)
            print(f"     img {o.name:<44} {len(blob):>9} B  {w}x{h}")
    print(f"[{group}] text -> {tdir}")
    print(f"[{group}] imgs -> {idir}")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    keys = sys.argv[1:] or list(GROUPS)
    rc = 0
    for k in keys:
        rc |= run(k)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
