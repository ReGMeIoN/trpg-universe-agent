# -*- coding: utf-8 -*-
"""成品图水印/角标兜底：检测图片底部是否存在"文字状"高对比条带并裁掉。

NAI 即便 NEG 里压了 text/watermark，仍会偶发在右下角渲染一行英文水印
（实测某些批次会带）。这个工具做确定性兜底，不依赖再出图。

判据（只看底部区域）：某一行像素的"暗底亮字/亮底暗字"边缘密度显著高于画面中位数，
且该行以下基本无内容 → 判为水印带，从该行上方裁掉。

用法:
    # 只报告，不改文件
    .venv\\Scripts\\python.exe tools\\_trim_watermark.py "D:\\path\\dir"
    # 就地裁切（先写 .bak 同目录备份）
    .venv\\Scripts\\python.exe tools\\_trim_watermark.py "D:\\path\\dir" --apply
    # 调阈值 / 只处理部分文件
    .venv\\Scripts\\python.exe tools\\_trim_watermark.py "dir" --ratio 2.2 --apply
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image

EXTS = {".png", ".jpg", ".jpeg", ".webp"}


def edge_profile(gray: np.ndarray) -> np.ndarray:
    """按行统计水平方向的强边缘数量（文字会让某几行边缘密集）。"""
    d = np.abs(np.diff(gray.astype(np.int16), axis=1))
    return (d > 40).sum(axis=1)


def find_watermark_band(img: Image.Image, ratio: float = 2.2,
                        bottom_frac: float = 0.16) -> int | None:
    """返回建议裁切后的高度（None = 没检测到水印）。"""
    gray = np.array(img.convert("L"))
    h, w = gray.shape
    start = int(h * (1 - bottom_frac))
    prof = edge_profile(gray)
    body = prof[:start] if start > 0 else prof
    med = float(np.median(body)) or 1.0
    # 底部区域里边缘最密的那一行
    zone = prof[start:]
    if zone.size == 0:
        return None
    peak_rel = int(np.argmax(zone))
    peak = zone[peak_rel]
    if peak < med * ratio or peak < w * 0.02:
        return None
    cut = start + peak_rel
    # 水印只占很窄一条（<= bottom_frac），且裁掉后画面仍足够高
    if cut < h * 0.75:
        return None
    return cut


def process(p: Path, ratio: float, apply: bool, pad: int = 6) -> tuple[bool, str]:
    try:
        img = Image.open(p)
        img.load()
    except Exception as e:  # noqa: BLE001
        return False, f"读不了 {type(e).__name__}: {e}"
    cut = find_watermark_band(img, ratio)
    if cut is None:
        return False, "干净"
    new_h = max(1, cut - pad)
    if not apply:
        return True, f"检测到水印带（{img.height} → 建议 {new_h}）"
    if not (p.with_suffix(p.suffix + ".bak")).exists():
        shutil.copyfile(p, p.with_suffix(p.suffix + ".bak"))
    out = img.crop((0, 0, img.width, new_h))
    fmt = "PNG" if p.suffix.lower() == ".png" else ("WEBP" if p.suffix.lower() == ".webp" else "JPEG")
    out.save(p, fmt, quality=95) if fmt != "PNG" else out.save(p, fmt)
    return True, f"已裁切 {img.height} → {new_h}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("target", help="目录或单个图片")
    ap.add_argument("--apply", action="store_true", help="就地裁切（默认只报告）")
    ap.add_argument("--ratio", type=float, default=2.2, help="边缘密度倍数阈值（默认 2.2）")
    a = ap.parse_args()
    t = Path(a.target)
    files = [t] if t.is_file() else sorted(p for p in t.rglob("*") if p.suffix.lower() in EXTS)
    hit = 0
    for p in files:
        flag, msg = process(p, a.ratio, a.apply)
        mark = "✂" if flag else "  "
        print(f"{mark} {p.name:<26} {msg}")
        hit += int(flag)
    print(f"\n{hit}/{len(files)} 张检测到水印带" + ("（已处理）" if a.apply else "（未改动，加 --apply 才裁）"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
