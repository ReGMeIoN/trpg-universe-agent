# -*- coding: utf-8 -*-
"""One-off: list a zip archive's entries (handles GBK/UTF-8 filename flags).

Usage:
    .venv\\Scripts\\python.exe tools\\_inspect_zip.py "D:\\path\\a.zip"
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    if len(sys.argv) < 2:
        print("usage: _inspect_zip.py <zip path>")
        return 1
    p = Path(sys.argv[1])
    print(f"zip: {p}  size={p.stat().st_size}")
    with zipfile.ZipFile(p) as z:
        infos = z.infolist()
        print(f"entries: {len(infos)}")
        total = 0
        for i in infos:
            name = i.filename
            if not (i.flag_bits & 0x800):
                try:
                    name = i.filename.encode("cp437").decode("gbk")
                except (UnicodeEncodeError, UnicodeDecodeError):
                    pass
            kind = "DIR " if i.is_dir() else "FILE"
            total += i.file_size
            print(f"  {kind} {i.file_size:>10}  {name}")
        print(f"uncompressed total: {total} bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
