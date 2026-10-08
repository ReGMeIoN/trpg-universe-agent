# -*- coding: utf-8 -*-
"""把 6 位 PL 在「圣剑英雄谭」的本团角色与画像写进补丁（走 player_updates / profile_updates）。

为什么需要它：`players.json` / `pl_profiles.json` 原先只支持"新增条目"，uid 已存在就整条跳过 ——
所以"某 PL 在本团演了谁 / 本团表现"永远写不进去。2026-10-03 给 merger 补了 `player_updates` /
`profile_updates`（追加语义），本脚本负责生成这批数据。

uid 全部来自库里既有的 `players.json`（宽/雪人/往/pd/菌羊/ReGMeIoN 都已在册），无需编造。

用法:
    .venv\\Scripts\\python.exe tools\\_apply_pl_fixes.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_apply_pl_fixes.py --write
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
PATCH = WS / ".trpg" / "patches" / "圣剑英雄谭_patch.json"
GROUP = "圣剑英雄谭"

# (uid, 玩家名, 本团角色, 画像补充)
ROLES = [
    ("u_1hcxJopFPAX4FqHw244Dgg", "ReGMeIoN", "PC：莉亚·岩心（半兽人·土之圣剑「无双天下磁场爆破剑」；当年毁灭鼹鼠人王国的人）"),
    ("u_WXSj6Z3i1SCeuaJKoDrh6A", "pd", "PC：飒飒米（提夫林吟游诗人·音之圣剑「小尤里」，理念「只是一味传唱着英雄的故事」）"),
    ("u_iNPT6i4TzRDATnGdKzr3Mg", "雪人（砂狼真奈的旁白）", "PC：流星亚什（风龙裔·风之圣剑／雪山水晶圣剑；终局主角「我守护的是人类的现在」）"),
    ("u_9Kb8IIw3_sOBpESFP8IJpA", "往（杨瑾宣）", "PC：妮娜·可可（人造人·炎之圣剑「血」；血钉/血涡等血系作战主力）"),
    ("u_DODMKVWsHhZcbZfiB6AOMQ", "宽（薄荷糖）", "PC：八重樱（人族·烟剑／烟之呼吸，武痴）"),
    ("u_OVHNJ1ZkshyGSOsm6DHJyw", "菌羊（凤樱姬玩家）", "KP（本团主持人；皇帝/圣女/教皇/四骑士等全部 NPC 由他扮演）"),
]

PROFILE_ADD = {
    "u_DODMKVWsHhZcbZfiB6AOMQ": {
        "rp": "SJT（圣剑英雄谭）：本团行动核心。武痴式 RP——开场拒绝皇帝「想要我做事，只有我认可的人」；"
              "收威尔娜为徒只教「找到自己的呼吸」，雷之国攻城时把雷剑交给她促成共鸣；"
              "烟之呼吸玩成烟卷风驱散黄虫；为笼中红狐狸一刀砍了哥布林商队护卫。"
              "**现实身份：调酒师** —— 给雪人调过一杯能点燃的高度烈酒，捏他《蔚蓝之海》，"
              "所以世界内流传的「无龙茶」其实是「乌龙茶」这个桌边梗。",
        "speak": "抽烟梗常驻（「戒了烟我不习惯」）；口头禅式玩梗多，行动先于讨论。",
        "imp": ["本团戏份最重（88 处被点名）", "武痴 + 抽烟梗", "现实中是调酒师（乌龙茶梗）"],
    },
    "u_iNPT6i4TzRDATnGdKzr3Mg": {
        "rp": "SJT（圣剑英雄谭）：RP 偏冷面寡言、行动派。段4 矮人酒馆自称喝过「无龙茶（乌龙茶）」震惊全场；"
              "雪山段直接化龙载全队上山；段5 冲上去偷圣兽嘴里的剑被打飞，最终拔起水晶圣剑并被剑选择；"
              "段6 拒绝成为新四骑士的堕落路线，独白「我守护的是人类的现在」。",
        "speak": "话少、句子短；关键处才有大段独白。",
        "imp": ["冷面行动派", "被点名 98 处（与宽并列最多）", "终局主角视角"],
    },
    "u_9Kb8IIw3_sOBpESFP8IJpA": {
        "rp": "SJT（圣剑英雄谭）：血系作战主力（血钉把自己固定在马上、血涡、血液凝成剑/披风）。"
              "终局以「拒绝这个故事」的立场与雪人对峙，投骰投出 95 级骰面否决对方的结局叙事；台词简短克制。",
        "speak": "台词简短、立场鲜明；骰运关键时刻很硬（终局 95）。",
        "imp": ["血系战斗担当", "终局「拒绝这个故事」", "投骰定结局的关键一手"],
    },
    "u_WXSj6Z3i1SCeuaJKoDrh6A": {
        "rp": "SJT（圣剑英雄谭）：演提夫林吟游诗人飒飒米 —— 段1 在马车上传唱英雄故事（转写写作「一忧四人」），"
              "段2 被同伴叫作「沙沙／杀杀」。角色理念「事不关己，只是一味传唱着英雄的故事」与玩家本人的记录者气质一致。",
        "speak": "以吟游诗人的口吻插科打诨、负责叙事性台词。",
        "imp": ["本团演吟游诗人", "「沙沙／杀杀」都是他", "记录者气质"],
    },
    "u_1hcxJopFPAX4FqHw244Dgg": {
        "rp": "SJT（圣剑英雄谭）：在**本团是 PL 不是 KP**，演半兽人土系魔法师莉亚·岩心（土偶／石柱／地裂／捏泥巴，"
              "转写里的「地牙?」「劳昌?」都指她）；段4 在矮人国学剑。当年召唤魔像引发地震、毁灭鼹鼠人王国的人也是她。",
        "speak": "本团话不多，但被反复点名（威尔娜被安排「跟着劳昌学习」）。",
        "imp": ["本团身份＝PL（莉亚·岩心）", "土系能力担当", "悬赏令上的「毁灭鼹鼠人王国」"],
    },
    "u_OVHNJ1ZkshyGSOsm6DHJyw": {
        "rp": "SJT（圣剑英雄谭）：**本团 KP**，兼演全部 NPC（皇帝奥古斯都、圣女赛林斯蒂亚、教皇、"
              "维克托、兰斯洛特、四骑士、老瞎眼、矮人大师 80铁砧…）；战后回收「六个（＝六把圣剑）」等早期伏笔。",
        "speak": "KP 口播风格：临场描述 + 伏笔回收。",
        "imp": ["本团 KP", "演全部 NPC", "伏笔回收者"],
    },
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    doc = json.loads(PATCH.read_text(encoding="utf-8"))

    pu = doc.setdefault("player_updates", [])
    by_uid = {u.get("uid"): u for u in pu}
    for uid, name, role in ROLES:
        item = by_uid.get(uid)
        if item is None:
            item = {"uid": uid, "add_roles": [], "confirmed": True}
            pu.append(item)
            by_uid[uid] = item
        if not any(r.get("group") == GROUP for r in item["add_roles"]):
            item["add_roles"].append({"group": GROUP, "role": role})
            print(f"  [player_updates] {name}: + {role[:44]}…")

    pf = doc.setdefault("profile_updates", [])
    by_puid = {u.get("uid"): u for u in pf}
    for uid, extra in PROFILE_ADD.items():
        item = by_puid.get(uid)
        if item is None:
            item = {"uid": uid, "confirmed": True}
            pf.append(item)
            by_puid[uid] = item
        card = {"group": GROUP, "role": next(r for u, n, r in ROLES if u == uid)}
        item.setdefault("add_cards", [])
        if not any(c.get("group") == GROUP for c in item["add_cards"]):
            item["add_cards"].append(card)
        item.setdefault("add_groups_played", [])
        gp = f"{GROUP}（{card['role'].split('：', 1)[-1].split('（')[0]}）"
        if gp not in item["add_groups_played"]:
            item["add_groups_played"].append(gp)
        item["append_rp_style"] = extra["rp"]
        item["append_speaking_style"] = extra["speak"]
        item.setdefault("add_impressions", [])
        for x in extra["imp"]:
            if x not in item["add_impressions"]:
                item["add_impressions"].append(x)
        print(f"  [profile_updates] {uid[:12]}…: 画像 +1 张卡 / rp 与 speaking 追加")

    print(f"\nplayer_updates {len(pu)} 条 · profile_updates {len(pf)} 条")
    if not write:
        print("[dry-run] 未落盘。加 --write 生效。")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(PATCH, PATCH.with_suffix(f".json.bak_pl_{stamp}"))
    PATCH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"OK 已写入 {PATCH}\n备份 {PATCH.with_suffix(f'.json.bak_pl_{stamp}')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
