# -*- coding: utf-8 -*-
"""把「小夜丸 / 莱娜」补进生产库（2026-10-06）。

背景：这两张是**魔法少女五 · 周年庆**的角色卡（卡面自称"8 位勇者的周年庆"），
      但全文检索 `魔法少女五_转写.txt`（702KB）**零命中** —— 卡在、人没上场。
      主人 2026-10-06 拍板：**入库并上图（接受孤岛）**。

做法（幂等，可重复跑）：
  1. 建两个节点（tags 带 `待确认`，note 写明"卡在、转写未出场"）；
  2. 建一条关系：小夜丸 ↔ 莱娜（卡面原文：相依为命 / 对立出身但结成两人小队）；
  3. 同步写进 `.trpg/patches/魔法少女五_patch.json`（否则下次 store --apply 会打回来）；
  4. 全程备份 `数据/*.bak_mg5card_*`。

用法：
    .venv\\Scripts\\python.exe tools\\_add_mg5_cards.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_add_mg5_cards.py --apply
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DATA = WS / "\u6570\u636e"
PATCH = WS / ".trpg" / "patches" / ("\u9b54\u6cd5\u5c11\u5973\u4e94_patch.json")
GROUP = "\u9b54\u6cd5\u5c11\u5973\u4e94"          # 魔法少女五

NODES = [
    {
        "id": "mg5_xiaoyewan",
        "name": "\u5c0f\u591c\u4e38",                      # 小夜丸
        "aliases": ["\u4e71\u7834\u5c0f\u591c\u4e38"],        # 乱破小夜丸
        "identity": "\u9b54\u6cd5\u5c11\u5973\u00b7\u5468\u5e74\u5e86\u52c7\u8005\uff08\u539f\u6cbb\u5b89\u6218\u8b66\u961f\u6210\u5458\uff0c\u65a9\u5200\u4f7f\uff09",
        "note": (
            "\u3010\u672c\u56e2\u9996\u6b21\u51fa\u73b0\u3011\u9b54\u6cd5\u5c11\u5973\u4e94\u30fb\u5468\u5e74\u5e86\u201c8 \u4f4d\u52c7\u8005\u201d\u4e4b\u4e00"
            "\uff08\u5361\u9762\u81ea\u79f0\uff09\u3002\u539f\u4e3a**\u6cbb\u5b89\u6218\u8b66\u961f**\u6210\u5458\u2014\u2014\u8ffd\u7f09\u83b1\u5a1c\u9014\u4e2d\u53d1\u73b0\u961f\u5185"
            "\u9ed1\u6697\u771f\u76f8\uff0c\u9762\u5bf9\u5931\u53bb\u62b5\u6297\u80fd\u529b\u7684\u83b1\u5a1c\u9009\u62e9\u653e\u5f03\u8eab\u4efd\uff0c\u4e0e\u5979\u4e00\u8d77\u5bf9\u6297"
            "\u201c\u64cd\u7eb5\u65f6\u7a7a\u7684\u9ed1\u6697\u9762\u201d\uff0c\u540e\u88ab\u6293\u5230\u5f02\u4e16\u754c\u3002\u4e0e\u83b1\u5a1c\u76f8\u5bf9\uff0c\u5e78\u8fd0\u503c\u9ad8\u3001"
            "\u4f5c\u4e8b\u4e00\u677f\u4e00\u773c\u3002\u80fd\u529b\uff1a\u7a7a\u95f4\u6495\u88c2\uff08\u4f69\u5200\u80fd\u4e00\u5b9a\u7a0b\u5ea6\u6495\u88c2\u7a7a\u95f4\uff09\u00b7"
            "\u7d27\u6025\u64a4\u79bb\uff08\u5e26\u4e00\u540d\u5176\u4ed6\u89d2\u8272\u540c\u65f6\u8fdb\u201c\u8d5b\u535a\u7a7a\u95f4\u201d\uff09\u00b7\u8ffd\u7f09\u9886\u57df\uff08\u4f7f\u76ee\u6807"
            "\u5468\u56f4\u65f6\u95f4\u6d41\u901f\u53d8\u6162\uff09\u3002\u9053\u5177\uff1a\u5c0f\u591c\u4e38\u7684\u4f69\u5200\u00b7\u624b\u91cc\u5251\u00b7\u5927\u9003\u6740\u5b9a\u4f4d\u5668"
            "\uff08\u7ed1\u5b9a\u8bc5\u5492\uff09\u3002"
            "\u26a0\ufe0f **\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\u5165\u5e93\u5e76\u4e0a\u56fe**\uff1b\u4f46\u5168\u6587\u68c0\u7d22\u300a\u9b54\u6cd5\u5c11\u5973\u4e94\u300b"
            "\u8f6c\u5199\uff08702KB\uff09**\u96f6\u547d\u4e2d**\uff08\u5361\u5728\u3001\u4eba\u672a\u51fa\u573a\uff09\u2192 \u72ec\u7acb\u5efa\u8282\u70b9\u3001\u4e0d\u63d0\u4f9b\u5267\u60c5\u4e8b\u4ef6\u3002"
        ),
        "tags": ["\u8de8\u56e2", "\u5f85\u786e\u8ba4"],     # 跨团 / 待确认
    },
    {
        "id": "mg5_laina",
        "name": "\u83b1\u5a1c",                            # 莱娜
        "aliases": [],
        "identity": "\u9b54\u6cd5\u5c11\u5973\u00b7\u5468\u5e74\u5e86\u52c7\u8005\uff08\u9ed1\u5ba2 / \u5927\u76d7\uff0c\u4e24\u4eba\u5c0f\u961f\u7684\u667a\u529b\u62c5\u5f53\uff09",
        "note": (
            "\u3010\u672c\u56e2\u9996\u6b21\u51fa\u73b0\u3011\u9b54\u6cd5\u5c11\u5973\u4e94\u30fb\u5468\u5e74\u5e86\u201c8 \u4f4d\u52c7\u8005\u201d\u4e4b\u4e00"
            "\uff08\u5361\u9762\u81ea\u79f0\uff09\u3002\u4e0e\u5c0f\u591c\u4e38\u76f8\u4f9d\u4e3a\u547d\u7684\u5c11\u5973\uff0c\u7a7f\u81ea\u5236\u8bbe\u5907\uff1b\u8fd0\u6c14\u5f88\u5dee\u3002"
            "\u539f\u4e16\u754c\u91cc\u662f\u81ed\u540d\u662d\u8457\u7684\u5927\u76d7\u3001\u51fa\u8272\u7684\u9ed1\u5ba2\uff0c\u6709\u4e00\u8f86\u53ef\u968f\u65f6\u53ec\u5524\u7684\u6469\u6258\u8f66\uff0c"
            "\u4ee5 E.M.P \u624b\u6bb5\u6218\u6597\uff1b\u5e73\u65e5\u6709\u70b9\u5929\u7136\u5446\uff0c\u6d89\u53ca\u76d7\u7a83\u65f6\u53d8\u5f97\u5341\u5206\u72e1\u8bc8\u3002\u80fd\u529b\uff1a"
            "\u73b0\u5b9e\u5e72\u6270\uff08\u9ed1\u5ba2\u80fd\u529b\u5f71\u54cd\u73b0\u5b9e\u7269\u54c1\uff0c\u751a\u81f3\u975e\u7535\u5b50\u8bbe\u5907\uff09\u00b7\u8d5b\u535a\u7a7a\u95f4"
            "\uff08\u968f\u610f\u8fdb\u51fa\u3001\u53ec\u5524\u5b58\u653e\u7269\uff0c\u80fd\u89c2\u5bdf\u5e76\u7be1\u6539\u4fe1\u606f\u7f51\u7edc\uff09\u3002\u9053\u5177\uff1a"
            "E.M.P \u624b\u96f7\u00b7\u6218\u672f\u62a4\u76ee\u955c\u00b7\u5f88\u5e05\u7684\u6469\u6258\u8f66\uff08\u85cf\u5728\u8d5b\u535a\u7a7a\u95f4\uff09\u00b7\u5927\u9003\u6740\u5b9a\u4f4d\u5668"
            "\uff08\u7ed1\u5b9a\u8bc5\u5492\uff09\u3002"
            "\u26a0\ufe0f **\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\u5165\u5e93\u5e76\u4e0a\u56fe**\uff1b\u540c\u6837\u5728\u8f6c\u5199\u91cc**\u96f6\u547d\u4e2d**\u3002"
        ),
        "tags": ["\u8de8\u56e2", "\u5f85\u786e\u8ba4"],
    },
]

REL = {
    "from": "mg5_xiaoyewan",
    "to": "mg5_laina",
    "type": "\u53cb\u8c0a",                             # 友谊（受控词表；卡面：相依为命）
    "strength": "\u5f3a",
    "event": ("\u9b54\u6cd5\u5c11\u5973\u4e94\uff08\u5468\u5e74\u5e86\uff09\uff1a\u5361\u9762\u539f\u6587\u2014\u2014\u5c0f\u591c\u4e38\u8ffd\u7f09\u83b1\u5a1c\u65f6\u53d1\u73b0\u6cbb\u5b89\u6218\u8b66\u961f"
              "\u7684\u9ed1\u6697\u771f\u76f8\uff0c\u9009\u62e9\u653e\u5f03\u8eab\u4efd\u4e0e\u5979\u4e00\u8d77\u5bf9\u6297\uff1b\u4e24\u4eba\u662f\u201c\u76f8\u4f9d\u4e3a\u547d\u201d\u7684\u4e24\u4eba\u5c0f\u961f"
              "\uff08\u83b1\u5a1c\u662f\u667a\u529b\u62c5\u5f53\uff09\u3002\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\u5165\u5e93\u3002"),
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    a = ap.parse_args()

    cfile = DATA / "characters.json"
    rfile = DATA / "relations.json"
    chars = json.loads(cfile.read_text(encoding="utf-8"))
    rels = json.loads(rfile.read_text(encoding="utf-8"))
    had = {c.get("id") for c in chars["characters"]}

    log = []
    for n in NODES:
        if n["id"] in had:
            log.append(f"skip（已存在）: {n['id']} {n['name']}")
            continue
        node = {
            "id": n["id"], "name": n["name"], "aliases": n.get("aliases", []),
            "identity": n["identity"], "groups": [GROUP], "tags": n["tags"],
            "played_by": "\u5f85\u786e\u8ba4", "note": n["note"], "events": [],
            "confirmed": True, "origin": "\u89d2\u8272\u5361\uff08\u8f6c\u5199\u672a\u51fa\u573a\uff09",
        }
        chars["characters"].append(node)
        log.append(f"+ 角色 {n['id']} {n['name']}（{GROUP}）")

    key = (REL["from"], REL["to"], REL["type"])
    has_rel = any((r.get("from"), r.get("to"), r.get("type")) == key for r in rels["relations"])
    if not has_rel:
        rels["relations"].append({**REL, "type_raw": "", "confirmed": True})
        log.append(f"+ 关系 {REL['from']} —{REL['type']}→ {REL['to']}")
    else:
        log.append("skip（关系已存在）")

    # 补丁同步
    if PATCH.is_file():
        patch = json.loads(PATCH.read_text(encoding="utf-8"))
    else:
        patch = {"characters": [], "relations": [], "character_updates": [], "pending": []}
    pids = {c.get("id") for c in patch.get("characters", [])}
    for n in NODES:
        if n["id"] not in pids:
            patch.setdefault("characters", []).append({
                "id": n["id"], "name": n["name"], "aliases": n.get("aliases", []),
                "identity": n["identity"], "groups": [GROUP], "tags": n["tags"],
                "played_by": "\u5f85\u786e\u8ba4", "note": n["note"], "events": [],
                "confirmed": True,
            })
            log.append(f"補丁 + 角色 {n['id']}")
    prels = patch.setdefault("relations", [])
    if not any((r.get("from"), r.get("to"), r.get("type")) == key for r in prels):
        prels.append({**REL, "confirmed": True})
        log.append("補丁 + 关系")

    print("\n".join("  " + x for x in log))
    print(f"\n库内角色 {len(chars['characters'])} · 关系 {len(rels['relations'])}")
    if not a.apply:
        print("[dry-run] 加 --apply 真正写入")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f in (cfile, rfile, PATCH):
        if f.is_file():
            shutil.copyfile(f, f.with_name(f.name + ".bak_mg5card_" + stamp))
    cfile.write_text(json.dumps(chars, ensure_ascii=False, indent=1), encoding="utf-8")
    rfile.write_text(json.dumps(rels, ensure_ascii=False, indent=1), encoding="utf-8")
    PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已写入（备份 *.bak_mg5card_{stamp}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
