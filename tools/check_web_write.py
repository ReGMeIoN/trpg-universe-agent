# -*- coding: utf-8 -*-
"""Web 写路径冒烟: 启动任务 / 裁决保存 / 裁决应用(需在安全副本工作区上运行)。"""
import json
import sys
import time
from pathlib import Path

import requests

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

B = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8766"
WS = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".tmp/web_ws")
GROUP = sys.argv[3] if len(sys.argv) > 3 else "星海列车"
fails = []


def check(label: str, cond: bool, extra: str = "") -> None:
    print(f"[{'OK  ' if cond else 'FAIL'}] {label} {extra}")
    if not cond:
        fails.append(label)


print(f"== 目标 {B} · 工作区 {WS} · 团 {GROUP} ==")

# 1) 启动一个安全任务(housekeep: 只写产出/收尾清单.md)
r = requests.post(B + "/api/jobs", json={"step": "housekeep"}, timeout=30)
check("POST /api/jobs (housekeep)", r.status_code == 200, f"({r.status_code})")
if r.status_code != 200:
    print(r.text[:300])
    sys.exit(1)
rec = r.json()
jid = rec["id"]
print(f"       job={jid} pid={rec['pid']} argv={rec['argv'][3:]}")

# 2) 轮询到结束
status = "running"
for _ in range(30):
    time.sleep(2)
    jobs = requests.get(B + "/api/jobs", timeout=30).json()
    me = next((x for x in jobs if x["id"] == jid), None)
    if me and me["status"] != "running":
        status = me["status"]
        break
check("任务完成(非 running)", status in ("finished", "unknown"), f"status={status}")
lg = requests.get(B + f"/api/jobs/{jid}/log?tail=200", timeout=30).json()["log"]
check("任务有日志", len(lg) > 0, f"({len(lg)} 字)")
print("       日志末行:", (lg.splitlines() or [""])[-1][:80])
check("产出文件已生成", (WS / "产出" / "收尾清单.md").is_file())

# 3) 裁决: 读 -> 保存 -> 应用
rv = requests.get(B + f"/api/review/{GROUP}", timeout=30).json()
check("读到待确认项", len(rv["items"]) > 0, f"({len(rv['items'])} 项)")
if rv["items"]:
    first = rv["items"][0]
    print(f"       首条: ({first['target']}[{first['index']}]) {first['summary'][:50]}")
    body = {"decisions": [
        {"target": first["target"], "index": first["index"], "action": "accept", "note": "web 冒烟"},
        {"action": "merge", "canonical": "老鸦", "variant": "老鸭二代"},
    ]}
    r2 = requests.post(B + f"/api/review/{GROUP}", json=body, timeout=30)
    check("POST 保存裁决", r2.status_code == 200 and r2.json()["saved"] == 2,
          f"({r2.status_code}, {r2.text[:80]})")

    patch_before = json.loads((WS / ".trpg" / "patches" / f"{GROUP}_patch.json").read_text(encoding="utf-8"))
    tgt, idx = first["target"], first["index"]
    before_conf = (patch_before.get(tgt) or [{}])[idx].get("confirmed")

    r3 = requests.post(B + f"/api/review/{GROUP}/apply", timeout=60)
    check("POST 应用裁决", r3.status_code == 200, f"({r3.status_code}, {r3.text[:120]})")
    if r3.status_code == 200:
        res = r3.json()
        print(f"       补丁改动 {len(res['applied'])} 项 / 称呼归一 {len(res['naming_merges'])} 项")
        patch_after = json.loads((WS / ".trpg" / "patches" / f"{GROUP}_patch.json").read_text(encoding="utf-8"))
        after_conf = (patch_after.get(tgt) or [{}])[idx].get("confirmed")
        check("裁决写回了补丁(confirmed 变化)", before_conf != after_conf or after_conf is True,
              f"{before_conf} -> {after_conf}")
        naming = json.loads((WS / ".trpg" / "canon" / "naming.json").read_text(encoding="utf-8"))
        aliases = [a for e in naming.get("canonical", []) for a in (e.get("aliases") or [])]
        check("称呼表已并入新变体", "老鸭二代" in aliases)

print()
print("全部通过" if not fails else f"{len(fails)} 个失败: {fails}")
sys.exit(1 if fails else 0)
