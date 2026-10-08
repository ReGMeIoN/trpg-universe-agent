# -*- coding: utf-8 -*-
"""前端托管冒烟: 首页/静态资源/API 共存/兜底 404。"""
import re
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
fails = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"[{'OK  ' if cond else 'FAIL'}] {label} {extra}")
    if not cond:
        fails.append(label)


r = requests.get(B + "/", timeout=20)
check("GET / 返回 200", r.status_code == 200, f"({r.status_code})")
check("是 Vue 页面(含 #app 挂载点)", '<div id="app">' in r.text)

m_js = re.search(r'src="(/assets/[^"]+)"', r.text)
m_css = re.search(r'href="(/assets/[^"]+)"', r.text)
if m_js:
    js = requests.get(B + m_js.group(1), timeout=30)
    check(f"GET {m_js.group(1)}", js.status_code == 200 and len(js.content) > 10000,
          f"({js.status_code}, {len(js.content)//1024} KB)")
else:
    check("首页含 JS 资源引用", False)
if m_css:
    css = requests.get(B + m_css.group(1), timeout=30)
    check(f"GET {m_css.group(1)}", css.status_code == 200, f"({css.status_code}, {len(css.content)} B)")

check("GET /docs 未被兜底路由吃掉", requests.get(B + "/docs", timeout=20).status_code == 200)
check("GET /openapi.json", requests.get(B + "/openapi.json", timeout=20).status_code == 200)
check("GET /api/groups", requests.get(B + "/api/groups", timeout=30).status_code == 200)
check("GET /api/status", requests.get(B + "/api/status", timeout=30).status_code == 200)
check("GET /nope 返回 404(兜底)", requests.get(B + "/nope", timeout=20).status_code == 404)

print()
print("全部通过" if not fails else f"{len(fails)} 个失败: {fails}")
sys.exit(1 if fails else 0)
