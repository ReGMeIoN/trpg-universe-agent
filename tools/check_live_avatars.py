# -*- coding: utf-8 -*-
"""线上抽查 5 名圣剑使的新立绘是否真的发布成功（含中文名 URL 编码）。

用法:
    .venv\\Scripts\\python.exe tools\\check_live_avatars.py
    .venv\\Scripts\\python.exe tools\\check_live_avatars.py --proxy ""
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
import urllib.request

BASE = "https://sjt-chronicle.sjt-chronicle.workers.dev"
NAMES = ["八重樱", "飒飒米", "流星亚什", "妮娜·可可", "莉亚·岩心"]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--proxy", default="http://127.0.0.1:7897")
    ap.add_argument("--base", default=BASE)
    a = ap.parse_args()
    if a.proxy:
        op = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": a.proxy, "https": a.proxy}))
    else:
        op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    bad = 0
    # Cloudflare WAF 会拦非浏览器 UA（返回 403）→ 用浏览器 UA
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 " \
         "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    for n in NAMES:
        rel = f"/assets/avatars/圣剑英雄谭_{n}.jpg"
        url = a.base.rstrip("/") + urllib.parse.quote(rel, safe="/:")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with op.open(req, timeout=25) as r:
                b = r.read()
            print(f"  {r.status}  {len(b):>9,} B  {rel}")
            if r.status != 200 or len(b) < 5000:
                bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {rel}  {type(e).__name__}: {e}")
            bad += 1
    print("\n" + ("线上 5 张新立绘全部就位 ✅" if not bad else f"有 {bad} 张取不到 ❌"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
