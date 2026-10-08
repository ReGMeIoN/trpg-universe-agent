# -*- coding: utf-8 -*-
"""Write per-group PL roles / group listings into both new-group patches.

Why: `players[]` / `pl_profiles[]` only support NEW uids, so an existing PL never learns
"我在这团演了谁" —— that needs `player_updates[].add_roles` + `profile_updates[].add_groups_played`.
The extract cannot do it (it has no uid table), which is exactly what its pending item said.

usage:
    python tools/_fix_pl.py                 # dry-run
    python tools/_fix_pl.py --apply
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCHES = WS / ".trpg" / "patches"
G1 = "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08"          # 阴阳差事录 超自然怪谈
G2 = "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6"                     # 魔法少女育成计划 6

# 既有 PL 的 uid（取自 数据/players.json）
UID = {
    "ReGMeIoN": "u_1hcxJopFPAX4FqHw244Dgg",
    "pd": "u_WXSj6Z3i1SCeuaJKoDrh6A",
    "\u96ea\u4eba": "u_iNPT6i4TzRDATnGdKzr3Mg",          # 雪人
    "\u5f80": "u_9Kb8IIw3_sOBpESFP8IJpA",                # 往
    "\u83cc\u7f8a": "u_OVHNJ1ZkshyGSOsm6DHJyw",          # 菌羊
    "\u5bbd": "u_DODMKVWsHhZcbZfiB6AOMQ",                # 宽
}
# 库里还没有的 PL -> 用本地占位 uid（下次拿到 QQ 号可替换）
NEW_UID = {
    "\u4fca\u677e": "u_local_junsong",                    # 俊松
    "\u725b\u7237": "u_local_niuye",                      # 牛爷
}

ROLES = {
    G1: [
        ("\u4fca\u677e", "\u4e8e\u79c0\u4e3d",
         "\u6563\u4fee\u00b7\u6e38\u4e50\u573a\u9b3c\u5c4b\u8001\u677f\uff1b\u5f71\u4e2d\u300c\u7231\u4eba\u300d\uff0f\u788e\u9885\u9524"),
        ("ReGMeIoN", "\u5218\u6cf7", "\u9053\u6559\u00b7\u4ed9\u6cd5\u7b26\u7b93\uff0f\u795e\u9704\u96f7\u6cd5"),
        ("\u83cc\u7f8a", "\u53f6\u5343\u7b71", "\u5723\u739b\u5229\u4e9a\u5973\u6821\u00b7\u4f0f\u9b54\u68cd\uff0f\u795e\u517d\u793a\u73b0"),
        ("\u96ea\u4eba", "\u6797\u5c0f\u9e22", "\u5357\u5bab\u6d3e\u6c14\u529f\u7b2c\u4e8c\u5341\u516b\u4ee3\u00b7\u7b97\u547d\u5148\u751f\uff08\u8d64\u9e22\uff09"),
        ("\u5f80", "\u8881\u7cef\u7cef", "\u85cf\u6559\u00b7\u5341\u4e8c\u5904\u6cd5\u5668\uff0f\u52a0\u6cb9"),
        ("\u5bbd", "\u8f69\u8f95\u51ac\u9752", "\u5fa1\u4e09\u5bb6\u00b7\u4eba\u524d\u663e\u5723\uff0f\u62d8\u7075\u9063\u5c06"),
        ("\u725b\u7237", "\u77e5\u884c", "\u5c0f\u9640\u5bfa\u5c0f\u548c\u5c1a\u00b7\u77e5\u89c1\u969c"),
    ],
    G2: [
        ("\u5f80", "\u4e8c\u4f0a\u68b9\u7eb1\u7eb1", "\u767d\u6559\u4f7f\u5f92\u00b7\u5b66\u9662\u6559\u5e08\uff1b\u5e78\u798f\u8bfe\u8868\uff0f\u8f6e\u56de"),
        ("ReGMeIoN", "\u8f58\u7ef4\u5e0c", "\u5996\u7cbe\u65cf\u00b7\u524d\u300c\u7ae5\u8bdd\u300d\u961f\u957f\uff08Zweig\uff09"),
        ("\u96ea\u4eba", "\u767d\u8431", "\u690d\u7269\u5b66\u5bb6\u00b7\u81ea\u7136\u5f8b\u6cd5\uff08\u751f\u957f\uff0f\u6bc1\u706d\u4e24\u5f62\u6001\uff09"),
        ("\u83cc\u7f8a", "\u9732\u897f\u83c8", "S \u7ea7\u00b7\u518d\u6f14\uff0f\u7ec8\u66f2\uff08Lucilla\uff09"),
        ("\u5bbd", "\uff08\u7b2c 5 \u540d\u524d\u8f88\uff0c\u89d2\u8272\u5361\u5f85\u8865\uff09", "\u524d\u8f88 PC\uff1b\u8f85\u5bfc\u5bf9\u8c61 = \u675c\u9e43\uff08\u9662\uff09\uff08\u5361\u5f85\u8865\uff09"),
    ],
    # pd 在两团都是 KP
}
KP_ROLES = {
    G1: "KP\uff08\u672c\u56e2\u5168\u90e8 NPC \u7531\u4ed6\u626e\u6f14\uff09",
    G2: "KP\uff08\u540e\u8f88 5 \u540d NPC \u5168\u90e8\u7531\u4ed6\u4ee3\u6f14\uff09",
}
KP_ROLE_G1 = KP_ROLES[G1]
KP_ROLE_G2 = KP_ROLES[G2]


BAD_CHAR = "\u68b9"   # 梹 —— 手写转义时敲错的字
GOOD_CHAR = "\u68c2"  # 棂 —— 卡面正字（二伊棂纱纱）


def role_text(pc: str, detail: str) -> str:
    return f"PC\uff1a{pc}\uff08{detail}\uff09"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    summary: list[str] = []

    for group, table in ROLES.items():
        p = PATCHES / f"{group}_patch.json"
        if not p.is_file():
            print(f"!! 缺补丁 {p.name}")
            continue
        patch = json.loads(p.read_text(encoding="utf-8"))
        # 纠错：手写转义敲错的「梹」-> 卡面正字「棂」（幂等）
        blob = json.dumps(patch, ensure_ascii=False)
        if BAD_CHAR in blob:
            patched = json.loads(blob.replace(BAD_CHAR, GOOD_CHAR))
            print(f"  {p.name}: 纠正 {blob.count(BAD_CHAR)} 处「{BAD_CHAR}」->「{GOOD_CHAR}」")
            patch = patched
        pu = {x.get("uid"): x for x in (patch.get("player_updates") or [])}
        fu = {x.get("uid"): x for x in (patch.get("profile_updates") or [])}
        players_new = {x.get("uid"): x for x in (patch.get("players") or [])}
        profiles_new = {x.get("uid"): x for x in (patch.get("pl_profiles") or [])}
        added_roles = added_groups = added_new = 0

        def add_role(uid: str, role: str, gp_entry: str, card: dict):
            nonlocal added_roles, added_groups, added_new
            if uid in UID.values() or uid in players_new:
                rec = pu.setdefault(uid, {"uid": uid, "add_roles": []})
                if not any(r.get("role") == role for r in rec["add_roles"]):
                    rec["add_roles"].append({"group": group, "role": role})
                    added_roles += 1
                frec = fu.setdefault(uid, {"uid": uid, "add_groups_played": [], "add_cards": []})
                if gp_entry not in frec["add_groups_played"]:
                    frec["add_groups_played"].append(gp_entry)
                    added_groups += 1
                if not any(c.get("group") == group for c in frec["add_cards"]):
                    frec["add_cards"].append(card)
            else:
                # 库里没有的 PL -> 新建 players + pl_profiles
                nm = next(k for k, v in {**UID, **NEW_UID}.items() if v == uid)
                if uid not in players_new:
                    players_new[uid] = {"uid": uid, "qq_name": nm, "real_alias": None,
                                        "roles": [{"group": group, "role": role}]}
                    added_new += 1
                elif not any(r.get("group") == group for r in players_new[uid]["roles"]):
                    players_new[uid]["roles"].append({"group": group, "role": role})
                if uid not in profiles_new:
                    profiles_new[uid] = {
                        "uid": uid, "name": nm, "aliases": [],
                        "groups_played": [gp_entry], "cards": [card],
                        "speaking_style": "", "rp_style": "", "impressions": [], "highlights": [],
                    }
                else:
                    if gp_entry not in profiles_new[uid]["groups_played"]:
                        profiles_new[uid]["groups_played"].append(gp_entry)

        for pl, pc, detail in table:
            role = role_text(pc, detail)
            uid = UID.get(pl) or NEW_UID.get(pl)
            if not uid:
                print(f"  !! 未登记 uid 的 PL: {pl}")
                continue
            add_role(uid, role, f"{group}\uff08{pc}\uff09",
                     {"group": group, "role": f"{pc}\uff08{detail}\uff09"})
        # KP
        add_role(UID["pd"], KP_ROLES[group], f"{group}\uff08KP\uff09",
                 {"group": group, "role": KP_ROLES[group]})

        patch["player_updates"] = list(pu.values())
        patch["profile_updates"] = list(fu.values())
        patch["players"] = list(players_new.values())
        patch["pl_profiles"] = list(profiles_new.values())

        # ---- 写盘前后处理：字符归一 + 逐项去重（对重跑/错字残留都幂等）----
        # 1) 再次把错字归一（前面只处理了读入时的那一份）
        blob2 = json.dumps(patch, ensure_ascii=False)
        if BAD_CHAR in blob2:
            patch = json.loads(blob2.replace(BAD_CHAR, GOOD_CHAR))
        # 2) add_roles / add_groups_played / add_cards 去重
        dedup = 0
        for rec in patch["player_updates"]:
            seen_r, roles = set(), []
            for r in rec.get("add_roles") or []:
                k = (r.get("group"), r.get("role"))
                if k in seen_r:
                    dedup += 1
                    continue
                seen_r.add(k)
                roles.append(r)
            rec["add_roles"] = roles
        for rec in patch["profile_updates"]:
            for key in ("add_groups_played",):
                seen_g, kept = set(), []
                for x in rec.get(key) or []:
                    if x in seen_g:
                        dedup += 1
                        continue
                    seen_g.add(x)
                    kept.append(x)
                rec[key] = kept
            seen_c, cards = set(), []
            for c in rec.get("add_cards") or []:
                k = (c.get("group"), c.get("role"))
                if k in seen_c:
                    dedup += 1
                    continue
                seen_c.add(k)
                cards.append(c)
            rec["add_cards"] = cards
        # 3) player_updates 为空的条目丢掉（store 会报「无实际变更」噪音）
        patch["player_updates"] = [r for r in patch["player_updates"] if r.get("add_roles")]
        patch["profile_updates"] = [
            r for r in patch["profile_updates"]
            if r.get("add_groups_played") or r.get("add_cards") or r.get("append_note")
            or r.get("append_speaking_style") or r.get("append_rp_style")
        ]
        # 4) 新建 PL 的追加条目去掉：store 先落 players[]/pl_profiles[]，
        #    随后按**既有**名单校验 player_updates -> 必然报「玩家不存在」的噪音
        new_uids = set(NEW_UID.values())
        patch["player_updates"] = [r for r in patch["player_updates"] if r.get("uid") not in new_uids]
        patch["profile_updates"] = [r for r in patch["profile_updates"] if r.get("uid") not in new_uids]
        msg = (f"{group}: 角色 {added_roles} · 团履历 {added_groups} · 新建 PL {added_new} · "
               f"player_updates {len(pu)} · profile_updates {len(fu)}")
        summary.append(msg)
        if apply:
            bak = p.with_name(p.name + f".bak_pl_{datetime.now():%Y%m%d_%H%M%S}")
            shutil.copy2(p, bak)
            p.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"已写入 {p.name}")
    for s in summary:
        print("  " + s)
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
