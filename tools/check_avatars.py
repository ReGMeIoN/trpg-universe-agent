# -*- coding: utf-8 -*-
"""核对「5 名圣剑使立绘落地」链路：picks → 数据\\头像 → characters.json → site/assets。

用法:
    .venv\\Scripts\\python.exe tools\\check_avatars.py
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_site as B  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
TARGETS = ["八重樱", "飒飒米", "流星亚什", "妮娜·可可", "莉亚·岩心"]


def main() -> int:
    picks = B.load_picks()
    # 直接读文件，省得绕 Workspace
    cfile = WS / "数据" / "characters.json"
    doc = json.loads(cfile.read_text(encoding="utf-8"))
    by_name = {c.get("name"): c for c in doc.get("characters", [])}
    roster = json.loads((B.SITE / "data" / "roster.json").read_text(encoding="utf-8"))

    print(f"{'角色':<12}{'picked':<8}{'avatar 字段':<44}{'数据侧文件':<10}{'站点侧文件':<10}")
    print("-" * 92)
    bad = 0
    for name in TARGETS:
        pick = picks.get(name, "-")
        av = (by_name.get(name) or {}).get("avatar") or ""
        fname = Path(av).name if av else ""
        in_data = (WS / av).is_file() if av else False
        site_name = Path(av).stem + ".jpg" if av else ""
        in_site = (B.SITE / "assets" / "avatars" / site_name).is_file() if site_name else False
        flag = "" if (pick != "-" and in_data and in_site) else "  <== 有问题"
        if flag:
            bad += 1
        print(f"{name:<12}{pick:<8}{fname:<44}{str(in_data):<10}{str(in_site):<10}{flag}")

    print("\nroster.json（站点真正用的）:")
    for c in roster["characters"]:
        if c["name"] in TARGETS:
            print(f"  {c['name']:<12} avatar={c.get('avatar') or '(空)'}")
    noav = [c["name"] for c in roster["characters"] if not c.get("avatar")]
    print(f"\n无立绘角色: {noav if noav else '无 (OK)'}")
    print("全部通过 ✅" if not bad else f"有 {bad} 项不一致 ❌")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
