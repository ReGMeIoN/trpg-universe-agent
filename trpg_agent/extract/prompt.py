# -*- coding: utf-8 -*-
"""提炼 prompt 渲染与补丁 JSON Schema。

- 分段提炼: 模板 + canon 注入 + 段原文 -> Markdown 结构化草稿
- 汇总入库: 各段草稿 + canon + 补丁契约 -> 一个补丁 JSON(交给 store)
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
DEFAULT_TEMPLATE = TEMPLATES / "extract_template.md"
DEFAULT_CONSOLIDATE = TEMPLATES / "consolidate_template.md"

PATCH_CONTRACT = """
{
  "group": "<团名, 群名即团名>",
  "id_prefix": "<新角色的 id 前缀, 由调用方给出>",
  "characters": [
    {"id": "<前缀>_<拼音短名>", "name": "角色名", "aliases": ["别名"], "identity": "身份/定位",
     "groups": ["<团名>"], "tags": ["PC"|"NPC"|"BOSS"|"待确认"],
     "played_by": "<PL 标准称呼或 待确认>", "note": "一句话概述(必须带剧情依据)",
     "events": [{"group": "<团名>", "items": ["事件(注明段号)"]}],
     "confirmed": true,
     "pending_reason": "confirmed=false 时必填", "segment": "段N"}
  ],
  "character_updates": [
    {"id": "<已入库角色的 id>", "add_groups": ["<团名>"], "append_note": "本团出场补充",
     "add_events": [{"group": "<团名>", "items": ["..."]}]
     "set_played_by": null, "confirmed": true}
  ],
  "relations": [
    {"from": "<角色id>", "to": "<角色id>", "type": "关系类型", "strength": "强"|"中"|"弱",
     "event": "剧情依据(哪个团/什么事)", "confirmed": true}
  ],
  "players": [],
  "pl_profiles": [],
  "pending": [{"item": "拿不准的内容", "reason": "为什么拿不准", "segment": "段N"}]
}
"""


def render(
    template_path: Path | str,
    replacements: dict[str, str],
) -> str:
    path = Path(template_path)
    if not path.is_absolute():
        path = Path(__file__).resolve().parent.parent / template_path
    text = path.read_text(encoding="utf-8")
    for key, value in replacements.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def render_segment_prompt(
    cfg, ws, group: str, seg: dict[str, Any], text: str, canon_block: str
) -> str:
    template = cfg.extract.template
    tp = Path(template)
    if not tp.is_absolute():
        tp = Path(__file__).resolve().parent.parent / template
    if not tp.is_file():
        tp = DEFAULT_TEMPLATE
    return render(
        tp,
        {
            "CANON": canon_block,
            "GROUP": group,
            "SEGMENT_LABEL": str(seg.get("label") or f"段{seg.get('n')}"),
            "SEGMENT_FILE": str(seg.get("file", "")),
            "SEGMENT_LINES": str(seg.get("lines", "")),
            "SEGMENT_N": str(seg.get("n", "")),
            "SEGMENT_TEXT": text,
        },
    )


def render_consolidate_prompt(
    cfg, group: str, id_prefix: str, extracts: list[tuple[str, str]], canon_block: str
) -> str:
    tp = Path(cfg.extract.consolidate_template)
    if not tp.is_absolute():
        tp = Path(__file__).resolve().parent.parent / cfg.extract.consolidate_template
    if not tp.is_file():
        tp = DEFAULT_CONSOLIDATE
    blocks = []
    for label, body in extracts:
        blocks.append(f"### {label}\n\n{body.strip()}")
    return render(
        tp,
        {
            "CANON": canon_block,
            "GROUP": group,
            "ID_PREFIX": id_prefix,
            "CONTRACT": PATCH_CONTRACT.strip(),
            "EXTRACTS": "\n\n".join(blocks),
        },
    )


def patch_json_schema() -> dict[str, Any]:
    """给 Ollama format / OpenAI response_format 用的补丁 JSON Schema。"""
    events = {
        "type": "array",
        "items": {
            "type": "object",
            "properties": {"group": {"type": "string"}, "items": {"type": "array", "items": {"type": "string"}}},
            "required": ["group", "items"],
        },
    }
    return {
        "type": "object",
        "properties": {
            "group": {"type": "string"},
            "id_prefix": {"type": "string"},
            "characters": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "name": {"type": "string"},
                        "aliases": {"type": "array", "items": {"type": "string"}},
                        "identity": {"type": "string"},
                        "groups": {"type": "array", "items": {"type": "string"}},
                        "tags": {"type": "array", "items": {"type": "string"}},
                        "played_by": {"type": "string"},
                        "note": {"type": "string"},
                        "events": events,
                        "confirmed": {"type": "boolean"},
                        "pending_reason": {"type": "string"},
                        "segment": {"type": "string"},
                    },
                    "required": ["id", "name", "groups"],
                },
            },
            "character_updates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string"},
                        "add_groups": {"type": "array", "items": {"type": "string"}},
                        "append_note": {"type": "string"},
                        "add_events": events,
                        "add_tags": {"type": "array", "items": {"type": "string"}},
                        "set_played_by": {"type": ["string", "null"]},
                        "confirmed": {"type": "boolean"},
                        "pending_reason": {"type": "string"},
                    },
                    "required": ["id"],
                },
            },
            "relations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "from": {"type": "string"},
                        "to": {"type": "string"},
                        "type": {"type": "string"},
                        "strength": {"type": "string"},
                        "event": {"type": "string"},
                        "confirmed": {"type": "boolean"},
                        "pending_reason": {"type": "string"},
                    },
                    "required": ["from", "to", "type", "strength", "event"],
                },
            },
            "players": {"type": "array", "items": {"type": "object"}},
            "pl_profiles": {"type": "array", "items": {"type": "object"}},
            "pending": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "item": {"type": "string"},
                        "reason": {"type": "string"},
                        "segment": {"type": "string"},
                    },
                    "required": ["item"],
                },
            },
        },
        "required": ["group", "characters", "relations", "pending"],
    }
