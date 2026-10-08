# -*- coding: utf-8 -*-
"""Apply the owner's round-2 answers for 潮汐监狱 (idempotent, backup first).

Answers being applied (2026-10-06):
  R01  "天眼霸杀" is an ASR mishearing -> the NPC is 「天元大人」 (all of it is 天元).
  R03  "铁奶龙" is an ASR mishearing -> 「典狱长阶奶龙」; 典狱长 is a real in-story NPC
       and must exist as its own node.
  R04  八变场旧址 is actually **巴别塔旧址**; 巴别塔 is the previous group's meme but this
       is real plot -> reword in every derived doc.
  R06  「艾斯利尔」and「窗」 really do appear (ending mention) -> add 潮汐监狱 to the
       existing cross-group nodes (no duplicate nodes).
  R05  音乐家 is NOT the existing 「音乐演奏者」 -> nothing to merge.
  R02  the score rules are correct, but they are a KP misdirection -> record as such.

usage:
    python tools/_fix_tide_qa.py            # dry-run
    python tools/_fix_tide_qa.py --apply
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
DATA = WS / "\u6570\u636e"                                   # 数据
CANON = WS / ".trpg" / "canon" / "groups" / ("\u6f6e\u6c50\u76d1\u72f1.md")
PATCH = WS / ".trpg" / "patches" / ("\u6f6e\u6c50\u76d1\u72f1_patch.json")

GROUP = "\u6f6e\u6c50\u76d1\u72f1"                            # 潮汐监狱
TIAN = "td_tianyuan"
NAILONG = "td_nailong"
DIANYU = "td_dianyu"
TIANYUAN_NAME = "\u5929\u5143\u5927\u4eba"                     # 天元大人
OLD_WRONG = "\u5929\u773c\u9738\u6740"                          # 天眼霸杀
OLD_ALT = "\u5929\u8fdc"                                       # 天远
HAND = "\u770b\u5b88"                                          # 看守
PENDING = "\u5f85\u786e\u8ba4"                                  # 待确认
MEME_OLD = "\u516b\u53d8\u573a"                                 # 八变场
MEME_NEW = "\u5df4\u522b\u5854\u65e7\u5740"                      # 巴别塔旧址
IRON = "\u94c1\u5976\u9f99"                                     # 铁奶龙
IRON_FIX = "\u5178\u72f1\u957f\u9636\u5976\u9f99"                 # 典狱长阶奶龙
DIANYU_NAME = "\u5178\u72f1\u957f"                              # 典狱长

# cross-group nodes that really appear in this group (owner: R06 = 真的)
CROSS_HITS = {
    "g2_aisilie": "\u827e\u65af\u5229\u5c14",                          # 艾斯利尔
    "mg_aisilie": "\u827e\u65af\u5229\u5c14\u00b7\u5fb7\u96f7\u59c6\uff08Hopes\uff09",
    "mg3_aisilie": "\u827e\u65af\u5229\u5c14\uff08\u6551\u8d4e\u7ebf\uff09",
    "yy_wulianren": "\u827e\u65af\u5229\u5c14\uff08\u9634\u9633\u5dee\u4e8b\u5f55\uff09",
    "mg_chuang": "\u7a97\uff08\u5723\u6127\uff09",                       # 窗（圣愚）
    "mg4_chudaidechuang": "\u521d\u4ee3\u7684\u7a97\uff08\u8001\u5927\uff09",
}
CROSS_EVENT = ("\u6bb5\uff15\u7ed3\u5c40\uff1a\u73a9\u5bb6\u590d\u76d8\u79f0\u300c\u50cf\u4ec0\u4e48\u827e\u65af\u5229\u5c14\u3001"
               "\u4ec0\u4e48\u7a97\u5168\u90e8\u56e2\u706d\u4e86\u300d\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u771f\u51fa\u573a\uff09")


def walk_replace(node, old: str, new: str) -> int:
    n = 0
    if isinstance(node, dict):
        for k, v in node.items():
            if isinstance(v, str):
                if old in v:
                    n += v.count(old)
                    node[k] = v.replace(old, new)
            else:
                n += walk_replace(v, old, new)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            if isinstance(v, str):
                if old in v:
                    n += v.count(old)
                    node[i] = v.replace(old, new)
            else:
                n += walk_replace(v, old, new)
    return n


def find(doc_key: str, doc: dict, cid: str):
    for c in doc.get(doc_key, []):
        if c.get("id") == cid:
            return c
    return None


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
    patch = json.loads(PATCH.read_text(encoding="utf-8"))

    log: list[str] = []

    # ---------- 1) 天元大人 ----------
    ty = find("characters", chars, TIAN)
    if ty:
        if ty.get("name") != TIANYUAN_NAME:
            log.append("天元 name: %s -> %s" % (ty.get("name"), TIANYUAN_NAME))
            ty["name"] = TIANYUAN_NAME
        al = ty.setdefault("aliases", [])
        clean = [x for x in al if OLD_WRONG not in x and OLD_ALT not in x and x != TIANYUAN_NAME]
        clean += [OLD_WRONG + "\uff08ASR \u8bef\u5199\uff09", OLD_ALT + "\uff08ASR \u8bef\u5199\uff09"]
        if al != clean:
            ty["aliases"] = clean
            log.append("天元 aliases -> %s" % "/".join(clean))
        ty["identity"] = "神秘招募者 / 最终接应者（非人生物，白色空间出场）"
        ty["tags"] = [t for t in ty.get("tags", []) if t != PENDING] or ["NPC"]
        ty["note"] = ("段1 在白色空间招募五名 PC 潜入潮汐监狱救出林小元，称此事关乎世界存亡；"
                      "段5 在船上接应撤离的 PC，并揭示世界已被色彩杰克入侵、潮汐监狱原是巴别塔旧址改建。"
                      "**主人 2026-10-06 确认：正名「天元大人」；「天眼霸杀」「天远」均为 ASR 误写（听错）。**")
        ev = ty.get("events", [])
        for block in ev:
            if block.get("group") == GROUP:
                block["items"] = [it.replace(OLD_WRONG, TIANYUAN_NAME).replace(OLD_ALT, TIANYUAN_NAME)
                                  for it in block.get("items", [])]
        n = walk_replace(ev, MEME_OLD, MEME_NEW)
        if n:
            log.append("天元 events: 八变场 -> 巴别塔旧址 x%d" % n)
    else:
        log.append("!! td_tianyuan not found")

    # ---------- 2) 奶龙描述 + 新建典狱长 ----------
    nl = find("characters", chars, NAILONG)
    if nl:
        if IRON in nl.get("note", ""):
            nl["note"] = nl["note"].replace(IRON + "?", IRON_FIX).replace(IRON, IRON_FIX)
            log.append("奶龙 note: 铁奶龙 -> 典狱长阶奶龙")
        nl["identity"] = "潮汐监狱狱警 / 守卫势力（低阶奶龙 · 高阶奶龙；含护士、打饭、塔顶狙）"
        nl["tags"] = [t for t in nl.get("tags", []) if t != PENDING] or ["NPC"]
        for block in nl.get("events", []):
            if block.get("group") == GROUP:
                block["items"] = [it.replace(IRON + "?", IRON_FIX).replace(IRON, IRON_FIX)
                                  for it in block.get("items", [])]
        walk_replace(nl.get("events"), MEME_OLD, MEME_NEW)

    dy = find("characters", chars, DIANYU)
    if dy is None:
        dy = {
            "id": DIANYU,
            "name": DIANYU_NAME,
            "aliases": [IRON + "\uff08ASR \u8bef\u5199\uff09", IRON_FIX],
            "identity": "\u6f6e\u6c50\u76d1\u72f1\u5178\u72f1\u957f\uff08\u5976\u9f99\u4e2d\u6700\u9ad8\u9636\uff0c\u201c\u6709\u5934\u6709\u8138\u6709\u540d\u5b57\u201d\u7684\u90a3\u4e00\u6863\uff09",
            "groups": [GROUP],
            "tags": ["NPC", "BOSS"],
            "played_by": "\u5f85\u786e\u8ba4",
            "note": ("\u5178\u72f1\u957f = \u5976\u9f99\u4e2d\u6700\u9ad8\u9636\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a"
                     "\u8f6c\u5199\u7684\u300c\u70b9\u871c\u638c\u94c1\u5976\u9f99\u300d\u4e3a ASR \u8bef\u5199\uff0c"
                     "\u6b63\u786e\u8bfb\u6cd5\u662f\u300c\u5178\u72f1\u957f\u9636\u5976\u9f99\u300d\uff09\u3002"
                     "\u6301\u6709\u9ed1\u6f6e\u7262\u623f\u623f\u5361\uff0c\u638c\u7ba1\u5168\u72f1\u89c4\u5219\u4e0e\u79ef\u5206\u5151\u6362\u3002"),
            "events": [{"group": GROUP, "items": [
                "\u6bb5\uff11\uff1a\u4ecb\u7ecd\u5976\u9f99\u5206\u4e09\u7b49\uff0c\u5178\u72f1\u957f\u662f\u6700\u9ad8\u9636\uff08\u201c\u6709\u5934\u6709\u8138\u6709\u540d\u5b57\u201d\uff09",
                "\u6bb5\uff13\u2013\u6bb5\uff14\uff1a\u9ed1\u6f6e\u7262\u623f\u623f\u5361\u5728\u5178\u72f1\u957f\u624b\u91cc\uff08\u5899\u4e2d\u4eba\u60c5\u62a5\uff09\uff1b\u7d2f\u8ba1 100 \u5206\u53ef\u5411\u5178\u72f1\u957f\u6dfb\u52a0\u4e00\u6761\u81ea\u5b9a\u4e49\u89c4\u5219",
                "\u6bb5\uff15\uff1a\u5976\u9f99\u5927\u6148\u5584\u5bb6/\u59d4\u5458\u957f\u5de1\u76d1\u65f6\u7531\u5178\u72f1\u957f\u62db\u5f85",
            ]}],
            "confirmed": True,
            "segment": "\u6bb5\uff11-\u6bb5\uff15",
        }
        chars.setdefault("characters", []).append(dy)
        log.append("new node: %s (%s)" % (DIANYU, DIANYU_NAME))
    else:
        log.append("node %s already exists" % DIANYU)

    # 把「看守」边改成指向典狱长
    changed = 0
    for r in rels.get("relations", []):
        if r.get("to") == NAILONG and r.get("type") == HAND:
            r["to"] = DIANYU
            r["event"] = (r.get("event", "") + "（主人 2026-10-06 确认：看守者即典狱长阶奶龙）")
            changed += 1
    if changed:
        log.append("relations: 看守 edge -> %s x%d" % (DIANYU, changed))
    exists = any(r.get("from") == DIANYU and r.get("to") == "td_linxiaoyuan" for r in rels.get("relations", []))
    if not exists:
        rels.setdefault("relations", []).append({
            "from": DIANYU, "to": "td_linxiaoyuan", "type": HAND, "strength": "\u5f3a",
            "event": ("\u6f6e\u6c50\u76d1\u72f1\u6bb5\uff13\uff1a\u5899\u4e2d\u4eba\u544a\u77e5\u6797\u5c0f\u5143\u88ab\u56da\u9ed1\u6f6e\u7262\u623f\uff0c"
                      "**\u623f\u5361\u5728\u5178\u72f1\u957f\u624b\u91cc**\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\u5178\u72f1\u957f\u4e3a\u5267\u5185 NPC\uff09"),
            "confirmed": True,
        })
        log.append("new edge: %s -> td_linxiaoyuan [%s]" % (DIANYU, HAND))

    # ---------- 3) 跨团出场（R06 = 真的）----------
    for cid, cname in CROSS_HITS.items():
        c = find("characters", chars, cid)
        if not c:
            log.append("!! cross node missing: %s" % cid)
            continue
        gs = c.setdefault("groups", [])
        if GROUP not in gs:
            gs.append(GROUP)
            log.append("cross %s (%s): groups += %s" % (cid, cname, GROUP))
        ev = c.setdefault("events", [])
        block = next((b for b in ev if b.get("group") == GROUP), None)
        if block is None:
            ev.append({"group": GROUP, "items": [CROSS_EVENT]})
            log.append("cross %s: +event" % cid)
        c["tags"] = [t for t in c.get("tags", []) if t != PENDING] or c.get("tags", [])

    # ---------- 4) 全量改写：八变场 -> 巴别塔旧址 ----------
    n_meme = walk_replace(chars, MEME_OLD, MEME_NEW)
    n_meme_r = walk_replace(rels, MEME_OLD, MEME_NEW)
    log.append("八变场 -> 巴别塔旧址: characters x%d / relations x%d" % (n_meme, n_meme_r))

    # ---------- 5) 积分规则 = KP 的误导 ----------
    for c in chars.get("characters", []):
        for block in c.get("events", []):
            if block.get("group") != GROUP:
                continue
            items = block.get("items", [])
            block["items"] = [
                (it + "（**主人 2026-10-06 确认：此积分规则是 KP 的误导**）")
                if ("100" in it and ("\u79ef\u5206" in it or "\u89c4\u5219" in it))
                and "KP \u7684\u8bef\u5bfc" not in it else it
                for it in items
            ]

    # ---------- 6) 补丁同步（去重键 (from,to,type) 必须一致）----------
    pc = find("characters", patch, TIAN)
    if pc:
        pc["name"] = TIANYUAN_NAME
        pc["tags"] = [t for t in pc.get("tags", []) if t != PENDING] or ["NPC"]
        pc["aliases"] = [OLD_WRONG, OLD_ALT, TIANYUAN_NAME]
        pc["note"] = ty["note"] if ty else pc.get("note")
    pn = find("characters", patch, NAILONG)
    if pn:
        pn["tags"] = [t for t in pn.get("tags", []) if t != PENDING] or ["NPC"]
        if IRON in pn.get("note", ""):
            pn["note"] = pn["note"].replace(IRON, IRON_FIX).replace(IRON_FIX + "?", IRON_FIX)
    if find("characters", patch, DIANYU) is None:
        patch.setdefault("characters", []).append({
            "id": DIANYU, "name": DIANYU_NAME,
            "aliases": [IRON_FIX, IRON], "identity": dy["identity"], "groups": [GROUP],
            "tags": ["NPC", "BOSS"], "played_by": "\u5f85\u786e\u8ba4",
            "note": dy["note"], "events": dy["events"], "confirmed": True, "segment": "\u6bb5\uff11-\u6bb5\uff15",
        })
        log.append("patch: +node %s" % DIANYU)
    prels = patch.setdefault("relations", [])
    for r in prels:
        if r.get("to") == NAILONG and r.get("type") == HAND:
            r["to"] = DIANYU
    if not any(r.get("from") == DIANYU and r.get("to") == "td_linxiaoyuan" for r in prels):
        prels.append({
            "from": DIANYU, "to": "td_linxiaoyuan", "type": HAND, "strength": "\u5f3a",
            "event": ("\u6f6e\u6c50\u76d1\u72f1\u6bb5\uff13\uff1a\u623f\u5361\u5728\u5178\u72f1\u957f\u624b\u91cc\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff09"),
            "confirmed": True,
        })
        log.append("patch: +edge %s->td_linxiaoyuan" % DIANYU)
    for upd in patch.get("character_updates", []) or []:
        cid = upd.get("id") or upd.get("character_id")
        if cid in CROSS_HITS:
            ag = upd.setdefault("add_groups", [])
            if GROUP not in ag:
                ag.append(GROUP)
    walk_replace(patch, MEME_OLD, MEME_NEW)
    # 标记已答的待确认条目（第2轮）
    ans_map = {
        IRON: "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u8f6c\u5199\u7684\u300c\u94c1\u5976\u9f99\u300d\u662f ASR \u8bef\u5199\uff0c"
              "\u6b63\u786e\u662f\u300c\u5178\u72f1\u957f\u9636\u5976\u9f99\u300d\uff1b\u5178\u72f1\u957f\u662f\u5267\u5185 NPC\uff0c\u5df2\u5355\u72ec\u5efa\u8282\u70b9 td_dianyu",
        OLD_WRONG: "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u300c\u5929\u773c\u9738\u6740\u300d\u662f\u542c\u9519\uff0c\u6b63\u540d\u300c\u5929\u5143\u5927\u4eba\u300d",
        MEME_OLD: "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u662f\u300c\u5df4\u522b\u5854\u65e7\u5740\u300d\uff08\u5df4\u522b\u5854\u662f\u4e0a\u4e00\u4e2a\u56e2\u7684\u6897\uff0c\u4f46\u672c\u56e2\u5c5e\u771f\u5267\u60c5\uff09",
    }
    for pend in patch.get("pending", []) or patch.get("\u5f85\u786e\u8ba4", []) or []:
        item = pend.get("item", "")
        for k, v in ans_map.items():
            if k in item:
                pend["item"] = item + "\uff08" + v + "\uff09"
                pend["confirmed"] = True
                log.append("pending answered: %s..." % item[:24])
                break
    if IRON in json.dumps(patch, ensure_ascii=False):
        log.append("note: 铁奶龙 remains only inside the answered pending item text")

    print("\n".join("  " + x for x in log) or "  (no change)")
    if not a.apply:
        print("\n[dry-run] add --apply to write")
        return 0

    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f in (cfile, rfile, PATCH):
        shutil.copyfile(f, f.with_name(f.name + ".bak_tideqa_" + stamp))
    cfile.write_text(json.dumps(chars, ensure_ascii=False, indent=1), encoding="utf-8")
    rfile.write_text(json.dumps(rels, ensure_ascii=False, indent=1), encoding="utf-8")
    PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwritten (backups *.bak_tideqa_%s)" % stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
