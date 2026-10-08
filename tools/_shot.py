# -*- coding: utf-8 -*-
"""给展示站截图（Selenium + 本机 Edge 无头），用来肉眼核对 UI 与动画后的静态帧。

用法:
    # 单页
    .venv\\Scripts\\python.exe tools\\_shot.py --hash "#/" --out .tmp\\shots\\home.png
    # 整页长图
    .venv\\Scripts\\python.exe tools\\_shot.py --hash "#/roster" --full --out x.png
    # 点一下再拍（验证翻页/卡页动画）：--click 选择器 --after 毫秒
    .venv\\Scripts\\python.exe tools\\_shot.py --hash "#/book/0" --click "[data-go=next]" --after 320 --out turn.png
    # 跑一段 JS 再拍
    .venv\\Scripts\\python.exe tools\\_shot.py --hash "#/book/0" --exec "location.hash='#/book/40'" --after 500 --out cc.png
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.edge.options import Options
from selenium.webdriver.edge.service import Service

ROOT = Path(__file__).resolve().parent.parent
# 沙箱下 ~/.cache/selenium 不可写 → 用工作区里已下好的 driver（与 Edge 154.0.4258.53 同版）
_DRV = sorted((ROOT / "msedgedriver").glob("*/msedgedriver.exe"))


def build_driver(w: int, h: int):
    o = Options()
    o.add_argument("--headless=new")
    o.add_argument("--disable-gpu")
    o.add_argument("--hide-scrollbars")
    o.add_argument("--no-first-run")
    o.add_argument("--no-default-browser-check")
    # 必须给独立 profile，否则会被用户正在运行的 Edge 接管 → DevTools 连接被踢
    o.add_argument(f"--user-data-dir={ROOT / '.tmp' / 'edge-shot-profile'}")
    o.add_argument("--force-device-scale-factor=1")
    o.add_experimental_option("excludeSwitches", ["enable-logging"])
    return webdriver.Edge(options=o, service=Service(str(_DRV[-1]))) if _DRV else webdriver.Edge(options=o)


def shot(url, out: Path, w, h, full, wait, delay, click, exe, after) -> int:
    drv = build_driver(w, h)
    try:
        # 无头默认 prefers-reduced-motion:reduce → CSS 入场动画被跳过、元素停在 opacity:0。
        # 强制 no-preference，保证截到的是最终态。
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia", {
            "features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        drv.set_window_size(w, h)
        drv.get(url)
        time.sleep(wait / 1000)

        if click:
            els = drv.find_elements("css selector", click)
            if not els:
                print(f"  !! 找不到 {click}")
            else:
                els[0].click()
                time.sleep(after / 1000)
        if exe:
            drv.execute_script(exe)
            time.sleep(after / 1000)

        if full:
            total = drv.execute_script("return document.documentElement.scrollHeight")
            print(f"  page height = {total}px")
            drv.set_window_size(w, min(total + 40, 20000))
            time.sleep(delay / 1000)

        out.parent.mkdir(parents=True, exist_ok=True)
        ok = drv.save_screenshot(str(out))
        print(f"  -> {out}  ({out.stat().st_size // 1024} KB)  ok={ok}")
        return 0
    finally:
        drv.quit()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8899/index.html")
    ap.add_argument("--hash", default="#/")
    ap.add_argument("--out", default=r".tmp\shots\shot.png")
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--anim", action="store_true", help="保留入场动画（不加 noanim=1）")
    ap.add_argument("--wait", type=int, default=1400, help="首屏等待 ms")
    ap.add_argument("--delay", type=int, default=2600, help="全页展开后再等 ms")
    ap.add_argument("--click", default=None, help="点击选择器")
    ap.add_argument("--exec", default=None, help="执行的 JS")
    ap.add_argument("--after", type=int, default=400, help="click/exec 之后再等 ms")
    a = ap.parse_args()
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    sep = "&" if "?" in a.base else "?"
    url = a.base + ("" if a.anim else sep + "noanim=1") + a.hash
    print(f"shot {url}" + (f"  click={a.click}" if a.click else "") + (f"  exec={a.exec}" if a.exec else ""))
    return shot(url, ROOT / a.out, a.width, a.height, a.full, a.wait, a.delay, a.click, a.exec, a.after)


if __name__ == "__main__":
    sys.exit(main())
