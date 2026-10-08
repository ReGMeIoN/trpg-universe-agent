# -*- coding: utf-8 -*-
"""构建「游戏风角色关系网」站点（★ 新站，顶掉旧的绘本站）。

设计参考：`素材\\明日方舟关系网效果图\\`（三层钻取：势力总览 → 卡片关系网 → 人物档案）。
美术概念：「跑团档案库 · 观测终端」——冷色全息底 + 蓝图网格 + 每组一套主题色。

选角范围：主人指定的 3 个「照片齐全」团（阴阳 / 圣剑 / 魔法少女育成计划 6）
          + 与它们有直接关系的跨团角色 + 各团代表人物（保证跨团/同位体视角有东西看）。

用法:
    python tools/build_net_site.py --plan        # 只打印选角结果，不出站
    python tools/build_net_site.py               # 出站到 TRPG-agent\\site\\
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
SITE = ROOT / "site"
SRC = ROOT / "tools" / "_netsite"                      # 前端模板（html/css/js）
ASSETS = SITE / "assets" / "portraits"

# 主人指定的三个团
CORE_GROUPS = [
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08",          # 阴阳差事录 超自然怪谈
    "\u5723\u5251\u82f1\u96c4\u8c2d",                                            # 圣剑英雄谭
    "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6",                        # 魔法少女育成计划 6
]
# 每个「非核心团」额外带进来的代表人物数（按度数）
TYPICAL_PER_GROUP = 3

# 每组主题色（hue/sat/light 由前端算渐变；这里给主色）
GROUP_COLOR = {
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08": "#d94b3a",   # 朱砂
    "\u5723\u5251\u82f1\u96c4\u8c2d": "#d8b25a",                                  # 羊皮纸金
    "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6": "#6fd6c0",               # 薄荷
    "\u9b54\u6cd5\u5c11\u5973\u6551\u8d4e\u7ebf": "#c86fd6",                       # 紫
    "\u9b54\u6cd5\u5c11\u5973\u6728\u67dc\u5b50": "#e08a5a",                       # 橙
    "\u9b54\u6cd5\u5c11\u59732": "#7fa8e8",                                        # 蓝
    "\u9b54\u6cd5\u5c11\u5973\u4e94": "#e0709a",                                   # 粉
    "\u9b54\u5973\u88c1\u5224\u5385": "#9aa7b8",                                   # 冷灰
    "\u65e0\u654c\u5de8\u9ca8\u5927\u6218\u5948\u4e9a\u62c9\u6258\u63d0\u666e": "#4fa3c7",  # 海蓝
    "\u81f4\u65e0\u540d\u8005\u4e4b\u58f0": "#6b7f9e",
    "\u604b\u7231\u4e0e\u547d\u8fd0\u7684\u4e0d\u601d\u8bae\u5192\u9669\uff01\uff1f": "#e0b0c0",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u4f2a\u4eba\u6740": "#b03a3a",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u96ea\u5c71\u72fc\u4eba\u6740": "#8a3ab0",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u5f02\u4e16\u754c\u5927\u9003\u6740": "#3ab07a",
}
DEFAULT_COLOR = "#8fa3b8"

# 角色类型色条：PC 金 / NPC 灰 / BOSS 红 / 跨团 紫 / KP 蓝
KIND_ORDER = ["PC", "NPC", "BOSS", "\u8de8\u56e2", "KP"]

# 团名 → 封面 slug（对应 novelai/trpg-gen25-covers.py 的 CASES）
COVER_SLUG = {
    "\u9b54\u6cd5\u5c11\u5973\u80b2\u6210\u8ba1\u5212 6": "mg6",
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08": "yy",
    "\u5723\u5251\u82f1\u96c4\u8c2d": "sjt",
    "\u9b54\u6cd5\u5c11\u5973\u4e94": "mg5",
    "\u65e0\u654c\u5de8\u9ca8\u5927\u6218\u5948\u4e9a\u62c9\u6258\u63d0\u666e": "js",
    "\u9b54\u6cd5\u5c11\u5973\u6551\u8d4e\u7ebf": "mg3",
    "\u9b54\u6cd5\u5c11\u5973\u6728\u67dc\u5b50": "mg4",
    "\u604b\u7231\u4e0e\u547d\u8fd0\u7684\u4e0d\u601d\u8bae\u5192\u9669\uff1f\uff01": "love",
    "\u9b54\u6cd5\u5c11\u5973\u0032": "mg2",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u5f02\u4e16\u754c\u5927\u9003\u6740": "dw_isekai",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u4f2a\u4eba\u6740": "dw_rensha",
    "\u9b54\u5973\u88c1\u5224\u5385": "g2",
    "\u81f4\u65e0\u540d\u8005\u4e4b\u58f0": "g3",
    "\u5367\u69fd\u662f\u4f2a\u4eba\u7fa4\u00b7\u96ea\u5c71\u72fc\u4eba\u6740": "xs",
}
COVER_SRC = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '25-trpg-covers')
COVER_PICKS = COVER_SRC / "_picks_cover.json"


def kind_of(c: dict) -> str:
    tags = c.get("tags") or []
    if "KP" in tags:
        return "KP"
    if "\u8de8\u56e2" in tags:
        return "\u8de8\u56e2"
    if "BOSS" in tags:
        return "BOSS"
    if "PC" in tags:
        return "PC"
    return "NPC"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    plan_only = "--plan" in sys.argv

    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    by_id = {c["id"]: c for c in chars}
    deg: dict[str, int] = {}
    for r in rels:
        deg[r["from"]] = deg.get(r["from"], 0) + 1
        deg[r["to"]] = deg.get(r["to"], 0) + 1

    core = {c["id"] for c in chars if set(c.get("groups") or []) & set(CORE_GROUPS)}
    # ① 与核心三人有直接关系的团外角色
    nb = set()
    for r in rels:
        a, b = r["from"], r["to"]
        if a in core and b not in core:
            nb.add(b)
        elif b in core and a not in core:
            nb.add(a)
    # ② 跨团角色
    cross = {c["id"] for c in chars if "\u8de8\u56e2" in (c.get("tags") or [])}
    # ③ 每个非核心团的代表人物（按度数）
    others: dict[str, list[str]] = {}
    for c in chars:
        for g in (c.get("groups") or []):
            if g not in CORE_GROUPS:
                others.setdefault(g, []).append(c["id"])
    typical = set()
    for g, ids in others.items():
        for cid in sorted(ids, key=lambda i: -deg.get(i, 0))[:TYPICAL_PER_GROUP]:
            typical.add(cid)

    # ⚠️ **2026-10-06 主人拍板：站点口径改成「全量」** —— 以前只挑核心+邻居+跨团+每团代表，
    #    导致"以前那些团的角色"根本不在站上。现在所有角色都上站（没立绘的也上，
    #    前端显示「未解封」剪影卡），只剔除 `confirmed: false` 的（按项目铁律不算存在）。
    #    ⚠️ 必须和 server/edit_api.py 的 `select_site_scope()` 完全一致，否则静态站与服务器会打架。
    all_ids = [c["id"] for c in chars if c.get("confirmed", True) is not False]
    sel = sorted(all_ids, key=lambda i: (-deg.get(i, 0), by_id[i].get("name", "")))
    sel_set = set(sel)
    sel_rels = [r for r in rels if r["from"] in sel_set and r["to"] in sel_set
                and r["from"] != r["to"]]
    # 只保留两端都在选角里的边
    deg2: dict[str, int] = {i: 0 for i in sel}
    for r in sel_rels:
        deg2[r["from"]] += 1
        deg2[r["to"]] += 1
    iso = [i for i in sel if deg2[i] == 0]

    print(f"全量口径 {len(sel)} 人（核心 {len(core)} · 其余全收；剔除 confirmed:false）")
    print(f"选中的边 {len(sel_rels)} / 全库 {len(rels)}")
    print(f"其中无立绘 {sum(1 for i in sel if not by_id[i].get('avatar'))} 人"
          f"，孤立（全量内没边）{len(iso)} 人")
    if plan_only:
        for i in sel:
            c = by_id[i]
            tag = "\u6838\u5fc3" if i in core else ("\u90bb\u5c45" if i in nb else
                                           ("\u8de8\u56e2" if i in cross else "\u4ee3\u8868"))
            print(f"  [{tag}] {c.get('name',''):<20}{i:<28}{deg.get(i,0):>3} 边  "
                  f"{'\u3001'.join(c.get('groups') or [])}"[:110])
        print("\n各团人数：")
        cnt: dict[str, int] = {}
        for i in sel:
            for g in (by_id[i].get("groups") or ["(无)"]):
                cnt[g] = cnt.get(g, 0) + 1
        for g, n in sorted(cnt.items(), key=lambda kv: -kv[1]):
            print(f"  {n:>4}  {g}")
        return 0

    # ── 出站 ─────────────────────────────────────────────────────────
    if SITE.exists():
        shutil.rmtree(SITE)
    ASSETS.mkdir(parents=True, exist_ok=True)

    def portrait(i: str) -> dict | None:
        c = by_id[i]
        av = c.get("avatar")
        if not av:
            return None
        src = DATA / "\u5934\u50cf" / Path(str(av).replace("\\", "/")).name
        if not src.is_file():
            return None
        try:
            im = Image.open(src).convert("RGB")
        except Exception:  # noqa: BLE001
            return None
        w, h = im.size
        # 卡片：2:3，宽 300；档案：宽 620
        thumb = ASSETS / f"{i}_t.jpg"
        full = ASSETS / f"{i}_f.jpg"
        for dst, tw, q in ((thumb, 300, 82), (full, 620, 86)):
            nh = int(tw * 3 / 2)
            # 按 2:3 裁切（居中偏上，保头）
            target = tw / nh
            if w / h > target:
                nw = int(h * target)
                box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
            else:
                nh2 = int(w / target)
                top = max(0, int((h - nh2) * 0.12))
                box = (0, top, w, top + nh2)
            im.crop(box).resize((tw, nh), Image.LANCZOS).save(
                dst, "JPEG", quality=q, optimize=True, progressive=True)
        return {"thumb": f"assets/portraits/{thumb.name}", "full": f"assets/portraits/{full.name}"}

    out_chars = []
    for i in sel:
        c = by_id[i]
        out_chars.append({
            "id": i, "name": c.get("name") or i,
            "groups": c.get("groups") or [],
            "tags": [t for t in (c.get("tags") or []) if t not in ("\u5f85\u786e\u8ba4",)],
            "kind": kind_of(c),
            "played_by": c.get("played_by") or "",
            "identity": c.get("identity") or "",
            "note": c.get("note") or "",
            "degree": deg2.get(i, 0),
            "events": c.get("events") or [],
            "profile": c.get("profile") or "",      # wiki 正文（Markdown 子集：## 分节 / ==关键词== / > 台词）
            "profile_src": c.get("profile_src") or "",
            "attrs": c.get("attrs") or {},          # 结构化属性标签：{维度: 值}，值可为字符串或数组
            "avatar": portrait(i),
            "is_core": c.get("groups", [None])[0] in CORE_GROUPS if c.get("groups") else False,
        })
    out_rels = [{"a": r["from"], "b": r["to"], "type": r.get("type") or "",
                 "raw": r.get("type_raw") or "", "strength": r.get("strength") or "",
                 "event": r.get("event") or ""} for r in sel_rels]

    gc: dict[str, int] = {}
    for ch in out_chars:
        for g in (ch["groups"] or ["(\u672a\u5206\u7ec4)"]):
            gc[g] = gc.get(g, 0) + 1
    out_groups = [{"name": g, "count": n,
                   "color": GROUP_COLOR.get(g, DEFAULT_COLOR),
                   "core": g in CORE_GROUPS}
                  for g, n in sorted(gc.items(), key=lambda kv: (-kv[1], kv[0]))]

    # ── 封面 ────────────────────────────────────────────────────────
    # 按团：NAI 生成的宿命感大图（读 _picks_cover.json；没有就默认候选 a）
    # 按创作者 / 按类型：用「该 PL / 该类型里度数最高的角色」的立绘当封面
    picks = {}
    if COVER_PICKS.is_file():
        try:
            picks = json.loads(COVER_PICKS.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            picks = {}
    cov_dir = SITE / "assets" / "covers"
    cov_dir.mkdir(parents=True, exist_ok=True)
    covers: dict[str, dict[str, str]] = {"group": {}, "creator": {}, "kind": {}}
    for g in out_groups:
        slug = COVER_SLUG.get(g["name"])
        if not slug:
            continue
        tag = str(picks.get(slug) or "a").strip().lstrip("_")
        if tag not in ("a", "b", "c"):
            tag = "a"
        src = COVER_SRC / f"{slug}_{tag}.png"
        if not src.is_file():
            for t in ("a", "b", "c"):
                if (COVER_SRC / f"{slug}_{t}.png").is_file():
                    src = COVER_SRC / f"{slug}_{t}.png"
                    break
        if not src.is_file():
            continue
        im = Image.open(src).convert("RGB")
        im.resize((560, 560), Image.LANCZOS).save(
            cov_dir / f"{slug}.jpg", "JPEG", quality=84, optimize=True)
        covers["group"][g["name"]] = f"assets/covers/{slug}.jpg"

    deg_of = {c["id"]: deg2.get(c["id"], 0) for c in out_chars}
    av_of = {c["id"]: (c["avatar"] or {}).get("full") for c in out_chars}

    def front(ids: list[str]) -> str | None:
        best = sorted([i for i in ids if av_of.get(i)], key=lambda i: -deg_of.get(i, 0))
        if best:
            return av_of[best[0]]
        best = sorted(ids, key=lambda i: -deg_of.get(i, 0))
        return av_of.get(best[0]) if best else None

    by_creator: dict[str, list[str]] = {}
    by_kind: dict[str, list[str]] = {}
    for c in out_chars:
        by_creator.setdefault(c["played_by"] or "(\u672a\u8bb0\u5f55)", []).append(c["id"])
        by_kind.setdefault(c["kind"], []).append(c["id"])
    for k, ids in by_creator.items():
        f = front(ids)
        if f:
            covers["creator"][k] = f
    for k, ids in by_kind.items():
        f = front(ids)
        if f:
            covers["kind"][k] = f

    SITE.mkdir(parents=True, exist_ok=True)
    (SITE / "data.js").write_text(
        "window.NET=" + json.dumps(
            {"generated": datetime.now().strftime("%Y-%m-%d %H:%M"),
             "groups": out_groups, "chars": out_chars, "rels": out_rels,
             "covers": covers, "core_groups": CORE_GROUPS, "kinds": KIND_ORDER,
             "cover_picks": picks},
            ensure_ascii=False, separators=(",", ":")) + ";\n", encoding="utf-8")
    # 前端模板整目录拷过来（data.js 是上面生成的，不拷）
    # ⚠️ 原来是写死 ("index.html","style.css","app.js") 三个名字 ——
    #    2026-10-06 加 wiki.js / wiki-boot.js 时就被漏掉了，改成通配以免再犯。
    n_front = 0
    for f in sorted(SRC.glob("*")):
        if f.is_file() and f.name != "data.js":
            shutil.copy2(f, SITE / f.name)
            n_front += 1
    size = sum(p.stat().st_size for p in SITE.rglob("*") if p.is_file())
    print(f"\n出站: {SITE}")
    print(f"  {len(out_chars)} 角色 / {len(out_rels)} 关系 / {len(out_groups)} 个团")
    print(f"  立绘 {sum(1 for c in out_chars if c['avatar'])} 张 · 总大小 {size / 1048576:.1f} MB")
    print(f"  封面：团 {len(covers['group'])} / 创作者 {len(covers['creator'])} / 类型 {len(covers['kind'])}")
    dims: dict[str, int] = {}
    for ch in out_chars:
        for k in (ch.get("attrs") or {}):
            dims[k] = dims.get(k, 0) + 1
    if dims:
        top = "、".join(f"{k} {n}" for k, n in sorted(dims.items(), key=lambda kv: -kv[1])[:6])
        print(f"  属性维度：{len(dims)} 种（{top}）")
    if not covers["group"]:
        print("  ⚠ 一张团封面都没找到——先跑 novelai\\trpg-gen25-covers.py")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
