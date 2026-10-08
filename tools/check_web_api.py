# -*- coding: utf-8 -*-
"""Web API 冒烟: 逐个 GET 端点验证(只读, 不触发任何任务)。"""
import json
import sys

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
fails = []


def get(path: str):
    r = requests.get(B + path, timeout=45)
    mark = "OK  " if r.status_code == 200 else "FAIL"
    print(f"[{mark}] GET {path} -> {r.status_code}")
    if r.status_code != 200:
        fails.append(path)
        return None
    return r


w = get("/api/workspace").json()
print(f"       root={w['root']}  生产库={w['is_production']}  可写={w['writable']}  v{w['version']}")

s = get("/api/status").json()
print(f"       数据量={s['counts']}")
print(f"       LLM routes={s['llm']['routes']}")
print(f"       providers={ {k: v['model'] for k, v in s['llm']['providers'].items()} }")
print(f"       key 是否就绪={ {k: v['has_key'] for k, v in s['llm']['providers'].items()} }")
print(f"       数据卫生(脏 groups 值)={s['data_hygiene']['dirty_group_values']}")

g = get("/api/groups").json()
print(f"       团数={len(g)}")
for row in g[:6]:
    print(f"         {row['group']:<26} 段={row['segments']:>2} 角色={row['characters']:>3} "
          f"提炼={row['extracts']:>2} 补丁={row['has_patch']} 报告={row['has_report']} 待确认={row['pending']}")

j = get("/api/jobs").json()
print(f"       任务数={len(j)}  最新={j[0]['kind']}/{j[0]['status']} ({j[0]['id']})" if j else "       无任务")

if j:
    lg = get(f"/api/jobs/{j[0]['id']}/log?tail=3")
    if lg:
        tail = lg.json()["log"].splitlines()[-1:] or [""]
        print(f"       日志末行: {tail[0][:70]}")

p = get("/api/products").json()
print(f"       产物数={len(p)}  例: {[x['name'] for x in p[:4]]}")

grp = "无敌巨鲨大战奈亚拉托提普"
rv = get(f"/api/review/{grp}").json()
print(f"       待确认项={len(rv['items'])}  裁决文件={rv['decisions_file']}")
if rv["items"]:
    print(f"       首条: {rv['items'][0]['summary'][:60]}")

rp = get(f"/api/reports/{grp}?kind=pending").json()
print(f"       待确认报告 {len(rp['markdown'])} 字")
rr = get(f"/api/reports/{grp}?kind=report").json()
print(f"       入库报告 {len(rr['markdown'])} 字")

pa = get(f"/api/patches/{grp}").json()
print(f"       补丁: 角色{len(pa.get('characters') or [])} 更新{len(pa.get('character_updates') or [])} "
      f"关系{len(pa.get('relations') or [])} 待确认{len(pa.get('pending') or [])}")

sg = get(f"/api/segments/{grp}").json()
print(f"       段索引: {sg['count']} 段 / {sg['total_lines']} 行")

ex = get(f"/api/extract/{grp}/1").json()
print(f"       段1 提炼 {len(ex['markdown'])} 字")

# 路径越界必须被拒
r = requests.get(B + "/api/product", params={"path": "../../../windows/win.ini"}, timeout=20)
print(f"[{'OK  ' if r.status_code == 400 else 'FAIL'}] 路径越界防护 -> {r.status_code}")
if r.status_code != 400:
    fails.append("path-traversal")

print()
print("全部通过" if not fails else f"{len(fails)} 个失败: {fails}")
sys.exit(1 if fails else 0)
