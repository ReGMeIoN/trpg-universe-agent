# -*- coding: utf-8 -*-
"""把站点上「已采纳」的 wiki 建议拉回生产库。

背景（两步走的闭环）：
    访客提交 → 待审箱 → 主人审核通过 → **站点立刻可见（覆盖层）**
                                          ↓ 但生产库还没动
    本工具：拉回生产库 → 走既有流程（备份 + 复验 + 重建站点）

为什么不一键全自动：项目铁律是 **生产库改动必须人工过审**，而且 `store` 只支持
「新增角色 / 新增关系 / 追加 note」，**不支持删节点、改关系端点**。
所以这里的分工是：
    · `char_create` / `rel_create` / `char_update`  → 可安全落盘（写补丁 + 直接改库）
    · `char_delete` / `rel_delete` / `rel_update`   → **只列清单，不自动执行**（要人确认）

用法:
    python tools\\_pull_suggestions.py                    # 预览（默认从线上拉）
    python tools\\_pull_suggestions.py --apply            # 落盘（全程备份 + 复验）
    python tools\\_pull_suggestions.py --from-file x.json # 读审核页「导出补丁」的文件
    python tools\\_pull_suggestions.py --url http://127.0.0.1:8787   # 打本地 wrangler dev
"""
from __future__ import annotations

import os
import argparse
import json
import shutil
import sys
import urllib.request
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))          # TRPG关系网
DATA = WS / "\u6570\u636e"                                   # 数据
PATCHES = WS / ".trpg" / "patches"
REPORTS = WS / ".trpg" / "reports"
DEFAULT_URL = "https://sjt-chronicle.sjt-chronicle.workers.dev"

SAFE_KINDS = {"char_create", "rel_create", "char_update"}
# 关系的「改 / 删」现在也支持落盘了（会**同步改补丁**，否则 store 下次会把旧边又加回来）。
# 只剩「删角色」仍需人工 —— 它牵连该角色的所有关系边，是这里最重的操作。
REL_EDIT_KINDS = {"rel_update", "rel_delete"}
MANUAL_KINDS = {"char_delete"}


def fetch_approved(base: str) -> list[dict]:
    url = base.rstrip("/") + "/api/suggestions?status=approved&limit=200"
    with urllib.request.urlopen(url, timeout=60) as r:
        d = json.loads(r.read().decode("utf-8"))
    if not d.get("ok"):
        raise RuntimeError(d.get("error") or "接口返回异常")
    return d.get("items") or []


def load_chars() -> tuple[dict, list]:
    doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    chars = doc["characters"]
    return doc, chars


