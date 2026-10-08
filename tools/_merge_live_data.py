# -*- coding: utf-8 -*-
"""把本地生产库的**新增**并进线上库（以线上为基准，绝不覆盖已有改动）。

为什么需要它：主人手动推代码时只推了 `site/` + `server/*.py`，没推 `server/data/`，
所以线上还是"潮汐监狱第2轮答疑之前"的数据 —— 少了 8 个角色：
  td_dianyu(典狱长) · td_aonier(奥尼尔舅舅) · td_fulisike(弗里斯克) ·
  td_jieximin(杰西敏) · td_sugeladi(苏格拉底) · td_haochen(浩辰) ·
  td_hgailisi(海格丽丝) · td_lzeyuan(柳如烟)

**以线上为基准**（朋友可能在线编辑过）：本地有、线上没有的才补进去；
两边都有的**保留线上那份**（不覆盖别人的改动）。

用法：
    # 1) 先拉线上数据
    curl -o .tmp/live_all.json "http://<服务器IP>:8080/api/data?scope=all"
    # 2) 合并
    .venv\\Scripts\\python.exe tools\\_merge_live_data.py --live .tmp/live_all.json --out .tmp/to_upload
    # 3) 上传（见交付说明）
"""
from __future__ import annotations

import os
import argparse
import json
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
LOCAL_DATA = WS / "\u6570\u636e"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--live", required=True, help="线上 /api/data?scope=all 的 JSON")
    ap.add_argument("--out", default=".tmp/to_upload")
    ap.add_argument("--local", default=str(LOCAL_DATA))
    a = ap.parse_args()

    live = json.loads(Path(a.live).read_text(encoding="utf-8"))
    live_chars = live.get("chars") or []
    # ⚠️ `/api/data` 的关系端点是 `a`/`b`，而生产库文件用的是 `from`/`to` —— 必须转回来，
    #    否则去重键全落空（第一次跑就把 461 条关系重复补了一遍，922 条 / 461 条）。
    live_rels = [{"from": r.get("a"), "to": r.get("b"), "type": r.get("type") or "",
                  "type_raw": r.get("raw") or "", "strength": r.get("strength") or "",
                  "event": r.get("event") or ""}
                 for r in (live.get("rels") or [])]
    live_ids = {c.get("id") for c in live_chars}

    local_chars = json.loads((Path(a.local) / "characters.json").read_text(encoding="utf-8"))["characters"]
    local_rels = json.loads((Path(a.local) / "relations.json").read_text(encoding="utf-8"))["relations"]

    # 以线上为基准：只补「线上没有的角色」
    add_chars = [c for c in local_chars if c.get("id") not in live_ids]
    print(f"线上角色 {len(live_chars)} · 本地 {len(local_chars)} · 需要补 {len(add_chars)} 个:")
    for c in add_chars:
        print(f"  + {c.get('id'):<16} {c.get('name','')}")

    # 关系：线上有的（按 from|to|type）保留，只补新的
    seen = {(r.get("from"), r.get("to"), r.get("type")) for r in live_rels}
    add_rels = [r for r in local_rels
                if (r.get("from"), r.get("to"), r.get("type")) not in seen]
    # 新补进来的角色相关的边也要带上（两端都得在最终集合里）
    final_ids = live_ids | {c.get("id") for c in add_chars}
    add_rels = [r for r in add_rels
                if r.get("from") in final_ids and r.get("to") in final_ids
                and r.get("from") != r.get("to")]
    print(f"线上关系 {len(live_rels)} · 本地 {len(local_rels)} · 需要补 {len(add_rels)} 条")

    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)

    # 写两份"可直接上传"的文件：**以线上为基准 + 补新增**
    chars_doc = {"_meta": {"note": "merged: live baseline + local additions",
                           "updated": __import__("datetime").datetime.now().isoformat(timespec="seconds")},
                 "characters": live_chars + add_chars}
    rels_doc = {"_meta": {"note": "merged: live baseline + local additions",
                          "updated": __import__("datetime").datetime.now().isoformat(timespec="seconds")},
                "relations": live_rels + add_rels}
    (out / "characters.json").write_text(json.dumps(chars_doc, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "relations.json").write_text(json.dumps(rels_doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n已写出 -> {out}\\characters.json （{len(chars_doc['characters'])} 人）")
    print(f"         -> {out}\\relations.json （{len(rels_doc['relations'])} 条）")
    print("\n上传命令（服务器上会先备份）：")
    print("  scp .tmp/to_upload/characters.json .tmp/to_upload/relations.json "
          "root@<服务器IP>:/opt/trpg-wiki/server/data/")
    print("  ssh root@<服务器IP> \"chown www-data:www-data /opt/trpg-wiki/server/data/*.json && "
          "systemctl restart trpg-wiki\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
