# -*- coding: utf-8 -*-
"""待确认闭环: 收集 -> 展示 -> 裁决 -> 固化进 canon。

裁决文件: <work>/review/<团>_待确认.json
{
  "group": "<团名>",
  "decisions": [
    {"target": "characters", "index": 4, "action": "accept", "note": "确认为独立 NPC"},
    {"target": "relations",  "index": 3, "action": "reject", "note": "证据不足"},
    {"target": "characters", "index": 0, "action": "set", "field": "played_by", "value": "<PL 标准称呼>"},
    {"target": "naming", "action": "merge", "canonical": "<标准称呼>", "variant": "<误写>"}
  ]
}
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.workspace import Workspace

LIST_TARGETS = ("characters", "character_updates", "relations", "players", "pl_profiles", "pending")


def patch_path(ws: Workspace, group: str) -> Path:
    return ws.patches / f"{group}_patch.json"


def decisions_path(ws: Workspace, cfg: Config, group: str) -> Path:
    return ws.work / cfg.review.decisions_dir / f"{group}_待确认.json"


def collect(ws: Workspace, group: str) -> list[dict[str, Any]]:
    """汇总所有待确认项: 补丁 pending + 各列表里 confirmed=false 的条目。"""
    items: list[dict[str, Any]] = []
    p = patch_path(ws, group)
    if not p.is_file():
        return items
    patch = json.loads(p.read_text(encoding="utf-8"))
    for target in LIST_TARGETS:
        for i, entry in enumerate(patch.get(target) or []):
            if not isinstance(entry, dict):
                continue
            if target == "pending" or entry.get("confirmed") is False:
                desc = (
                    entry.get("item")
                    or f"{entry.get('name') or entry.get('id') or entry.get('from')} — {entry.get('type') or ''}"
                )
                items.append({
                    "target": target,
                    "index": i,
                    "summary": str(desc)[:160],
                    "reason": entry.get("pending_reason") or entry.get("reason") or "",
                    "segment": entry.get("segment") or "",
                })
    return items


def render_items(items: list[dict[str, Any]]) -> list[str]:
    lines = []
    for n, it in enumerate(items, 1):
        seg = f" [{it['segment']}]" if it.get("segment") else ""
        reason = f" — {it['reason']}" if it.get("reason") else ""
        lines.append(f"{n:>2}. ({it['target']}[{it['index']}]) {it['summary']}{seg}{reason}")
    return lines


def write_decisions_template(ws: Workspace, cfg: Config, group: str, items: list[dict[str, Any]]) -> Path:
    path = decisions_path(ws, cfg, group)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_file():
        return path
    payload = {
        "group": group,
        "_说明": [
            "action 取值: accept(确认入库) / reject(驳回, 留在待确认) / set(改字段) / merge(称呼归一)",
            "accept/reject/set 需填 target + index; merge 需填 canonical + variant",
        ],
        "decisions": [
            {"target": it["target"], "index": it["index"], "action": "accept", "note": ""}
            for it in items[:0]
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def apply_decisions(ws: Workspace, cfg: Config, group: str) -> dict[str, Any]:
    """把裁决写回补丁(accept/reject/set) 与 canon 称呼表(merge)。"""
    dp = decisions_path(ws, cfg, group)
    if not dp.is_file():
        raise FileNotFoundError(f"裁决文件不存在: {dp}（先跑 review --group {group} 生成模板）")
    doc = json.loads(dp.read_text(encoding="utf-8"))
    decisions = doc.get("decisions") or []

    p = patch_path(ws, group)
    if not p.is_file():
        raise FileNotFoundError(f"补丁不存在: {p}")
    patch = json.loads(p.read_text(encoding="utf-8"))

    applied: list[str] = []
    merged: list[dict[str, str]] = []
    for d in decisions:
        action = (d.get("action") or "").strip()
        target = d.get("target")
        idx = d.get("index")
        if action == "merge":
            canon_name = d.get("canonical")
            variant = d.get("variant")
            if canon_name and variant:
                merged.append({"canonical": canon_name, "variant": variant})
            continue
        if target not in LIST_TARGETS or not isinstance(idx, int):
            log.warn(f"裁决项无效, 跳过: {d}")
            continue
        arr = patch.get(target) or []
        if not (0 <= idx < len(arr)):
            log.warn(f"裁决索引越界, 跳过: {target}[{idx}]")
            continue
        entry = arr[idx]
        if action == "accept":
            entry["confirmed"] = True
            entry.pop("pending_reason", None)
            applied.append(f"{target}[{idx}] accept")
        elif action == "reject":
            entry["confirmed"] = False
            entry["pending_reason"] = d.get("note") or "用户驳回"
            applied.append(f"{target}[{idx}] reject")
        elif action == "set":
            field = d.get("field")
            if field:
                entry[field] = d.get("value")
                applied.append(f"{target}[{idx}].{field} = {d.get('value')!r}")
        else:
            log.warn(f"未知 action: {action!r}")

    if applied:
        p.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    naming_updates = _merge_naming(ws, merged)
    log.ok(f"裁决已应用: 补丁改动 {len(applied)} 项, 称呼归一 {naming_updates} 项")

    result = {
        "group": group,
        "applied": applied,
        "naming_merges": merged,
        "patch": ws.rel(p),
        "decisions_file": ws.rel(dp),
        "applied_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    logp = ws.work / cfg.review.decisions_dir / f"{group}_裁决记录.json"
    logp.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def _merge_naming(ws: Workspace, merges: list[dict[str, str]]) -> int:
    if not merges:
        return 0
    np_ = ws.canon / "naming.json"
    if not np_.is_file():
        return 0
    doc = json.loads(np_.read_text(encoding="utf-8"))
    entries = doc.setdefault("canonical", [])
    by_name = {e.get("name"): e for e in entries}
    n = 0
    for m in merges:
        e = by_name.get(m["canonical"])
        if e is None:
            e = {"name": m["canonical"], "aliases": []}
            entries.append(e)
            by_name[m["canonical"]] = e
        aliases = e.setdefault("aliases", [])
        if m["variant"] not in aliases:
            aliases.append(m["variant"])
            n += 1
    if n:
        doc.setdefault("_meta", {})["updated"] = datetime.now().strftime("%Y-%m-%d")
        np_.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return n