def group_of(cid: str, chars: list) -> str | None:
    for c in chars:
        if c.get("id") == cid:
            g = c.get("groups") or []
            return g[0] if g else None
    return None


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default=DEFAULT_URL, help="站点地址（默认线上）")
    ap.add_argument("--from-file", default=None, help="改用审核页导出的 JSON")
    ap.add_argument("--apply", action="store_true", help="真正落盘")
    ap.add_argument("--limit", type=int, default=200)
    args = ap.parse_args()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── 取数据 ────────────────────────────────────────────────
    if args.from_file:
        blob = json.loads(Path(args.from_file).read_text(encoding="utf-8"))
        items = blob.get("items") or []
        src = f"文件 {args.from_file}"
    else:
        items = fetch_approved(args.url)
        src = args.url
    print(f"来源: {src}")
    print(f"已采纳建议: {len(items)} 条")
    if not items:
        print("没有需要同步的东西。")
        return 0

    _cdoc, chars = load_chars()
    by_id = {c.get("id"): c for c in chars}
    rdoc = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))
    rels = rdoc.get("relations") or []
    rel_keys = {(r.get("from"), r.get("to"), r.get("type")) for r in rels}

    safe, manual, dup, rel_edits = [], [], [], []
    for it in items:
        k = it.get("kind")
        p = it.get("payload") or {}
        if k in REL_EDIT_KINDS:
            if p.get("from") not in by_id or p.get("to") not in by_id:
                manual.append(dict(it, _why="端点角色在生产库里不存在"))
                continue
            rel_edits.append(it)
        elif k in MANUAL_KINDS:
            manual.append(it)
        elif k == "char_update":
            cid = it.get("target_id") or p.get("id")
            if cid not in by_id:
                manual.append(dict(it, _why="生产库里找不到该角色"))
                continue
            safe.append(it)
        elif k == "char_create":
            if p.get("id") in by_id:
                dup.append(dict(it, _why="该 id 已存在于生产库"))
                continue
            if not p.get("id"):
                manual.append(dict(it, _why="缺 id"))
                continue
            safe.append(it)
        elif k == "rel_create":
            key = (p.get("from"), p.get("to"), p.get("type") or "其他")
            if key in rel_keys:
                dup.append(dict(it, _why="该关系已存在"))
                continue
            if p.get("from") not in by_id or p.get("to") not in by_id:
                manual.append(dict(it, _why="端点角色在生产库里不存在"))
                continue
            safe.append(it)
        else:
            manual.append(dict(it, _why="未知 kind"))

    print(f"\n可安全落盘 {len(safe)} · 关系改删 {len(rel_edits)} · 需人工确认 {len(manual)} · 跳过(重复) {len(dup)}")

    # ── 落盘计划 ──────────────────────────────────────────────
    # 按团分桶：一个补丁文件装一个团的新角色/新关系
    patch_buckets: dict[str, dict] = {}

    def bucket(g: str) -> dict:
        if g not in patch_buckets:
            patch_buckets[g] = {"characters": [], "character_updates": [], "relations": []}
        return patch_buckets[g]

    live_edits: list[tuple[str, str, dict]] = []      # (kind, id, payload) 直接改生产库

    for it in safe:
        k, p = it["kind"], it["payload"]
        if k == "char_create":
            g = (p.get("groups") or ["(未分组)"])[0]
            bucket(g)["characters"].append({
                "id": p["id"], "name": p.get("name") or p["id"],
                "aliases": p.get("aliases") or [], "identity": p.get("identity") or "",
                "groups": p.get("groups") or [], "tags": p.get("tags") or [],
                "played_by": p.get("played_by") or "", "note": p.get("note") or "",
                "confirmed": True, "pending_reason": "", "segment": "wiki 建议",
            })
        elif k == "rel_create":
            g = group_of(p["from"], chars) or "(未分组)"
            bucket(g)["relations"].append({
                "from": p["from"], "to": p["to"], "type": p.get("type") or "其他",
                "strength": p.get("strength") or "中", "event": p.get("event") or "",
                "confirmed": True,
            })
        elif k == "char_update":
            cid = it.get("target_id") or p.get("id")
            upd = {"id": cid}
            if p.get("name") and p["name"] != by_id[cid].get("name"):
                upd["set_name"] = p["name"]
            live_edits.append(("char_update", cid, p))
            g = group_of(cid, chars)
            if g:
                bucket(g)["character_updates"].append(upd)

    print("\n--- 补丁分桶 ---")
    for g, b in sorted(patch_buckets.items()):
        print(f"  [{g}] 新角色 {len(b['characters'])} · 新关系 {len(b['relations'])} · 更新 {len(b['character_updates'])}")
    if live_edits:
        print("\n--- 直接改生产库（store 不支持，故本地写入）---")
        for kind, cid, p in live_edits:
            fields = "、".join(f"{k}" for k in p.keys())
            print(f"  {by_id.get(cid, {}).get('name', cid)}: 改 {fields}")
    if manual:
        print("\n--- ⚠️ 需人工确认（未执行）---")
        for it in manual:
            print(f"  #{it['id']} {it['kind']} {it.get('_why') or ''} :: {str(it.get('payload'))[:80]}")
    if dup:
        print("\n--- 跳过（已存在）---")
        for it in dup:
            print(f"  #{it['id']} {it['kind']} {it.get('_why')}")

    # ── 报告 ─────────────────────────────────────────────────
    REPORTS.mkdir(parents=True, exist_ok=True)
    rep = REPORTS / f"wiki同步_{stamp}.md"
    lines = [f"# wiki 建议同步报告 · {datetime.now():%Y-%m-%d %H:%M}", "",
             f"来源：{src}", f"已采纳：**{len(items)}** 条；可落盘 {len(safe)} · 需人工 {len(manual)} · 跳过 {len(dup)}", ""]
    if patch_buckets:
        lines += ["## 补丁分桶", ""]
        for g, b in sorted(patch_buckets.items()):
            lines.append(f"- **{g}**：新角色 {len(b['characters'])} · 新关系 {len(b['relations'])} · 更新 {len(b['character_updates'])}")
        lines.append("")
    if manual:
        lines += ["## ⚠️ 需人工确认（脚本未执行）", ""]
        for it in manual:
            lines.append(f"- `#{it['id']}` **{it['kind']}** {it.get('_why') or ''}")
            lines.append(f"  - payload: `{json.dumps(it.get('payload'), ensure_ascii=False)[:300]}`")
            lines.append(f"  - 理由: {it.get('reason') or '（无）'} · 提交者: {it.get('author') or '匿名'}")
        lines.append("")
    if dup:
        lines += ["## 跳过（已存在）", ""]
        for it in dup:
            lines.append(f"- `#{it['id']}` {it['kind']} — {it.get('_why')}")
        lines.append("")

    print(f"\n报告: {rep}")

    if not args.apply:
        print("\n(dry-run；加 --apply 落盘)")
        rep.write_text("\n".join(lines), encoding="utf-8")
        return 0

    # ── 真正落盘 ─────────────────────────────────────────────
    bdir = DATA / f"_bak_wiki_{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    for f in (DATA / "characters.json", DATA / "relations.json"):
        shutil.copy2(f, bdir / f.name)
    _patch_writes: dict[Path, dict] = {}     # 待写补丁：路径 → 文档（关系改删先收集，最后统一写）

    # 1) 直接改生产库：char_update 的字段覆盖（含 attrs 按维度合并）
    changed_msgs = []
    for kind, cid, p in live_edits:
        c = by_id.get(cid)
        if not c:
            continue
        touched = []
        for f in ("name", "identity", "note", "played_by", "aliases", "groups", "tags"):
            if f in p and p[f] != c.get(f):
                c[f] = p[f]
                touched.append(f)
        if isinstance(p.get("attrs"), dict):
            if not isinstance(c.get("attrs"), dict):
                c["attrs"] = {}
            at = c["attrs"]
            for dim, val in p["attrs"].items():
                if val is None:                       # null = 删掉这个维度
                    if dim in at:
                        at.pop(dim)
                        touched.append(f"-{dim}")
                elif at.get(dim) != val:
                    at[dim] = val
                    touched.append(f"+{dim}")
        if touched:
            changed_msgs.append(f"{c.get('name')}({cid}): {'、'.join(touched)}")

    # 2) 关系改 / 删：直接改 relations.json，并**同步改补丁**（否则 store 下次会把旧边加回来）
    rel_msgs = []
    for it in rel_edits:
        p = it["payload"]
        parts = str(it.get("target_id") or "").split("|")
        idx = None
        if len(parts) == 3:
            for i, r in enumerate(rels):
                if (r.get("from"), r.get("to"), r.get("type")) == (parts[0], parts[1], parts[2]):
                    idx = i
                    break
        if idx is None:                                # 退化为按端点找
            for i, r in enumerate(rels):
                if r.get("from") == p.get("from") and r.get("to") == p.get("to"):
                    idx = i
                    break
        if idx is None:
            manual.append(dict(it, _why="生产库里找不到这条关系"))
            continue
        old = rels[idx]
        old_key = (old.get("from"), old.get("to"), old.get("type"))
        if it["kind"] == "rel_delete":
            rels.pop(idx)
            rel_msgs.append(f"删关系 {old_key[0]}—{old_key[2]}→{old_key[1]}")
        else:
            for f in ("type", "strength", "event", "raw"):
                if p.get(f) is not None and p.get(f) != old.get(f):
                    old[f] = p[f]
            rel_msgs.append(f"改关系 {old_key[0]}—{old_key[2]}→{old_key[1]} ⇒ "
                            f"{old.get('type')}/{old.get('strength')}")
        # 同步补丁：把该团的补丁里同一端点的那条一起改/删
        for g in {group_of(p.get("from"), chars), group_of(p.get("to"), chars)}:
            if not g:
                continue
            pf = PATCHES / f"{g}_patch.json"
            if not pf.is_file():
                continue
            pd = json.loads(pf.read_text(encoding="utf-8"))
            pr = pd.get("relations") or []
            kept, hit = [], False
            for r in pr:
                if (r.get("from"), r.get("to"), r.get("type")) == old_key:
                    hit = True
                    if it["kind"] == "rel_update":
                        for f in ("type", "strength", "event", "raw"):
                            if p.get(f) is not None:
                                r[f] = p[f]
                        kept.append(r)
                    # rel_delete → 不 append（等于从补丁里删掉）
                else:
                    kept.append(r)
            if hit:
                pd["relations"] = kept
                _patch_writes[pf] = pd
                rel_msgs.append(f"  补丁 {pf.name} 已同步")
    if changed_msgs:
        (DATA / "characters.json").write_text(
            json.dumps(_cdoc, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3) 补丁：新角色 / 新关系 / 更新（供 store 使用，也方便下次重建）
    for g, b in patch_buckets.items():
        pf = PATCHES / f"{g}_patch.json"
        if pf in _patch_writes:
            pd = _patch_writes[pf]                 # 关系段已经改过它了，接着往里加
        elif pf.is_file():
            shutil.copy2(pf, bdir / pf.name)
            pd = json.loads(pf.read_text(encoding="utf-8"))
        else:
            pd = {"group": g, "id_prefix": "", "characters": [], "character_updates": [],
                  "relations": [], "players": [], "pl_profiles": [], "pending": []}
            print(f"  （新建补丁 {pf.name}）")
        pd.setdefault("characters", [])
        pd.setdefault("character_updates", [])
        pd.setdefault("relations", [])
        have_c = {c.get("id") for c in pd["characters"]}
        have_u = {c.get("id") for c in pd["character_updates"]}
        have_r = {(r.get("from"), r.get("to"), r.get("type")) for r in pd["relations"]}
        for c in b["characters"]:
            if c["id"] not in have_c:
                pd["characters"].append(c)
        for u in b["character_updates"]:
            if len(u) > 1 and u["id"] not in have_u:
                pd["character_updates"].append(u)
        for r in b["relations"]:
            if (r["from"], r["to"], r["type"]) not in have_r:
                pd["relations"].append(r)
        _patch_writes[pf] = pd

    # 4) 统一写：补丁 + relations.json
    for pf, pd in _patch_writes.items():
        pf.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
    if rel_msgs:
        rdoc["relations"] = rels
        (DATA / "relations.json").write_text(
            json.dumps(rdoc, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 复验 ────────────────────────────────────────────────
    chk = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    ids = {c.get("id") for c in chk}
    re_rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    dangling = [r for r in re_rels if r.get("from") not in ids or r.get("to") not in ids]

    lines += ["## 落盘结果", "", f"备份：`{bdir}`",
              f"生产库：角色 {len(chk)} · 关系 {len(re_rels)}", ""]
    lines += ["### 改角色"] + ([f"- {m}" for m in changed_msgs] or ["- （无）"])
    lines += ["", "### 关系改 / 删"] + ([f"- {m}" for m in rel_msgs] or ["- （无）"])
    lines += ["", f"悬空端点：**{len(dangling)}**", ""]
    rep.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n已落盘（备份 {bdir}）")
    print(f"  改角色: {len(changed_msgs)} 个")
    print(f"  改/删关系: {len(rel_msgs)} 条（含补丁同步）")
    print(f"  补丁文件: {len(_patch_writes)} 个")
    print(f"  复验: 角色 {len(chk)} · 关系 {len(re_rels)} · 悬空端点 {len(dangling)}")
    print(f"  报告: {rep}")
    print("\n下一步：")
    print("  1) 影子库预演 → store --apply（把补丁里的新角色/新关系入库）")
    print("  2) tools\\build_net_site.py 重建站点 → wrangler deploy")
    print("  3) 需人工确认的删除/改端点项见报告")
    return 0 if not dangling else 1


if __name__ == "__main__":
    raise SystemExit(main())
