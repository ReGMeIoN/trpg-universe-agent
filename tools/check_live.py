# -*- coding: utf-8 -*-
"""上线后自检：确认公开 URL 能取到站点、数据完整、挑图页正常。

国内网络直连 workers.dev 通常超时，所以默认走本机代理；直连可传 --proxy ""。

用法:
    .venv\\Scripts\\python.exe tools\\check_live.py
    .venv\\Scripts\\python.exe tools\\check_live.py --proxy ""            # 直连
    .venv\\Scripts\\python.exe tools\\check_live.py --url https://其他域名
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

DEFAULT = "https://sjt-chronicle.sjt-chronicle.workers.dev"
# Cloudflare WAF 会拦非浏览器 User-Agent（实测 403）→ 抽查必须带浏览器 UA
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")


def opener(proxy: str):
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))   # 显式直连，忽略环境变量
    return urllib.request.build_opener(*handlers)


def get(url: str, op, timeout: int = 25) -> tuple[int, bytes, dict]:
    req = urllib.request.Request(urllib.parse.quote(url, safe=":/?&=#%"),
                                headers={"User-Agent": UA})
    with op.open(req, timeout=timeout) as r:
        return r.status, r.read(), dict(r.headers)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT)
    ap.add_argument("--proxy", default="http://127.0.0.1:7897",
                    help="HTTP 代理；传空串表示直连")
    a = ap.parse_args()
    base = a.url.rstrip("/")
    op = opener(a.proxy)
    print(f"检查 {base}" + (f"  via {a.proxy}" if a.proxy else "  (直连)"))
    bad = 0

    for p in ["/", "/index.html", "/asset-pick.html", "/data/bundle.js", "/style.css", "/app.js"]:
        try:
            code, body, hd = get(base + p, op)
            ct = hd.get("Content-Type", "")
            print(f"  {code}  {len(body):>10,} B  {ct[:26]:<26} {p}")
            if code != 200:
                bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {p}  {type(e).__name__}: {e}")
            bad += 1

    try:
        _, body, _ = get(base + "/data/bundle.js", op)
        raw = body.decode("utf-8")
        d = json.loads(raw[raw.index("{"):raw.rindex(";")])
        st = d["meta"]["stats"]
        print(f"\n  线上数据: pages={len(d['pages'])} cg={st.get('cg')} audio={st.get('clips')} "
              f"bgm={st.get('bgm')} avatars={st.get('avatars')} characters={st.get('characters')}")
        noav = [c["name"] for c in d["roster"]["characters"] if not c.get("avatar")]
        print(f"  无立绘角色: {noav if noav else '无 (OK)'}")
    except Exception as e:  # noqa: BLE001
        print(f"  !! bundle 解析失败: {type(e).__name__}: {e}")
        bad += 1

    for p in ["/assets/cg/段1_003.jpg", "/assets/avatars/圣剑英雄谭_八重樱.jpg",
              "/assets/bgm/calm.mp3", "/assets/audio/段1_003.mp3"]:
        try:
            code, body, _ = get(base + p, op)
            print(f"  {code}  {len(body):>10,} B  {p}")
            if code != 200 or len(body) < 500:
                bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {p}  {type(e).__name__}: {e}")
            bad += 1

    try:
        _, body, _ = get(base + "/asset-pick.html", op)
        c = body.decode("utf-8")
        n = len(re.findall(r'"src": "', c))
        print(f'\n  挑图页: 候选 {n} 张, 残留占位符={"__DATA__" in c}')
    except Exception as e:  # noqa: BLE001
        print(f"  !! 挑图页失败: {type(e).__name__}: {e}")
        bad += 1

    print("\n" + ("线上全部通过 (OK)" if not bad else f"有 {bad} 项异常 (FAIL)"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
