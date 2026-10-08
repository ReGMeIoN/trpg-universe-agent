# -*- coding: utf-8 -*-
"""数据契约: 必填最小集 + 可选字段宽松放行。

策略(主人 2026-09 确认):
    - characters  必填 id / name / groups
    - relations   必填 from / to / type / strength / event
    - players     必填 uid
    - pl_profiles 必填 uid / name
    - 其余字段: 有则校验类型, 未知字段原样保留(现有数据含 in_graph / played_by_alt /
      avatar / 待确认 tag 等, 不允许被判非法或丢弃)
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from jsonschema import Draft202012Validator

KINDS = ("characters", "relations", "players", "pl_profiles")

_STR_OR_NULL = {"type": ["string", "null"]}


def _str_array() -> dict[str, Any]:
    return {"type": "array", "items": {"type": "string"}}


EVENT_ITEM = {
    "type": "object",
    "required": ["group", "items"],
    "properties": {"group": {"type": "string"}, "items": _str_array()},
    "additionalProperties": True,
}

SCHEMAS: dict[str, dict[str, Any]] = {
    "characters": {
        "type": "object",
        "required": ["_meta", "characters"],
        "properties": {
            "_meta": {"type": "object"},
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["id", "name", "groups"],
                    "properties": {
                        "id": {"type": "string", "minLength": 1},
                        "name": {"type": "string", "minLength": 1},
                        "aliases": _str_array(),
                        "identity": _STR_OR_NULL,
                        "groups": _str_array(),
                        "tags": _str_array(),
                        "played_by": _STR_OR_NULL,
                        "played_by_alt": _STR_OR_NULL,
                        "note": _STR_OR_NULL,
                        "avatar": _STR_OR_NULL,
                        "in_graph": {"type": ["boolean", "null"]},
                        "events": {"type": "array", "items": EVENT_ITEM},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    },
    "relations": {
        "type": "object",
        "required": ["_meta", "relations"],
        "properties": {
            "_meta": {"type": "object"},
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["from", "to", "type", "strength", "event"],
                    "properties": {
                        "from": {"type": "string", "minLength": 1},
                        "to": {"type": "string", "minLength": 1},
                        "type": {"type": "string", "minLength": 1},
                        "strength": {"type": "string"},
                        "event": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    },
    "players": {
        "type": "object",
        "required": ["_meta", "players"],
        "properties": {
            "_meta": {"type": "object"},
            "players": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["uid"],
                    "properties": {
                        "uid": {"type": "string", "minLength": 1},
                        "uin": _STR_OR_NULL,
                        "qq_name": _STR_OR_NULL,
                        "real_alias": _STR_OR_NULL,
                        "note": _STR_OR_NULL,
                        "roles": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                        "alt_accounts": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    },
    "pl_profiles": {
        "type": "object",
        "required": ["_meta", "profiles"],
        "properties": {
            "_meta": {"type": "object"},
            "profiles": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["uid", "name"],
                    "properties": {
                        "uid": {"type": "string", "minLength": 1},
                        "name": {"type": "string", "minLength": 1},
                        "aliases": _str_array(),
                        "groups_played": _str_array(),
                        "cards": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                        "speaking_style": _STR_OR_NULL,
                        "rp_style": _STR_OR_NULL,
                        "impressions": _str_array(),
                        "highlights": _str_array(),
                        "avatar": _STR_OR_NULL,
                    },
                    "additionalProperties": True,
                },
            },
        },
        "additionalProperties": True,
    },
}

LIST_KEY = {
    "characters": "characters",
    "relations": "relations",
    "players": "players",
    "pl_profiles": "profiles",
}

ID_KEY = {"characters": "id", "relations": None, "players": "uid", "pl_profiles": "uid"}

VALID_STRENGTH = {"强", "中", "弱"}


@dataclass
class Issue:
    level: str  # error | warn
    kind: str
    where: str
    msg: str

    def __str__(self) -> str:
        return f"[{self.level.upper()}] {self.kind} {self.where}: {self.msg}"


@dataclass
class ValidationReport:
    kind: str
    path: str
    total: int = 0
    issues: list[Issue] = field(default_factory=list)

    @property
    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    @property
    def warns(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warn"]

    @property
    def ok(self) -> bool:
        return not self.errors

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": self.path,
            "total": self.total,
            "errors": len(self.errors),
            "warns": len(self.warns),
            "issues": [i.__dict__ for i in self.issues],
        }


def validate_document(kind: str, doc: Any, path: str = "<mem>") -> ValidationReport:
    rep = ValidationReport(kind=kind, path=path)
    if kind not in SCHEMAS:
        rep.issues.append(Issue("error", kind, path, f"未知数据种类: {kind}"))
        return rep

    validator = Draft202012Validator(SCHEMAS[kind])
    for err in sorted(validator.iter_errors(doc), key=lambda e: list(e.absolute_path)):
        where = "/".join(str(p) for p in err.absolute_path) or "<root>"
        rep.issues.append(Issue("error", kind, where, err.message))

    if isinstance(doc, dict):
        items = doc.get(LIST_KEY[kind])
        if isinstance(items, list):
            rep.total = len(items)
            idk = ID_KEY[kind]
            if idk:
                seen: dict[str, int] = {}
                for i, it in enumerate(items):
                    if not isinstance(it, dict):
                        continue
                    key = it.get(idk)
                    if key in seen:
                        rep.issues.append(
                            Issue("error", kind, f"{LIST_KEY[kind]}[{i}].{idk}", f"id 重复: {key!r}")
                        )
                    seen[key] = i
            if kind == "relations":
                for i, r in enumerate(items):
                    if isinstance(r, dict) and r.get("strength") not in VALID_STRENGTH:
                        rep.issues.append(
                            Issue(
                                "warn",
                                kind,
                                f"relations[{i}].strength",
                                f"强度取值异常: {r.get('strength')!r} (既有约定: 强/中/弱)",
                            )
                        )
    return rep


def validate_file(path: Path, kind: str | None = None) -> ValidationReport:
    kind = kind or path.stem
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        rep = ValidationReport(kind=kind, path=str(path))
        rep.issues.append(Issue("error", kind, str(path), f"无法解析 JSON: {e}"))
        return rep
    return validate_document(kind, doc, str(path))


def check_references(chars_doc: Any, rels_doc: Any, level: str = "warn") -> list[Issue]:
    """关系边的两端必须存在于 characters; 既有脏引用只按配置等级报告。"""
    issues: list[Issue] = []
    ids = {c.get("id") for c in (chars_doc or {}).get("characters", []) if isinstance(c, dict)}
    for i, r in enumerate((rels_doc or {}).get("relations", [])):
        if not isinstance(r, dict):
            continue
        for side in ("from", "to"):
            v = r.get(side)
            if v and v not in ids:
                issues.append(
                    Issue(level, "relations", f"relations[{i}].{side}", f"引用了不存在的角色 id: {v!r}")
                )
    return issues


def all_ok(reports: Iterable[ValidationReport]) -> bool:
    return all(r.ok for r in reports)
