# -*- coding: utf-8 -*-
"""跨团同位体立绘复用登记（免费、一致性优先）。

口径：主人 2026-10-05 已确认下述角色各自成节点、互为**同位体**。
同位体＝同一个人的不同宇宙版本 → **视觉上必须长一样**，所以直接复用已入库的立绘，
不重复让 NAI 生成（否则同一个艾斯利尔会出现三张不同的脸）。

两种落地方式：
  COPY  —— 拷成 `<团名>_<角色名>.<ext>` 再指向它（角色名与节点名一致时用，便于人眼认文件）
  POINT —— 直接把 avatar 指到既有文件（多人共享同一张时用，避免同一个人出现多份副本）

用法:
    python tools/_apply_reuse_portraits.py            # dry-run
    python tools/_apply_reuse_portraits.py --apply
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))   # TRPG关系网
DATA = WS / "\u6570\u636e"                            # 数据
AVATARS = DATA / "\u5934\u50cf"                       # 头像
CHARS = DATA / "characters.json"

MODE_COPY, MODE_POINT = "copy", "point"

# 目标 id -> (模式, 源文件（相对 数据/头像）, 目标文件名或 None, 说明)
REUSE: dict[str, tuple[str, str, str | None, str]] = {
    # ── 艾斯利尔：mg_aisilie（魔法少女2·Hopes）已有立绘，g2/mg3 是同位体 → 共享同一张
    "g2_aisilie": (MODE_POINT, "\u827e\u65af\u5229\u5c14\u00b7\u5fb7\u96f7\u59c6.jpg", None,
                   "魔女裁判厅版；与 mg_aisilie（Hopes）同位体，共享立绘"),
    "mg3_aisilie": (MODE_POINT, "\u827e\u65af\u5229\u5c14\u00b7\u5fb7\u96f7\u59c6.jpg", None,
                    "救赎线版（本团最终BOSS）；同位体共享立绘"),
    # ── 神川玛利亚：mg6 有卡内原图立绘 → 魔女裁判厅版复用
    "g2_shenchuan": (MODE_COPY, "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6_\u795e\u5ddd\u739b\u5229\u4e9a.jpg",
                     "\u9b54\u5973\u88c1\u5224\u5385_\u795e\u5ddd\u739b\u5229\u4e9a.jpg",
                     "魔女裁判厅版；与 mg6_shenchuan_maliya 同位体"),
    # ── 马卡龙 / 神前早月：既有立绘 → 魔法少女育成计划 6 的节点复用
    "mg6_makalong": (MODE_COPY, "\u9a6c\u5361\u9f99.png",
                     "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6_\u9a6c\u5361\u9f99.png",
                     "第二赛区对手；与 mg_makalong 同位体"),
    "mg6_shenqianzaoyue": (MODE_COPY, "\u795e\u524d\u65e9\u6708.png",
                           "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6_\u795e\u524d\u65e9\u6708.png",
                           "图书馆口令；与 mg3_zaoyue 同位体"),
    # ── 曼德拉 = 圣剑团的「莉亚·岩心」（主人 2026-10-05 确认：蔓德拉就是圣剑团的莉亚）
    #    圣剑团的莉亚本来就是按《明日方舟》蔓德拉画的那张卡内原图 → 直接指过去
    "mg6_mandela": (MODE_POINT,
                    "\u5723\u5251\u82f1\u96c4\u8c2d_\u8389\u4e9a\u00b7\u5ca9\u5fc3_card1.png", None,
                    "第七赛区参赛学生；= 圣剑英雄谭的莉亚·岩心（同为《明日方舟》蔓德拉路数），共享立绘"),
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv

    doc = json.loads(CHARS.read_text(encoding="utf-8"))
    index = {c.get("id"): c for c in doc.get("characters") or []}

    plan: list[tuple[str, str, str, str, str, str]] = []   # (id, name, mode, avatar_rel, src_name, note)
    bad: list[str] = []
    for cid, (mode, src_name, dst_name, note) in REUSE.items():
        c = index.get(cid)
        if c is None:
            bad.append(f"节点不存在: {cid}")
            continue
        src = AVATARS / src_name
        if not src.is_file():
            bad.append(f"源图不存在: {src}")
            continue
        rel = (f"{DATA.name}\\{AVATARS.name}\\{dst_name}" if mode == MODE_COPY
               else f"{DATA.name}\\{AVATARS.name}\\{src_name}")
        plan.append((cid, c.get("name") or cid, mode, rel, src_name, note))

    print(f"{'id':<22}{'角色':<20}{'模式':<7}avatar")
    print("-" * 96)
    for cid, name, mode, rel, _src, _n in plan:
        print(f"{cid:<22}{name:<20}{mode:<7}{rel}")
    if bad:
        print("\n!! 问题:")
        for b in bad:
            print("   " + b)

    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
        return 0
    if bad:
        print("\n有问题 -> 拒绝写入")
        return 1

    bak = CHARS.with_name(CHARS.name + f".bak_reuse_{datetime.now():%Y%m%d_%H%M%S}")
    shutil.copy2(CHARS, bak)
    for cid, name, mode, rel, src_name, _n in plan:
        if mode == MODE_COPY:
            dst = AVATARS / Path(rel.replace("\\", "/")).name
            if not dst.is_file():
                shutil.copy2(AVATARS / src_name, dst)
        index[cid]["avatar"] = rel
    CHARS.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写入（备份 {bak.name}）")

    chk = json.loads(CHARS.read_text(encoding="utf-8"))
    ci = {c.get("id"): c for c in chk["characters"]}
    ok = 0
    for cid, name, mode, rel, _s, _n in plan:
        av = ci[cid].get("avatar") or ""
        fn = Path(av.replace("\\", "/")).name
        if av and (AVATARS / fn).is_file():
            ok += 1
        else:
            print(f"  !! 复验失败 {cid}: {av}")
    print(f"复验: {ok}/{len(plan)} 张头像可解析")
    return 0 if ok == len(plan) else 1


if __name__ == "__main__":
    raise SystemExit(main())
