# -*- coding: utf-8 -*-
"""Apply the owner's round-1 answers (23 questions) for 潮汐监狱. Idempotent.

Key rulings (2026-10-06):
  Q01  KP = pd.
  Q02  PL: Himmel=ReGMeIoN / 失败的 man=宽 / 忒玛萝=往 / Ace=雪人 / 莉娜=菌羊.
  Q04  「林小元」= 林小鸢 (yy_linxiaoyuan) -> merge, keep yy_ id, both groups.
  Q08 奶龙 is a **species** (看守奶龙 + 典狱长奶龙).
  Q11 技能**没有**封印.
  Q12 没有饱食度；地图不买就要自己画；小黑屋 = 造反后被抓去削土豆.
  Q14 弗洛男=福瑞男（furry 肌肉男，福瑞帮成员）；福尔兰/福瑞南 都是他.
  Q15 小绿骰=场外骰子颜色（不管）；墙中人=墙里提供情报的人；小丑黄=小丑皇；
      安迪=奶蛋（只会说「安迪」的黄色蛋）.
  Q16 唐四爷 / 秦仲义 / 萧炎（原写萧岩）/ 腕豪（原写万豪）/ 五山贼（五个山贼，第五个是叛徒）.
  Q17 奥利巴是《刃牙》角色；傻呼啦是网络 meme（tongtongtongsahur）.
  Q18 海格力斯（不是海格丽丝/海克力斯）；柳如烟（不是柳泽元）；
      元素狼=异世界大逃杀出现过；缝合线=像《咒术回战》羂索那样侵占大脑.
  Q19 海洋之泪/非洲之心 = 三角洲行动梗的高价值收藏品.
  Q21 苏格拉底=早期团角色（真剧情）；浩辰=角色+梗（re0 傲慢司教头像，狮子的心脏）；神光棒→迪迦.
  Q22 雪人下水捞海洋之泪时淹死 → 变水鬼 → 之后换卡.
  Q20 「编号/刑期不关键」 -> 不改数据.
  Q03 Ace 的 PL 确是雪人.  Q05 圣杯团角色（未上传）-> 不入库.  Q06 天元.  Q07 宰羊帮对.
  Q09 弗里斯克=《Undertale》Frisk（本团首次出现）；梅露露=魔女裁判厅角色；
      奥尼尔舅舅=月计团（可当首次出现）；莫迪亚迪=莫里亚蒂（蒸汽朋克团，未上传）；
      杰西敏=上一个团角色（未上传）.
  Q13 PPT 档位判定对.

usage:
    python tools/_fix_tide_qa2.py            # dry-run
    python tools/_fix_tide_qa2.py --apply
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
DATA = WS / "\u6570\u636e"
PATCH = WS / ".trpg" / "patches" / ("\u6f6e\u6c50\u76d1\u72f1_patch.json")
GROUP = "\u6f6e\u6c50\u76d1\u72f1"                       # 潮汐监狱
PENDING = "\u5f85\u786e\u8ba4"                            # 待确认
PD = "pd"
KD = "\u5bbd"                                            # 宽
WANG = "\u5f80"                                          # 往
XR = "\u96ea\u4eba"                                       # 雪人
JY = "\u83cc\u7f8a"                                       # 菌羊
REG = "ReGMeIoN"

PL_OF_PC = {
    "td_himmel": REG,
    "td_shibaideman": KD,
    "td_temaluo": WANG,
    "td_ace": XR,
    "td_lina": JY,
}

RENAME = {
    "td_fulan": ("\u798f\u745e\u7537", None, "ASR \u8bef\u5199\uff1a\u5f17\u6d1b\u5357 / \u798f\u5c14\u5170 / \u798f\u745e\u5357"),
    "td_qiangzhongren": (None, "\u5899\u91cc\u6ca1\u9732\u9762\u3001\u4e3a PC \u63d0\u4f9b\u60c5\u62a5\u7684\u4eba", None),
    "td_xiaochouhuang": ("\u5c0f\u4e11\u7687", None, "ASR \u8bef\u5199\uff1a\u5c0f\u4e11\u9ec4"),
    "td_anndi": ("\u5976\u86cb", "\u9ec4\u8272\u7684\u3001\u6709\u773c\u775b\u5634\u5df4\u7684\u86cb\uff0c\u53ea\u4f1a\u8bf4\u300c\u5b89\u8fea\u300d", "ASR \u8bef\u5199\uff1a\u5b89\u8fea"),
    "td_xiaoyan": ("\u8427\u708e", None, "ASR \u8bef\u5199\uff1a\u8427\u5ca9 / \u8427\u5ae3 / \u785d\u70df"),
    "td_wanhao": ("\u8155\u8c6a", None, "ASR \u8bef\u5199\uff1a\u4e07\u8c6a"),
    "td_wusanzei": ("\u4e94\u5c71\u8d3c", "\u4e94\u4e2a\u5c71\u8d3c\uff08\u7b2c\u4e94\u4e2a\u5c71\u8d3c\u662f\u53db\u5f92\uff09", "ASR \u8bef\u5199\uff1a\u6b66\u4e09\u8d3c / \u4e94\u4e09\u8d3c"),
    "td_hgailisi": ("\u6d77\u683c\u529b\u65af", None, "ASR \u8bef\u5199\uff1a\u6d77\u683c\u4e3d\u4e1d / \u6d77\u514b\u529b\u65af"),
    "td_lzeyuan": ("\u67f3\u5982\u70df", None, "ASR \u8bef\u5199\uff1a\u67f3\u6cfd\u5143"),
    "td_moriyadi": ("\u83ab\u91cc\u4e9a\u8482", None, "ASR \u8bef\u5199\uff1a\u83ab\u8fea\u4e9a\u8fea"),
}

# 既有跨团角色在这场里的补充（id -> (note, event)）
CROSS = {
    "g2_yuedaixue": ("\u6f6e\u6c50\u76d1\u72f1\u6bb5\uff13\uff1a\u5728\u76d1\u72f1\u91cc\u4e0e PC \u6253\u8fc7\u4ea4\u9053\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u5979\u662f\u300c\u9b54\u5973\u5ba1\u5224\u5385\u300d\u7684\u89d2\u8272\uff09",
                    "\u6bb5\uff13\uff1a\u51fa\u73b0\u5728\u6f6e\u6c50\u76d1\u72f1\uff08\u4e3b\u4eba\u786e\u8ba4\uff1a\u6765\u81ea\u300c\u9b54\u5973\u5ba1\u5224\u5385\u300d\uff09"),
}

# 新节点（本团首次出现 / 未上传的团）
NEW_NODES = [
    {
        "id": "td_fulisike", "name": "\u5f17\u91cc\u65af\u514b",
        "identity": "\u540e\u671f\u5927\u6df7\u6218\u4e2d\u7684\u5bf9\u624b\uff08\u62ff\u4e09\u7ea7\u9632\u5854\uff09",
        "aliases": ["\u5f17\u96f7\u65af\u514b", "Frisk"],
        "note": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u5f17\u91cc\u65af\u514b = \u300aUndertale\u300b\u91cc\u7684 Frisk\uff0c**\u672c\u56e2\u9996\u6b21\u51fa\u73b0**",
        "tags": ["NPC"],
    },
    {
        "id": "td_aonier", "name": "\u5965\u5c3c\u5c14\u8205\u8205",
        "identity": "\u76d1\u72f1\u91cc\u6709\u52bf\u529b\u7684\u8001\u5927\uff08\u201c\u5965\u5c3c\u5c14\u8205\u8205\u201d\uff09",
        "aliases": ["\u5965\u5c3c\u5c14"],
        "note": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u4e4b\u524d\u300c\u6708\u8ba1\u56e2\u300d\u51fa\u73b0\u8fc7\uff0c**\u53ef\u5f53\u6210\u672c\u56e2\u9996\u6b21\u51fa\u73b0**",
        "tags": ["NPC"],
    },
    {
        "id": "td_jieximin", "name": "\u6770\u897f\u654f",
        "identity": "\u524d\u6240\u957f\u6770\u897f\u7684\u5173\u8054\u8005\uff08\u4e0e\u300c\u672a\u6765\u81ea\u5df1\u300d\u6709\u5173\uff09",
        "aliases": ["\u6770\u897f\u7c73", "\u6770\u5174\u8fdc"],
        "note": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u662f**\u8fd9\u4e2a\u56e2\u7684\u4e0a\u4e00\u4e2a\u56e2**\u51fa\u73b0\u7684\u89d2\u8272\uff08\u4e0a\u4e00\u4e2a\u56e2\u5c1a\u672a\u4e0a\u4f20\uff09",
        "tags": ["NPC"],
    },
    {
        "id": "td_sugeladi", "name": "\u82cf\u683c\u62c9\u5e95",
        "identity": "\u65e9\u671f\u56e2\u7684\u89d2\u8272\uff08\u771f\u5267\u60c5\uff09",
        "aliases": [],
        "note": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u82cf\u683c\u62c9\u5e95\u662f\u65e9\u671f\u56e2\u7684\u89d2\u8272\uff0c**\u771f\u5267\u60c5**",
        "tags": ["NPC"],
    },
    {
        "id": "td_haochen", "name": "\u6d69\u8fb0",
        "identity": "\u89d2\u8272 + \u6897\uff08\u5934\u50cf\u50cf re0 \u50b2\u6162\u53f8\u6559\uff0c\u5e38\u642c\u8fd0\u89c6\u9891\uff09",
        "aliases": ["\u53f7\u57ce"],
        "note": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u6d69\u8fb0\u662f\u89d2\u8272\u4e5f\u662f\u6897\uff08\u56e0\u4ed6\u5e38\u642c\u8fd0\u89c6\u9891\u3001\u5934\u50cf\u5f88\u50cf\u300are0\u300b\u50b2\u6162\u53f8\u6559\uff09\uff1b\u5728\u56e2\u91cc\u6709\u300c\u72ee\u5b50\u7684\u5fc3\u810f\u300d\u80fd\u529b",
        "tags": ["NPC"],
    },
]


def find(doc: dict, key: str, cid: str):
    for c in doc.get(key, []):
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

    cfile, rfile, pfile = DATA / "characters.json", DATA / "relations.json", DATA / "players.json"
    chars = json.loads(cfile.read_text(encoding="utf-8"))
    rels = json.loads(rfile.read_text(encoding="utf-8"))
    plays = json.loads(pfile.read_text(encoding="utf-8"))
    patch = json.loads(PATCH.read_text(encoding="utf-8"))
    log: list[str] = []

    # ---------- A) PC -> PL ----------
    for cid, pl in PL_OF_PC.items():
        c = find(chars, "characters", cid)
        if not c:
            log.append("!! missing PC %s" % cid)
            continue
        if c.get("played_by") != pl:
            log.append("played_by %s: %s -> %s" % (c["name"], c.get("played_by"), pl))
            c["played_by"] = pl
        c["tags"] = [t for t in c.get("tags", []) if t != PENDING] or ["PC"]
        pc = find(patch, "characters", cid)
        if pc:
            pc["played_by"] = pl
            pc["tags"] = [t for t in pc.get("tags", []) if t != PENDING] or ["PC"]
    # 补丁里补 PC->PL 关系边 + player_updates
    prels = patch.setdefault("relations", [])
    for cid, pl in PL_OF_PC.items():
        if not any(r.get("from") == cid and r.get("to") == pl for r in prels):
            prels.append({"from": cid, "to": pl, "type": "\u73a9\u5bb6\u89d2\u8272",
                          "strength": "\u5f3a", "event": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\u7684\u73a9\u5bb6\u5bf9\u5e94",
                          "confirmed": True})
            log.append("patch: +edge %s -> %s" % (cid, pl))
    ups = patch.setdefault("player_updates", [])
    for cid, pl in PL_OF_PC.items():
        c = find(chars, "characters", cid)
        entry = next((u for u in ups if u.get("name") == pl or u.get("uid") == pl), None)
        if entry is None:
            ups.append({"name": pl, "add_roles": [{"group": GROUP,
                                                   "role": "PC\uff1a" + (c["name"] if c else cid)}]})
            log.append("patch: player_updates += %s" % pl)
        else:
            rs = entry.setdefault("add_roles", [])
            if not any(r.get("group") == GROUP for r in rs):
                rs.append({"group": GROUP, "role": "PC\uff1a" + (c["name"] if c else cid)})
                log.append("patch: player %s += role" % pl)

    # ---------- A2) PC -> PL 关系边同时写入生产库 ----------
    for cid, pl in PL_OF_PC.items():
        if not any(r.get("from") == cid and r.get("to") == pl for r in rels.get("relations", [])):
            rels.setdefault("relations", []).append({
                "from": cid, "to": pl, "type": "\u73a9\u5bb6\u89d2\u8272", "strength": "\u5f3a",
                "event": "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a" + pl + " \u6f14\u672c\u56e2 PC",
                "confirmed": True,
            })
            log.append("relations: +edge %s -> %s" % (cid, pl))

    # ---------- B) 名字/身份修正 ----------
    for cid, (newname, newident, note_add) in RENAME.items():
        c = find(chars, "characters", cid)
        if not c and newname:
            # 原本 confirmed:false 没写盘的两个节点（主人已答 -> 现在正式入库）
            c = {
                "id": cid, "name": newname, "aliases": [], "identity": newident or "NPC",
                "groups": [GROUP], "tags": ["NPC"], "played_by": "\u5f85\u786e\u8ba4",
                "note": (note_add or ""), "events": [{"group": GROUP, "items": [note_add or newname]}],
                "confirmed": True, "segment": "\u6bb5\uff15",
            }
            chars.setdefault("characters", []).append(c)
            if find(patch, "characters", cid) is None:
                patch.setdefault("characters", []).append(dict(c))
            log.append("new node (was confirmed:false): %s (%s)" % (cid, newname))
            continue
        if not c:
            log.append("!! missing %s" % cid)
            continue
        old = c.get("name")
        if newname and old != newname:
            al = c.setdefault("aliases", [])
            if old not in al:
                al.append(old)
            c["name"] = newname
            log.append("rename %s: %s -> %s" % (cid, old, newname))
        if newident:
            c["identity"] = newident
        if note_add and note_add not in c.get("note", ""):
            c["note"] = (c.get("note", "") + "\uff08" + note_add + "\uff09")
        c["tags"] = [t for t in c.get("tags", []) if t != PENDING] or c.get("tags", [])
        c["confirmed"] = True
        pc = find(patch, "characters", cid)
        if pc:
            if newname:
                if pc.get("name") != newname:
                    pc.setdefault("aliases", []).append(pc.get("name"))
                pc["name"] = newname
            if newident:
                pc["identity"] = newident
            pc["tags"] = [t for t in pc.get("tags", []) if t != PENDING] or pc.get("tags", [])
            pc["confirmed"] = True

    # ---------- C) 林小元 -> 林小鸢 合并（R07）----------
    old_id, keep_id = "td_linxiaoyuan", "yy_linxiaoyuan"
    src_run = find(chars, "characters", old_id)
    dst = find(chars, "characters", keep_id)
    if src_run and dst:
        al = dst.setdefault("aliases", [])
        for x in [src_run.get("name")] + src_run.get("aliases", []):
            if x and x not in al:
                al.append(x)
        gs = dst.setdefault("groups", [])
        if GROUP not in gs:
            gs.append(GROUP)
        tg = dst.setdefault("tags", [])
        for x in ["\u8de8\u56e2\u540c\u4f4d\u4f53"]:
            if x not in tg:
                tg.append(x)
        ev = dst.setdefault("events", [])
        new_items = []
        for b in src_run.get("events", []):
            new_items += b.get("items", [])
        if new_items:
            blk = next((b for b in ev if b.get("group") == GROUP), None)
            if blk is None:
                ev.append({"group": GROUP, "items": new_items})
            else:
                for it in new_items:
                    if it not in blk["items"]:
                        blk["items"].append(it)
        dst["note"] = (dst.get("note", "") + "\uff08**\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u6f6e\u6c50\u76d1\u72f1\u56e2\u91cc\u7684"
                       "\u300c\u6797\u5c0f\u5143/\u6797\u5c0f\u6e0a\u300d\u5c31\u662f\u672c\u4eba\uff1b\u4e94\u540d PC \u6765\u6f6e\u6c50\u76d1\u72f1"
                       "\u5c31\u662f\u4e3a\u4e86\u62ef\u6551\u5979**\uff09")
        chars["characters"] = [c for c in chars["characters"] if c.get("id") != old_id]
        n_red = 0
        for r in rels.get("relations", []):
            for k in ("from", "to"):
                if r.get(k) == old_id:
                    r[k] = keep_id
                    n_red += 1
        log.append("merge %s -> %s (rel endpoints redirected: %d)" % (old_id, keep_id, n_red))
        p2 = find(patch, "characters", old_id)
        if p2:
            patch["characters"] = [c for c in patch["characters"] if c.get("id") != old_id]
        for r in prels:
            for k in ("from", "to"):
                if r.get(k) == old_id:
                    r[k] = keep_id
        if not any(u.get("id") == keep_id for u in patch.get("character_updates", []) or []):
            patch.setdefault("character_updates", []).append(
                {"id": keep_id, "add_groups": [GROUP], "add_tags": ["\u8de8\u56e2\u540c\u4f4d\u4f53"],
                 "append_note": "\u6f6e\u6c50\u76d1\u72f1\u56e2\u7684\u62ef\u6551\u76ee\u6807\u6797\u5c0f\u5143\uff08\u6797\u5c0f\u6e0a\uff09\u5c31\u662f\u672c\u4eba\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff09"})

    # ---------- D) 跨团既有角色补出场 ----------
    for cid, (note_add, ev_item) in CROSS.items():
        c = find(chars, "characters", cid)
        if not c:
            log.append("!! cross missing %s" % cid)
            continue
        if GROUP not in c.setdefault("groups", []):
            c["groups"].append(GROUP)
            log.append("cross %s: +group" % cid)
        ev = c.setdefault("events", [])
        blk = next((b for b in ev if b.get("group") == GROUP), None)
        if blk is None:
            ev.append({"group": GROUP, "items": [ev_item]})
            log.append("cross %s: +event" % cid)

    # ---------- E) 新节点 ----------
    for spec in NEW_NODES:
        if find(chars, "characters", spec["id"]):
            continue
        node = {
            "id": spec["id"], "name": spec["name"], "aliases": spec.get("aliases", []),
            "identity": spec["identity"], "groups": [GROUP], "tags": spec.get("tags", ["NPC"]),
            "played_by": "\u5f85\u786e\u8ba4", "note": spec["note"],
            "events": [{"group": GROUP, "items": [spec["note"]]}],
            "confirmed": True, "segment": "\u6bb5\uff15",
        }
        chars.setdefault("characters", []).append(node)
        if find(patch, "characters", spec["id"]) is None:
            patch.setdefault("characters", []).append({**node, "played_by": "\u5f85\u786e\u8ba4"})
        log.append("new node: %s (%s)" % (spec["id"], spec["name"]))

    # ---------- F) 主串改写（技能未封印 / 无饱食度 / 八变场已在上个脚本处理）----------
    fixes = [
        ("\u7591\u4f3c\u300c\u5165\u72f1\u540e\u6280\u80fd\u88ab\u5c01\u5370\u300d", "\u6bb5\uff11\u4e3b\u7ebf\uff08\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a\u6280\u80fd**\u6ca1\u6709**\u88ab\u5c01\u5370\uff09"),
        ("\u5361\u9762\u9644\u5f55\u5199\u7684\u4e09\u4e2a\u81ea\u5b9a\u673a\u5236", "\u4e3b\u4eba 2026-10-06 \u786e\u8ba4\uff1a**\u6ca1\u6709\u9971\u98df\u5ea6**\uff1b\u5730\u56fe**\u4e0d\u4e70\u5c31\u8981\u81ea\u5df1\u7ed8\u5236**\uff1b\u5c0f\u9ed1\u5c4b = **\u76d1\u72f1\u9020\u53cd\u540e\u88ab\u902e\u6355\u8fdb\u53bb\u524a\u571f\u8c46**"),
    ]
    for c in chars.get("characters", []):
        for blk in c.get("events", []):
            if blk.get("group") != GROUP:
                continue
            items = blk.get("items", [])
            new = []
            for it in items:
                for old, rep in fixes:
                    if old in it:
                        it = it.replace(old, rep)
                new.append(it)
            blk["items"] = new

    # ---------- G) 补丁 pending 标记已答 ----------
    answered = {
        "KP": "\u5df2\u7b54\uff082026-10-06\uff09\uff1aKP = pd",
        "\u4e94\u5f20\u6b7b\u56da\u5361": "\u5df2\u7b54\uff082026-10-06\uff09\uff1aHimmel=ReGMeIoN\u3001\u5931\u8d25\u7684 man=\u5bbd\u3001\u5fd2\u739b\u841d=\u5f80\u3001Ace=\u96ea\u4eba\u3001\u83b2\u5a1c=\u83cc\u7f8a",
        "\u6797\u5c0f\u5143": "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u6797\u5c0f\u5143 = \u6797\u5c0f\u9e22\uff0c\u5df2\u5408\u5e76\u5165 yy_linxiaoyuan",
        "\u8d5b\u5f52": "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u9488\u5bf9\u6027\u5f52\u4e00\uff08\u8427\u708e/\u8155\u8c6a/\u4e94\u5c71\u8d3c/\u5c0f\u4e11\u7687/\u5976\u86cb\u7b49\uff09",
        "\u5f17\u6d1b\u5357": "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u798f\u745e\u7537\uff08furry \u808c\u8089\u7537\uff09",
        "\u6d77\u683c\u4e3d\u4e1d": "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u6d77\u683c\u529b\u65af\uff1b\u67f3\u5982\u70df",
        "\u82cf\u683c\u62c9\u5e95": "\u5df2\u7b54\uff082026-10-06\uff09\uff1a\u65e9\u671f\u56e2\u89d2\u8272\uff08\u771f\u5267\u60c5\uff09\uff1b\u6d69\u8fb0\u662f\u89d2\u8272\u4e5f\u662f\u6897",
    }
    for pend in patch.get("pending", []) or []:
        item = pend.get("item", "")
        if "\u5df2\u7b54\uff082026-10-06\uff09" in item:
            continue
        for k, v in answered.items():
            if k in item:
                pend["item"] = item + "\uff08" + v + "\uff09"
                pend["confirmed"] = True
                log.append("pending answered: %s..." % item[:20])
                break

    print("\n".join("  " + x for x in log) or "  (no change)")
    if not a.apply:
        print("\n[dry-run] add --apply to write")
        return 0
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for f in (cfile, rfile, pfile, PATCH):
        shutil.copyfile(f, f.with_name(f.name + ".bak_tideqa2_" + stamp))
    cfile.write_text(json.dumps(chars, ensure_ascii=False, indent=1), encoding="utf-8")
    rfile.write_text(json.dumps(rels, ensure_ascii=False, indent=1), encoding="utf-8")
    pfile.write_text(json.dumps(plays, ensure_ascii=False, indent=1), encoding="utf-8")
    PATCH.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\nwritten (backups *.bak_tideqa2_%s)" % stamp)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
