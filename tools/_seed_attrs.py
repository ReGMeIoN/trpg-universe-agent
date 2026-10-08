# -*- coding: utf-8 -*-
"""给生产库的角色补 `attrs`（结构化属性标签）的**初始值**。

背景：主人要「一个角色能打上所有属性（性别/种族/职业/出处/创作者…）＋ 单独的 tag 查询页」。
本脚本**只补已有事实的重新表达，零编造**：

    出处    ← groups
    创作者  ← played_by
    类型    ← 由 tags 推出的 kind（KP > 跨团 > BOSS > PC > NPC）

其余维度（性别 / 种族 / 职业 / 阵营 / 年龄 …）留给编辑者在站点上通过提案箱补。

数据形状（与 `tags` 分开，互不干扰）：
    "tags":  ["NPC", "BOSS"]                      ← 系统分类，建站/着色用它
    "attrs": {"出处": ["阴阳差事录 超自然怪谈"],
              "创作者": "pd",
              "类型": "BOSS",
              "性别": "女",                        ← 人工补的，值可以是字符串
              "职业": ["作家", "侦探"]}             ← 也可以是多值数组

幂等：只补**缺失**的维度，**不覆盖**已存在的值（人工填过的优先）。

用法:
    python tools\\_seed_attrs.py            # 预览
    python tools\\_seed_attrs.py --apply    # 落盘（备份 + 复验）
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据


def kind_of(c: dict) -> str:
    """与 build_net_site.py 的 kind_of 保持一致（优先级 KP > 跨团 > BOSS > PC > NPC）。"""
    tags = c.get("tags") or []
    if "KP" in tags:
        return "KP"
    if "\u8de8\u56e2" in tags:        # 跨团
        return "\u8de8\u56e2"
    if "BOSS" in tags:
        return "BOSS"
    if "PC" in tags:
        return "PC"
    return "NPC"


def seed_for(c: dict) -> dict:
    out: dict = {}
    groups = c.get("groups") or []
    if groups:
        out["\u51fa\u5904"] = list(groups)          # 出处
    pb = c.get("played_by") or ""
    if pb:
        out["\u521b\u4f5c\u8005"] = pb              # 创作者
    out["\u7c7b\u578b"] = kind_of(c)                # 类型
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    cf = DATA / "characters.json"
    doc = json.loads(cf.read_text(encoding="utf-8"))
    chars = doc["characters"]

    n_new, n_have, n_skip = 0, 0, 0
    changes: list[str] = []
    for c in chars:
        if not isinstance(c, dict):
            continue
        cur = c.get("attrs")
        if not isinstance(cur, dict):
            cur = {}
        seed = seed_for(c)
        added = {k: v for k, v in seed.items() if k not in cur or cur.get(k) in (None, "", [])}
        if not added and cur:
            n_have += 1
            continue
        if not added:
            n_skip += 1
            continue
        n_new += 1
        merged = dict(cur)
        merged.update(added)
        c["attrs"] = merged
        changes.append(f"  {c.get('id'):<26} {c.get('name') or '':<12} + {'、'.join(added.keys())}")

    print(f"角色总数 {len(chars)}")
    print(f"  本次补 attrs: {n_new} · 已有完整: {n_have} · 无需处理: {n_skip}")
    if changes:
        print("\n前 15 条：")
        for line in changes[:15]:
            print(line)
        if len(changes) > 15:
            print(f"  …（其余 {len(changes) - 15} 条同理）")

    # 汇总维度
    dims: dict[str, int] = {}
    for c in chars:
        for k in (c.get("attrs") or {}):
            dims[k] = dims.get(k, 0) + 1
    print("\n维度覆盖：")
    for k, v in sorted(dims.items(), key=lambda kv: -kv[1]):
        print(f"  {k:<10} {v} 个角色")

    if not args.apply:
        print("\n(dry-run；加 --apply 落盘)")
        return 0

    bdir = DATA / f"_bak_attrs_{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cf, bdir / cf.name)
    cf.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")

    chk = json.loads(cf.read_text(encoding="utf-8"))["characters"]
    with_attrs = sum(1 for c in chk if isinstance(c.get("attrs"), dict) and c["attrs"])
    print(f"\n已写入（备份 {bdir}）")
    print(f"  复验：角色 {len(chk)} · 带 attrs 的 {with_attrs}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
