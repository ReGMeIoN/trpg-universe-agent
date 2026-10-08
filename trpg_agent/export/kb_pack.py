# -*- coding: utf-8 -*-
"""KB 包导出: 由数据自动生成 RAG 友好的 Markdown(供 AstrBot / 本地向量库消费)。

安全原则:
    只覆盖**本工具自己生成过**的文件(记录在 <work>/kb_manifest.json);
    遇到非本工具管理的既有文件一律跳过并报告(要覆盖需设 export.overwrite_unmanaged: true)。
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.data_utils import collect_groups
from trpg_agent.visualize import jack_dossier, relations_md, universe_overview
from trpg_agent.workspace import Workspace

MANIFEST = "kb_manifest.json"


def _manifest_path(ws: Workspace) -> Path:
    return ws.work / MANIFEST


def load_manifest(ws: Workspace) -> dict[str, Any]:
    p = _manifest_path(ws)
    if not p.is_file():
        return {"files": []}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"files": []}


def _data_groups(ws: Workspace) -> list[str]:
    chars = json.loads(ws.data_file("characters").read_text(encoding="utf-8")).get("characters", [])
    return collect_groups(chars)


def run_export(ws: Workspace, cfg: Config) -> dict[str, Any]:
    ws.ensure_dirs()
    out_dir = ws.output / cfg.export.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    prev = set(load_manifest(ws).get("files", []))
    written: list[str] = []
    skipped: list[str] = []

    def emit(name: str, content: str) -> None:
        rel = ws.rel(out_dir / name)
        target = out_dir / name
        managed = rel in prev or not target.exists()
        if not managed and not cfg.export.overwrite_unmanaged:
            skipped.append(rel)
            return
        target.write_text(content, encoding="utf-8")
        written.append(rel)

    emit("00_跑团宇宙总览.md", universe_overview(ws))
    emit("00b_杰克档案.md", jack_dossier(ws, cfg))

    prof = json.loads(ws.data_file("pl_profiles").read_text(encoding="utf-8")).get("profiles", [])
    pl_lines = ["# PL 玩家档案（自动生成）", "", f"- 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
                f"- 共 {len(prof)} 位 PL", ""]
    for p in prof:
        pl_lines += [f"## {p.get('name')}", ""]
        if p.get("aliases"):
            pl_lines.append(f"- 别名：{'、'.join(p['aliases'])}")
        if p.get("groups_played"):
            pl_lines.append(f"- 出场：{'；'.join(p['groups_played'])}")
        for c in p.get("cards") or []:
            pl_lines.append(f"- 卡：{c.get('group')} · {c.get('role')}")
        if p.get("speaking_style"):
            pl_lines += ["", f"**说话风格**：{p['speaking_style']}"]
        if p.get("rp_style"):
            pl_lines += ["", f"**RP 风格**：{p['rp_style']}"]
        for key, title in (("impressions", "人物印象"), ("highlights", "高光时刻")):
            if p.get(key):
                pl_lines += ["", f"**{title}**"]
                pl_lines += [f"- {x}" for x in p[key]]
        pl_lines.append("")
    emit("00c_PL档案.md", "\n".join(pl_lines) + "\n")

    for g in _data_groups(ws):
        safe = g.replace("/", "_")
        emit(f"{safe}.md", relations_md(ws, g))

    clean = [f for f in (_manifest_path(ws) and load_manifest(ws).get("files", [])) if f not in written
             and f not in skipped and (ws.root / f).is_file()]
    _manifest_path(ws).write_text(
        json.dumps({"files": sorted(written), "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S")},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    if skipped:
        log.warn(
            f"跳过 {len(skipped)} 个非本工具生成的既有文件(避免覆盖你的手工内容); "
            f"要覆盖请设 export.overwrite_unmanaged: true"
        )
        for s in skipped[:6]:
            log.info(f"    - {s}")
    if clean:
        log.info(f"有 {len(clean)} 个上次生成、本次不再需要的文件(未删除, 供你确认): {clean[:5]}")
    log.ok(f"KB 包: {len(written)} 份 -> {ws.rel(out_dir)}")
    return {"out_dir": ws.rel(out_dir), "written": written, "skipped": skipped}
