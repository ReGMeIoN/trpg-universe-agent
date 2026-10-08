# -*- coding: utf-8 -*-
"""canon(铁律/称呼规范/合并表/已入库名单)的固化与注入。

设计:
- 规则文本: <work>/canon/canon_rules.md(workspace 级) > templates/canon_rules.md(默认)
  —— 示例团必须能用自己的虚构 canon, 不能被生产库的铁律污染。
- 称呼表: <work>/canon/naming.json; `canon build` 在缺失时从模板生成(不覆盖已有文件)。
- 名单: <work>/canon/roster.json, 由 characters.json 自动生成(id/name/aliases/groups/tags)。
- 注入块: render_canon_block() 决定每次提炼带上什么(这是跨段一致性的命门)。
"""
from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.workspace import Workspace

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_RULES = TEMPLATES / "canon_rules.md"
DEFAULT_NAMING = TEMPLATES / "naming_production.json"


def rules_path(ws: Workspace) -> Path:
    ws_file = ws.canon / "canon_rules.md"
    return ws_file if ws_file.is_file() else DEFAULT_RULES


def naming_path(ws: Workspace) -> Path:
    return ws.canon / "naming.json"


def roster_path(ws: Workspace) -> Path:
    return ws.canon / "roster.json"


def group_rules_path(ws: Workspace, group: str | None) -> Path | None:
    """团专属 canon: <work>/canon/groups/<团名>.md, 只在该团提炼时注入。

    为什么分文件: canon_rules.md 是**全库级**规则, 会被注入到每一个团的提炼 prompt。
    把「新团 X 的 PC 对照表」这类只对本团有效的内容塞进去, 会污染其它团的判断。
    团专属内容放这里, 两不打扰。
    """
    if not group:
        return None
    p = ws.canon / "groups" / f"{group}.md"
    return p if p.is_file() else None


def build(ws: Workspace, cfg: Config, force: bool = False) -> dict[str, Any]:
    """固化 canon: 缺失则从模板生成, 并重建已入库名单。"""
    ws.canon.mkdir(parents=True, exist_ok=True)
    created: list[str] = []

    naming = naming_path(ws)
    if force or not naming.is_file():
        naming.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(DEFAULT_NAMING, naming)
        created.append(ws.rel(naming))
    else:
        log.info(f"称呼表已存在, 不覆盖: {ws.rel(naming)}")

    rules_ws = ws.canon / "canon_rules.md"
    if not rules_ws.is_file():
        shutil.copy2(DEFAULT_RULES, rules_ws)
        created.append(ws.rel(rules_ws))

    roster = build_roster_file(ws)
    return {"created": created, "roster": ws.rel(roster)}


def build_roster_file(ws: Workspace) -> Path:
    """从 characters.json 生成名单(characters 不存在时生成空名单)。"""
    docs = {"characters": []}
    p = ws.data_file("characters")
    if p.is_file():
        try:
            docs = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            docs = {"characters": []}
    chars = docs.get("characters", [])
    roster = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(chars),
        "characters": [
            {
                "id": c.get("id"),
                "name": c.get("name"),
                "aliases": c.get("aliases") or [],
                "groups": c.get("groups") or [],
                "tags": c.get("tags") or [],
                "played_by": c.get("played_by") or "",
            }
            for c in chars
            if isinstance(c, dict)
        ],
    }
    path = roster_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(roster, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_roster(ws: Workspace) -> dict[str, Any]:
    p = roster_path(ws)
    if not p.is_file():
        build_roster_file(ws)
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"count": 0, "characters": []}


def render_naming_block(naming_doc: dict[str, Any]) -> str:
    lines: list[str] = []
    for e in naming_doc.get("canonical", []) if isinstance(naming_doc, dict) else []:
        name = e.get("name")
        aliases = "、".join(e.get("aliases") or [])
        lines.append(f"- {name} ← {aliases}" if aliases else f"- {name}")
    for m in naming_doc.get("phonetic_merges", []) if isinstance(naming_doc, dict) else []:
        lines.append(f"- {m.get('canonical')} ← {'、'.join(m.get('variants') or [])}（{m.get('rule','音近归一')}）")
    return "\n".join(lines)


def build_roster_block(roster: dict[str, Any], group: str | None, scope: str = "group") -> str:
    chars = roster.get("characters", [])
    if scope == "none":
        return ""
    if scope == "all_names":
        return "已入库角色名（共 %d，重名/同位体请复用，勿新建重复节点）：%s" % (
            len(chars), "、".join(c["name"] for c in chars if c.get("name")),
        )
    # group: 本团相关角色给详情; 其余只给名字（去重用）
    detail = [c for c in chars if group and group in (c.get("groups") or [])]
    detail_ids = {c["id"] for c in detail}
    others = [c["name"] for c in chars if c["id"] not in detail_ids and c.get("name")]
    lines: list[str] = []
    if detail:
        lines.append(f"### 本团相关角色（{len(detail)} 个，**必须复用其 id 或按规则更新，不要新建重复节点**）")
        for c in detail:
            al = "、".join(c.get("aliases") or [])
            pb = f" | 扮演:{c['played_by']}" if c.get("played_by") else ""
            gs = "、".join(c.get("groups") or [])
            lines.append(f"- `{c['id']}` {c['name']}" + (f"（别名：{al}）" if al else "") + f"{pb} | 团：{gs}")
    if others:
        lines.append("")
        lines.append(f"### 其它已入库角色名（{len(others)} 个，仅作去重参考）")
        lines.append("、".join(others))
    return "\n".join(lines)


def render_canon_block(ws: Workspace, group: str | None, roster_scope: str = "group") -> str:
    parts: list[str] = []
    rp = rules_path(ws)
    if rp.is_file():
        parts.append("## 铁律与命名规范\n\n" + rp.read_text(encoding="utf-8").strip())
    gp = group_rules_path(ws, group)
    if gp is not None:
        parts.append(f"## 本团专属规则（{group}）\n\n" + gp.read_text(encoding="utf-8").strip())
    np_ = naming_path(ws)
    if np_.is_file():
        try:
            doc = json.loads(np_.read_text(encoding="utf-8"))
            block = render_naming_block(doc)
            if block:
                parts.append("## PL 称呼归一表（左边的词一律归一到标准称呼）\n\n" + block)
        except (json.JSONDecodeError, OSError):
            pass
    roster = load_roster(ws)
    rb = build_roster_block(roster, group, scope=roster_scope)
    if rb:
        parts.append(f"## 已入库名单（当前共 {roster.get('count', 0)} 个角色节点）\n\n" + rb)
    return "\n\n".join(parts)
