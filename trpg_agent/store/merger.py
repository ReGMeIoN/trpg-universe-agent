# -*- coding: utf-8 -*-
"""补丁 -> 变更计划 -> 新文档(staging)。

这是"产品化"的核心替换: 不再为每个团手写 add_<团>.py, 而是由 extract 产出
数据驱动补丁(JSON), store 负责校验/归一/去重/写前备份/报告。

补丁契约(.trpg/patches/<团>_patch.json):
{
  "group": "星海列车",
  "id_prefix": "xs",
  "characters": [
    {"id": "xs_linhai", "name": "临海", "aliases": [...], "identity": "...",
     "groups": ["星海列车"], "tags": ["PC"], "played_by": "阿蓝",
     "note": "...", "events": [{"group": "星海列车", "items": ["..."]}],
     "confirmed": true}
  ],
  "character_updates": [
    {"id": "xh_heiyi", "add_groups": ["星海列车"], "append_note": "...",
     "add_events": [{"group": "星海列车", "items": ["..."]}]
     "set_played_by": null, "confirmed": true}
  ],
  "relations": [
    {"from": "xs_linhai", "to": "xs_miyue", "type": "同伴", "strength": "强",
     "event": "...", "confirmed": true}
  ],
  "players": [...], "pl_profiles": [...],
  "pending": [{"item": "...", "reason": "...", "segment": "段2"}]
}

只写明确项: confirmed=false 的条目一律降级进待确认, 不写盘。
"""
from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.store import naming as naming_mod
from trpg_agent.workspace import Workspace

KIND_LIST_KEY = {
    "characters": "characters",
    "relations": "relations",
    "players": "players",
    "pl_profiles": "profiles",
}
KIND_ID_KEY = {"characters": "id", "players": "uid", "pl_profiles": "uid"}


# --------------------------------------------------------------------------- 补丁

@dataclass
class Patch:
    group: str
    path: str
    id_prefix: str | None = None
    characters: list[dict] = field(default_factory=list)
    character_updates: list[dict] = field(default_factory=list)
    relations: list[dict] = field(default_factory=list)
    players: list[dict] = field(default_factory=list)
    pl_profiles: list[dict] = field(default_factory=list)
    # 给"已存在"的玩家/画像追加内容(两张表原先只支持新增, 已存在的 uid 会被整条跳过 ->
    # 于是"某 PL 在本团演了谁 / 本团的表现"永远写不进去)
    player_updates: list[dict] = field(default_factory=list)
    profile_updates: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    meta: dict = field(default_factory=dict)


def load_patch(path: Path) -> Patch:
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"补丁必须是 JSON 对象: {path}")
    group = str(doc.get("group") or "").strip()
    if not group:
        raise ValueError(f"补丁缺少 group 字段: {path}")
    return Patch(
        group=group,
        path=str(path),
        id_prefix=(str(doc["id_prefix"]).strip() if doc.get("id_prefix") else None),
        characters=list(doc.get("characters") or []),
        character_updates=list(doc.get("character_updates") or doc.get("updates") or []),
        relations=list(doc.get("relations") or []),
        players=list(doc.get("players") or []),
        pl_profiles=list(doc.get("pl_profiles") or []),
        player_updates=list(doc.get("player_updates") or []),
        profile_updates=list(doc.get("profile_updates") or []),
        pending=list(doc.get("pending") or []),
        meta=dict(doc.get("meta") or {}),
    )


def find_patch(ws: Workspace, group: str | None, explicit: Path | None = None) -> Path:
    if explicit:
        if not explicit.is_file():
            raise FileNotFoundError(f"补丁不存在: {explicit}")
        return explicit
    if not group:
        raise ValueError("需要 --patch 或 --group 之一")
    cand = ws.patches / f"{group}_patch.json"
    if not cand.is_file():
        raise FileNotFoundError(
            f"未找到补丁 {cand}\n"
            f"  补丁由 extract 步骤产出; 也可手写(契约见 trpg_agent/store/merger.py 顶部注释)。"
        )
    return cand


# --------------------------------------------------------------------------- 计划

