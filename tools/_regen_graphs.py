# -*- coding: utf-8 -*-
"""按「现有产出里有哪些团」重出全部关系图 + 关系网 md（一次性维护工具）。

为什么不直接用 `visualize --all`：那个会**给没有角色的团也出 0 节点空图**
（`tools\\check_html.py` 会把空图判 FAIL），而且**不会**重出 `<团>_关系网.md`
（那段代码在 `if group:` 里）。这里就照产出目录里已有的图来跑，跑完不留垃圾。

用法:
    python tools/_regen_graphs.py            # 干跑，列出会重出哪些
    python tools/_regen_graphs.py --write
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.visualize import run_visualize  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    cfg = load_config(ROOT / "config.yaml")
    ws = Workspace.from_config(cfg)
    groups = sorted(p.name[: -len("_\u5173\u7cfb\u56fe.html")]      # _关系图.html
                    for p in ws.output.glob("*_\u5173\u7cfb\u56fe.html"))
    # 跳过已停用的旧命名（`伪人杀` 之于 `卧槽是伪人群·伪人杀`）——旧文件仍在磁盘，按项目口径不删，
    # 但也别再拿旧团名重出（那样只会得到一张 0 节点空图）。
    prefix = "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7"          # 卧槽是伪人群·
    legacy = [g for g in groups if (prefix + g) in groups]
    groups = [g for g in groups if g not in legacy]
    if legacy:
        print(f"跳过 {len(legacy)} 个已停用的旧命名：{'、'.join(legacy)}")
    print(f"产出里现有 {len(groups)} 张关系图：")
    for g in groups:
        print(f"  {g}")
    if "--write" not in sys.argv:
        print("\n(dry-run; 加 --write 重出)")
        return 0
    for g in groups:
        try:
            run_visualize(ws, cfg, group=g)      # 同时重出该团的关系网 md
        except Exception as e:  # noqa: BLE001
            print(f"!! [{g}] 失败: {type(e).__name__}: {e}")
    print(f"\n完成：{len(groups)} 张关系图 + 对应关系网 md 已重出")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
