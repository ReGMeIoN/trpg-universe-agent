# -*- coding: utf-8 -*-
"""Apply the owner's 2026-10-05 Q&A answers to the 阴阳差事录 patch (idempotent, replayable).

Why a script: the patch is LLM output; the review step is "owner answers -> mechanically fix
the patch -> re-check -> store". Doing it by hand in a 41 KB JSON is unreproducible
(same discipline as the earlier `_fix_patch_sjt.py`).

What it fixes (all "主人确认" from the 2026-10-05 three-round Q&A):
  1. played_by: KP = pd (so every NPC is pd) + the 7 PCs' PLs
  2. proper nouns: 流汤/老汤->刘汤, 陆肖满/肖满->陆小满, 沈默/嘉兴/家豪/嘉欣->嘉豪,
     素颜/遗愿->夙愿, 师父->师傅
  3. 刘泷的妹妹 -> 刘汤 (name + aliases); 无脸人 -> 艾斯利尔（阴阳差事录）跨团同位体
  4. pending: owner-answered items move to `resolved_by_owner`, only真·未决 items stay in `pending`
  5. records `_meta.owner_review`

usage:
    python tools/_fix_patch_yy.py            # dry-run: 只报告会改什么
    python tools/_fix_patch_yy.py --apply
"""
from __future__ import annotations

import os
import copy
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08"      # 阴阳差事录 超自然怪谈
PATCH = WS / ".trpg" / "patches" / f"{GROUP}_patch.json"

KP = "pd"

# 角色名 -> PL（主人 2026-10-05 确认）
PL_BY_NAME = {
    "\u4e8e\u79c0\u4e3d": "\u4fca\u677e",                    # 于秀丽 = 俊松
    "\u5218\u6cf7": "ReGMeIoN",                              # 刘泷 = ReGMeIoN
    "\u53f6\u5343\u7b71": "\u83cc\u7f8a",                    # 叶千筱 = 菌羊
    "\u6797\u5c0f\u9e22": "\u96ea\u4eba",                    # 林小鸢 = 雪人
    "\u8881\u7cef\u7cef": "\u5f80",                          # 袁糯糯 = 往
    "\u8f69\u8f95\u51ac\u9752": "\u5bbd",                    # 轩辕冬青 = 宽
    "\u77e5\u884c": "\u725b\u7237",                          # 知行 = 牛爷
}

# 全局文本归一（转写/提炼里的写法 -> 标准写法）
RENAMES = [
    ("\u9ed1\u96ea", "\u9ed1\u8840"),      # 黑雪 -> 黑血（主人更正：是 BOSS 的新技能「黑血」）
    ("\u6d41\u6c64", "\u5218\u6c64"),      # 流汤 -> 刘汤
    ("\u8001\u6c64", "\u5218\u6c64"),      # 老汤 -> 刘汤
    ("\u9646\u8096\u6ee1", "\u9646\u5c0f\u6ee1"),  # 陆肖满 -> 陆小满
    ("\u8096\u6ee1", "\u5c0f\u6ee1"),      # 肖满 -> 小满
    ("\u6c88\u9ed8", "\u5609\u8c6a"),      # 沈默 -> 嘉豪
    ("\u5609\u5174", "\u5609\u8c6a"),      # 嘉兴 -> 嘉豪
    ("\u5bb6\u8c6a", "\u5609\u8c6a"),      # 家豪 -> 嘉豪
    ("\u5609\u6b23", "\u5609\u8c6a"),      # 嘉欣 -> 嘉豪（本团语境下同一个人）
    ("\u7d20\u989c", "\u5919\u613f"),      # 素颜 -> 夙愿
    ("\u9057\u613f", "\u5919\u613f"),      # 遗愿 -> 夙愿
    ("\u5e08\u7236", "\u5e08\u5085"),      # 师父 -> 师傅
]

