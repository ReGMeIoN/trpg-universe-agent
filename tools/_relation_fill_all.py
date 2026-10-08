# -*- coding: utf-8 -*-
"""批量补齐「关系边偏少」的团：抽关系 → 并补丁 → 影子预演 → 入库 → 重出关系图。

背景：`extract` 抽关系的口径天然偏小，多个团的关系图只剩「一圈孤零零的头像 + 几根线」。
两团（魔法少女6 / 阴阳差事录）已手工验证过整条链路，本文件把它批量跑完。

材料来源自动选择：有 `<团>_剧情编年史.md` 就用编年史，否则退化为 `characters.json` 的
身份/备注/事件纪要（见 `_extract_relations.build_events_material`）。

用法:
    python tools/_relation_fill_all.py                 # 自动挑「有孤立角色」的团，dry-run
    python tools/_relation_fill_all.py --write         # 真跑（抽+并+入库+重出图）
    python tools/_relation_fill_all.py --group "X" --write
    python tools/_relation_fill_all.py --write --skip-shadow   # 跳过影子预演（默认会预演第一个新补丁团）
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.store import run_store  # noqa: E402
from trpg_agent.visualize import run_visualize  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

import _extract_relations as EX  # noqa: E402
import _merge_relations as MG  # noqa: E402

WS_PATH = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS_PATH / "\u6570\u636e"                            # 数据
SHADOW = WS_PATH / ".trpg" / "shadow_ws"

# 已经单独补过、只剩「转写没点名」的那一个孤儿的团 —— 别再喂一遍 LLM（会全是重复边）
DONE = {
    "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6",   # 魔法少女育成计划 6
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08",  # 阴阳差事录 超自然怪谈
}


def stats() -> list[tuple[str, int, int, int]]:
    import json
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    by_g: dict[str, set[str]] = {}
    for c in chars:
        for g in (c.get("groups") or []):
            by_g.setdefault(g, set()).add(c["id"])
    out = []
    for g, ids in by_g.items():
        inner = [r for r in rels if r.get("from") in ids and r.get("to") in ids]
        deg: dict[str, int] = {i: 0 for i in ids}
        for r in inner:
            deg[r["from"]] = deg.get(r["from"], 0) + 1
            deg[r["to"]] = deg.get(r["to"], 0) + 1
        iso = sum(1 for i in ids if deg[i] == 0)
        out.append((g, len(ids), len(inner), iso))
    return sorted(out, key=lambda t: (-t[3], t[2] / max(1, t[1])))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    write = "--write" in argv
    skip_shadow = "--skip-shadow" in argv
    only = argv[argv.index("--group") + 1] if "--group" in argv else None

    rows = stats()
    todo = [(g, n, e, i) for g, n, e, i in rows
            if (g == only if only else (i > 0 and g not in DONE))]
    if not todo:
        print("没有需要补的团（孤立角色全为 0）")
        return 0

    print(f"{'团':<30}{'节点':>5}{'边':>5}{'边/节点':>9}{'孤立':>5}")
    print("-" * 56)
    for g, n, e, i in todo:
        print(f"{g:<30}{n:>5}{e:>5}{e / max(1, n):>9.2f}{i:>5}")
    if not write:
        print("\n(dry-run; 加 --write 真跑)")
        return 0

    cfg = load_config(ROOT / "config.yaml")
    ws = Workspace.from_config(cfg)          # 生产库（config 里的 root）
    sh_cfg = load_config(ROOT / "config.yaml", str(SHADOW))   # 影子库：root 指向 shadow_ws

    # ① 抽关系
    print("\n" + "=" * 60 + "\n① 从材料抽关系\n" + "=" * 60)
    extracted = []
    for g, *_ in todo:
        try:
            r = EX.run(g)
        except Exception as e:  # noqa: BLE001
            print(f"!! [{g}] 抽取异常: {type(e).__name__}: {e}")
            r = {"group": g, "ok": False, "reason": f"{type(e).__name__}: {e}"}
        extracted.append(r)

    # ② 合并进补丁
    print("\n" + "=" * 60 + "\n② 合并进补丁\n" + "=" * 60)
    merged = []
    for r in extracted:
        if not r.get("ok"):
            merged.append({"group": r["group"], "ok": False})
            continue
        merged.append(MG.merge(r["group"], write=True))

    # ③ 影子预演：**新建补丁**这条路径之前没跑过，至少预演一个团
    new_patch = [m for m in merged if m.get("ok") and m.get("created")]
    if new_patch and not skip_shadow:
        g = new_patch[0]["group"]
        print("\n" + "=" * 60 + f"\n③ 影子预演（新建补丁路径，拿 [{g}] 试）\n" + "=" * 60)
        import subprocess
        subprocess.run([sys.executable, str(Path(__file__).parent / "_shadow_sync.py"), "--apply"],
                       check=False)
        run_store(Workspace.from_config(sh_cfg), sh_cfg, group=g, apply=True, allow_production=False)

    # ④ 入库生产库
    print("\n" + "=" * 60 + "\n④ 入库生产库\n" + "=" * 60)
    for m in merged:
        if not m.get("ok"):
            continue
        g = m["group"]
        try:
            run_store(ws, cfg, group=g, apply=True, allow_production=True)
        except Exception as e:  # noqa: BLE001
            print(f"!! [{g}] 入库失败: {type(e).__name__}: {e}")

    # ⑤ 重出关系图 + 关系网 md
    print("\n" + "=" * 60 + "\n⑤ 重出关系图 / 关系网 md\n" + "=" * 60)
    for m in merged:
        if not m.get("ok"):
            continue
        try:
            run_visualize(ws, cfg, group=m["group"])
        except Exception as e:  # noqa: BLE001
            print(f"!! [{m['group']}] visualize 失败: {type(e).__name__}: {e}")

    # ⑥ 收尾对比
    print("\n" + "=" * 60 + "\n⑥ 前后对比\n" + "=" * 60)
    before = {g: (n, e, i) for g, n, e, i in rows}
    print(f"{'团':<30}{'边(前→后)':>16}{'孤立(前→后)':>16}")
    print("-" * 64)
    for g, n, e, i in stats():
        if g not in before or g not in {m['group'] for m in merged if m.get('ok')}:
            continue
        bn, be, bi = before[g]
        print(f"{g:<30}{be:>7} → {e:<6}{bi:>7} → {i:<6}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
