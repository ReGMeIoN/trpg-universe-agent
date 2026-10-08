# -*- coding: utf-8 -*-
"""store 编排: 读补丁 -> 校验现有数据 -> 生成计划 -> 写工作副本 -> 校验工作副本
            -> 出报告/待确认 -> (可选 --apply) 备份并回填数据目录。

安全铁律:
    1. 永远先写工作副本(.trpg/staging), 再谈回填;
    2. 回填前必备份, 回填后重载复验;
    3. 生产库回填需要显式授权(workspace.allow_production_write 或 --allow-production)。
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.store import backup as backup_mod
from trpg_agent.store.merger import (
    KIND_LIST_KEY,
    Plan,
    apply_plan_to_docs,
    build_plan,
    find_patch,
    load_data_docs,
    load_patch,
    write_plan,
    write_staging,
)
from trpg_agent.store.report import render_pending, render_report
from trpg_agent.store.schema import check_references, validate_document, validate_file
from trpg_agent.workspace import Workspace

KINDS = tuple(KIND_LIST_KEY.keys())


def run_store(
    ws: Workspace,
    cfg: Config,
    patch_path: Path | None = None,
    group: str | None = None,
    apply: bool = False,
    allow_production: bool = False,
) -> dict[str, Any]:
    ws.ensure_dirs()
    patch_file = find_patch(ws, group, patch_path)
    patch = load_patch(patch_file)
    log.info(f"补丁: {ws.rel(patch_file)} | 团: {patch.group}")

    docs = load_data_docs(ws)

    # 1) 校验入库前的现有数据
    pre_reports = [validate_document(k, docs[k], f"{k}.json(入库前)") for k in KINDS]
    pre_issues = sum(len(r.issues) for r in pre_reports)
    if pre_issues:
        log.warn(f"入库前校验: {pre_issues} 条问题(既有数据, 不阻断)")
    else:
        log.ok("入库前校验: 无问题")

    # 2) 生成计划
    plan = build_plan(docs, patch, cfg, ws)
    log.kv_table(
        f"入库计划 [{plan.group}]",
        [
            ("id 前缀", f"{plan.prefix}_ ({plan.prefix_source})"),
            ("新增角色", len(plan.new_characters)),
            ("更新角色", len(plan.updated_characters)),
            ("新增关系", len(plan.new_relations)),
            ("称呼归一", len(plan.normalized)),
            ("跳过/重复", f"{len(plan.skipped)}/{len(plan.duplicates)}"),
            ("待确认", len(plan.pending)),
        ],
    )

    # 3) 应用 -> 工作副本
    staged_docs = apply_plan_to_docs(docs, plan)
    staged_files = write_staging(ws, staged_docs)
    staged_reports = [validate_file(p, k) for k, p in staged_files.items()]

    ref_level = cfg.store.dangling_ref
    if ref_level != "ignore":
        ref_rep = validate_document("relations", staged_docs["relations"], "relations(引用检查)")
        ref_rep.issues = check_references(
            staged_docs["characters"],
            staged_docs["relations"],
            level="error" if ref_level == "error" else "warn",
        )
        ref_rep.total = len(staged_docs["relations"].get("relations", []))
        staged_reports.append(ref_rep)

    hard_errors = [i for r in staged_reports for i in r.errors]
    if hard_errors:
        log.err(f"工作副本校验失败: {len(hard_errors)} 条错误")
        for i in hard_errors[:10]:
            log.err(f"  {i}")
    else:
        log.ok("工作副本校验通过")

    plan_path = write_plan(ws, plan)

    # 4) 报告 / 待确认
    report_path = None
    pending_path = None
    if cfg.store.write_report:
        report_path = ws.reports / f"{plan.group}_入库报告.md"
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(
            render_report(plan, ws.rel(patch_file), staged_reports, applied=False,
                          staging={k: ws.rel(p) for k, p in staged_files.items()},
                          strictness=cfg.store.strictness),
            encoding="utf-8",
        )
        pending_path = ws.reports / f"{plan.group}_待确认.md"
        pending_path.write_text(render_pending(plan), encoding="utf-8")

    # 5) 回填
    backups: dict[str, str] = {}
    written: list[str] = []
    if apply:
        # 净变更判据不能只看条目数量: 纯更新(改字段/追加 note·events/称呼归一)不改计数,
        # 旧版用 counts_after == counts_before 判定, 导致"更新角色 1"永远被跳过回填。
        net = (
            plan.new_characters or plan.updated_characters or plan.new_relations
            or plan.new_players or plan.updated_profiles or plan.normalized
            or plan.player_changes or plan.profile_changes
        )
        if not net:
            log.warn("计划无净变更, 跳过回填")
        else:
            if not allow_production:
                ws.guard_write("store --apply")
            if cfg.store.backup:
                for k in KINDS:
                    dst = backup_mod.backup_file(ws.data_file(k), "store", cfg.workspace.backup_keep)
                    if dst:
                        backups[str(ws.data_file(k))] = str(dst)
                log.ok(f"已备份 {len(backups)} 个数据文件 (保留最近 {cfg.workspace.backup_keep} 份)")
            for k, src in staged_files.items():
                dst = ws.data_file(k)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
                written.append(ws.rel(dst))
            # 回填后复验
            post = [validate_file(ws.data_file(k), k) for k in KINDS]
            bad = [i for r in post for i in r.errors]
            if bad:
                log.err("回填后校验失败! 数据文件可能已损坏, 备份可用于回滚:")
                for i in bad[:10]:
                    log.err(f"  {i}")
                for src, dst in backups.items():
                    log.err(f"  回滚: copy \"{dst}\" \"{src}\"")
            else:
                log.ok(f"回填完成并复验通过: {', '.join(written)}")
            if cfg.store.write_report and report_path:
                report_path.write_text(
                    render_report(plan, ws.rel(patch_file), post, backups=backups, applied=True,
                                  staging={k: ws.rel(p) for k, p in staged_files.items()},
                                  strictness=cfg.store.strictness),
                    encoding="utf-8",
                )

    return {
        "group": plan.group,
        "plan": plan.to_dict(),
        "plan_path": ws.rel(plan_path),
        "staging": {k: ws.rel(p) for k, p in staged_files.items()},
        "report": ws.rel(report_path) if report_path else None,
        "pending": ws.rel(pending_path) if pending_path else None,
        "applied": bool(apply and written),
        "backups": backups,
        "written": written,
        "validation_ok": all(r.ok for r in staged_reports),
    }
