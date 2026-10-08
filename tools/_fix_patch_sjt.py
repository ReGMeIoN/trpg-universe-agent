# -*- coding: utf-8 -*-
"""按主人 2026-10-03 的逐条答疑，修正「圣剑英雄谭」入库补丁。

主人确认的映射（见 .trpg/canon/canon_rules.md 的新团小节）：
  KP = 菌羊（NPC 全由 KP 演）· ReGMeIoN 是 PL 不是 KP
  妮娜·可可=往 · 流星亚什=雪人 · 琉珈·深谣=NPC(菌羊) · 八重樱=宽 · 莉亚·岩心=ReGMeIoN · 飒飒米=pd
  八重樱的剑 = 烟剑（卡面误写「时之圣剑·以锐克武」）
  飒飒米要入库（录音里没出现卡名，只写角色卡设定，不编造事件）

用法：
    .venv\\Scripts\\python.exe tools\\_fix_patch_sjt.py            # dry-run 只看改动
    .venv\\Scripts\\python.exe tools\\_fix_patch_sjt.py --write    # 落盘（自动备份）
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

NPC_PLAYER = "菌羊"
PL_MAP = {
    "sjt_nina": "往",
    "sjt_yashi": "雪人",
    "sjt_bachongying": "宽",
    "sjt_liya": "ReGMeIoN",
}
# 琉珈·深谣：主人答「是 NPC（菌羊演）」-> 标签从 PC 改 NPC
NPC_CARD_IDS = {"sjt_liujia"}

NEW_CHAR = {
    "id": "sjt_sasami",
    "name": "飒飒米",
    "aliases": ["撒撒米", "音游诗人"],
    "identity": "提夫林 / 音之圣剑「小尤里」持有者 / 流浪吟游诗人",
    "groups": ["圣剑英雄谭"],
    "tags": ["PC"],
    "played_by": "pd",
    "note": (
        "角色卡设定：黑肤红瞳的吟游诗人，理念「事不关己，只是一味传唱着英雄的故事」；"
        "音之圣剑「小尤里」可演奏使气氛缓和/音速斩击/令人狂舞/声化实体的音墙；"
        "**录音转写里查不到「飒飒米/撒撒米」**（主人：语音里可能只以称呼出现）→ 只写角色卡设定，不编造剧情事件"
    ),
    "events": [],
    "confirmed": True,
    "segment": "角色卡",
}

# pending 里已被主人答疑解决 / 已裁决的条目（按 JSON 文本匹配，命中即整条移除）
RESOLVED = [
    "五名PC的PL归属未确认",
    "pd在本团的扮演角色",
    "菌羊（转写「军阳/君羊」）在本团扮演的角色",
    "音近/形近人名归一存疑",
    "段6大量玩梗",              # 主人裁决: 标为玩梗不入库
    "流星亚什的扮演者是否为雪人",  # 已确认: 雪人
]
# 部分解决：整条留着会丢掉还没定论的部分 -> 改写成剩下的疑问
REWRITE = {
    "天津诗情诗": (
        "段6 其余转写词「士兮」「铁匠/贤将」「高文」「敌者」的准确写法及是否为专有名词"
        "（「天津诗情诗」已裁决为玩家玩梗，不采信）",
        "除已裁决的词外，仍有转写错字无法确认",
    ),
    "维克托/维克多/维格托": (
        "段4出现的「维克多尸体」是否与维克托同一人",
        "译名已归一（维克托←维克多/维格托）；尸体身份仍未明",
    ),
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    write = "--write" in sys.argv
    if not PATCH.is_file():
        print(f"补丁不存在: {PATCH}")
        return 1
    doc = json.loads(PATCH.read_text(encoding="utf-8"))
    chars = doc.get("characters") or []
    log: list[str] = []

    # ---- 1. PC 的 played_by ----
    for c in chars:
        cid = c.get("id")
        old = c.get("played_by")
        if cid in PL_MAP:
            c["played_by"] = PL_MAP[cid]
            log.append(f"[PL] {cid} ({c.get('name')}): played_by {old!r} -> {PL_MAP[cid]!r}")
        elif cid in NPC_CARD_IDS:
            c["played_by"] = NPC_PLAYER
            tags = [t for t in (c.get("tags") or []) if t != "PC"]
            if "NPC" not in tags:
                tags.append("NPC")
            c["tags"] = tags
            log.append(f"[NPC] {cid} ({c.get('name')}): played_by {old!r} -> {NPC_PLAYER!r}, tags PC->NPC")
        elif old != NPC_PLAYER:
            # 其余都是 KP 扮演的 NPC / BOSS
            c["played_by"] = NPC_PLAYER
            log.append(f"[NPC] {cid} ({c.get('name')}): played_by {old!r} -> {NPC_PLAYER!r}")

    # ---- 2. 八重樱的剑: 时之圣剑 -> 烟剑 ----
    for c in chars:
        if c.get("id") == "sjt_bachongying":
            for key in ("identity", "note"):
                if isinstance(c.get(key), str) and "时之圣剑" in c[key]:
                    before = c[key]
                    c[key] = (
                        c[key]
                        .replace("时之圣剑「以锐克武」", "烟剑")
                        .replace("时之圣剑·以锐克武", "烟剑")
                        .replace("时之圣剑", "烟剑")
                    )
                    log.append(f"[剑] sjt_bachongying.{key}: 时之圣剑 -> 烟剑\n      {before[:80]}\n   -> {c[key][:80]}")

    # ---- 3. 新增飒飒米 ----
    if not any(c.get("id") == NEW_CHAR["id"] for c in chars):
        chars.append(dict(NEW_CHAR))
        log.append(f"[新增] {NEW_CHAR['id']} {NEW_CHAR['name']} (PL={NEW_CHAR['played_by']})")
    else:
        log.append("[新增] sjt_sasami 已存在, 跳过")

    # ---- 3b. note 里已过时的表述 ----
    NOTE_FIX = {
        "sjt_liya": [("；圣剑英雄谭中其具体行动与扮演者未确认",
                      "；PL=ReGMeIoN（主人 2026-10-03 确认；本团录音中其具体行动未见明确记录）")],
        "sjt_bachongying": [("（卡内提到「宽」）",
                             "（PL=宽；卡面剑名误写「时之圣剑·以锐克武」，已按「烟剑」处理）")],
    }
    for c in chars:
        for old_s, new_s in NOTE_FIX.get(c.get("id"), []):
            if isinstance(c.get("note"), str) and old_s in c["note"]:
                c["note"] = c["note"].replace(old_s, new_s)
                log.append(f"[note] {c['id']}: {old_s[:20]}... -> 已更新")

    # ---- 4. pending 清理 ----
    pending = doc.get("pending") or []
    kept, dropped, rewritten = [], [], []
    for p in pending:
        blob = json.dumps(p, ensure_ascii=False)
        hit = next((k for k in REWRITE if k in blob), None)
        if hit:
            new_item, new_reason = REWRITE[hit]
            if isinstance(p, dict):
                p = dict(p)
                p["item"] = new_item
                p["reason"] = new_reason
            else:
                p = f"{new_item} — {new_reason}"
            kept.append(p)
            rewritten.append(new_item)
            continue
        if any(k in blob for k in RESOLVED):
            dropped.append(blob[:110])
            continue
        kept.append(p)
    doc["pending"] = kept
    for x in rewritten:
        log.append(f"[pending-改写] {x}")
    for x in dropped:
        log.append(f"[pending-移除] {x}")

    # ---- 5. 记一笔 meta ----
    meta = doc.setdefault("_meta", {})
    if isinstance(meta, dict):
        meta["owner_answers_20261003"] = (
            "KP=菌羊; ReGMeIoN=PL(莉亚·岩心); 往=妮娜·可可; 雪人=流星亚什; 宽=八重樱(烟剑); "
            "琉珈·深谣=NPC(菌羊演); pd=飒飒米; HP 照卡面; 团名用「圣剑英雄谭」"
        )

    print(f"角色 {len(chars)} 个 · 关系 {len(doc.get('relations') or [])} · "
          f"pending {len(pending)} -> {len(kept)}")
    for line in log:
        print(" ", line)
    if not write:
        print("\n[dry-run] 未落盘。加 --write 生效。")
        return 0
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    bak = PATCH.with_suffix(f".json.bak_{stamp}")
    shutil.copy2(PATCH, bak)
    PATCH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK 已写入 {PATCH}\n备份 {bak}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
