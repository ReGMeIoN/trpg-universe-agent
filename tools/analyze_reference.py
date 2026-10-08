# -*- coding: utf-8 -*-
"""从参考图里程序化提取配色/构图线索(替代"看图": 我的模型不支持图像输入)。

输出: 整体主色 + 按横向分带(发/脸/上身/下身)的主色 + 明暗比例 + 画幅比例。
这些是与像素绑定的客观事实, 可直接转成 NovelAI 的颜色/服装提示词。
"""
import sys
from collections import Counter
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

path = Path(sys.argv[1] if len(sys.argv) > 1 else '<工作区>/数据/头像/杰克.jpg')
img = Image.open(path).convert("RGB")
w, h = img.size
print(f"文件: {path.name}  {w}x{h}  比例 {w/h:.2f}")

small = img.resize((160, int(160 * h / w)))
px = list(small.getdata())
n = len(px)


def hexc(c):
    return "#%02x%02x%02x" % c


def bucket(c, step=32):
    return tuple(min(255, (v // step) * step + step // 2) for v in c)


def top_colors(pixels, k=6):
    cnt = Counter(bucket(p) for p in pixels)
    return [(hexc(c), round(100.0 * v / len(pixels), 1)) for c, v in cnt.most_common(k)]


def luminance(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


lum = [luminance(p) for p in px]
dark = sum(1 for x in lum if x < 60) / n
mid = sum(1 for x in lum if 60 <= x < 170) / n
light = sum(1 for x in lum if x >= 170) / n
sat = sum(1 for p in px if (max(p) - min(p)) > 45) / n

print(f"明暗: 暗(<60) {dark*100:.0f}%  中 {mid*100:.0f}%  亮(>=170) {light*100:.0f}%  彩色像素(饱和>45) {sat*100:.0f}%")
print("整体主色:", top_colors(px, 8))

print("\n--- 横向分带主色 ---")
bands = [("上 1/5(帽/发)", 0.0, 0.2), ("上 1/5~2/5(脸/眼)", 0.2, 0.4),
         ("中 2/5~3/5(胸/领)", 0.4, 0.6), ("下 3/5~4/5(身/衣)", 0.6, 0.8),
         ("底 1/5(下摆/腿)", 0.8, 1.0)]
for label, a, b in bands:
    y0, y1 = int(h * a), int(h * b)
    crop = img.crop((0, y0, w, y1)).resize((120, 40))
    pixels = list(crop.getdata())
    lums = [luminance(p) for p in pixels]
    d = sum(1 for x in lums if x < 60) / len(pixels)
    lt = sum(1 for x in lums if x >= 170) / len(pixels)
    print(f"{label:<18} 主色 {top_colors(pixels, 4)}  暗{d*100:.0f}% 亮{lt*100:.0f}%")

print("\n--- 中央纵向条(通常是人物的脸/躯干) ---")
cx0, cx1 = int(w * 0.35), int(w * 0.65)
for label, a, b in bands:
    y0, y1 = int(h * a), int(h * b)
    crop = img.crop((cx0, y0, cx1, y1)).resize((60, 40))
    pixels = list(crop.getdata())
    print(f"{label:<18} 主色 {top_colors(pixels, 4)}")
