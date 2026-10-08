# -*- coding: utf-8 -*-
"""从角色卡里抽出图片（.docx 的 word/media，.doc 的 OLE 流里扫 JPEG/PNG）。

为什么要它：`数据/头像/` 里既有的那批（形如 `<团>_<角色>__image1.png`）就是从卡里
抽出来的立绘，但有些卡没走这一步 —— 关系图因此只有问号没有头像。

用法:
    .venv\\Scripts\\python.exe tools\\_extract_sheet_images.py <卡目录> <输出目录>
"""
from __future__ import annotations

import struct
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from _doc_text import Ole  # noqa: E402

JPEG_SOI = b"\xff\xd8\xff"
PNG_SIG = b"\x89PNG\r\n\x1a\n"
PNG_END = b"IEND\xaeB`\x82"


def _png_size(b: bytes) -> tuple[int, int]:
    try:
        w, h = struct.unpack(">II", b[16:24])
        return int(w), int(h)
    except struct.error:
        return 0, 0


def _jpeg_size(b: bytes) -> tuple[int, int]:
    i = 2
    n = len(b)
    while i + 9 < n:
        if b[i] != 0xFF:
            i += 1
            continue
        marker = b[i + 1]
        if marker in (0xD8, 0xD9) or 0xD0 <= marker <= 0xD7:
            i += 2
            continue
        seg = struct.unpack(">H", b[i + 2:i + 4])[0]
        if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB,
                      0xCD, 0xCE, 0xCF):
            h, w = struct.unpack(">HH", b[i + 5:i + 9])
            return int(w), int(h)
        i += 2 + seg
    return 0, 0


def read_zip_member_nocrc(z: zipfile.ZipFile, name: str) -> bytes:
    """读 zip 成员，**跳过 CRC 校验**。

    起因：某角色的 .docx 的 `word/media/*` 在中央目录里写的是**错误的 CRC**
    （两张图都是），`z.read()` 因此抛 `BadZipFile: Bad CRC-32`，害得「知行」被判成"卡内图损坏、无立绘"。
    实测解压出来的字节是**完整的、能正常解码的** JPEG/PNG —— 坏的只是目录里的校验值，
    多半是某次重打包（网盘/转存工具）留下的。所以不该因为 CRC 不符就放弃这张图。
    """
    fp = z.open(name)
    try:
        fp._expected_crc = None  # type: ignore[attr-defined]
        return fp.read()
    finally:
        fp.close()


def find_images(data: bytes, min_bytes: int = 3000) -> list[tuple[str, bytes, int, int]]:
    """扫描 JPEG/PNG 完整数据块。返回 [(ext, bytes, w, h)]。"""
    out: list[tuple[str, bytes, int, int]] = []
    i = 0
    n = len(data)
    while i < n - 8:
        jp = data.find(JPEG_SOI, i)
        pn = data.find(PNG_SIG, i)
        cands = [(p, "jpg") for p in (jp,) if p >= 0] + [(p, "png") for p in (pn,) if p >= 0]
        if not cands:
            break
        pos, ext = min(cands)
        if ext == "jpg":
            end = data.find(b"\xff\xd9", pos + 3)
            if end < 0:
                i = pos + 3
                continue
            blob = data[pos:end + 2]
        else:
            end = data.find(PNG_END, pos + 8)
            if end < 0:
                i = pos + 8
                continue
            blob = data[pos:end + len(PNG_END)]
        i = pos + len(blob)
        if len(blob) < min_bytes:
            continue
        w, h = _jpeg_size(blob) if ext == "jpg" else _png_size(blob)
        out.append((ext, blob, w, h))
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    for p in sorted(src.iterdir()):
        if p.suffix.lower() not in (".doc", ".docx"):
            continue
        found: list[tuple[str, bytes, int, int]] = []
        if p.suffix.lower() == ".docx":
            try:
                with zipfile.ZipFile(p) as z:
                    for name in z.namelist():
                        if not name.startswith("word/media/"):
                            continue
                        try:
                            blob = z.read(name)
                        except zipfile.BadZipFile as e:
                            # CRC 写错但数据完好（见 read_zip_member_nocrc 注释）→ 绕过校验再读一次
                            print(f"  ~ {p.name}/{name}: {e} -> 绕过 CRC 校验重读")
                            blob = read_zip_member_nocrc(z, name)
                        ext = Path(name).suffix.lstrip(".").lower() or "bin"
                        w, h = (0, 0)
                        if ext in ("jpg", "jpeg"):
                            ext, w, h = "jpg", *_jpeg_size(blob)
                        elif ext == "png":
                            w, h = _png_size(blob)
                        found.append((ext, blob, w, h))
            except (zipfile.BadZipFile, OSError) as e:
                print(f"  !! {p.name}: {e}")
        else:
            try:
                ole = Ole(p.read_bytes())
            except Exception as e:  # noqa: BLE001
                print(f"  !! {p.name}: OLE 解析失败 {e}")
                continue
            for st in ole.entries:
                if st["type"] != 2:
                    continue
                blob = ole.stream(st["name"])
                if not blob:
                    continue
                found += find_images(blob)
        found.sort(key=lambda t: len(t[1]), reverse=True)
        print(f"{p.name}: 找到 {len(found)} 张")
        for idx, (ext, blob, w, h) in enumerate(found, 1):
            out = dst / f"{p.stem}__image{idx}.{ext}"
            out.write_bytes(blob)
            print(f"   {out.name:<40} {len(blob):>9} 字节  {w}x{h}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
