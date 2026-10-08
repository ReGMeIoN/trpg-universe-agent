# -*- coding: utf-8 -*-
"""轻量自检（不开浏览器）：核对站点页面能取到、数据/bundle 结构正确、候选图齐全。

用法:
    .venv\\Scripts\\python.exe tools\\check_http.py            # 需先起 http.server 8899
    .venv\\Scripts\\python.exe tools\\check_http.py --port 8899
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.request

ROOT_PATHS = ["/site/index.html", "/site/relations.html", "/site/data/bundle.js",
              "/site/assets/kv.jpg"]
IMG_PATHS = ["/site/assets/cg/段1_003.jpg", "/site/assets/avatars/杰克.jpg"]
# 挑图页刻意放在 site/ 之外（不随站点发布）；服务需挂在项目根才能取到
PICK_PATH = "/.trpg/pickpage/asset-pick.html"


def fetch(url: str) -> tuple[int, bytes]:
    # 站点素材文件名含中文（段1_003.jpg / 杰克.jpg）→ 必须先做百分号编码，
    # 否则 urllib 会在 http.client 里拿 ascii 编码而抛 UnicodeEncodeError。
    safe = urllib.parse.quote(url, safe=":/?&=#%")
    with urllib.request.urlopen(safe, timeout=10) as r:
        return r.status, r.read()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8899)
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    base = f"http://{a.host}:{a.port}"
    bad = 0

    for p in ROOT_PATHS + IMG_PATHS:
        try:
            code, body = fetch(base + p)
            print(f"  {code}  {len(body):>9,} B  {p}")
            if code != 200 or not body:
                bad += 1
        except Exception as e:  # noqa: BLE001
            print(f"  ERR  {p}  {type(e).__name__}: {e}")
            bad += 1

    # bundle 结构
    try:
        _, body = fetch(base + "/site/data/bundle.js")
        raw = body.decode("utf-8")
        data = json.loads(raw[raw.index("{"):raw.rindex(";")])
        st = data["meta"]["stats"]
        print(f"\n  bundle: pages={len(data['pages'])} cg={st.get('cg')} audio={st.get('clips')} "
              f"bgm={st.get('bgm')} characters={st.get('characters')} relations={st.get('relations')}")
        print(f"  段情绪: " + ", ".join(
            f"{s['tag']}={s.get('mood')}" for s in data["story"]["segments"]))
    except Exception as e:  # noqa: BLE001
        print(f"  !! bundle 解析失败: {type(e).__name__}: {e}")
        bad += 1

    # 挑图页内容
    try:
        _, body = fetch(base + PICK_PATH)
        c = body.decode("utf-8")
        srcs = re.findall(r'"src": "([^"]+)"', c)
        groups = re.findall(r'"title": "([^"]+)"', c)
        print(f"\n  挑图页: 组={groups}  候选图={len(srcs)} 张")
        print(f"  残留占位符 __DATA__={'__DATA__' in c}  __PICKED__={'__PICKED__' in c}")
        miss = 0
        for s in srcs[:6]:
            try:
                code, b = fetch(base + "/.trpg/pickpage/cg-cand/" + urllib.parse.quote(s))
                if code != 200 or not b:
                    miss += 1
            except Exception:  # noqa: BLE001
                miss += 1
        print(f"  抽查前 6 张候选图，取不到 {miss} 张")
        if "__DATA__" in c or miss:
            bad += 1
    except Exception as e:  # noqa: BLE001
        print(f"  !! 挑图页校验失败: {type(e).__name__}: {e}")
        bad += 1

    print("\n" + ("全部通过 ✅" if not bad else f"有 {bad} 项失败 ❌"))
    return 1 if bad else 0


if __name__ == "__main__":
    import urllib.parse  # noqa: E402  (仅此处需要)
    sys.exit(main())