@dataclass
class Plan:
    group: str
    prefix: str = ""
    prefix_source: str = ""
    new_characters: list[dict] = field(default_factory=list)
    updated_characters: list[dict] = field(default_factory=list)
    new_relations: list[dict] = field(default_factory=list)
    new_players: list[dict] = field(default_factory=list)
    updated_profiles: list[dict] = field(default_factory=list)
    player_changes: list[dict] = field(default_factory=list)   # [{uid, changes}]
    profile_changes: list[dict] = field(default_factory=list)  # [{uid, changes}]
    normalized: list[dict] = field(default_factory=list)
    duplicates: list[dict] = field(default_factory=list)
    skipped: list[dict] = field(default_factory=list)
    pending: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    counts_before: dict[str, int] = field(default_factory=dict)
    counts_after: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "group": self.group,
            "id_prefix": self.prefix,
            "id_prefix_source": self.prefix_source,
            "counts_before": self.counts_before,
            "counts_after": self.counts_after,
            "new_characters": [c.get("id") for c in self.new_characters],
            "updated_characters": [c.get("id") for c in self.updated_characters],
            "new_relations": [
                f"{r.get('from')}--{r.get('type')}--{r.get('to')}" for r in self.new_relations
            ],
            "new_players": [p.get("uid") for p in self.new_players],
            "updated_profiles": [p.get("uid") for p in self.updated_profiles],
            "player_changes": [c.get("uid") for c in self.player_changes],
            "profile_changes": [c.get("uid") for c in self.profile_changes],
            "normalized": self.normalized,
            "duplicates": self.duplicates,
            "skipped": self.skipped,
            "pending": self.pending,
            "warnings": self.warnings,
        }


def resolve_prefix(cfg: Config, group: str, patch: Patch) -> tuple[str, str]:
    explicit = cfg.store.id_prefix_map.get(group)
    if explicit:
        if patch.id_prefix and patch.id_prefix != explicit:
            log.warn(f"补丁 id_prefix={patch.id_prefix!r} 与 config 登记 {explicit!r} 不一致, 以 config 为准")
        return explicit, "config.store.id_prefix_map"
    if patch.id_prefix:
        return patch.id_prefix, "patch"
    mode = cfg.store.id_prefix_fallback
    if mode == "error":
        raise ValueError(f"团 {group!r} 未登记 id 前缀, 且 store.id_prefix_fallback=error")
    if mode == "seq":
        return f"g{len(cfg.store.id_prefix_map) + 1}", "fallback:seq"
    ascii_part = "".join(ch for ch in group if ch.isascii() and (ch.isalnum()))
    if ascii_part:
        return ascii_part.lower()[:6], "fallback:ascii"
    h = hashlib.sha1(group.encode("utf-8")).hexdigest()[:4]
    return f"t{h}", "fallback:hash"


def _dedupe_key(group: str, eid: str) -> str:
    return f"{group}|{eid}"


