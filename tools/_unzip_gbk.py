# -*- coding: utf-8 -*-
"""One-off: unzip an archive, fixing legacy GBK filenames (no UTF-8 flag bit).

Usage:
    .venv\\Scripts\\python.exe tools\\_unzip_gbk.py <zip> <dest dir>
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path


def fixed_name(info: zipfile.ZipInfo) -> str:
    if info.flag_bits & 0x800:  # UTF-8 flag set
        return info.filename
    try:
        return info.filename.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    if len(sys.argv) < 3:
        print("usage: _unzip_gbk.py <zip> <dest dir>")
        return 1
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    dst.mkdir(parents=True, exist_ok=True)
    count = 0
    with zipfile.ZipFile(src) as z:
        for info in z.infolist():
            name = fixed_name(info)
            target = dst / name
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with z.open(info) as fh, open(target, "wb") as out:
                out.write(fh.read())
            count += 1
            print(f"OK  {target}  ({info.file_size} bytes)")
    print(f"extracted {count} files -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
