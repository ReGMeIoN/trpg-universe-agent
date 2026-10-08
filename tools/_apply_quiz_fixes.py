# -*- coding: utf-8 -*-
"""把「听录音答疑」的结论落到数据与文档上（2026-10-03 那一轮 Q01–Q18）。

做三件事：
  1) 补丁里 `sjt_yanshu_zhanglao` 的显示名「艳术长老」→「**鼹鼠人长老**」（id 不变），
     identity/note 里的「艳术」一并改成「鼹鼠人」。
  2) 在《剧情编年史》末尾追加「答疑校正表」（幂等：先删旧表再写）。
  3) 打印结果；改完由调用方跑 store --apply 与 visualize。

用法:
    .venv\\Scripts\\python.exe tools\\_apply_quiz_fixes.py            # dry-run
    .venv\\Scripts\\python.exe tools\\_apply_quiz_fixes.py --write
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
CHRONICLE = WS / "产出" / "圣剑英雄谭_剧情编年史.md"
MARK = "## 附二：答疑校正表"

# (转写里的写法, 正确写法/结论, 出处)
CORRECTIONS = [
    ("黄泳多", "**煌炎国**", "Q02"),
    ("死鬼", "**尸鬼**", "Q03"),
    ("吉祖哥", "**肌肉哥**（段2 那位肌肉型候选人）", "Q04"),
    ("沙沙 / 杀杀", "**飒飒米（pd）**", "Q04"),
    ("雪人沙铃", "**不存在** —— 原句「给雪人塞了点零食吃」", "Q04"),
    ("诺亚 / 压实", "**都不采信** —— 灾星就是流星亚什本人", "Q05"),
    ("艳术 / 焰术 / 炎术", "**鼹鼠人**（原句「毁灭了鼹鼠人王国」）", "Q07"),
    ("80铁饭", "**80铁砧**（矮人大师真名）", "Q08"),
    ("马斯特", "master 的音译 —— **称呼不是名字**", "Q08"),
    ("格洛斯达", "**格洛斯塔**（黑夜之志）", "Q09"),
    ("无龙茶", "**乌龙茶** —— 桌边梗：宽（PL）是调酒师，捏他《蔚蓝之海》", "Q10"),
    ("哈基米", "**戏称** —— 冰晶圣兽无正式名", "Q12"),
    ("蓝丰炸药", "**不是名字** —— 雪人随口说的「难绷炸药」", "Q13"),
    ("写者之实 / 血者之实", "**贤者之石**", "Q14"),
    ("腐败的人", "**不是名字** —— 往的吐槽「真是腐败啊」", "Q15"),
    ("士兮", "**四骑士**", "Q16"),
    ("敌者 / 贤将 / 铁将", "**铁匠** —— 第十二位贤者的代号", "Q16"),
    ("高文", "**高温**", "Q16"),
    ("西修 / 希秀", "日语「**师傅**」（ししょう）—— 称呼不是人名", "Q17"),
    ("捷克", "**杰克**（场外玩梗，不入库）", "Q17"),
    ("色蛮亚", "**瑟莱娅·阿尔根**（以角色卡为准）", "Q17"),
    ("背了一把火箭", "**背了一把火剑**", "Q18"),
    ("有六个", "**六把圣剑**", "Q18"),
    # ---- 第二轮 R01–R08 ----
    ("古人的清洗", "古人的**侵袭**（「古人」这批机械敌人主人亦无印象，名称存疑）", "R01"),
    ("四骑士的名字", "**四骑士都没有名字**，直接用代号（饥荒/战争/瘟疫/死亡）", "R02"),
    ("核心拔掉", "核心被拔掉后**肉不再再生、开始脱落**", "R02"),
    ("虚空镇店 / 虚空神殿", "**虚空圣殿**", "R03"),
    ("第十一把剑", "象征**平衡**的虚无之剑（永生）＝与「均衡的意志/世界意志」同一回事", "R03"),
    ("爱人帮你们消了毒", "「**矮人**」帮你们消了毒", "R04"),
    ("爱人国", "**矮人国**", "R08"),
    ("牛家", "「**刘家**」＝**琉珈·深谣**", "R06"),
    ("追兵不是真心追", "**确认放水**（做样子追）", "R06"),
    ("红色蝴蝶", "是「**猎虫一方**」的实力（会复活猎虫），**不是队伍队友**", "R07"),
    ("三重", "「三重」＝**三虫**（第三只虫）", "R07"),
    ("毁灭了艳术能亡国", "毁灭了**鼹鼠人**王国 —— 凶手是「**莉亚·岩心**」", "R08"),
]

# 第二轮：这里的关系端点被编年史的"以宽为主语"带偏了，需要改到正确的人身上
RELATION_FIXES = [
    {"from": "sjt_yanshu_zhanglao", "to": "sjt_bachongying", "new_to": "sjt_liya",
     "why": "主人确认：当年毁灭鼹鼠人王国的是莉亚·岩心（ReGMeIoN），不是八重樱"},
]


# 这轮问答已彻底解决的 pending 条目（按 JSON 文本匹配，命中即整条移除）
RESOLVED_KW = [
    "威尔娜/维尼拉",
    "「黄泳多」疑为「煌炎国」",
    "「吉祖哥」（约5132）",
    "「石痕剑格」信件的署名",
    "灾星名字「诺亚/压实」",
    "矮人大师的名字",
    "「无龙茶」与「传奇调酒师宽」",
    "「企鹅人」是实际种族名",
    "「哈基米」是冰晶圣兽的正式名",
    "瘟疫骑士的「写者之实/血者之实」",
    "「士兮」「铁匠/贤将」「高文」「敌者」",
    "女巫「色蛮/瑟蛮」",
    "「背火箭的矮人」「六把圣剑」",
    # ---- 第二轮已解决 ----
    "「古人/机械腐烂敌人」的正式名称",   # 主人亦无印象, 不再追
    "战争骑士真名",                      # 四骑士无名, 已确认
    "村庄死亡人数",                      # 就是"大概几千人"
    "鲛人族追兵是否真心追击",            # 已确认放水
    "当年毁灭鼹鼠人王国的 PC",           # 是莉亚·岩心
]
# 部分解决：改写成"剩下的疑问"，不要整条丢
PENDING_REWRITE = [
    ("「艳术/焰术/炎术」种族名",
     "当年毁灭鼹鼠人王国的 PC 是哪一位",
     "种族名已确认＝鼹鼠人；当年那位 PC 仍未确认"),
    ("「死鬼」疑为「尸鬼」",
     "「古人/机械腐烂敌人」的正式名称与性质",
     "「死鬼」已确认＝尸鬼；机械敌人的正式名仍未确认"),
    ("瘟疫骑士正式名是否即「腐败的人」",
     "村庄死亡人数「几千人」的准确数字",
     "瘟疫骑士本无名（已确认）；死亡人数未确证"),
    ("三重猎虫「超越之光亚尼姆斯",
     "三重猎虫的归属与能力细节（红色蝴蝶的复活/治疗）",
     "三个名字已确认；归属与能力细节仍未确认"),
    ("神庙中看不清面目者的身份",
     "神庙中那位看不清面目者的**具体身份**（第十一把剑已确认为象征平衡的虚无之剑）",
     "剑的含义已解决；那人身份仍不明"),
    ("大桥上母女是否被PC杀死",
     "大桥母女的最终结局（主人亦记不得，推测已死）",
     "不要写死；仅记录「被救下/被放走」与「后续不明」"),
]


def prune_pending(doc: dict) -> None:
    pend = doc.get("pending") or []
    kept, dropped, rewritten = [], [], []
    for p in pend:
        blob = json.dumps(p, ensure_ascii=False)
        hit = next((r for r in PENDING_REWRITE if r[0] in blob), None)
        if hit:
            _, new_item, new_reason = hit
            if isinstance(p, dict):
                p = dict(p)
                p["item"] = new_item
                p["reason"] = new_reason
            kept.append(p)
            rewritten.append(new_item)
            continue
        if any(k in blob for k in RESOLVED_KW):
            dropped.append(blob[:80])
            continue
        kept.append(p)
    doc["pending"] = kept
    for x in rewritten:
        print(f"  [pending-改写] {x}")
    for x in dropped:
        print(f"  [pending-移除] {x}")


def fix_relations(write: bool) -> None:
    """关系端点修正 —— 必须直接改生产库：store 只支持"新增关系"，不支持改/删端点。"""
    rels_file = WS / "数据" / "relations.json"
    if not rels_file.is_file():
        print("  !! 找不到 relations.json")
        return
    doc = json.loads(rels_file.read_text(encoding="utf-8"))
    changed = 0
    for fx in RELATION_FIXES:
        hits = [r for r in doc.get("relations") or []
                if r.get("from") == fx["from"] and r.get("to") in (fx["to"], fx["new_to"])]
        if not hits:
            print(f"  [关系] {fx['from']} 相关关系不存在（可能已处理）")
            continue
        keep = hits[0]
        if keep.get("to") != fx["new_to"]:
            keep["to"] = fx["new_to"]
            changed += 1
        ev = keep.get("event") or ""
        if "主人确认" not in ev:
            keep["event"] = f"{ev}（2026-10-03 主人确认：{fx['why']}）"
            changed += 1
        # 同一组关系里多出来的（例如 store 又把补丁里那条旧关系加了回来）一律删掉，避免重复
        for extra in hits[1:]:
            doc["relations"].remove(extra)
            changed += 1
            print(f"  [关系] 删除重复: {extra.get('from')} → {extra.get('to')} ({extra.get('type')})")
        print(f"  [关系] 保留: {keep.get('from')} → {keep.get('to')} ({keep.get('type')})")
    if not changed:
        print("  [关系] 无需修正（幂等）")
        return
    if write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(rels_file, rels_file.with_suffix(f".json.bak_relfix_{stamp}"))
        rels_file.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_patch(write: bool) -> None:
    doc = json.loads(PATCH.read_text(encoding="utf-8"))
    hit = next((c for c in doc.get("characters") or [] if c.get("id") == "sjt_yanshu_zhanglao"), None)
    if not hit:
        print("  !! 补丁里没找到 sjt_yanshu_zhanglao")
        return
    old_name = hit.get("name")
    hit["name"] = "鼹鼠人长老"
    for key in ("identity", "note"):
        if isinstance(hit.get(key), str):
            hit[key] = hit[key].replace("艳术", "鼹鼠人")
    print(f"  [补丁] sjt_yanshu_zhanglao: name {old_name!r} -> '鼹鼠人长老'")

    # 关键: 库里已存在这个 id, characters[] 里的改名不会被 store 采纳(会被当重复跳过);
    # 必须走 character_updates 的 set_name 才会更新既有节点(merger 已支持)。
    ups = doc.setdefault("character_updates", [])
    up = next((u for u in ups if u.get("id") == "sjt_yanshu_zhanglao"), None)
    if up is None:
        ups.append({"id": "sjt_yanshu_zhanglao", "set_name": "鼹鼠人长老",
                    "confirmed": True, "segment": "角色卡"})
        print("  [补丁] character_updates += sjt_yanshu_zhanglao.set_name")
    elif up.get("set_name") != "鼹鼠人长老":
        up["set_name"] = "鼹鼠人长老"
        up["confirmed"] = True
        print("  [补丁] character_updates.set_name 已更新")
    else:
        print("  [补丁] character_updates.set_name 已存在")

    prune_pending(doc)

    # 补丁里的关系端点也要跟着改，否则下次 store 又会把旧端点当新关系加回来
    for r in doc.get("relations") or []:
        for fx in RELATION_FIXES:
            if r.get("from") == fx["from"] and r.get("to") == fx["to"]:
                r["to"] = fx["new_to"]
                print(f"  [补丁-关系] {fx['from']} → {fx['to']} 改为 → {fx['new_to']}")

    if write:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        shutil.copy2(PATCH, PATCH.with_suffix(f".json.bak_quiz_{stamp}"))
        PATCH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def apply_chronicle(write: bool) -> None:
    lines = ["", "---", "", f"{MARK}（2026-10-03 听录音逐条确认）", "",
             "> 下表是**转写原样 vs 实际内容**的对照，用来读正编时排雷。正编正文保留了当时的转写原样（史料价值），",
             "> 以本表为准。凡标「不存在 / 不采信」的，都是 ASR 听串或场外玩梗，**不要写进设定**。", "",
             "| 转写里的写法 | 实际 | 出处 |", "|---|---|---|"]
    for a, b, src in CORRECTIONS:
        lines.append(f"| {a} | {b} | {src} |")
    lines.append("")
    block = "\n".join(lines)
    text = CHRONICLE.read_text(encoding="utf-8")
    idx = text.find("\n---\n\n" + MARK)
    if idx >= 0:
        text = text[:idx]
    print(f"  [编年史] 追加校正表 {len(CORRECTIONS)} 条（幂等）")
    if write:
        CHRONICLE.write_text(text.rstrip() + "\n" + block, encoding="utf-8")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    apply_patch(write)
    fix_relations(write)
    apply_chronicle(write)
    print("\n[dry-run] 未落盘" if not write else "\nOK 已落盘")
    if write:
        print("下一步: store --apply --allow-production  然后 visualize --group 圣剑英雄谭")
    return 0


if __name__ == "__main__":
    sys.exit(main())
