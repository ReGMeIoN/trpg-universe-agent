# -*- coding: utf-8 -*-
"""多团 + 多视口的卡片重叠快测（本地 8788 服务）。

要看的是「换完布局之后，所有团的卡片网到底有没有重叠」——
不变量测试保证的是**数据层面**不会重合，这里保证**真实渲染**也不重合。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
CW, CHh = 120, 180

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def overlap(js_result, cw, chh):
    bad = []
    for i in range(len(js_result)):
        for j in range(i + 1, len(js_result)):
            a, b = js_result[i], js_result[j]
            if abs(a[0] - b[0]) < cw - 1 and abs(a[1] - b[1]) < chh - 1:
                bad.append((a[2], b[2]))
    return bad


def run(drv, groups):
    for g in groups:
        drv.get(BASE + "?r=%d#/g/%s" % (int(time.time() * 1000), g))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return document.querySelectorAll('#cards .card').length>0"):
                break
            time.sleep(0.25)
        time.sleep(1.0)
        got = drv.execute_script("""
          var o = [];
          document.querySelectorAll('#cards .card').forEach(function (el) {
            o.push([parseFloat(el.style.left)||0, parseFloat(el.style.top)||0, el.dataset.id]);
          });
          var cs = getComputedStyle(document.documentElement);
          return { cards: o,
                   cw: parseFloat(cs.getPropertyValue('--card-w')) || 120,
                   chh: parseFloat(cs.getPropertyValue('--card-h')) || 180 };
        """)
        cw = got["cw"] or CW
        chh = got["chh"] or CHh
        bad = overlap(got["cards"], cw, chh)
        chk(f"卡片网零重叠：{g}", not bad,
            f"{len(got['cards'])} 张 · 卡 {cw:g}×{chh:g}" + (f" / {bad[:2]}" if bad else ""))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    drv = m.build_driver(1500, 950)
    try:
        drv.set_page_load_timeout(60)
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        drv.get(BASE + "?r=" + str(int(time.time() * 1000)))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return !!(window.NET && (window.NET.groups||[]).length)"):
                break
            time.sleep(0.25)
        time.sleep(5)
        groups = drv.execute_script("return (window.NET.groups||[]).map(g => g.name)")
        print(f"共 {len(groups)} 个团")
        run(drv, groups)

        print("=== 手机竖屏（375×667）再跑一遍 ===")
        drv.set_window_size(375, 667)
        time.sleep(1.5)
        run(drv, groups[:6])
        drv.set_window_size(1500, 950)
        print(f"\n结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
        return 1 if FAIL else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