def build_plan(
    docs: dict[str, Any],
    patch: Patch,
    cfg: Config,
    ws: Workspace,
) -> Plan:
    plan = Plan(group=patch.group)
    for kind, key in KIND_LIST_KEY.items():
        plan.counts_before[kind] = len((docs.get(kind) or {}).get(key, []))

    prefix, prefix_source = resolve_prefix(cfg, patch.group, patch)
    plan.prefix = prefix
    plan.prefix_source = prefix_source
    if prefix_source.startswith("fallback"):
        plan.warnings.append(
            f"团 {patch.group!r} 使用兜底前缀 {prefix!r} ({prefix_source}); "
            f"建议在 config.store.id_prefix_map 显式登记"
        )

    naming = naming_mod.load_naming(ws.canon / Path(cfg.store.normalization_file).name)

    chars = list((docs.get("characters") or {}).get("characters", []))
    rels = list((docs.get("relations") or {}).get("relations", []))
    players = list((docs.get("players") or {}).get("players", []))
    profiles = list((docs.get("pl_profiles") or {}).get("profiles", []))

    existing_ids = {c.get("id") for c in chars}
    by_id = {c.get("id"): c for c in chars}
    new_ids: set[str] = set()

    # ---- 新增角色 ----
    for i, raw in enumerate(patch.characters):
        c = copy.deepcopy(raw)
        where = f"characters[{i}]"
        if not c.get("confirmed", True):
            plan.pending.append(
                {
                    "item": f"{c.get('name') or c.get('id') or where}: {c.get('pending_reason') or '补丁标记未确认'}",
                    "reason": c.get("pending_reason") or "confirmed=false",
                    "segment": c.get("segment", ""),
                }
            )
            continue
        cid = str(c.get("id") or "").strip()
        name = str(c.get("name") or "").strip()
        if not cid or not name:
            plan.skipped.append({"where": where, "reason": "缺少 id 或 name (schema 必填)"})
            continue
        if cid in existing_ids or cid in new_ids:
            plan.skipped.append({"where": where, "reason": f"id 已存在: {cid}"})
            continue
        groups = list(c.get("groups") or [])
        if patch.group not in groups:
            groups.append(patch.group)
        c["groups"] = groups
        c.setdefault("tags", [])
        c.setdefault("aliases", [])
        pb, changed = naming.normalize(c.get("played_by"))
        if changed:
            plan.normalized.append({"field": "played_by", "where": cid, "old": raw.get("played_by"), "new": pb})
        if pb is not None:
            c["played_by"] = pb
        if not cid.startswith(prefix):
            plan.warnings.append(f"{cid} 不符合团前缀 {prefix}_ 规范")
        new_ids.add(cid)
        plan.new_characters.append(c)

    # ---- 复用/更新既有角色 ----
    for i, raw in enumerate(patch.character_updates):
        where = f"character_updates[{i}]"
        if not raw.get("confirmed", True):
            plan.pending.append(
                {"item": f"{raw.get('id')}: {raw.get('pending_reason') or '补丁标记未确认'}",
                 "reason": raw.get("pending_reason") or "confirmed=false", "segment": raw.get("segment", "")}
            )
            continue
        cid = str(raw.get("id") or "").strip()
        target = by_id.get(cid)
        if target is None:
            plan.skipped.append({"where": where, "reason": f"待更新角色不存在: {cid}"})
            continue
        changes: dict[str, Any] = {}
        groups = list(target.get("groups") or [])
        added_groups = [g for g in (raw.get("add_groups") or []) if g not in groups]
        if added_groups:
            groups.extend(added_groups)
            changes["groups"] = groups
        if raw.get("append_note"):
            add = str(raw["append_note"]).strip()
            old_note = (target.get("note") or "").rstrip()
            # ⚠️ 幂等: append_note 用「原文是否已出现」判重。
            #    否则同一份补丁重复 --apply 会把同一句越写越多（实测一个节点被写了 2~3 遍，
            #    与 add_groups / add_events 的现有判重逻辑保持一致）。
            if add and add not in old_note:
                sep = "" if (not old_note or old_note.endswith(("。", "！", "？", "."))) else "。"
                changes["note"] = f"{old_note}{sep}{add}" if old_note else add
        for ev in raw.get("add_events") or []:
            events = list(changes.get("events", target.get("events") or []))
            found = next((e for e in events if e.get("group") == ev.get("group")), None)
            if found:
                items = list(found.get("items") or [])
                items.extend(x for x in (ev.get("items") or []) if x not in items)
                found["items"] = items
            else:
                events.append(copy.deepcopy(ev))
            changes["events"] = events
        if raw.get("add_tags"):
            tags = list(target.get("tags") or [])
            tags.extend(t for t in raw["add_tags"] if t not in tags)
            changes["tags"] = tags
        # 改名(ASR 错字修正的常用需求): 支持 character_updates 里给 set_name
        if raw.get("set_name"):
            new_name = str(raw["set_name"]).strip()
            if new_name and new_name != (target.get("name") or ""):
                changes["name"] = new_name
        if raw.get("set_played_by"):
            pb, changed = naming.normalize(raw["set_played_by"])
            if changed:
                plan.normalized.append({"field": "played_by", "where": cid, "old": raw["set_played_by"], "new": pb})
            changes["played_by"] = pb
        if not changes:
            plan.skipped.append({"where": where, "reason": f"{cid} 无实际变更"})
            continue
        plan.updated_characters.append({"id": cid, "changes": changes})

    # ---- 新增关系 ----
    known_ids = existing_ids | new_ids
    seen_triple = {(r.get("from"), r.get("to"), r.get("type")) for r in rels}
    for i, raw in enumerate(patch.relations):
        where = f"relations[{i}]"
        r = copy.deepcopy(raw)
        if not r.get("confirmed", True):
            plan.pending.append(
                {"item": f"{r.get('from')}—{r.get('to')}: {r.get('pending_reason') or '补丁标记未确认'}",
                 "reason": r.get("pending_reason") or "confirmed=false", "segment": r.get("segment", "")}
            )
            continue
        a, b = r.get("from"), r.get("to")
        if not a or not b:
            plan.skipped.append({"where": where, "reason": "缺少 from/to"})
            continue
        missing = [x for x in (a, b) if x not in known_ids]
        if missing:
            plan.skipped.append({"where": where, "reason": f"关系端点不存在: {missing}"})
            continue
        if (a, b, r.get("type")) in seen_triple:
            plan.duplicates.append({"where": where, "reason": f"关系已存在: {a}--{r.get('type')}--{b}"})
            continue
        for k in ("type", "strength", "event"):
            r.setdefault(k, "")
        seen_triple.add((a, b, r.get("type")))
        plan.new_relations.append(r)

    # ---- 玩家 / 画像 ----
    # 缺 uid 的条目不能写(uid 是主键), 但也不能静默丢: 转成待确认, 把内容留在报告里
    known_uids = {p.get("uid") for p in players}
    for i, raw in enumerate(patch.players):
        p = copy.deepcopy(raw)
        if not p.get("confirmed", True):
            plan.pending.append({"item": f"玩家 {p.get('uid') or i}", "reason": "confirmed=false", "segment": ""})
            continue
        uid = str(p.get("uid") or "").strip()
        if not uid:
            plan.pending.append({
                "item": f"玩家条目缺 uid: {p.get('qq_name') or p.get('real_alias') or p}",
                "reason": "uid 是 players.json 主键且必须来自 QQ 名单, 不能编造; 请人工补 uid",
                "segment": "",
            })
            continue
        if uid in known_uids:
            plan.duplicates.append({"where": f"players[{i}]", "reason": f"玩家已存在: {uid}"})
            continue
        known_uids.add(uid)
        plan.new_players.append(p)

    known_prof_uids = {p.get("uid") for p in profiles}
    for i, raw in enumerate(patch.pl_profiles):
        p = copy.deepcopy(raw)
        if not p.get("confirmed", True):
            plan.pending.append({"item": f"PL画像 {p.get('uid') or i}", "reason": "confirmed=false", "segment": ""})
            continue
        uid = str(p.get("uid") or "").strip()
        if not uid:
            detail = " / ".join(
                str(x) for x in (p.get("speaking_style"), p.get("rp_style")) if x
            )[:160]
            plan.pending.append({
                "item": f"PL 画像待补 uid: {p.get('name') or i}"
                        + (f"（表现：{detail}）" if detail else ""),
                "reason": "pl_profiles 的 uid 必须来自 canon/players 名单, 不能编造; "
                          "先把 PL 表现记在这里, 补到 uid 后再入库",
                "segment": "",
            })
            continue
        if uid in known_prof_uids:
            plan.duplicates.append({"where": f"pl_profiles[{i}]", "reason": f"PL画像已存在: {uid}"})
            continue
        known_prof_uids.add(uid)
        plan.updated_profiles.append(p)

    # ---- 已有玩家 / 已有画像的追加更新 ----
    players_by_uid = {p.get("uid"): p for p in players}
    for i, raw in enumerate(patch.player_updates):
        uid = str(raw.get("uid") or "").strip()
        target = players_by_uid.get(uid)
        if target is None:
            plan.skipped.append({"where": f"player_updates[{i}]", "reason": f"玩家不存在: {uid}"})
            continue
        changes: dict[str, Any] = {}
        roles = list(target.get("roles") or [])
        for r in raw.get("add_roles") or []:
            if not any(x.get("group") == r.get("group") and x.get("role") == r.get("role") for x in roles):
                roles.append(copy.deepcopy(r))
        if roles != (target.get("roles") or []):
            changes["roles"] = roles
        if raw.get("append_note"):
            add = str(raw["append_note"]).strip()
            old = (target.get("note") or "").rstrip()
            if add and add not in old:   # 幂等, 同上
                sep = "" if (not old or old.endswith(("。", "！", "？", "."))) else "。"
                changes["note"] = f"{old}{sep}{add}" if old else add
        if not changes:
            plan.skipped.append({"where": f"player_updates[{i}]", "reason": f"{uid} 无实际变更"})
            continue
        plan.player_changes.append({"uid": uid, "changes": changes})

    profiles_by_uid = {p.get("uid"): p for p in profiles}
    for i, raw in enumerate(patch.profile_updates):
        uid = str(raw.get("uid") or "").strip()
        target = profiles_by_uid.get(uid)
        if target is None:
            plan.skipped.append({"where": f"profile_updates[{i}]", "reason": f"PL画像不存在: {uid}"})
            continue
        pchanges: dict[str, Any] = {}
        for key, add_key in (("cards", "add_cards"),
                             ("groups_played", "add_groups_played"),
                             ("impressions", "add_impressions")):
            if raw.get(add_key):
                cur = list(target.get(key) or [])
                for x in raw[add_key]:
                    if x not in cur:
                        cur.append(copy.deepcopy(x))
                if cur != (target.get(key) or []):
                    pchanges[key] = cur
        for key in ("speaking_style", "rp_style"):
            add = raw.get(f"append_{key}")
            if add:
                old = (target.get(key) or "").rstrip()
                if str(add).strip() and str(add).strip() not in old:   # 幂等, 同上
                    pchanges[key] = f"{old}\n{add}" if old else str(add)
        if not pchanges:
            plan.skipped.append({"where": f"profile_updates[{i}]", "reason": f"{uid} 无实际变更"})
            continue
        plan.profile_changes.append({"uid": uid, "changes": pchanges})

    # ---- 显式待确认 ----
    for item in patch.pending:
        if isinstance(item, dict):
            plan.pending.append(
                {"item": str(item.get("item") or item.get("text") or ""), "reason": str(item.get("reason") or ""),
                 "segment": str(item.get("segment") or "")}
            )
        else:
            plan.pending.append({"item": str(item), "reason": "", "segment": ""})

    # ---- 数量预估 ----
    plan.counts_after = {
        "characters": plan.counts_before["characters"] + len(plan.new_characters),
        "relations": plan.counts_before["relations"] + len(plan.new_relations),
        "players": plan.counts_before["players"] + len(plan.new_players),
        "pl_profiles": plan.counts_before["pl_profiles"] + len(plan.updated_profiles),
    }
    return plan


