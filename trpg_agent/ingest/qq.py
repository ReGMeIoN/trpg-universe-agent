# -*- coding: utf-8 -*-
"""QQ 导出 JSON -> 纯文本记录 (移植素材\\_scripts\\process_group.py)。

输出到 <work>/normalized/<团名>_聊天记录纯文本.txt, 保持素材目录干净且幂等。
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent.workspace import Workspace

TEXTLOG_SUFFIX = "_聊天记录纯文本.txt"


def fmt_ts(ms: Any) -> str:
    try:
        return datetime.fromtimestamp(int(ms) / 1000).strftime("%m-%d %H:%M")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def message_to_line(msg: dict[str, Any]) -> str:
    sender = msg.get("sender") or {}
    name = sender.get("name", "?")
    mtype = msg.get("type") or "?"
    content = msg.get("content") or {}
    text = (content.get("text") or "") if isinstance(content, dict) else str(content)
    ts = fmt_ts(msg.get("timestamp", 0))
    if mtype == "system":
        return f"[{ts}] [系统] {text}"
    if mtype == "text":
        return f"[{ts}] {name}: {text}"
    if mtype == "reply":
        return f"[{ts}] {name}: (回复) {text}"
    if mtype == "audio":
        return f"[{ts}] {name}: [语音]"
    if mtype == "forward":
        return f"[{ts}] {name}: [合并转发]"
    if mtype == "json":
        return f"[{ts}] {name}: [卡片消息]"
    if mtype in ("video", "file"):
        return f"[{ts}] {name}: [{mtype}]"
    return f"[{ts}] {name}: ({mtype}) {text[:100]}"


def parse_export(src: Path) -> tuple[list[dict[str, Any]], str]:
    """返回 (messages, chat_name)。"""
    raw = json.loads(src.read_text(encoding="utf-8"))
    msgs = raw.get("messages", [])
    if not isinstance(msgs, list):
        raise ValueError(f"messages 不是数组: {src}")
    chat = raw.get("chatInfo") or {}
    name = chat.get("name") or chat.get("groupName") or ""
    return msgs, str(name)


def summarize(msgs: list[dict[str, Any]]) -> dict[str, Any]:
    stamps = [m.get("timestamp", 0) for m in msgs if m.get("timestamp")]
    d0 = datetime.fromtimestamp(min(stamps) / 1000).strftime("%Y-%m-%d") if stamps else "?"
    d1 = datetime.fromtimestamp(max(stamps) / 1000).strftime("%Y-%m-%d") if stamps else "?"
    speakers: dict[str, int] = {}
    names: dict[str, str] = {}
    for m in msgs:
        s = m.get("sender") or {}
        uid = s.get("uid", "?")
        speakers[uid] = speakers.get(uid, 0) + 1
        names[uid] = s.get("name", "?")
    lines = [message_to_line(m) for m in msgs]
    return {
        "text": "\n".join(lines),
        "lines": len(lines),
        "msgs": len(msgs),
        "d0": d0,
        "d1": d1,
        "speakers": speakers,
        "names": names,
        "types": _count(m.get("type") for m in msgs),
    }


def convert_qq_export(ws: Workspace, src: Path) -> dict[str, Any]:
    """整份导出 -> 纯文本 + 统计。"""
    msgs, chat_name = parse_export(src)
    info = summarize(msgs)
    info["chat_name"] = chat_name
    return info


def msg_date(msg: dict[str, Any]) -> str:
    ts = msg.get("timestamp", 0)
    try:
        return datetime.fromtimestamp(int(ts) / 1000).strftime("%Y-%m-%d")
    except (TypeError, ValueError, OSError, OverflowError):
        return ""


def split_export_by_ranges(
    ws: Workspace,
    src: Path,
    ranges: list[Any],
    unmatched_group: str | None = None,
    parent_group: str | None = None,
) -> list[dict[str, Any]]:
    """按日期区间把一份导出拆成多段(每段一个团)。

    区间外消息: 有 unmatched_group 则归它, 否则进 "<来源团>·未归类"。绝不静默丢弃。
    """
    msgs, _chat = parse_export(src)
    buckets: list[dict[str, Any]] = []
    used: set[int] = set()

    for rng in ranges:
        start = str(getattr(rng, "start", "") or (rng.get("start") if isinstance(rng, dict) else ""))
        end = str(getattr(rng, "end", "") or (rng.get("end") if isinstance(rng, dict) else ""))
        group = str(getattr(rng, "group", "") or (rng.get("group") if isinstance(rng, dict) else ""))
        if not (start and end and group):
            continue
        picked = []
        for i, m in enumerate(msgs):
            d = msg_date(m)
            if d and start <= d <= end:
                picked.append(m)
                used.add(i)
        if not picked:
            continue
        info = summarize(picked)
        info["group"] = group
        info["range"] = f"{start}~{end}"
        buckets.append(info)

    leftovers = [m for i, m in enumerate(msgs) if i not in used]
    if leftovers:
        group = unmatched_group or f"{parent_group or src.stem}·未归类"
        info = summarize(leftovers)
        info["group"] = group
        info["range"] = f"{info['d0']}~{info['d1']}"
        info["unmatched"] = True
        buckets.append(info)
    return buckets


def _count(it: Any) -> dict[str, int]:
    out: dict[str, int] = {}
    for k in it:
        out[str(k)] = out.get(str(k), 0) + 1
    return out


def write_textlog(ws: Workspace, group: str, text: str) -> Path:
    ws.normalized.mkdir(parents=True, exist_ok=True)
    out = ws.normalized / f"{group}{TEXTLOG_SUFFIX}"
    if out.exists():
        old = out.read_text(encoding="utf-8", errors="replace")
        if old == text:
            return out  # 幂等: 内容一致不重写
    out.write_text(text, encoding="utf-8")
    return out


MERGE_HEADER = "===== 来源: {rel} | {msgs} 条消息 | {range} ====="


def merge_textlogs(group: str, parts: list[tuple[str, dict[str, Any]]]) -> str:
    """把同一团的多个 QQ 导出合并成一份纯文本。

    ⚠️ 必须合并而不是各自写同名文件: 一个团可能有多个导出(如某团的正群 + 小群),
    逐个覆盖会导致静默丢数据。
    """
    if len(parts) == 1:
        return parts[0][1]["text"]
    blocks: list[str] = []
    for rel, info in parts:
        header = MERGE_HEADER.format(rel=rel, msgs=info["msgs"], range=f"{info['d0']}~{info['d1']}")
        blocks.append(f"{header}\n{info['text']}")
    return "\n\n".join(blocks)


def write_sources(ws: Workspace, group: str, parts: list[tuple[str, dict[str, Any]]]) -> Path:
    """记录合并来源(审计用): <work>/normalized/<团>_sources.json"""
    ws.normalized.mkdir(parents=True, exist_ok=True)
    path = ws.normalized / f"{group}_sources.json"
    payload = {
        "group": group,
        "merged_from": [
            {"path": rel, "messages": info["msgs"], "lines": info["lines"],
             "range": f"{info['d0']}~{info['d1']}", "speakers": len(info["speakers"])}
            for rel, info in parts
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def textlog_path(ws: Workspace, group: str) -> Path:
    return ws.normalized / f"{group}{TEXTLOG_SUFFIX}"


def find_existing_textlogs(ws: Workspace) -> list[Path]:
    """素材目录里已存在的 *_聊天记录纯文本.txt (历史产物) 也要能被切段消费。"""
    if not ws.material.is_dir():
        return []
    return sorted(p for p in ws.material.rglob("*" + TEXTLOG_SUFFIX) if p.is_file())


def clean_speaker_label(label: str) -> str:
    """去掉 QQ 昵称里的团名后缀: '砂狼真奈的旁白（XX团名）' -> '砂狼真奈的旁白'"""
    return re.sub(r"（[^）]*）\s*$", "", label).strip() or label
