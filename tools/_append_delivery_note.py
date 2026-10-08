# -*- coding: utf-8 -*-
"""Append the 2026-10-05 夜间「答疑落地 + 入库」续记 to the two delivery docs.

Append-only on purpose: the existing sections are already reviewed, so this adds a clearly
dated block instead of rewriting them.

usage: python tools/_append_delivery_note.py [--apply]
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))

NOTE = """

---

# ✅ 夜间续记：5 轮答疑落地 + 两团入库（2026-10-05 夜）

> 生产库基线：`162 角色 / 164 关系 / 8 players / 10 画像` → **`231 角色 / 190 关系 / 10 players / 12 画像`**
> （写前自动备份；`check_html.py` 14 张关系图全部通过）

| 团 | 入库 | 关系图 |
|---|---|---|
| **阴阳差事录 超自然怪谈** | 新增 **27 角色** / 更新 1 / 新增 **6 关系** / 待确认 21 | `产出\\阴阳差事录 超自然怪谈_关系图.html`（27/6） |
| **魔法少女育成计划 6** | 新增 **42 角色** / 更新 2 / 新增 **20 关系** / 待确认 23 | `产出\\魔法少女育成计划 6_关系图.html`（44/21） |

## 1. 主人答了什么（都写进 canon + 补丁）

- **阴阳差事录**：KP=**pd**（NPC 全由他代演）；PC↔PL：于秀丽=俊松、刘泷=ReGMeIoN、叶千筱=菌羊、
  林小鸢=雪人、袁糯糯=往、轩辕冬青=宽、知行=牛爷；**绰号不作归人依据**；
  专名归一 **刘汤 / 陆小满 / 嘉豪 / 师傅的夙愿**；「玉山家 = 御三家之一（御三家包含轩苑世家）——不等同」；
  三角村=林小鸢老家；**艾斯利尔与 g2/mg/mg3 是同位体**（各自成节点 + `跨团同位体` + 交叉引用）；
  第二人格不单独建节点（当作战形态）；「双王之战」「三听五眼」判为不用管；主播名=**眠眠**；
  段1 小绿/小红是**两个不同的人**；段7「老师」=林清芷。
- **魔法少女育成计划 6**：KP=**pd**（5 名后辈 NPC 由他代演）；前辈 PL：纱纱=往、茨维希=ReGMeIoN、
  白萱=雪人、露西菈=菌羊、**第 5 名前辈=宽（卡待补）**；辅导配对：纱纱→析芝花田、茨维希→雨、
  白萱→法尔纳塞刻刻蒂芙尼、露西菈→神川玛利亚、宽→杜鹃（院）；
  同名节点按同位体：神川玛利亚→`g2_shenchuan`、马卡龙→`mg_makalong`、神前早月→`mg3_zaoyue`、李安→`mg4_lian`；
  段12「嘉豪」= 神川玛利亚绰号；**杰克玩偶/唱片/知风牧场 = `cross_jieke` 本人出场**；段11「牢昌」= 桌边玩梗不入库。

## 2. 后辈卡（图卡）补充

5 张后辈卡是**图片**（`素材\\魔法少女育成计划 6\\带带魔法少女后辈卡\\<名>.jpg` + `_立绘.jpg`），
用读图方式录入，已写进团 canon：

| 后辈 | 能力 | HP/特长 |
|---|---|---|
| 杜鹃（院） | 扫把飞行·极速猛冲／专属司机／徘徊训练 | 15 · 驾驶/妙手/导航/伪造文书 |
| 雨 | 撑伞反弹／伞面降雨／力气大 | 21 · 投掷 |
| 法尔纳塞 刻刻 蒂芙尼 | 时间三术（暂时世界/转流时间/倒果为因） | 17 · 历史/图书馆/聆听/射击/骑术/锁匠/演奏 |
| 神川 玛利亚 | 万众瞩目手术时间／新生之喜／被动受肉 | 16 · 生物学/聆听/电汽维修/急救 |
| 析芝 花田 | 花田芽盛开／域展开·万轮葵葬林／被动永世向阳花 | 20 · 植物学/观察/恐吓/斗殴/心理学 |

## 3. 顺带补齐的

- 库里缺的 **俊松 / 牛爷** 两名 PL 已建档（占位 uid `u_local_junsong` / `u_local_niuye`，拿到 QQ 号可替换）。
- 10 名 PL 全部写入本团角色（`player_updates.add_roles`）与团履历（`profile_updates.add_groups_played` / `add_cards`）。
- **PL 画像散文**：从 7 + 12 段草稿的「PL 表现」小节机械汇总进 `impressions`，
  再逐 PL 由 LLM 蒸馏（按团分键）写进 `speaking_style` / `rp_style`。工具：`tools\\_pl_profile_from_drafts.py`。

## 4. 新增/常用的审阅与落地工具

| 工具 | 用途 |
|---|---|
| `tools\\_review_patch.py --ids / --dangling` | 补丁速览；**列悬空端点**（store 会跳过这些关系） |
| `tools\\_fix_patch_yy.py` / `_fix_patch_mg6.py` | 把主人答疑机械地写进补丁（可重放、幂等、带备份） |
| `tools\\_shadow_sync.py` | 一键重建影子库（生产库零风险预演） |
| `tools\\_show_group_chars.py` | 列某团的入库节点（id/名字/标签/played_by/别名） |
| `tools\\_pl_report.py [--pl 名字]` | PL 名册与画像覆盖；`--pl` 看单个画像全文 |
| `tools\\_pl_profile_from_drafts.py` | 从段草稿抽 PL 表现 → 画像 |
| `tools\\_fix_pl.py` | 写 PL 角色/团履历（含新建 PL） |

## 5. 仍未完成

1. **待确认**：阴阳差事录 21 条 + 魔法少女6 23 条（`_review_patch.py --group X` 看清单）。
2. **宽的第 5 名前辈卡**：占位节点 `mg6_diwu_qianbei` 等补卡后用 `set_name` 改名。
3. **展示站**：两团都还没建站（绘本/CG/原声/立绘）；立绘口径未变（PC 严格用卡内原图）。
"""

TARGETS = [
    ROOT / "docs" / "\u65b0\u56e2\u8f6c\u5f55-\u4ea4\u4ed8\u8bf4\u660e-2026-10-05.md",
    WS / ".trpg" / "reports" / "\u65b0\u56e2\u8f6c\u5f55_\u4f1a\u8bdd\u62a5\u544a_20261005.md",
]


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    apply = "--apply" in sys.argv
    for p in TARGETS:
        if not p.is_file():
            print(f"!! 缺文件 {p}")
            continue
        text = p.read_text(encoding="utf-8")
        if "\u591c\u95f4\u7eed\u8bb0" in text:
            print(f"  ok      {p.name}: 已有续记，跳过")
            continue
        print(f"  {'append' if apply else 'dry'}  {p.name}: +{len(NOTE)} 字符")
        if apply:
            p.write_text(text.rstrip() + "\n" + NOTE, encoding="utf-8")
    if not apply:
        print("\n(dry-run; 加 --apply 写入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
