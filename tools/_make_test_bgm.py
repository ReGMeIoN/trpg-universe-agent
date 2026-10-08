# -*- coding: utf-8 -*-
"""自检用：生成一个 3 秒正弦测试音（wav），验证 BGM 通道能否被 build_site 正确归类。

用法:
    .venv\\Scripts\\python.exe tools\\_make_test_bgm.py            # 生成 素材/bgm/_selftest_title.wav
    .venv\\Scripts\\python.exe tools\\_make_test_bgm.py --clean    # 删掉测试文件与产物
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BGM = ROOT / "素材" / "bgm"
DST = BGM / "_selftest_title.wav"
SITE_BGM = ROOT / "site" / "assets" / "bgm"


def make() -> None:
    BGM.mkdir(parents=True, exist_ok=True)
    sr, sec = 44100, 3
    with wave.open(str(DST), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = bytearray()
        for i in range(sr * sec):
            t = i / sr
            v = 0.12 * math.sin(2 * math.pi * 220 * t) + 0.06 * math.sin(2 * math.pi * 330 * t)
            frames += struct.pack("<h", int(max(-1.0, min(1.0, v)) * 32000))
        w.writeframes(bytes(frames))
    print(f"wrote {DST}  ({DST.stat().st_size // 1024} KB)")


def clean() -> None:
    for p in (DST, SITE_BGM / "title.mp3", SITE_BGM / "calm.mp3"):
        if p.is_file():
            p.unlink()
            print(f"removed {p}")
    if SITE_BGM.is_dir() and not any(SITE_BGM.iterdir()):
        SITE_BGM.rmdir()
        print(f"removed empty {SITE_BGM}")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean()
    else:
        make()
