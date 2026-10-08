# -*- coding: utf-8 -*-
"""参考图区域定位: 找出"脸在哪、红色在哪、黑色在哪、背景什么色"。

不依赖"看图", 只输出像素事实, 供编写立绘提示词时对照。
用法: python tools/analyze_layout.py <图片> [输出目录]
"""
import sys
from pathlib import Path

from PIL import Image

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

W = 96  # 分析用的降采样宽度


def classify(c):
    r, g, b = c
    mx, mn = max(c), min(c)
    if mx - mn <= 28:                      # 低饱和
        v = 0.2126 * r + 0.7152 * g + 0.0722 * b
        if v < 55:
            return "黑"
        if v < 150:
            return "灰"
        return "白"
    if r > g and r > b:
        if r > 150 and g > 90 and b > 70 and (r - b) < 90:
            return "肤色"                   # 偏亮橙粉
        if r > 120 and g < 90:
            return "红"                     # 纯红/绯红
        return "深红棕"                     # 暗红/棕
    if g >= r and g >= b:
        return "绿"
    return "蓝"


def analyze(img: Image.Image, tag: str, out_dir: Path | None = None) -> None:
    w, h = img.size
    scale = W / w
    small = img.resize((W, max(1, int(h * scale))))
    sw, sh = small.size
    px = small.load()

    counts: dict[str, int] = {}
    boxes: dict[str, list[int]] = {}
    for y in range(sh):
        for x in range(sw):
            k = classify(px[x, y])
            counts[k] = counts.get(k, 0) + 1
            b = boxes.setdefault(k, [x, y, x, y])
            b[0], b[1] = min(b[0], x), min(b[1], y)
            b[2], b[3] = max(b[2], x), max(b[3], y)

    total = sw * sh
    print(f"\n===== {tag}  {w}x{h} (比例 {w/h:.2f}) =====")
    print("四角背景色:", [("#%02x%02x%02x" % px[cx, cy]) for cx, cy in
                        ((0, 0), (sw - 1, 0), (0, sh - 1), (sw - 1, sh - 1))])
    print(f"{'类别':<8}{'占比':>7}   位置(宽% , 高%)")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1]):
        x0, y0, x1, y1 = boxes[k]
        print(f"{k:<8}{100.0*v/total:>6.1f}%   x {100*x0/sw:>3.0f}-{100*x1/sw:>3.0f}%  y {100*y0/sh:>3.0f}-{100*y1/sh:>3.0f}%")

    # 脸部定位(肤色最大连通区域近似: 用肤色像素的中位框)
    skin = [(x, y) for y in range(sh) for x in range(sw) if classify(px[x, y]) == "肤色"]
    if skin:
        xs = sorted(p[0] for p in skin)
        ys = sorted(p[1] for p in skin)
        med_x, med_y = xs[len(xs) // 2], ys[len(ys) // 2]
        print(f"肤色像素 {len(skin)} 个, 中位位置: 宽 {100*med_x/sw:.0f}% 高 {100*med_y/sh:.0f}%"
              f"  (提示: 高 <35% 通常是头部/脸)")

    # 竖直三分带的类别分布
    print("竖直分带:")
    for label, a, b in (("上 1/3", 0, sh // 3), ("中 1/3", sh // 3, 2 * sh // 3), ("下 1/3", 2 * sh // 3, sh)):
        band: dict[str, int] = {}
        for y in range(a, b):
            for x in range(sw):
                k = classify(px[x, y])
                band[k] = band.get(k, 0) + 1
        tot = sum(band.values())
        top3 = ", ".join(f"{k} {100*v/tot:.0f}%" for k, v in sorted(band.items(), key=lambda kv: -kv[1])[:3])
        print(f"  {label}: {top3}")


src = Path(sys.argv[1])
out_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else None
analyze(Image.open(src).convert("RGB"), src.name, out_dir)

# 可选: 从视频抽帧(拿另一角度/姿态的配色)
if len(sys.argv) > 3:
    import av

    vid = Path(sys.argv[3])
    container = av.open(str(vid))
    stream = container.streams.video[0]
    dur = float(stream.duration * stream.time_base) if stream.duration else 0
    print(f"\n视频 {vid.name}: {stream.width}x{stream.height}, {dur:.1f}s, {stream.frames or '?'} 帧")
    want = [dur * 0.25, dur * 0.5, dur * 0.75] if dur else [0]
    got = 0
    for i, frame in enumerate(container.decode(stream)):
        t = float(frame.pts * stream.time_base) if frame.pts is not None else i / 25.0
        if want and t >= want[0]:
            want.pop(0)
            arr = frame.to_image()
            tag = f"视频帧 {t:.1f}s"
            analyze(arr, tag)
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                arr.save(out_dir / f"jack_frame_{int(t)}s.png")
                print(f"  -> 已存 {out_dir / f'jack_frame_{int(t)}s.png'}")
            got += 1
            if not want:
                break
    container.close()
    if not got:
        print("  (未取到帧)")
