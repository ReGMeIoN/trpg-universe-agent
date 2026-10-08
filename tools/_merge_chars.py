# -*- coding: utf-8 -*-
"""把「同一个人被建成两个节点」合并成一个（数据层定向修正，带备份 + 复验）。

场景：`阴阳差事录` 的「刘汤」与「老师的妹妹」其实是同一人；
本工具把 drop 节点的**别名 / 标签 / 身份 / 备注 / 事件**并进 keep，重定向所有关系边，
删掉 drop 节点，并**同步改补丁**。

⚠️ 为什么要改补丁：`store` 的 `characters[]` 是「新节点」清单——
只从生产库删、不删补丁，下次 `store --apply` 会把 drop 节点**重新建成新角色**。
关系边同理（去重键是 `(from,to,type)`）。

用法:
    python tools/_merge_chars.py --keep yy_liulong_meimei --drop yy_laoshimeimei \
        --name "刘汤" --avatar-from drop          # dry-run
    ... 加 --apply 落盘
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
AVATARS = DATA / "\u5934\u50cf"                         # 头像
PATCHES = WS / ".trpg" / "patches"


def merge_events(a: list, b: list) -> list:
    """按 group 合并事件条目并去重（保持原顺序）。"""
    out: list[dict] = []
    idx: dict[str, dict] = {}
    for ev in list(a or []) + list(b or []):
        g = ev.get("group") or ""
        if g not in idx:
            item = {"group": g, "items": []}
            idx[g] = item
            out.append(item)
        for it in ev.get("items") or []:
            if it not in idx[g]["items"]:
                idx[g]["items"].append(it)
    return out


def uniq(seq: list) -> list:
    seen, out = set(), []
    for x in seq:
        if x is None:
            continue
        s = str(x).strip()
        if s and s not in seen:
            seen.add(s)
            out.append(s)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    a = sys.argv
    if "--keep" not in a or "--drop" not in a:
        print(__doc__)
        return 1
    keep_id = a[a.index("--keep") + 1]
    drop_id = a[a.index("--drop") + 1]
    new_name = a[a.index("--name") + 1] if "--name" in a else None
    avatar_from = a[a.index("--avatar-from") + 1] if "--avatar-from" in a else "keep"
    apply_ = "--apply" in a
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    cf = DATA / "characters.json"
    rf = DATA / "relations.json"
    cdoc = json.loads(cf.read_text(encoding="utf-8"))
    chars = cdoc["characters"]
    by_id = {c.get("id"): c for c in chars}
    keep, drop = by_id.get(keep_id), by_id.get(drop_id)
    if not keep or not drop:
        print(f"!! 找不到节点: keep={bool(keep)} drop={bool(drop)}")
        return 1

    # ── 合并角色字段 ───────────────────────────────────────────
    before = json.dumps(keep, ensure_ascii=False)
    keep["aliases"] = uniq((keep.get("aliases") or []) + (drop.get("aliases") or []) + [drop.get("name")])
    keep["aliases"] = [x for x in keep["aliases"] if x != (new_name or keep.get("name"))]
    keep["tags"] = uniq((keep.get("tags") or []) + (drop.get("tags") or []))
    if new_name:
        keep["name"] = new_name
    if drop.get("identity") and drop.get("identity") not in (keep.get("identity") or ""):
        keep["identity"] = "；".join(x for x in [keep.get("identity"), drop.get("identity")] if x)
    nk = (keep.get("note") or "").strip()
    nd = (drop.get("note") or "").strip()
    if nd and nd not in nk:
        keep["note"] = f"{nk}\n【合并】{nd}"
    if not keep.get("played_by") and drop.get("played_by"):
        keep["played_by"] = drop["played_by"]
    keep["events"] = merge_events(keep.get("events"), drop.get("events"))
    if drop.get("in_graph") is False and keep.get("in_graph") is not False:
        keep["in_graph"] = False

    # ── 立绘：把 drop 的图**覆盖到 keep 现有的文件名**上（路径不变，图换掉）──
    av_plan = None
    if avatar_from == "drop" and drop.get("avatar"):
        src = AVATARS / Path(str(drop["avatar"]).replace("\\", "/")).name
        if keep.get("avatar"):
            dst = AVATARS / Path(str(keep["avatar"]).replace("\\", "/")).name
        else:
            dst = AVATARS / f"{keep.get('groups', [''])[0]}_{keep.get('name', keep_id)}.jpg"
            keep["avatar"] = f"{DATA.name}\\{AVATARS.name}\\{dst.name}"
        av_plan = (src, dst)
    elif not keep.get("avatar") and drop.get("avatar"):
        keep["avatar"] = drop["avatar"]

    # ── 关系边重定向 ───────────────────────────────────────────
    # ⚠️ 只处理「重定向**造成**的」冲突：合并前就存在的重复边/自环**不许动**
    #    （那是别的问题，顺手清掉等于偷偷改了不相关的数据）。
    rdoc = json.loads(rf.read_text(encoding="utf-8"))
    rels = rdoc.get("relations") or []
    before_keys = {(r.get("from"), r.get("to"), r.get("type")) for r in rels}
    pre_dup = len(rels) - len(before_keys)
    pre_self = sum(1 for r in rels if r.get("from") == r.get("to"))
    moved, self_new, clash, dup_new = 0, 0, 0, 0
    kept: set = set()
    out: list[dict] = []
    for r in rels:
        f0, t0, ty = r.get("from"), r.get("to"), r.get("type")
        f = keep_id if f0 == drop_id else f0
        t = keep_id if t0 == drop_id else t0
        touched = (f, t) != (f0, t0)
        if touched:
            moved += 1
        k0, k = (f0, t0, ty), (f, t, ty)
        if touched and f == t:
            self_new += 1
            continue                                    # 合并合并出来的自环
        if touched and k in before_keys and k != k0:
            clash += 1
            continue                                    # 重定向后撞上一条已存在的边
        if k in kept:
            if touched:
                dup_new += 1
                continue                                # 两条边被重定向成同一条
            # 原始就重复的：保留第一条（不动原数据）
        kept.add(k)
        out.append(dict(r, **{"from": f, "to": t}) if touched else r)

    print(f"=== 合并 {drop_id} → {keep_id} ===")
    print(f"  keep: {keep.get('name')}  别名 {len(keep['aliases'])}  标签 {keep['tags']}  事件组 {len(keep['events'])}")
    print(f"  立绘: {'用 drop 的图覆盖 ' + av_plan[1].name if av_plan else '(不变)'}")
    print(f"  关系: 重定向 {moved} 条 · 合并出自环丢弃 {self_new} · 撞已有边丢弃 {clash} · 相互撞车丢弃 {dup_new}"
          f" · {len(rels)} → {len(out)} 条")
    if pre_dup or pre_self:
        print(f"  （合并前就存在的重复边 {pre_dup} 条 / 自环 {pre_self} 条——**未动**，属另一码事）")

    # ── 补丁同步（只动真正引用到这两个 id 的补丁）───────────────
    patch_plan = []
    for pf in sorted(PATCHES.glob("*_patch.json")):
        pd = json.loads(pf.read_text(encoding="utf-8"))
        hit_rel = [r for r in (pd.get("relations") or [])
                   if r.get("from") in (keep_id, drop_id) or r.get("to") in (keep_id, drop_id)]
        hit_char = [c for c in (pd.get("characters") or []) if c.get("id") in (keep_id, drop_id)]
        hit_upd = [c for c in (pd.get("character_updates") or []) if c.get("id") == drop_id]
        if not (hit_char and any(c.get("id") == drop_id for c in hit_char)) and not hit_upd and not any(
                r.get("from") == drop_id or r.get("to") == drop_id for r in hit_rel):
            continue
        touched = []
        cs = pd.get("characters") or []
        if any(c.get("id") == drop_id for c in cs):
            pd["characters"] = [c for c in cs if c.get("id") != drop_id]
            touched.append("characters 去掉 drop")
        for c in pd.get("characters") or []:
            if c.get("id") == keep_id:
                c.update({k: keep[k] for k in ("name", "aliases", "tags", "identity", "note", "events") if k in keep})
                touched.append("characters 更新 keep")
        for k in ("character_updates",):
            lst = pd.get(k) or []
            n = len(lst)
            lst = [x for x in lst if x.get("id") != drop_id]
            if len(lst) != n:
                pd[k] = lst
                touched.append(f"{k} 去掉 drop")
        n = 0
        for r in pd.get("relations") or []:
            if r.get("from") == drop_id:
                r["from"] = keep_id
                n += 1
            if r.get("to") == drop_id:
                r["to"] = keep_id
                n += 1
        if n:
            touched.append(f"relations 重定向 {n}")
        if touched:
            patch_plan.append((pf, pd, touched))
            print(f"  补丁 {pf.name}: {' · '.join(touched)}")

    drafts = []
    for df in sorted(PATCHES.glob("*_relations_draft.json")):
        dd = json.loads(df.read_text(encoding="utf-8"))
        n = 0
        for r in dd.get("relations") or []:
            if r.get("from") == drop_id or r.get("to") == drop_id:
                if r.get("from") == drop_id:
                    r["from"] = keep_id
                if r.get("to") == drop_id:
                    r["to"] = keep_id
                n += 1
        if n:
            drafts.append((df, dd))
            print(f"  草稿 {df.name}: 重定向 {n}")

    if not apply_:
        print("\n(dry-run; 加 --apply 落盘)")
        return 0

    bdir = DATA / f"_bak_merge_{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    for f in (cf, rf):
        shutil.copy2(f, bdir / f.name)
    if av_plan and av_plan[0].is_file():
        shutil.copy2(av_plan[0], av_plan[1])
        print(f"  立绘已覆盖: {av_plan[1].name}")
    cdoc["characters"] = [c for c in chars if c.get("id") != drop_id]
    cdoc["characters"] = [keep if c.get("id") == keep_id else c for c in cdoc["characters"]]
    rf_bak = bdir / rf.name
    rdoc["relations"] = out
    cf.write_text(json.dumps(cdoc, ensure_ascii=False, indent=2), encoding="utf-8")
    rf.write_text(json.dumps(rdoc, ensure_ascii=False, indent=2), encoding="utf-8")
    for pf, pd, _ in patch_plan:
        shutil.copy2(pf, bdir / pf.name)
        pf.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
    for df, dd in drafts:
        shutil.copy2(df, bdir / df.name)
        df.write_text(json.dumps(dd, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 复验 ───────────────────────────────────────────────────
    chk_c = json.loads(cf.read_text(encoding="utf-8"))["characters"]
    chk_r = json.loads(rf.read_text(encoding="utf-8"))["relations"]
    ids = {c.get("id") for c in chk_c}
    dangling = [r for r in chk_r if r.get("from") not in ids or r.get("to") not in ids]
    still = [c for c in chk_c if c.get("id") == drop_id]
    print(f"\n已写入（备份 {bdir}）")
    print(f"  角色 {len(chk_c)} · 关系 {len(chk_r)}")
    print(f"  复验：drop 节点残留 {len(still)} · 悬空端点 {len(dangling)}")
    return 0 if not still and not dangling else 1


if __name__ == "__main__":
    raise SystemExit(main())
