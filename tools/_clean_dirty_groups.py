# -*- coding: utf-8 -*-
"""清 `groups` 里的脏值（主人 2026-10-05 点头）。

两类脏值：
  1. **id 类**：`bot_luoerxidi` / `cross_jieke` / `g2_aisilie` / `js_jinx` / `mg_aisilie` /
     `mg3_aisilie` / `mg4_chudaidechuang` / `mg4_cixiaogui` —— 这些是**节点 id**，被误写进团名列表，
     会让关系图/KB 包/统计凭空多出"团"（`data_utils.is_real_group` 只滤标签、不滤 id 形态，所以漏网）。
  2. **标签类**：`跨团` / `跨团常驻` / `待确认` / `KP` / `PC` / `NPC`（守卫的 RESERVED 集合，
     留着虽然不影响展示，但属于脏数据；跨团性由 `tags` 表达）。

保留：`config.ingest.known_groups` 里的规范团名 + 库里现存的真实团名。

用法:
    python tools/_clean_dirty_groups.py            # dry-run
    python tools/_clean_dirty_groups.py --apply
"""
from __future__ import annotations

import os
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config            # noqa: E402
from trpg_agent.data_utils import is_real_group      # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e" / "characters.json"
ID_LIKE = re.compile(r"^[a-z][a-z0-9]*_[a-z0-9_]+$")   # bot_luoerxidi / mg4_cixiaogui ...


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    cfg = load_config(ROOT / "config.yaml")
    known = {str(g) for g in cfg.ingest.known_groups}

    doc = json.loads(DATA.read_text(encoding="utf-8"))
    chars = doc.get("characters") or []

    # 真实团名 = 已知团名 ∪ 非 id 非标签的现存值
    real: set[str] = set(known)
    for c in chars:
        for g in c.get("groups") or []:
            s = str(g)
            if is_real_group(s) and not ID_LIKE.match(s):
                real.add(s)

    changes: list[tuple[str, str, str]] = []   # (id, 删掉的值, 类别)
    for c in chars:
        kept = []
        for g in c.get("groups") or []:
            s = str(g)
            if s in real:
                kept.append(g)
                continue
            kind = "id类" if ID_LIKE.match(s) else ("标签类" if not is_real_group(s) else "未知团名")
            changes.append((str(c.get("id")), s, kind))
        c["_kept_groups"] = kept

    print(f"角色 {len(chars)} · 真实团名 {len(real)} 个")
    if not changes:
        print("没有脏值，无需清理。")
        return 0
    by_kind: dict[str, int] = {}
    for cid, val, kind in changes:
        by_kind[kind] = by_kind.get(kind, 0) + 1
    print(f"待清理 {len(changes)} 处：" + " · ".join(f"{k} {v}" for k, v in sorted(by_kind.items())))
    for cid, val, kind in changes:
        print(f"  {cid:<26} 删 groups 里的 {val!r}  [{kind}]")

    if not apply:
        for c in chars:
            c.pop("_kept_groups", None)
        print("\n(dry-run; 加 --apply 写入)")
        return 0

    bak = DATA.with_name(DATA.name + f".bak_groupclean_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(DATA, bak)
    for c in chars:
        c["groups"] = c.pop("_kept_groups")
    DATA.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")

    chk = json.loads(DATA.read_text(encoding="utf-8"))
    left = []
    for c in chk["characters"]:
        for g in c.get("groups") or []:
            s = str(g)
            if s not in real:
                left.append((c.get("id"), s))
    print(f"复验: 剩余脏值 {len(left)} 处")
    # 团名统计
    groups: dict[str, int] = {}
    for c in chk["characters"]:
        for g in c.get("groups") or []:
            groups[str(g)] = groups.get(str(g), 0) + 1
    print(f"清理后团数 {len(groups)}:")
    for g, n in sorted(groups.items(), key=lambda kv: -kv[1]):
        print(f"  {g:<28} {n}")
    return 0 if not left else 1


if __name__ == "__main__":
    raise SystemExit(main())
