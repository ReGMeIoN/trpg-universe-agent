# -*- coding: utf-8 -*-
"""线上卡片网重叠检查：把 15 个团在**线上站**逐个打开，量卡片坐标看有没有重叠。

用途：主人部署完新版后，本机（或本小姐）用来确认"新布局真的上去了、没有错位"。
用法：
    .venv\\Scripts\\python.exe tools\\_test_live_layout.py [--base http://<服务器IP>:8080/]
"""
from __future__ import annotations

import os
import argparse
import importlib.util
import sys
import time
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=os.environ.get("TRPG_LIVE_BASE", "http://127.0.0.1:8080/"))
    a = ap.parse_args()
    BASE = a.base if a.base.endswith("/") else a.base + "/"

    drv = m.build_driver(1440, 900)
    bad_total = 0
    try:
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.get(BASE + "?r=" + str(int(time.time())))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return !!(window.NET && (window.NET.groups||[]).length)"):
                break
            time.sleep(0.3)
        time.sleep(6)
        groups = drv.execute_script("return (window.NET.groups||[]).map(function(g){return g.name;})")
        print("线上团数:", len(groups))
        for g in groups:
            drv.get(BASE + "?r=%d#/g/%s" % (int(time.time() * 1000), g))
            end = time.time() + 25
            while time.time() < end:
                if drv.execute_script("return document.querySelectorAll('#cards .card').length>0"):
                    break
                time.sleep(0.25)
            time.sleep(0.8)
            got = drv.execute_script("""
              var o = [];
              document.querySelectorAll('#cards .card').forEach(function (el) {
                o.push([parseFloat(el.style.left) || 0, parseFloat(el.style.top) || 0, el.dataset.id]);
              });
              var cs = getComputedStyle(document.documentElement);
              return { cards: o,
                       cw: parseFloat(cs.getPropertyValue('--card-w')) || 120,
                       chh: parseFloat(cs.getPropertyValue('--card-h')) || 180 };
            """)
            cw, chh, cards = got["cw"], got["chh"], got["cards"]
            dup = []
            for i in range(len(cards)):
                for j in range(i + 1, len(cards)):
                    if abs(cards[i][0] - cards[j][0]) < cw - 1 and abs(cards[i][1] - cards[j][1]) < chh - 1:
                        dup.append((cards[i][2], cards[j][2]))
            bad_total += len(dup)
            print("  %-28s %3d 张  卡 %gx%g  重叠 %d %s"
                  % (g[:28], len(cards), cw, chh, len(dup), dup[:2] if dup else ""))
        print("\n线上总重叠对数:", bad_total)
        return 1 if bad_total else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
