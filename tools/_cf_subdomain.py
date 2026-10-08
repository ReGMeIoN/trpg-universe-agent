# -*- coding: utf-8 -*-
"""注册 Cloudflare workers.dev 子域名（wrangler deploy 的前置条件）。

从 wrangler 的 default.toml 读 oauth_token，直接调 API。
用法:
    .venv\\Scripts\\python.exe tools\\_cf_subdomain.py            # 列出候选并试注册首位
    .venv\\Scripts\\python.exe tools\\_cf_subdomain.py --name xxx  # 指定名字
    .venv\\Scripts\\python.exe tools\\_cf_subdomain.py --status    # 只查现状
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import requests

TOML = Path.home() / "AppData" / "Roaming" / "xdg.config" / ".wrangler" / "config" / "default.toml"
ACCT = os.environ.get("CF_ACCOUNT_ID", "")   # 从环境变量读, 不要硬编码
CANDIDATES = ["sjt-chronicle", "swordheroes", "sjt-universe", "huanying-sjt"]


def token() -> str:
    txt = TOML.read_text(encoding="utf-8")
    m = re.search(r'^oauth_token = "([^"]+)"', txt, re.M)
    if not m:
        raise SystemExit(f"读不到 oauth_token（{TOML}）")
    return m.group(1)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--name")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()

    if not ACCT:
        raise SystemExit("未设 CF_ACCOUNT_ID 环境变量")
    tok = token()
    h = {"Authorization": "Bearer " + tok}
    base = f"https://api.cloudflare.com/client/v4/accounts/{ACCT}/workers/subdomain"

    r = requests.get(base, headers=h, timeout=30)
    print(f"GET  {r.status_code}  {r.text[:300]}")
    if a.status:
        return 0

    names = [a.name] if a.name else CANDIDATES
    for n in names:
        print(f"\nPUT  subdomain={n} ...")
        try:
            r = requests.put(base, headers={**h, "Content-Type": "application/json"},
                             data=json.dumps({"subdomain": n}), timeout=60)
        except Exception as e:  # noqa: BLE001
            print(f"  EXC {type(e).__name__}: {e}")
            continue
        print(f"  {r.status_code}  {r.text[:400]}")
        if r.status_code == 200 and r.json().get("success"):
            print(f"\n✅ 子域名已注册：{r.json()['result'].get('subdomain')}.workers.dev")
            return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
