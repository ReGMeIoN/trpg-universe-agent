# -*- coding: utf-8 -*-
"""把关系草稿（`_extract_relations.py` 的产物）合并进某团的入库补丁，去重后供 store 消费。

去重键与 `store` 一致：`(from, to, type)` 三元组。

**补丁不存在时会自动新建**（只含 `group` + `relations`）——
`魔法少女救赎线` / `魔法少女木柜子` 这类"当年没走 extract、库里只有角色"的团就靠它补关系。

用法:
    .venv\\Scripts\\python.exe tools\\_merge_relations.py --group "魔法少女木柜子"            # dry-run
    .venv\\Scripts\\python.exe tools\\_merge_relations.py --group "魔法少女木柜子" --write
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
PATCHES = WS / ".trpg" / "patches"
DATA = WS / "\u6570\u636e"                              # 数据


def merge(group: str, write: bool = False, quiet: bool = False) -> dict:
    patch_path = PATCHES / f"{group}_patch.json"
    draft_path = PATCHES / f"{group}_relations_draft.json"
    if not draft_path.is_file():
        if not quiet:
            print(f"!! 缺关系草稿: {draft_path}")
        return {"group": group, "ok": False, "reason": "no draft"}

    created = not patch_path.is_file()
    patch = ({"group": group, "relations": []} if created
             else json.loads(patch_path.read_text(encoding="utf-8")))
    patch.setdefault("group", group)
    draft = json.loads(draft_path.read_text(encoding="utf-8"))
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    name = {c["id"]: c.get("name") or c["id"] for c in chars}
    all_ids = {c["id"] for c in chars}

    have = patch.setdefault("relations", [])
    before = len(have)
    seen = {(r.get("from"), r.get("to"), r.get("type")) for r in have}
    added, skipped, bad, pending = [], [], [], []
    for r in draft.get("relations") or []:
        if r.get("from") not in all_ids or r.get("to") not in all_ids:
            bad.append(r)
            continue
        k = (r.get("from"), r.get("to"), r.get("type"))
        if k in seen:
            skipped.append(r)
            continue
        if not r.get("confirmed", True):
            pending.append(r)
        seen.add(k)
        have.append(r)
        added.append(r)

    tag = "（新建补丁）" if created else ""
    if not quiet:
        print(f"[{group}] 补丁关系 {before} → {len(have)} 条{tag}"
              f"（新增 {len(added)} / 重复 {len(skipped)} / 端点非法 {len(bad)}"
              f" / 其中待确认 {len(pending)} 会被 store 降级）")
        for r in bad:
            print(f"  !! 端点不在库: {r.get('from')} -> {r.get('to')}")

    if not write:
        if not quiet:
            print("  [dry-run] 未落盘（加 --write）")
        return {"group": group, "ok": True, "added": len(added), "total": len(have),
                "pending": len(pending), "bad": len(bad), "created": created, "written": False}

    PATCHES.mkdir(parents=True, exist_ok=True)
    if not created:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(patch_path, patch_path.with_suffix(f".json.bak_rel_{stamp}"))
    patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    if not quiet:
        print(f"  已写入 {patch_path.name}")
    return {"group": group, "ok": True, "added": len(added), "total": len(have),
            "pending": len(pending), "bad": len(bad), "created": created, "written": True}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    if "--group" not in argv:
        print(__doc__)
        return 1
    r = merge(argv[argv.index("--group") + 1], write="--write" in argv)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
