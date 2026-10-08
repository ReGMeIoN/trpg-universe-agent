# -*- coding: utf-8 -*-
"""自检：BGM 文件名 → 情绪分类（纯 ASCII 输出，避开 PS 控制台编码干扰）。"""
import os
import sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_site import _mood_of  # noqa: E402

CASES = [
    ("_selftest_title.wav", "title"),
    ("01-epic_battle.mp3", "epic"),
    ("3_dark.mp3", "dark"),
    ("epic_final.mp3", "epic"),
    ("final.mp3", "final"),
    ("sad_03.mp3", "sad"),
    ("whatever.mp3", "calm"),
    ("\u5b81\u9759_\u65c5\u9014.mp3", "calm"),      # 宁静_旅途
    ("\u53f2\u8bd7_battle.mp3", "epic"),            # 史诗_battle
    ("\u7ec8\u7ae0_final.mp3", "final"),            # 终章_final
    ("\u5e7d\u6697_\u6050\u6016.mp3", "dark"),      # 幽暗_恐怖
    ("\u6807\u9898\u66f2 title.mp3", "title"),      # 主题曲 title
    ("\u60b2\u6006_\u79bb\u522b.mp3", "sad"),       # 悲怆_离别
]
bad = 0
for name, want in CASES:
    got = _mood_of(name)
    flag = "ok " if got == want else "BAD"
    if got != want:
        bad += 1
    print(f"{flag} {name!r:34} -> {got:6} (want {want})")
print(f"\n{len(CASES)-bad}/{len(CASES)} passed")
sys.exit(1 if bad else 0)
