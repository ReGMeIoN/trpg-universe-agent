# -*- coding: utf-8 -*-
"""Apply the owner's 2026-10-05 answers to the 魔法少女育成计划 6 patch (idempotent).

Covers (all "主人确认"):
  * 同名节点 -> 各自成节点 + 标「跨团同位体」+ note 交叉引用（神川玛利亚/马卡龙/神前早月/李安）
  * 第 5 名前辈（宽）-> 占位节点放行（否则引它的 4 条关系会被 store 当悬空端点跳过）
  * 段12「嘉豪/加豪」= 神川玛利亚的绰号
  * 杰克玩偶/唱片/知风牧场 -> 算 cross_jieke 本人出场
  * 段11「牢昌」-> 只是桌边玩梗，不入库
  * PL 画像 uid 缺失 -> 已由 player_updates / pl_profiles 补齐（见 _fix_pl.py）

usage:
    python tools/_fix_patch_mg6.py            # dry-run
    python tools/_fix_patch_mg6.py --apply
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6"     # 魔法少女育成计划 6
PATCH = WS / ".trpg" / "patches" / f"{GROUP}_patch.json"

CROSS_TAG = "\u8de8\u56e2\u540c\u4f4d\u4f53"                     # 跨团同位体
# mg6 节点 -> (既有节点 id, 名字)
SAME_NAME = {
    "mg6_shenchuan_maliya": ("g2_shenchuan", "\u795e\u5ddd\u739b\u5229\u4e9a"),        # 神川玛利亚
    "mg6_makalong": ("mg_makalong", "\u9a6c\u5361\u9f99"),                            # 马卡龙
    "mg6_shenqianzaoyue": ("mg3_zaoyue", "\u795e\u524d\u65e9\u6708"),                 # 神前早月
    "mg6_liang": ("mg4_lian", "\u674e\u5b89"),                                        # 李昂/李安
}
PLACEHOLDER_ID = "mg6_diwu_qianbei"          # 第5名前辈
PLACEHOLDER_NOTE = (
    "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u5bbd\u626e\u6f14\u7684\u7b2c 5 \u540d\u524d\u8f88 PC\uff0c"
    "\u89d2\u8272\u5361\u5f85\u8865\uff08\u540d\u5b57\u4e0e\u80fd\u529b\u5f85\u5b9a\uff09\uff1b"
    "\u8f85\u5bfc\u5bf9\u8c61 = \u675c\u9e43\uff08\u9662\uff09\u3002"
)
ALIAS_FOR = {"mg6_shenchuan_maliya": ["\u5609\u8c6a", "\u52a0\u8c6a"]}   # 嘉豪 / 加豪
# 主人二次答疑后需要放行（confirmed:false -> true）的节点
RELEASE = {
    "mg6_zhangxuefeng": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u540c\u4e00\u4eba\uff0c\u6807\u51c6\u5199\u6cd5\u300c\u5f20\u96ea\u5cf0\u300d\u3002",
    "mg6_zhanmusi": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u8a79\u59c6\u65af\uff0f\u6218\u65a7\u4f7f\uff0f\u6218\u6b66\u5e08\u540c\u4e00\u4eba\u3002",
    "mg6_maisili": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u4e0e\u9ea6\u65af\u5a01\u5c14**\u4e0d\u662f**\u540c\u4e00\u4eba\uff08\u4e24\u4e2a\u8003\u6838\u5b98\uff09\u3002",
    "mg6_alfred": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1aG \u7684\u8089\u4f53 + \u963f\u5c14\u5f17\u96f7\u5fb7\u7075\u9b42 = \u73b0\u5728\u7684\u82b1\u7530\u3002",
}
# 主人第三轮答疑附带的数据动作
EXTRA_ALIAS = {"mg6_yu": ["\u8bfa\u4e9a"]}                     # 雨 <- 诺亚（最终 BOSS 形态名）
DROP_NODES = {"mg6_dachishouwang"}                              # 玩梗名，不作为角色入库
EXTRA_RELATIONS = [
    {"from": "mg6_alfred", "to": "mg6_xizhi_huatian", "type": "\u7075\u9b42\u6765\u6e90\uff0f\u524d\u4e16",
     "strength": "\u5f3a",
     "event": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1aG \u7684\u8089\u4f53 + \u963f\u5c14\u5f17\u96f7\u5fb7\u7075\u9b42 = \u73b0\u5728\u7684\u82b1\u7530\uff08\u6bb52/\u6bb511\uff09",
     "confirmed": True},
]
# 杰克在本团的引用（主人确认玛利亚台词是真实台词）
JACK_EVENT = "\u6bb51 \u795e\u5ddd\u739b\u5229\u4e9a\u53f0\u8bcd\u300c\u6253\u8fc7\u6770\u514b\u300d\uff08\u4e3b\u4eba\u786e\u8ba4\uff1a\u771f\u5b9e\u53f0\u8bcd\uff0c\u7b97\u5bf9\u6770\u514b\u7684\u5f15\u7528\uff09"

RESOLVED_RULES: list[tuple[tuple[str, ...], str]] = [
    (("\u7b2c5\u540d\u524d\u8f88", "\u89d2\u8272\u5361\u5f85\u8865"), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5148\u5360\u4f4d\uff0c\u5361\u5230\u518d\u8865\u540d\u5b57\u4e0e\u80fd\u529b"),
    (("\u795e\u5ddd\u739b\u5229\u4e9a\u4e0e\u5df2\u5165\u5e93",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4f4d\u4f53\uff08\u5404\u81ea\u6210\u8282\u70b9 + \u8de8\u56e2\u540c\u4f4d\u4f53\u6807\u8bb0\uff09"),
    (("\u795e\u524d\u65e9\u6708\u4e0e\u5df2\u5165\u5e93",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4f4d\u4f53"),
    (("\u9a6c\u5361\u9f99\u4e0e\u5df2\u5165\u5e93",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4f4d\u4f53"),
    (("\u521d\u4ee3\u7684\u7a97",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4f4d\u4f53\uff08\u672c\u56e2\u65e0\u72ec\u7acb\u8282\u70b9\uff0c\u4ec5\u63d0\u53ca\uff09"),
    (("\u78c1\u5c0f\u9b3c",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4f4d\u4f53\uff08\u672c\u56e2\u65e0\u72ec\u7acb\u8282\u70b9\uff09"),
    (("\u54ea\u4e00\u7248",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6309\u540c\u4f4d\u4f53\u5904\u7406\uff08\u672c\u56e2\u4ec5\u63d0\u53ca\uff09"),
    (("\u674e\u6602",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e0e\u5df2\u5165\u5e93\u674e\u5b89\u540c\u4f4d\u4f53"),
    (("\u52a0\u8c6a", "\u5609\u8c6a"), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5c31\u662f\u795e\u5ddd\u739b\u5229\u4e9a\u7684\u7ef0\u53f7"),
    (("\u7262\u660c\u662f\u5426",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u53ea\u662f\u684c\u8fb9\u73a9\u6897\uff0c\u4e0d\u5165\u5e93"),
    (("\u77e5\u98ce\u7267\u573a",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u7b97 cross_jieke\uff08\u6770\u514b\uff09\u672c\u4eba\u51fa\u573a"),
    (("uid", "pl_profiles"), "\u672c\u4f1a\u8bdd\u5df2\u8865\uff1aplayer_updates / pl_profiles \u5df2\u5199\u5165\u5404 PL \u7684\u672c\u56e2\u89d2\u8272"),
    # ---- 第二轮答疑（2026-10-05 夜）----
    (("\u6821\u957f\u4e0e\u9662\u957f",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u540c\u4e00\u4eba**\uff08\u6821\u957f=\u9662\u957f\uff0c\u6bb510 \u73b0\u771f\u9762\u76ee\u4e3a\u6700\u7ec8 BOSS\uff09"),
    (("\u5f20\u96ea\u5cf0",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u540c\u4e00\u4eba**\uff0c\u6807\u51c6\u5199\u6cd5\u300c\u5f20\u96ea\u5cf0\u300d\uff08\u5176\u4f59\u5f53 aliases\uff09"),
    (("\u8a79\u59c6\u65af",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u8a79\u59c6\u65af\uff0f\u6218\u65a7\u4f7f\uff0f\u6218\u6b66\u5e08\u662f**\u540c\u4e00\u4eba**"),
    (("\u57c3\u65af\u8482\u5c14", "\u5723\u5730\u6587"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6307**\u827e\u65af\u5229\u5c14**\uff08\u6309\u8de8\u56e2\u540c\u4f4d\u4f53\u5904\u7406\uff09"),
    (("\u738b\u53f0", "\u738b\u8001\u5e08"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u8f6c\u5199\u91cc\u7684\u300c\u738b\u53f0\uff0f\u738b\u8001\u5e08\u300d\u5176\u5b9e\u662f**\u5f80**"
     "\uff08PL\uff0c\u672c\u56e2\u626e\u4e8c\u4f0a\u68c2\u7eb1\u7eb1\uff09\u2014\u2014\u7167\u5199\u300c\u5f80\u300d\uff0c**\u4e0d\u662f\u300c\u738b\u300d**"),
    (("\u739b\u5229\u4e9a\u53f0\u8bcd", "\u6253\u8fc7\u6770\u514b"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u662f\u771f\u5b9e\u53f0\u8bcd**\uff0c\u7b97\u5bf9 cross_jieke\uff08\u6770\u514b\uff09\u4e0e\u827e\u65af\u5229\u5c14\u7684\u5f15\u7528"),
    (("\u4eba\u540d\u5f52\u4e00",), "\u5df2\u5904\u7406\uff1a\u8fd9\u4e9b\u97f3\u8fd1/\u5f62\u8fd1\u5199\u6cd5\u5747\u4f5c\u4e3a\u5404\u81ea\u8282\u70b9\u7684 aliases \u5f52\u4e00\u5e76\u5b58"),
    (("\u8042\u83ab\u65af", "\u5947\u7f8e\u5170"),
     "\u5df2\u5904\u7406\uff1a\u5df2\u5408\u5e76\u4e3a\u4e00\u4e2a\u8282\u70b9 `mg6_qimeilan`\uff08\u522b\u540d \u8042\u83ab\u65af\uff0f\u6d85\u83ab\u65af\uff09"),
    # ---- 第三轮（听录音核对后的答疑，2026-10-05 夜）----
    (("\u5c0f\u666f",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5a46\u5a46\u53e3\u4e2d\u7684\u300c\u5c0f\u666f\u300d= **\u666f\u4fee\u6587**\uff08\u4e0d\u662f\u7eb1\u7eb1\uff09"),
    (("\u666f\u4fee\u6587",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u666f\u4fee\u6587 = \u666f\u4e3b\u4efb = \u5c0f\u666f** \u540c\u4e00\u4eba\uff08\u5b66\u9662\u4e3b\u4efb\u7ea7 NPC\uff09"),
    (("\u4f7f\u5f92",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u9732\u897f\u83c8\u54c4\u9a97\u739b\u5229\u4e9a**\uff0c\u81ea\u79f0\u662f\u739b\u5229\u4e9a\u7684\u4f7f\u5f92\uff08**\u4e0d\u662f\u771f\u5b9e\u4ece\u5c5e\u5173\u7cfb**\uff09"),
    (("\u57f9\u517b\u7cfb\u7edf",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u8fd9\u662f**\u4e8c\u4f0a\u68c2\u7eb1\u7eb1\u5728\u54c4\u9a97\u82b1\u7530**\uff08\u4e0d\u662f\u771f\u5b9e\u7cfb\u7edf\uff09"),
    (("\u827e\u68ee\u5c3c\u5c14",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u300c\u827e\u68ee\u5c3c\u5c14\u9ed1\u9738\u300d= **\u9ed1\u53d1\u5f62\u6001\u7684\u827e\u65af\u5229\u5c14**\uff08\u6309\u540c\u4f4d\u4f53\uff0f\u5f62\u6001\u5904\u7406\uff09"),
    (("\u4e09\u4e2a\u5bb6\u4f19",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u662f**\u4e09\u4e2a\u5b66\u751f\u7ec4\u7ec7**\uff08\u5404\u7531\u4e00\u540d\u5934\u9886\u7387\u9886\uff09\u2014\u2014"
     "\u8f6c\u5199\u91cc\u8bf4\u300c\u6709\u4e09\u4e2a\u9b54\u5973\uff0c\u90fd\u662f\u6211\u4eec\u5b66\u6821\u7684\u6bd5\u4e1a\u751f\uff0c\u8499\u853d\u4e86\u6821\u957f\u3001"
     "\u6539\u53d8\u5e76\u7edf\u6cbb\u4e86\u6821\u56ed\u300d\uff0c\u4efb\u52a1\u662f\u628a\u4ed6\u4eec\u8d76\u4e0b\u53f0\uff1b**\u539f\u6587\u672a\u70b9\u540d** \u2192 \u4e0d\u5efa\u8282\u70b9"),
    (("\u9ea6\u65af\u5229",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u4e0d\u662f\u540c\u4e00\u4eba**\uff08\u9ea6\u65af\u5229\u4e0e\u9ea6\u65af\u5a01\u5c14\u662f\u4e24\u4e2a\u4eba\uff09"),
    (("\u8bfa\u4e9a\u662f\u5426",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u8bfa\u4e9a = \u96e8\u7684\u6700\u7ec8 BOSS \u5f62\u6001\u540d**"),
    (("\u7ed3\u5c40\u7ebf",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e24\u6761\u7ed3\u5c40\u7ebf = **\u6218\u80dc\u96e8** \u6216 **\u5c31\u8fd9\u6837\u653e\u96e8\u79bb\u5f00**"),
    (("\u53e3\u4ee4",), "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u4e3b\u4eba\u4e5f\u4e0d\u8bb0\u5f97**\uff08\u4fdd\u6301\u672a\u77e5\uff0c\u4e0d\u4f5c\u8bbe\u5b9a\uff09"),
    (("\u5927\u6148\u5bff\u738b",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u73a9\u6897**\u2014\u2014\u96ea\u4eba\u7684\u5361\u662f\u690d\u7269\u7cfb\u4e14\u6709\u4e00\u68f5\u5927\u6811\uff0c"
     "\u88ab\u620f\u79f0\u4e3a\u300a\u539f\u795e\u300b\u91cc\u7684\u5927\u6148\u6811\u738b \u2192 **\u4e0d\u5165\u5e93**"),
    (("\u963f\u5c14\u5f17\u96f7\u5fb7",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u963f\u5c14\u5f17\u96f7\u5fb7 = \u82b1\u7530\u7684\u7075\u9b42\u6765\u6e90**"
     "\uff08G \u7684\u8089\u4f53 + \u963f\u5c14\u5f17\u96f7\u5fb7\u7075\u9b42 = \u73b0\u5728\u7684\u82b1\u7530\uff09"),
    (("\u62a2\u52ab\u8001\u677f",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u7b97\u4e25\u8083\u5267\u60c5**\uff08\u6bb51 \u4e3a\u83b7\u5f97\u751f\u5b58\u8bbe\u5907\u800c\u62a2\u52ab\u8001\u677f\uff0c"
     "\u5df2\u8bb0\u5165\u7b2c 5 \u540d\u524d\u8f88\u8282\u70b9\u7684\u4e8b\u4ef6\uff09"),
]

# 追加事件到已存在的节点（用 character_updates.add_events，幂等）
EVENT_ADDS = [
    {"id": "mg6_diwu_qianbei", "confirmed": True,
     "add_events": [{"group": GROUP,
                     "items": ["\u6bb51\uff1a\u4e3a\u83b7\u5f97\u751f\u5b58\u8bbe\u5907\u800c\u62a2\u52ab\u8001\u677f"
                               "\uff08\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u7b97\u4e25\u8083\u5267\u60c5\uff09"]}]},
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    if not PATCH.is_file():
        print(f"!! 缺补丁 {PATCH}")
        return 1
    patch = json.loads(PATCH.read_text(encoding="utf-8"))

    # 1) 同名节点 -> 放行 + 跨团同位体
    tagged = []
    for c in patch.get("characters") or []:
        cid = c.get("id")
        if cid in SAME_NAME:
            other_id, other_name = SAME_NAME[cid]
            c["confirmed"] = True
            c["pending_reason"] = ""
            c["tags"] = [t for t in (c.get("tags") or []) if t != "\u5f85\u786e\u8ba4"]
            if CROSS_TAG not in c["tags"]:
                c["tags"].append(CROSS_TAG)
            note = (f"\u3010\u8de8\u56e2\u540c\u4f4d\u4f53\u3011\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a"
                    f"\u4e0e `{other_id}`\uff08{other_name}\uff09\u4e3a\u540c\u4f4d\u4f53\uff0c"
                    f"\u6309\u65e2\u6709\u7ea6\u5b9a\u5404\u81ea\u6210\u8282\u70b9\u3001\u4e92\u76f8\u4ea4\u53c9\u5f15\u7528\u3002")
            if note not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + note).strip()
            tagged.append(f"{cid}->{other_id}")

    # 2) 第5名前辈占位节点放行（否则 4 条关系被判悬空端点）
    for c in patch.get("characters") or []:
        if c.get("id") == PLACEHOLDER_ID:
            c["confirmed"] = True
            c["pending_reason"] = ""
            c["tags"] = [t for t in (c.get("tags") or []) if t != "\u5f85\u786e\u8ba4"]
            if PLACEHOLDER_NOTE not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + PLACEHOLDER_NOTE).strip()

    # 3) 嘉豪 = 神川玛利亚的绰号 -> 别名
    for c in patch.get("characters") or []:
        for add in ALIAS_FOR.get(c.get("id"), []):
            if add not in (c.get("aliases") or []):
                c.setdefault("aliases", []).append(add)
        for add in EXTRA_ALIAS.get(c.get("id"), []):
            if add not in (c.get("aliases") or []):
                c.setdefault("aliases", []).append(add)

    # 3b) 玩梗名不作为角色（大慈寿王 = 戏称「原神·大慈树王」）
    before = len(patch.get("characters") or [])
    patch["characters"] = [c for c in (patch.get("characters") or [])
                           if c.get("id") not in DROP_NODES]
    dropped = before - len(patch["characters"])
    # 3c) 补充关系（阿尔弗雷德 -> 花田）
    rels = patch.setdefault("relations", [])
    extra_rel = 0
    for r in EXTRA_RELATIONS:
        if not any(x.get("from") == r["from"] and x.get("to") == r["to"] for x in rels):
            rels.append(dict(r))
            extra_rel += 1

    # 3d) 追加事件到已存在节点（抢劫老板 -> 第5名前辈）
    ups = {u.get("id"): u for u in (patch.get("character_updates") or [])}
    ev_added = 0
    for spec in EVENT_ADDS:
        rec = ups.setdefault(spec["id"], {"id": spec["id"], "add_events": [], "confirmed": True})
        events = rec.setdefault("add_events", [])
        for ev in spec["add_events"]:
            found = next((e for e in events if e.get("group") == ev["group"]), None)
            if found is None:
                events.append(dict(ev))
                ev_added += len(ev.get("items") or [])
            else:
                for it in ev.get("items") or []:
                    if it not in (found.get("items") or []):
                        found.setdefault("items", []).append(it)
                        ev_added += 1
    patch["character_updates"] = list(ups.values())

    # 4) 杰克本人出场 -> 更新既有 cross_jieke（把「玩梗待确认」改成已确认出场）
    jack = 0
    for u in patch.get("character_updates") or []:
        if u.get("id") == "cross_jieke":
            u["confirmed"] = True
            add = ("\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u672c\u56e2\u7684\u6770\u514b\u73a9\u5076\uff0f\u5531\u7247\uff0f"
                   "\u77e5\u98ce\u7267\u573a\u7b49\u7ebf\u7d22\u7b97\u6770\u514b\u672c\u4eba\u51fa\u573a\uff08\u975e\u7eaf\u73a9\u6897\uff09\u3002")
            if add not in (u.get("append_note") or ""):
                u["append_note"] = ((u.get("append_note") or "").rstrip() + " " + add).strip()
            events = u.setdefault("add_events", [])
            grp = next((e for e in events if e.get("group") == GROUP), None)
            if grp is None:
                grp = {"group": GROUP, "items": []}
                events.append(grp)
            if JACK_EVENT not in grp["items"]:
                grp["items"].append(JACK_EVENT)
            jack += 1
    # ⚠️ 这段 append_note 已在 19:59 那次入库落盘（store 的 append_note 不去重）-> 清空，
    #    避免再入库时写两遍；裁决文本在生产数据与 resolved_by_owner 里都有留档
    for u in patch.get("character_updates") or []:
        if u.get("id") == "cross_jieke":
            u["append_note"] = ""

    # 4b) 放行主人已确认的 confirmed:false 节点
    released = []
    for c in patch.get("characters") or []:
        if c.get("id") in RELEASE and not c.get("confirmed", True):
            c["confirmed"] = True
            c["pending_reason"] = ""
            c["tags"] = [t for t in (c.get("tags") or []) if t != "\u5f85\u786e\u8ba4"]
            note = RELEASE[c["id"]]
            if note not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + note).strip()
            released.append(c["id"])

    # 5) pending 分流（保留已有 resolved_by_owner，保证可重跑）
    #    先把「被关键词误配」的条目打回（如「图书馆密室口令…试过阿尔弗雷德/诺亚」曾被
    #    「神前早月」这个宽泛关键词吃掉）
    MISMATCH = (("\u53e3\u4ee4",),)
    restored, kept_resolved = [], []
    for a in patch.get("resolved_by_owner") or []:
        item = str(a.get("item") or "")
        if any(any(m in item for m in marks) for marks in MISMATCH):
            restored.append({k: v for k, v in a.items() if k != "owner_answer"})
            continue
        kept_resolved.append(a)
    patch["resolved_by_owner"] = kept_resolved
    already = {str(a.get("item")) for a in kept_resolved}
    keep, answered = [], []
    for p in list(patch.get("pending") or []) + restored:
        item = str(p.get("item") or "")
        if item in already:
            continue
        hit = None
        for marks, note in RESOLVED_RULES:
            if any(m in item for m in marks):
                hit = note
                break
        if hit:
            answered.append({**p, "owner_answer": hit})
        else:
            keep.append(p)
    patch["pending"] = keep
    patch["resolved_by_owner"] = (patch.get("resolved_by_owner") or []) + answered

    # 6) 别名清洗
    cleaned = 0
    for c in patch.get("characters") or []:
        name = (c.get("name") or "").strip()
        seen, out = set(), []
        for a in c.get("aliases") or []:
            a = (a or "").strip()
            if not a or a == name or a in seen:
                cleaned += 1
                continue
            seen.add(a)
            out.append(a)
        if "aliases" in c or out:
            c["aliases"] = out

    print(f"补丁: {PATCH.name}")
    print(f"同名节点标跨团同位体: {len(tagged)} 条 -> {', '.join(tagged)}")
    print(f"占位节点放行: {PLACEHOLDER_ID}")
    print(f"嘉豪别名: {ALIAS_FOR}")
    print(f"杰克更新: {jack} 条")
    print(f"放行 confirmed:false: {len(released)} 条 {released}")
    print(f"玩梗节点删除: {dropped} 个 {sorted(DROP_NODES)} · 补充关系: {extra_rel} 条 · 追加事件: {ev_added} 条")
    print(f"别名清洗: {cleaned} 条")
    print(f"pending: {len(keep)} 条仍待确认 · 本轮新增已答 {len(answered)} 条（累计 {len(patch['resolved_by_owner'])}）")
    for a in answered:
        print(f"  [已答] {str(a.get('item'))[:58]} <- {a.get('owner_answer')}")

    if apply:
        bak = PATCH.with_name(PATCH.name + f".bak_ownerqa_{datetime.now():%Y%m%d_%H%M%S}")
        shutil.copy2(PATCH, bak)
        PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {PATCH.name}（备份 {bak.name}）")
    else:
        print("\n(dry-run; 加 --apply 写入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