# 需要改名/加别名的节点（按当前 name 定位）
SISTER_OLD = "\u5218\u6cf7\u7684\u59b9\u59b9"           # 刘泷的妹妹
SISTER_NEW = "\u5218\u6c64"                              # 刘汤
SISTER_ALIASES = ["\u5218\u6cf7\u7684\u59b9\u59b9", "\u6d41\u6c64", "\u8001\u6c64"]
FACELESS_OLD = "\u65e0\u8138\u4eba"                      # 无脸人
FACELESS_NEW = "\u827e\u65af\u5229\u5c14\uff08\u9634\u9633\u5dee\u4e8b\u5f55\uff09"  # 艾斯利尔（阴阳差事录）
FACELESS_ALIASES = ["\u65e0\u8138\u4eba", "\u827e\u65af\u5229\u5c14"]
AISI_CROSS = (
    "\u3010\u8de8\u56e2\u540c\u4f4d\u4f53\u3011\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a"
    "\u4e0e g2_aisilie\uff08\u9b54\u5973\u88c1\u5224\u5385\uff09/ mg_aisilie\uff08\u9b54\u6cd5\u5c11\u5973 2\uff09/ "
    "mg3_aisilie\uff08\u6551\u8d4e\u7ebf\uff09\u4e3a\u540c\u4f4d\u4f53\u3002"
    "\u672c\u56e2\u5f62\u6001\uff1a\u6bb5 4 \u7f8e\u672f\u5ba4\u300c\u65e0\u8138\u4eba\u300dBOSS\uff0c\u6700\u7ec8\u5f62\u6001\u4e3a\u5c0f\u7f8a\u5f62\u8c61\u3001"
    "\u672c\u4f53\u662f\u753b\u753b\u7684\u9ad8\u4e2d\u5973\u751f\uff08\u5f85\u786e\u8ba4\u7ec6\u8282\u4ee5\u5f55\u97f3\u4e3a\u51c6\uff09\u3002"
)

# 主人已答 -> 这些 confirmed:false 的条目可以落盘了（否则 store 会降级跳过）
CONFIRM_IDS = {
    "yy_yuxiuli_airen": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u4e8e\u79c0\u4e3d\u7684\u300c\u7231\u4eba\u300d\u5b58\u5728\u4f46\u6ca1\u6709\u540d\u5b57\u3002",
    "yy_liulong_meimei": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u59d3\u540d\u5199\u4f5c\u300c\u5218\u6c64\u300d\uff08\u5218\u6cf7\u4e4b\u59b9\u3001\u5341\u4e94\u5e74\u524d\u5927\u697c\u7eb5\u706b\u8005\uff09\u3002",
    "yy_shenmo": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u540c\u4e00\u4eba\uff0c\u5c31\u53eb\u300c\u5609\u8c6a\u300d\u3002",
}
# extract 把同一个人拆成了两个节点 -> 合并（保留左边，右边并入）
MERGE_INTO = {"yy_xiaoman": "yy_luxiaoman"}