# --------------------------------------------------------------------------- 落盘

def apply_plan_to_docs(docs: dict[str, Any], plan: Plan, when: str | None = None) -> dict[str, Any]:
    """在深拷贝上应用计划, 返回新文档集; 不改动入参。"""
    out = copy.deepcopy(docs)
    stamp = when or date.today().isoformat()

    ch_doc = out.setdefault("characters", {"_meta": {}, "characters": []})
    ch_doc.setdefault("characters", [])
    ch_doc["characters"].extend(copy.deepcopy(plan.new_characters))
    by_id = {c.get("id"): c for c in ch_doc["characters"]}
    for upd in plan.updated_characters:
        target = by_id.get(upd["id"])
        if target is not None:
            target.update(copy.deepcopy(upd["changes"]))

    rel_doc = out.setdefault("relations", {"_meta": {}, "relations": []})
    rel_doc.setdefault("relations", [])
    rel_doc["relations"].extend(copy.deepcopy(plan.new_relations))

    pl_doc = out.setdefault("players", {"_meta": {}, "players": []})
    pl_doc.setdefault("players", [])
    pl_doc["players"].extend(copy.deepcopy(plan.new_players))
    _by_uid = {p.get("uid"): p for p in pl_doc["players"]}
    for ch in plan.player_changes:
        tgt = _by_uid.get(ch["uid"])
        if tgt is not None:
            tgt.update(copy.deepcopy(ch["changes"]))

    prof_doc = out.setdefault("pl_profiles", {"_meta": {}, "profiles": []})
    prof_doc.setdefault("profiles", [])
    prof_doc["profiles"].extend(copy.deepcopy(plan.updated_profiles))
    _by_puid = {p.get("uid"): p for p in prof_doc["profiles"]}
    for ch in plan.profile_changes:
        tgt = _by_puid.get(ch["uid"])
        if tgt is not None:
            tgt.update(copy.deepcopy(ch["changes"]))

    for doc in out.values():
        if isinstance(doc, dict):
            doc.setdefault("_meta", {})
            doc["_meta"]["updated"] = stamp
    return out


def write_staging(ws: Workspace, docs: dict[str, Any]) -> dict[str, Path]:
    ws.staging.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}
    for kind, doc in docs.items():
        p = ws.staging / f"{kind}.json"
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        written[kind] = p
    return written


def load_data_docs(ws: Workspace) -> dict[str, Any]:
    docs: dict[str, Any] = {}
    for kind, key in KIND_LIST_KEY.items():
        p = ws.data_file(kind)
        if p.is_file():
            try:
                docs[kind] = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as e:
                raise ValueError(f"数据文件损坏, 无法入库: {p} ({e})") from e
        else:
            docs[kind] = {"_meta": {"description": f"{kind} (由 trpg-agent 创建)"}, key: []}
    return docs


def write_plan(ws: Workspace, plan: Plan) -> Path:
    ws.work.mkdir(parents=True, exist_ok=True)
    p = ws.work / f"plan_{plan.group}.json"
    payload = plan.to_dict()
    payload["generated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return p
