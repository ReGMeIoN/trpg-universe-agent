# -*- coding: utf-8 -*-
"""入库报告 + 待确认清单 (可直接放产出/, 人读)。"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from trpg_agent.store.merger import Plan
from trpg_agent.store.schema import ValidationReport


def _table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_(无)_\n"
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    for r in rows:
        out.append("| " + " | ".join(str(c).replace("|", "\\|").replace("\n", " ") for c in r) + " |")
    return "\n".join(out) + "\n"


def render_report(
    plan: Plan,
    patch_path: str,
    validations: list[ValidationReport],
    backups: dict[str, str] | None = None,
    applied: bool = False,
    staging: dict[str, str] | None = None,
    strictness: str = "strict",
) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = []
    lines.append(f"# {plan.group} 入库报告")
    lines.append("")
    lines.append(f"- 日期: {now}")
    lines.append(f"- 模式: **{'已回填数据目录' if applied else '工作副本(staging) — 未写数据目录'}**")
    lines.append(f"- 补丁: `{patch_path}`")
    lines.append(f"- id 前缀: `{plan.prefix}_` (来源: {plan.prefix_source})")
    lines.append(f"- 校验严格度: {strictness}")
    lines.append("")
    lines.append("数据口径(铁律): 只写入多段一致且明确的内容; 转写存疑/映射未定/拿不准一律进"
                 "「待确认清单」, 不写死; 写入前必备份。")
    lines.append("")
    if backups:
        lines.append("备份:")
        for src, dst in backups.items():
            lines.append(f"- `{src}` -> `{dst}`")
        lines.append("")
    if staging:
        lines.append("工作副本:")
        for kind, p in staging.items():
            lines.append(f"- `{p}`")
        lines.append("")

    lines.append(f"## 一、新增角色 ({len(plan.new_characters)})")
    lines.append("")
    lines.append(
        _table(
            ["id", "名称", "定位", "扮演", "说明"],
            [
                [
                    c.get("id"),
                    c.get("name"),
                    " / ".join(c.get("tags") or []) or c.get("identity", "")[:20],
                    c.get("played_by") or "-",
                    (c.get("note") or "")[:70],
                ]
                for c in plan.new_characters
            ],
        )
    )

    lines.append(f"## 二、复用/更新既有角色 ({len(plan.updated_characters)})")
    lines.append("")
    lines.append(
        _table(
            ["id", "变更字段", "变更内容"],
            [
                [
                    u["id"],
                    " / ".join(u["changes"].keys()),
                    "; ".join(
                        f"{k}: {_short(v)}" for k, v in u["changes"].items()
                    )[:180],
                ]
                for u in plan.updated_characters
            ],
        )
    )

    lines.append(f"## 三、新增关系 ({len(plan.new_relations)})")
    lines.append("")
    lines.append(
        _table(
            ["from", "关系", "强度", "to", "事件依据"],
            [
                [r.get("from"), r.get("type"), r.get("strength"), r.get("to"), (r.get("event") or "")[:80]]
                for r in plan.new_relations
            ],
        )
    )

    lines.append(f"## 四、称呼归一记录 ({len(plan.normalized)})")
    lines.append("")
    lines.append(
        _table(
            ["位置", "字段", "原值", "归一为"],
            [[n["where"], n["field"], n["old"], n["new"]] for n in plan.normalized],
        )
    )
    if plan.new_players or plan.updated_profiles:
        lines.append("## 五、玩家 / PL 画像")
        lines.append("")
        if plan.new_players:
            lines.append(_table(["uid", "qq_name", "说明"],
                                [[p.get("uid"), p.get("qq_name"), (p.get("note") or "")[:60]] for p in plan.new_players]))
        if plan.updated_profiles:
            lines.append(_table(["uid", "name"],
                                [[p.get("uid"), p.get("name")] for p in plan.updated_profiles]))
        lines.append("")

    n_skip = len(plan.skipped)
    n_dup = len(plan.duplicates)
    lines.append(f"## 六、跳过 / 重复 (跳过 {n_skip} · 重复 {n_dup})")
    lines.append("")
    lines.append(_table(["位置", "原因"], [[s["where"], s["reason"]] for s in plan.skipped + plan.duplicates]))

    lines.append(f"## 七、待确认清单 ({len(plan.pending)})")
    lines.append("")
    lines.append(_table(["项目", "原因", "段"], [[p["item"], p["reason"], p.get("segment", "")] for p in plan.pending]))
    lines.append("> 待确认不阻塞流程; 裁决后写回 canon, 后续步骤自动遵守。")
    lines.append("")

    lines.append("## 八、校验结果")
    lines.append("")
    for v in validations:
        mark = "PASS" if v.ok else "FAIL"
        lines.append(f"- `{v.kind}` **{mark}** (条目 {v.total}) 错误 {len(v.errors)} / 警告 {len(v.warns)}")
        for iss in v.issues[:10]:
            lines.append(f"    - {iss}")
        if len(v.issues) > 10:
            lines.append(f"    - … 另有 {len(v.issues) - 10} 条")
    lines.append("")

    lines.append("## 九、数据量变化")
    lines.append("")
    lines.append(_table(["种类", "入库前", "入库后"],
                        [[k, plan.counts_before.get(k, 0), plan.counts_after.get(k, 0)] for k in
                         ("characters", "relations", "players", "pl_profiles")]))
    if plan.warnings:
        lines.append("## 十、警告")
        lines.append("")
        for w in plan.warnings:
            lines.append(f"- {w}")
        lines.append("")
    return "\n".join(lines)


def _short(v: Any) -> str:
    if isinstance(v, list):
        return f"[{len(v)} 项] " + "; ".join(str(x)[:40] for x in v[:3])
    return str(v)[:80]


def render_pending(plan: Plan) -> str:
    lines = [f"# {plan.group} 待确认清单", ""]
    lines.append(f"生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")
    if not plan.pending:
        lines.append("_(无)_")
        return "\n".join(lines) + "\n"
    for i, p in enumerate(plan.pending, 1):
        seg = f" [{p.get('segment')}]" if p.get("segment") else ""
        reason = f" — {p['reason']}" if p.get("reason") else ""
        lines.append(f"{i}. {p['item']}{seg}{reason}")
    return "\n".join(lines) + "\n"