# 主人已答 → 从 pending 移到 resolved_by_owner
#   ⚠️ 只匹配 **item 文本**（不匹配 reason —— 第一版匹配了 reason，结果「三角村是哪位 PC 的老家」
#      因为 reason 里出现「KP」被误判成已答）。按具体 -> 宽泛排序。
#   ⚠️ 有些条目是「一问两半」（如 名称已答、机制未答）-> 给出 residual，把它作为新的待确认留下。
RESOLVED_RULES: list[tuple[tuple[str, ...], str, str | None]] = [
    (("KP",), "\u4e3b\u4eba\u786e\u8ba4\uff1aKP = pd\uff08NPC \u5168\u7531 pd \u626e\u6f14\uff09\uff1b"
              "\u4e03\u540d PC \u7684 PL \u89c1 canon", None),
    (("\u7ef0\u53f7",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u7ef0\u53f7\u4e0d\u7528\u7ba1\uff08\u4e0d\u4f5c\u5f52\u4eba\u4f9d\u636e\uff09", None),
    (("\u732b\u8138",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u732b\u8138\u8001\u592a\u592a\u4e0e\u9ec4\u76ae\u5b50\u662f\u4e24\u4e2a\u4e0d\u540c\u5b58\u5728",
     "\u9ed1\u96ea\uff0f\u56db\u6280\u80fd\u5c01\u5370\u7684\u5177\u4f53\u673a\u5236\uff1b\u9ec4\u76ae\u5b50\u662f\u5426\u4e3a\u4e8e\u79c0\u4e3d\u4f9d\u9644\u7684\u4e03\u53ea\u4f4e\u9636\u9b3c\u602a\u4e4b\u4e00"),
    (("\u5218\u6c64", "\u59b9\u59b9\u7684\u540d\u5b57", "\u7eb5\u706b"), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u59d3\u540d\u5199\u4f5c\u300c\u5218\u6c64\u300d",
     "\u6bb54 \u5218\u6cf7\u300c\u51a4\u9b42\u7ed5\u8eab\u300d\u5173\u952e\u65f6\u523b\u300c\u53d1\u4e94\u628a\u67aa\u300d\u7684\u673a\u5236\u4e0e\u6765\u6e90\uff08\u59d3\u540d\u90e8\u5206\u5df2\u7b54\uff09"),
    (("\u7389\u5c71",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u7389\u5c71\u5bb6\u662f\u5fa1\u4e09\u5bb6\u4e4b\u4e00\uff08\u5fa1\u4e09\u5bb6\u5305\u542b\u8f69\u82d1\u4e16\u5bb6\uff09\uff0c\u4e0d\u7b49\u540c\u4e8e\u8f69\u82d1\u4e16\u5bb6", None),
    (("\u5609\u8c6a", "\u5bb6\u742a"), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u540c\u4e00\u4eba\uff0c\u5c31\u53eb\u5609\u8c6a", None),
    (("\u4e09\u89d2\u6751", "\u8001\u5bb6"), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e09\u89d2\u6751 = \u6797\u5c0f\u9e22\u7684\u8001\u5bb6", None),
    (("\u7231\u4eba",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e8e\u79c0\u4e3d\u7684\u300c\u7231\u4eba\u300d\u6ca1\u6709\u540d\u5b57", None),
    (("\u8c1b\u542c", "\u591c\u9b47", "\u7b2c\u4e8c\u4eba\u683c"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u7b2c\u4e8c\u4eba\u683c\u4e0d\u5355\u72ec\u5efa\u8282\u70b9\uff0c\u5c31\u662f\u672c\u4eba\u7684\u6218\u6597\u5f62\u6001", None),
    (("\u827e\u65af\u5229\u5c14",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e0e g2_aisilie / mg_aisilie / mg3_aisilie \u662f\u540c\u4f4d\u4f53", None),
    # ---- 以下为主人当面答过、但上一轮漏写进本团补丁的（2026-10-05 补记）----
    (("\u4e3b\u64ad\u540d",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6807\u51c6\u5199\u6cd5\u300c\u7720\u7720\u300d", None),
    (("\u4e0a\u540a\u9b3c", "\u5c0f\u7eff\u6700\u7ec8", "\u5c0f\u7eff"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5c0f\u7eff\u4e0e\u5c0f\u7ea2\u662f\u4e24\u4e2a\u4e0d\u540c\u7684\u4eba\u2014\u2014"
     "\u5c0f\u7eff\uff08\u4e3b\u64ad\u56e2\u961f\uff09**\u8eab\u9996\u5206\u79bb**\uff1b\u5c0f\u7ea2 **\u7559\u4e0b\u4e00\u5177\u9057\u4f53**\uff08\u9b42\u88ab\u5438\u8d70\uff09\uff1b\u4e24\u4eba\u90fd\u5df2\u6b7b\uff0c\u5404\u81ea\u5206\u5f00\u5199",
     None),
    (("\u53cc\u738b\u4e4b\u6218",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u4e0d\u91cd\u8981\uff0c\u4e0d\u7528\u7ba1\uff08\u4e0d\u5c55\u5f00\uff09", None),
    (("\u4e09\u542c\u4e94\u773c",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u968f\u53e3\u8bf4\u7684\uff0c\u4e0d\u7528\u7ba1\uff08\u4e0d\u8fdb canon\uff09", None),
    (("\u8001\u65b9\u4e08\u540d\u5b57",), "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5c31\u5199\u300c\u8001\u65b9\u4e08\u300d", None),
    (("\u300c\u8001\u5e08\u300d\u7684\u8eab\u4efd", "\u300e\u8001\u5e08\u300f\u7684\u8eab\u4efd"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6bb57\u300c\u8001\u5e08\u300d= \u6797\u6e05\u82b7\uff08\u6797\u5c0f\u9e22\u7684\u5e08\u5085\uff09", None),
    (("\u6770\u514b\u76f8\u5173\u73a9\u6897", "\u4f60\u662f\u6770\u514b"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u672c\u56e2\u4e0d\u8ba1\u4e3a\u6770\u514b\u51fa\u573a**\uff08\u53ea\u7b97\u300c\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6\u300d\u90a3\u8fb9\uff09\uff1b"
     "\u73a9\u6897\u63d0\u53ca\u4e0d\u5165\u5173\u7cfb\u56fe", None),
    # ---- 按卡面证据即可结案（不是推测）----
    (("\u624b\u673a\u9b3c",),
     "\u5361\u9762\u8bc1\u636e\u7ed3\u6848\uff1a\u624b\u673a\u9b3c\uff0f\u5f55\u97f3\u673a\u9b3c\uff0f\u6f2b\u753b\u4e66\u9b3c\uff0f\u5012\u9709\u9b3c\uff0f\u7ea2\u96e8\u8863\u9b3c\uff0f\u4f1a\u8ba1\u9b3c "
     "\u5c5e\u4e8e\u79c0\u4e3d\uff08\u5361\u9762\u300c\u4f9d\u9644\u7684\u4f4e\u9636\u9b3c\u602a\u300d\u680f\uff09\uff1b**\u9ec4\u76ae\u94fe**\u5c5e\u8f69\u8f95\u51ac\u9752\uff08\u6bb53 \u62d8\u9b42\u6240\u5f97\uff09",
     None),
    (("PL \u753b\u50cf\u5f85\u8865", "pl_profiles"),
     "\u672c\u4f1a\u8bdd\u5df2\u8865\u9f50\uff1a10 \u540d PL \u7684\u672c\u56e2\u89d2\u8272\u4e0e\u753b\u50cf\u5df2\u5199\u5165"
     "\uff08\u300c\u5c0f\u949f\u300d=\u96ea\u4eba\uff08\u949f\u677e\u6797\uff09\uff09", None),
    # ---- 第二轮答疑（2026-10-05 夜）----
    (("\u9ec4\u76ae\u5b50\u662f\u5426\u4e3a\u4e8e\u79c0\u4e3d",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u4e0d\u662f**\u2014\u2014\u9ec4\u76ae\u5b50\uff08\u9ec4\u5927\u4ed9\uff09\u662f\u72ec\u7acb\u5b58\u5728\uff0c\u4e0e\u4e8e\u79c0\u4e3d\u4f9d\u9644\u7684\u4e03\u53ea\u4f4e\u9636\u9b3c\u602a\u65e0\u5173", None),
    (("\u9646\u5c0f\u6ee1\u7684\u771f\u5b9e\u7acb\u573a",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u7eaf NPC\uff0c\u666e\u901a\u670b\u53cb\uff08\u4e0d\u4fe1\u9b3c\u4f46\u4e00\u76f4\u7ed9\u7ebf\u7d22\uff09", None),
    (("\u8001\u660c\u8df3\u4e0b\u53bb", "\u8001\u660c"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u300c\u8001\u660c\u300d\u5c31\u662f\u4e3b\u4eba\u672c\u4eba\uff08ReGMeIoN\uff09\u2014\u2014"
     "\u4ed6\u5728\u672c\u56e2\u626e\u7684\u662f**\u5218\u6cf7**\uff0c\u6545\u8be5\u52a8\u4f5c\u5f52\u5230\u5218\u6cf7\u540d\u4e0b\uff1b"
     "\u6309\u94c1\u5f8b**\u73a9\u5bb6\u672c\u4eba\u4e0d\u5165\u56fe**", None),
    (("\u8881\u7cef\u7cef\u4e0e\u8089\u4f5b",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u6210\u7acb\uff0c\u5199\u8fdb canon**\uff08\u5c0f\u5b69\u2014\u5996\u602a\u670b\u53cb\u2014\u8089\u4f5b \u662f\u4e00\u6761\u7ebf\uff09", None),
    (("\u9759\u5ff5\u5c71\u9f99\u8109", "\u738b\u57ce\u4e0b\u6c34\u9053"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u90fd\u662f\u573a\u5916\u73a9\u6897\uff0c**\u4e0d\u5165\u4e16\u754c\u8bbe\u5b9a**", None),
    # ---- 第三轮（听录音核对后的答疑，2026-10-05 \u591c）----
    (("\u51a4\u9b42\u7ed5\u8eab", "\u4e94\u628a\u67aa"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u53ea\u662f\u73a9\u6897**\u2014\u2014\u5218\u6c64\u7684\u7075\u9b42\u4e0e\u5218\u6cf7\u4e92\u52a8\uff0c"
     "\u7c7b\u6bd4\u300a\u82f1\u96c4\u8054\u76df\u300b\u5384\u6590\u7409\u65af\uff08\u59b9\u59b9\u7ed9\u54e5\u54e5\u53d1 5 \u79cd\u6b66\u5668\uff09\uff0c\u4e0d\u5165\u5e93", None),
    (("\u5218\u773c", "\u6d41\u773c"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u8f6c\u5199\u91cc\u5176\u5b9e\u662f\u300c\uff08\u83cc\u7f8a\uff09\u6d41\u773c\u6cea\u4e86\u300d\u2014\u2014\u5373 **PL \u83cc\u7f8a\u54ed\u4e86**\uff08\u573a\u5916\uff09\uff1b"
     "\u53e6\u300c\u548c\u5c1a\u732e\u796d\u4e86\u4ed6\u7684\u5f92\u5f1f\u300d\u662f**\u5267\u60c5\u5185\u4e8b\u4ef6**\u3002\u6545\u300c\u5218\u773c\u300d\u4e0d\u5b58\u5728\uff0c\u4e0d\u5165\u5e93", None),
    (("\u9ea6\u514b",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u9ea6\u514b\u662f**\u8de8\u56e2\u89d2\u8272**\uff08\u4e0e\u6770\u514b\u5bc6\u5207\u76f8\u5173\uff09\uff0c"
     "\u672c\u56e2**\u53ea\u662f\u73a9\u6897\u63d0\u53ca** \u2192 \u672c\u56e2\u4e0d\u5165\u5e93", None),
    (("\u590f\u5bb9",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u8fd9\u91cc**\u542c\u9519\u4e86**\u2014\u2014\u4e0d\u662f\u590f\u5bb9\uff0c\u662f**\u65e2\u6709\u89d2\u8272\u300c\u590f\u672a\u7720\u300d**"
     "\uff08\u26a0\ufe0f \u5168\u5e93\u68c0\u7d22\u300c\u590f\u672a\u7720\u300d\u7ed3\u679c 0 \u547d\u4e2d\uff0c\u51fa\u5904\u5f85\u4e3b\u4eba\u8865\u5145\uff09", None),
    (("\u9ed1\u96ea",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u5e94\u4e3a\u300c**\u9ed1\u8840**\u300d\uff0c\u662f BOSS \u7684\u65b0\u6280\u80fd\uff08\u672f\u8bed\u66f4\u6b63\uff1a\u9ed1\u96ea\u2192\u9ed1\u8840\uff09", None),
    (("\u56db\u6280\u80fd", "\u5c01\u5370"),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u673a\u5236 = **\u89d2\u8272\u5361\u7684\u7b2c\u56db\u4e2a\u6280\u80fd\u4f1a\u88ab\u5c01\u5370**\uff08\u53e6\u4e00\u6bb5\u8bed\u97f3\u4e0e\u672c\u6761\u65e0\u5173\uff0c\u53ea\u662f\u573a\u666f\u63cf\u8ff0\uff09", None),
    (("\u6df1\u5733\u5b66",),
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6807\u51c6\u5199\u6cd5\u300c**\u6df1\u90d1\u5b66**\u300d", None),
]

# 主人 2026-10-05 追加澄清：段1 的主播「眠眠」= 既有角色「夏未眠」（段3 转写误作「夏容」也是她）
ANSWER_FIXES = [
    ("\u4e3b\u64ad\u540d",
     "\u4e3b\u4eba\u786e\u8ba4\uff1a\u6807\u51c6\u540d\u5b57\u662f\u300c**\u590f\u672a\u7720**\u300d\uff0c\u300c\u7720\u7720\u300d\u662f\u7b80\u79f0\uff0f\u6635\u79f0"
     "\uff08\u8f6c\u5199\u91cc\u7684 \u7ef5\u7ef5\uff0f\u68c9\u9762\uff0f\u660e\u660e\uff0f\u654f\u73a5\uff0f\u4e0b\u4f4d\u9762 \u90fd\u662f\u540c\u4e00\u4eba\uff09"),
    ("\u590f\u5bb9",
     "\u4e3b\u4eba\u786e\u8ba4\uff1a**\u542c\u9519\u4e86**\u2014\u2014\u4e0d\u662f\u590f\u5bb9\uff0c\u5c31\u662f\u65e2\u6709\u89d2\u8272\u300c**\u590f\u672a\u7720**\u300d"
     "\uff08=\u6bb51 \u4e3b\u64ad\u300c\u7720\u7720\u300d\uff1b\u6bb53 \u501f\u51fa\u5229\u5229\u5468\u8d26\u53f7\u7684\u4e5f\u662f\u5979\uff09"),
]
# 新建节点：夏未眠（既有角色，但本库里没有 -> 先在本团建节点 + 留出处待补）
NEW_CHARS = [
    {
        "id": "yy_xiaweimian", "name": "\u590f\u672a\u7720",
        "aliases": ["\u7720\u7720", "\u7ef5\u7ef5", "\u68c9\u9762", "\u660e\u660e", "\u654f\u73a5", "\u4e0b\u4f4d\u9762", "\u590f\u5bb9"],
        "identity": "\u63a2\u7075\u76f4\u64ad\u4e3b\u64ad\uff08\u76f4\u64ad\u95f4\u9886\u5934\u4eba\uff09",
        "groups": [GROUP], "tags": ["NPC"], "played_by": KP,
        "note": ("\u6bb51 \u5e26\u961f\u8fdb\u5e9f\u697c\u76f4\u64ad\u63a2\u7075\uff08\u76f4\u64ad\u95f4\u4eba\u6c14\u9ad8\u3001\u53f7\u540e\u88ab\u5c01\uff09\uff1b"
                 "\u6bb53 \u501f\u51fa\u5229\u5229\u5468\u8d26\u53f7\u7684\u4eba\uff08\u8f6c\u5199\u8bef\u4f5c\u300c\u590f\u5bb9\u300d\uff09\u3002"
                 "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u300c\u7720\u7720\u300d\u5c31\u662f\u5979\uff0c\u4e14\u5979\u662f**\u65e2\u6709\u89d2\u8272**\uff08\u26a0\ufe0f "
                 "\u5168\u5e93\u68c0\u7d22\u300c\u590f\u672a\u7720\u300d0 \u547d\u4e2d\uff0c\u51fa\u5904\uff0f\u6240\u5c5e\u56e2\u5f85\u4e3b\u4eba\u8865\u5145\uff0c\u5c4a\u65f6\u53ef\u5408\u5e76\u8282\u70b9\uff09\u3002"
                 "\u540c\u961f\uff1a\u6444\u50cf\u5c0f\u7ea2\uff08\u6bb51 \u7559\u4e0b\u9057\u4f53\uff09\u3001\u63a2\u5e97\u535a\u4e3b\u5c0f\u7eff\uff08\u6bb51 \u8eab\u9996\u5206\u79bb\uff09\u3002"),
        "confirmed": True,
    },
]
NAME_FIX = {"yy_shenzhenxue": "\u6df1\u90d1\u5b66"}      # 深圳学 -> 深郑学
RELEASE = {
    "yy_shenzhenxue": "\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u65b9\u540d\u5199\u4f5c\u300c\u6df1\u90d1\u5b66\u300d\uff08\u6bb56 \u5e26\u4eba\u4e0a\u5c71\u62cd\u7eaa\u5f55\u7247\uff0c\u6bb57 \u5c06\u88ab\u7ed1\u5165\u732e\u796d\u9635\uff09\u3002",
}


def sub_all(obj, pairs, counts):
    """递归替换字符串；返回新对象。"""
    if isinstance(obj, str):
        out = obj
        for old, new in pairs:
            if old in out:
                counts[old] = counts.get(old, 0) + out.count(old)
                out = out.replace(old, new)
        return out
    if isinstance(obj, list):
        return [sub_all(x, pairs, counts) for x in obj]
    if isinstance(obj, dict):
        return {k: sub_all(v, pairs, counts) for k, v in obj.items()}
    return obj


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    if not PATCH.is_file():
        print(f"!! 没有补丁: {PATCH}")
        return 1
    patch = json.loads(PATCH.read_text(encoding="utf-8"))

    # --- 1. played_by ---
    pl_fixes = []
    for c in patch.get("characters") or []:
        name = (c.get("name") or "").strip()
        tags = c.get("tags") or []
        is_pc = "PC" in tags
        want = PL_BY_NAME.get(name) if is_pc else KP
        if want and c.get("played_by") != want:
            pl_fixes.append((c.get("id"), c.get("played_by"), want, "PC" if is_pc else "NPC"))
            c["played_by"] = want
    # 跨团/无关节点不动（既不是 PC 也没有 NPC/BOSS 标签的，保持原样交给 store）
    for c in patch.get("characters") or []:
        if not (set(c.get("tags") or []) & {"PC", "NPC", "BOSS"}):
            c["played_by"] = c.get("played_by") or "\u5f85\u786e\u8ba4"

    # --- 2. 文本归一 ---
    counts: dict[str, int] = {}
    patch = sub_all(patch, RENAMES, counts)

    # --- 3. 改名 + 别名 ---
    ren = []
    for c in patch.get("characters") or []:
        nm = (c.get("name") or "").strip()
        if nm == SISTER_OLD or c.get("id") == "yy_liulongmeimei":
            if c.get("name") != SISTER_NEW:
                ren.append((c.get("id"), c.get("name"), SISTER_NEW))
                c["name"] = SISTER_NEW
            for a in SISTER_ALIASES:
                if a not in (c.get("aliases") or []):
                    c.setdefault("aliases", []).append(a)
        if nm == FACELESS_OLD or c.get("id") == "yy_wulianren":
            if c.get("name") != FACELESS_NEW:
                ren.append((c.get("id"), c.get("name"), FACELESS_NEW))
                c["name"] = FACELESS_NEW
            for a in FACELESS_ALIASES:
                if a not in (c.get("aliases") or []):
                    c.setdefault("aliases", []).append(a)
            if "\u8de8\u56e2\u540c\u4f4d\u4f53" not in (c.get("tags") or []):
                c.setdefault("tags", []).append("\u8de8\u56e2\u540c\u4f4d\u4f53")
            if AISI_CROSS not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + AISI_CROSS).strip()
        if c.get("id") == "yy_shenmo":
            for a in ["\u6c88\u9ed8", "\u5609\u5174", "\u5bb6\u8c6a"]:
                if a not in (c.get("aliases") or []):
                    c.setdefault("aliases", []).append(a)
        if c.get("id") == "yy_luxiaoman":
            for a in ["\u9646\u8096\u6ee1", "\u8096\u6ee1", "\u5c0f\u7f51"]:
                if a not in (c.get("aliases") or []):
                    c.setdefault("aliases", []).append(a)

    # --- 4b. 改名 + 主人已答的 confirmed:false 条目 -> 放行（并摘掉「待确认」标签）---
    released = []
    for c in patch.get("characters") or []:
        cid = c.get("id")
        if cid in NAME_FIX and (c.get("name") or "") != NAME_FIX[cid]:
            ren.append((cid, c.get("name"), NAME_FIX[cid]))
            c["name"] = NAME_FIX[cid]
        if cid in RELEASE and not c.get("confirmed", True):
            c["confirmed"] = True
            c["pending_reason"] = ""
            c["tags"] = [t for t in (c.get("tags") or []) if t != "\u5f85\u786e\u8ba4"]
            note = RELEASE[cid]
            if note not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + note).strip()
            released.append(cid)
        elif cid in CONFIRM_IDS and not c.get("confirmed", True):
            c["confirmed"] = True
            c["pending_reason"] = ""
            c["tags"] = [t for t in (c.get("tags") or []) if t != "\u5f85\u786e\u8ba4"]
            note = CONFIRM_IDS[cid]
            if note not in (c.get("note") or ""):
                c["note"] = ((c.get("note") or "").rstrip() + " " + note).strip()
            released.append(cid)
    # 已放行的条目也别再挂「待确认」标签（宁可多清，不留脏标签）
    for c in patch.get("characters") or []:
        if c.get("confirmed", True) and "\u5f85\u786e\u8ba4" in (c.get("tags") or []):
            c["tags"] = [t for t in c["tags"] if t != "\u5f85\u786e\u8ba4"]

    # --- 3b. 别名清洗：去重、去掉与正名同形、去空 ---
    alias_clean = 0
    for c in patch.get("characters") or []:
        name = (c.get("name") or "").strip()
        seen: set[str] = set()
        clean = []
        for a in c.get("aliases") or []:
            a = (a or "").strip()
            if not a or a == name or a in seen:
                alias_clean += 1
                continue
            seen.add(a)
            clean.append(a)
        if "aliases" in c or clean:
            c["aliases"] = clean

    # --- 4c. 同人合并（extract 拆出的重复节点）---
    merged = []
    for c in list(patch.get("characters") or []):
        cid = c.get("id")
        if cid in MERGE_INTO:
            dst_id = MERGE_INTO[cid]
            dst = next((x for x in patch["characters"] if x.get("id") == dst_id), None)
            if dst is None:
                continue
            merged.append((cid, dst_id))
            for a in [c.get("name")] + list(c.get("aliases") or []):
                if a and a not in (dst.get("aliases") or []) and a != dst.get("name"):
                    dst.setdefault("aliases", []).append(a)
            patch["characters"] = [x for x in patch["characters"] if x.get("id") != cid]
    # 端点重写（关系与更新都指向被合并的 id）
    def remap(obj):
        if isinstance(obj, dict):
            out = {}
            for k, v in obj.items():
                if k in ("from", "to") and isinstance(v, str) and v in MERGE_INTO:
                    v = MERGE_INTO[v]
                out[k] = remap(v)
            return out
        if isinstance(obj, list):
            return [remap(x) for x in obj]
        return obj
    patch = remap(patch)
    # 合并后可能出现重复关系 -> 去重
    seen_rel = set()
    rels = []
    for r in patch.get("relations") or []:
        key = (r.get("from"), r.get("to"), r.get("type"))
        if key in seen_rel:
            continue
        seen_rel.add(key)
        rels.append(r)
    patch["relations"] = rels

    # --- 5. pending 分流（保留已有 resolved_by_owner，保证可重跑）---
    already = {str(a.get("item")) for a in (patch.get("resolved_by_owner") or [])}
    keep, answered = [], []
    for p in patch.get("pending") or []:
        item = str(p.get("item") or "")
        if item in already:
            continue
        hit, residual = None, None
        for marks, note, res in RESOLVED_RULES:
            if any(m in item for m in marks):
                hit, residual = note, res
                break
        if hit:
            answered.append({**p, "owner_answer": hit})
            if residual:
                keep.append({"item": residual, "reason": "\u8be5\u6761\u672c\u662f\u300c\u4e00\u95ee\u4e24\u534a\u300d\uff0c\u5df2\u7b54\u90e8\u5206\u89c1 owner_answer\uff0c\u5269\u4e0b\u8fd9\u534a\u4ecd\u5f85\u786e\u8ba4",
                             "segment": p.get("segment")})
        else:
            keep.append(p)
    # 去重：残余条目可能与原有条目同文（如「黄皮子是否为…七只低阶鬼怪之一」）
    seen: set[str] = set()
    deduped = []
    for k in keep:
        key = str(k.get("item") or "").strip()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(k)
    keep = deduped
    patch["pending"] = keep
    patch["resolved_by_owner"] = (patch.get("resolved_by_owner") or []) + answered

    # --- 6a. 追加澄清：修正已答条目的答案文本（眠眠=夏未眠）---
    fixed_ans = 0
    for a in patch.get("resolved_by_owner") or []:
        item = str(a.get("item") or "")
        for mark, ans in ANSWER_FIXES:
            if mark in item and a.get("owner_answer") != ans:
                a["owner_answer"] = ans
                fixed_ans += 1
    # --- 6a2. 新建节点（夏未眠，含出处待补提示）---
    have = {c.get("id") for c in (patch.get("characters") or [])}
    added_chars = []
    for nc in NEW_CHARS:
        if nc["id"] not in have:
            patch.setdefault("characters", []).append(copy.deepcopy(nc))
            added_chars.append(nc["id"])

    # --- 6b. 杰克：主人确认「本团不计出场」-> 撤掉 add_groups/add_events，
    #     否则下次再跑 store 会把本团又加回杰克的 groups 里 ---
    jack_fix = 0
    for u in patch.get("character_updates") or []:
        if u.get("id") != "cross_jieke":
            continue
        u["add_groups"] = [g for g in (u.get("add_groups") or []) if g != GROUP]
        u["add_events"] = [e for e in (u.get("add_events") or []) if e.get("group") != GROUP]
        note = ("\u4e3b\u4eba 2026-10-05 \u786e\u8ba4\uff1a\u672c\u56e2\u91cc\u73a9\u5bb6\u73a9\u6897\u63d0\u53ca\u6770\u514b"
                "\uff08\u300c\u4f60\u662f\u6770\u514b\u300d\u300c\u5f00\u819b\u624b\u6770\u514b\u300d\uff09\uff0c"
                "**\u4e0d\u8ba1\u4e3a\u6770\u514b\u51fa\u573a**\uff08\u53ea\u7b97\u300c\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6\u300d\u90a3\u8fb9\uff09\u3002")
        # \u26a0\ufe0f \u8be5\u88c1\u51b3\u5df2\u76f4\u63a5\u5199\u8fdb\u751f\u4ea7\u6570\u636e\uff08store \u7684 append_note \u4e0d\u53bb\u91cd\uff0c
        #    \u518d\u5165\u5e93\u4e00\u6b21\u4f1a\u628a\u540c\u4e00\u53e5\u518d\u8ffd\u4e00\u904d\uff09-> \u8fd9\u91cc\u6e05\u7a7a\uff0c\u53ea\u4fdd\u7559\u4e8b\u4ef6\u4e0e groups \u7684\u64a4\u9500
        if u.get("append_note"):
            jack_fix += 1
        u["append_note"] = ""
    patch.setdefault("_meta", {})
    patch["_meta"]["owner_review"] = "2026-10-05 三轮当面答疑（KP/PL、专名、同位体、地点）"

    # --- 报告 ---
    print(f"补丁: {PATCH.name}")
    print(f"played_by 修正 {len(pl_fixes)} 条:")
    for cid, old, new, kind in pl_fixes:
        print(f"  {cid:<26} {str(old):<10} -> {new:<10} [{kind}]")
    print("文本归一命中:")
    for old, new in RENAMES:
        if counts.get(old):
            print(f"  {old} -> {new}  ×{counts[old]}")
    print(f"改名/别名 {len(ren)} 条:")
    for cid, old, new in ren:
        print(f"  {cid:<26} {old} -> {new}")
    print(f"放行 confirmed:false -> true: {len(released)} 条 {released}")
    print(f"别名清洗: 去掉 {alias_clean} 条（重复/与正名同形/空）")
    print(f"同人合并: {len(merged)} 条 " + ", ".join(f"{a}->{b}" for a, b in merged))
    print(f"pending: {len(keep)} 条仍待确认 · 本轮新增已答 {len(answered)} 条 "
          f"(累计 {len(patch.get('resolved_by_owner') or [])})")
    print(f"杰克出场修正: {jack_fix} 条（撤掉本团 add_groups/add_events）")

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
