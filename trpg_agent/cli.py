# -*- coding: utf-8 -*-
"""trpg-agent CLI。

固定工作流: ingest -> transcribe -> segment -> extract -> review -> store
            -> visualize -> export -> housekeep

用法示例:
    trpg-agent ingest   --ws examples/mini-group
    trpg-agent segment  --ws examples/mini-group
    trpg-agent store    --ws examples/mini-group --patch ... --apply
    trpg-agent status   --ws examples/mini-group
"""
from __future__ import annotations

import fnmatch
import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer

from trpg_agent import __version__, canon, jobs, log
from trpg_agent.adapters import make_llm_client
from trpg_agent.adapters.llm_base import LLMError
from trpg_agent.config import Config, find_config, load_config
from trpg_agent.export.kb_pack import run_export
from trpg_agent.extract import run_extract
from trpg_agent.housekeep import run_housekeep
from trpg_agent.ingest import (
    SEGMENT_INPUT_TYPES,
    TYPE_QQ_EXPORT,
    group_files,
    load_manifest,
    render_summary,
    scan,
)
from trpg_agent.ingest import qq as qq_mod
from trpg_agent.review import apply_decisions as review_apply
from trpg_agent.review import collect as review_collect
from trpg_agent.review import render_items as review_render
from trpg_agent.review import write_decisions_template as review_write_template
from trpg_agent.segment import SEGMENT_LOGIC_VERSION, load_index, render_group, segment_one
from trpg_agent.state import StepState, all_states, combine_hash, sha256_file, sha256_json
from trpg_agent.store import run_store
from trpg_agent.transcribe import group_from_audio, run_transcribe
from trpg_agent.visualize import run_visualize
from trpg_agent.workspace import ProductionWriteBlocked, Workspace

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="TRPG-Universe Agent · 跑团宇宙数据管家 (v0.1)",
)

SOURCE_PRIORITY = ["transcript", "qq_text", "raw_text"]


def _ctx(config: Optional[str], ws: Optional[str], cmd: str) -> tuple[Config, Workspace]:
    try:
        cfg = load_config(config, ws)
    except FileNotFoundError as e:
        log.err(str(e))
        raise typer.Exit(2)
    wsp = Workspace.from_config(cfg)
    wsp.ensure_dirs()
    log.bind_log_file(wsp.logs / f"{cmd}.log")
    return cfg, wsp


def _version_cb(value: bool) -> None:
    if value:
        typer.echo(f"trpg-agent {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: bool = typer.Option(False, "--version", callback=_version_cb, is_eager=True, help="显示版本"),
) -> None:
    """TRPG-Universe Agent · 把每一场跑团酿成一册可检索的宇宙档案。"""


# --------------------------------------------------------------------------- ingest

def _match_split_rule(cfg: Config, entry: dict[str, Any]) -> Any:
    name = Path(entry["path"]).name
    p = str(entry["path"])
    for r in cfg.ingest.date_group_rules:
        if fnmatch.fnmatch(name, r.source_glob) or fnmatch.fnmatch(p, r.source_glob):
            return r
    return None


@app.command()
def ingest(
    config: Optional[str] = typer.Option(None, "--config", "-c", help="配置文件路径"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w", help="工作区根目录(覆盖配置)"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="只处理指定团"),
    rebuild: bool = typer.Option(False, "--rebuild", help="忽略上次 manifest 全量重扫"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON 结果"),
) -> None:
    """M1 素材接入: 扫描 + 分类 + hash 去重 + manifest + QQ 导出转纯文本(含按日期拆团)。"""
    cfg, wsp = _ctx(config, ws, "ingest")
    log.step(f"ingest · {wsp.root}")

    manifest = scan(wsp, cfg, only_group=group, rebuild=rebuild)
    files = group_files(manifest, group)
    qq_entries = [f for f in files if f["type"] == TYPE_QQ_EXPORT]

    # 每个团的纯文本来源: [(来源标签, 统计)]; 拆团规则的产出按团归并
    parts_by_group: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    changed_groups: set[str] = set()
    split_sources: dict[str, list[str]] = {}   # 派生团 -> 来源文件
    split_parents: set[str] = set()            # 被拆团规则消费的来源团
    converted: list[dict[str, Any]] = []

    for e in qq_entries:
        rule = _match_split_rule(cfg, e)
        src = wsp.root / e["path"]
        if rule:
            split_parents.add(e["group"])
            try:
                buckets = qq_mod.split_export_by_ranges(
                    wsp, src, rule.ranges, rule.unmatched_group, parent_group=e["group"]
                )
            except (json.JSONDecodeError, OSError, ValueError) as ex:
                log.err(f"按日期拆团失败, 跳过: {e['path']} ({ex})")
                continue
            for b in buckets:
                g = b["group"]
                label = f"{e['path']}#{b.get('range', '')}"
                parts_by_group.setdefault(g, []).append((label, b))
                split_sources.setdefault(g, []).append(e["path"])
                if e["status"] != "unchanged":
                    changed_groups.add(g)
                if b.get("unmatched"):
                    log.warn(
                        f"[{g}] 来源 {e['path']} 有 {b['msgs']} 条消息不在任何日期区间内 "
                        f"({b['d0']}~{b['d1']}), 已单独归入「{g}」, 不计入任何团的 canon"
                    )
        else:
            try:
                info = qq_mod.convert_qq_export(wsp, src)
            except (json.JSONDecodeError, OSError, ValueError) as ex:
                log.warn(f"QQ 导出解析失败, 跳过: {e['path']} ({ex})")
                continue
            parts_by_group.setdefault(e["group"], []).append((e["path"], info))
            if e["status"] != "unchanged":
                changed_groups.add(e["group"])

    for g, parts in sorted(parts_by_group.items()):
        out_path = qq_mod.textlog_path(wsp, g)
        if out_path.is_file() and g not in changed_groups:
            log.info(f"[{g}] 纯文本来源未变化 ({len(parts)} 个), 跳过转换")
            continue
        text = qq_mod.merge_textlogs(g, parts)
        out = qq_mod.write_textlog(wsp, g, text)
        sidecar = qq_mod.write_sources(wsp, g, parts)
        total_msgs = sum(p[1]["msgs"] for p in parts)
        total_lines = sum(p[1]["lines"] for p in parts)
        converted.append(
            {
                "group": g,
                "sources": [p[0] for p in parts],
                "out": wsp.rel(out),
                "sources_index": wsp.rel(sidecar),
                "messages": total_msgs,
                "lines": total_lines,
                "range": f"{min(p[1]['d0'] for p in parts)}~{max(p[1]['d1'] for p in parts)}",
            }
        )
        via_split = g in split_sources
        tag = "按日期拆分" if via_split else ("合并" if len(parts) > 1 else "转换")
        log.ok(f"[{g}] {len(parts)} 个来源{tag} -> {wsp.rel(out)} ({total_msgs} 条消息 / {total_lines} 行)")
        for label, info in parts:
            log.info(f"    + {label} ({info['msgs']} 条 / {info['d0']}~{info['d1']})")

    # 被拆团取代的来源团: 其整份纯文本不再参与切段, 且清理旧的错误合并产物
    superseded_groups: list[str] = []
    for g in sorted(split_parents - set(parts_by_group)):
        eligible = [
            f for f in files
            if f["group"] == g and f["type"] in SEGMENT_INPUT_TYPES and not f.get("superseded")
        ]
        if eligible:
            log.warn(f"[{g}] 导出虽被按日期拆团, 但仍有 {len(eligible)} 个可切段输入, 保留该团")
            continue
        superseded_groups.append(g)
        for stale in (qq_mod.textlog_path(wsp, g), wsp.normalized / f"{g}_sources.json"):
            if stale.is_file():
                try:
                    stale.unlink()
                    log.warn(f"[{g}] 已停用并清理旧合并产物: {wsp.rel(stale)}")
                except OSError:
                    pass

    manifest["derived_groups"] = sorted(set(parts_by_group) - set(manifest["groups"]))
    manifest["superseded_groups"] = superseded_groups
    manifest["groups"] = sorted(set(manifest["groups"]) | set(parts_by_group))
    (wsp.work / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # 索引式清理: 上次产出的纯文本若本次不再产出(改规则/改团名), 删掉避免孤儿
    record_path = wsp.work / "state" / "ingest_textlogs.json"
    prev_record: dict[str, Any] = {}
    if record_path.is_file():
        try:
            prev_record = json.loads(record_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            prev_record = {}
    current_textlogs = sorted(
        {wsp.rel(qq_mod.textlog_path(wsp, g)) for g in parts_by_group}
        | {wsp.rel(wsp.normalized / f"{g}_sources.json") for g in parts_by_group}
    )
    for stale in sorted(set(prev_record.get("textlogs", [])) - set(current_textlogs)):
        sp = wsp.root / stale
        if sp.is_file():
            try:
                sp.unlink()
                log.warn(f"清理上次产出、本次已过期的纯文本: {stale}")
            except OSError:
                pass
    record_path.parent.mkdir(parents=True, exist_ok=True)
    record_path.write_text(
        json.dumps({"textlogs": current_textlogs, "updated": manifest["generated"]},
                   ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    if manifest["derived_groups"]:
        log.info("派生团(由拆团规则产生): " + ", ".join(manifest["derived_groups"]))
    render_summary(manifest)
    if not converted:
        log.info("无需转换的 QQ 导出(无新增/变化)")

    st = StepState(wsp, "ingest")
    h = combine_hash([(f["path"], f["sha256"]) for f in manifest["files"]])
    st.finish(
        outputs=[wsp.rel(wsp.work / "manifest.json")] + [c["out"] for c in converted],
        message=f"{manifest['counts']['total']} 文件 / {len(manifest['groups'])} 团"
                + (f" / 停用 {len(superseded_groups)}" if superseded_groups else ""),
        extra={"counts": manifest["counts"], "groups": manifest["groups"],
               "derived_groups": manifest["derived_groups"],
               "superseded_groups": superseded_groups},
    )
    st.data["input_hash"] = h
    st.save()

    if json_out:
        typer.echo(json.dumps({"manifest": {k: v for k, v in manifest.items() if k != "files"},
                               "converted": converted,
                               "superseded_groups": superseded_groups}, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- segment

def _pick_sources(
    wsp: Workspace, cfg: Config, group: str, manifest: dict[str, Any], force_type: str | None
) -> tuple[str | None, list[Path]]:
    tl = qq_mod.textlog_path(wsp, group)
    normalized_exists = tl.is_file()
    by_type: dict[str, list[Path]] = {}
    ignored_manual: list[str] = []

    def is_manual_textlog(path_posix: str) -> bool:
        return path_posix.endswith(qq_mod.TEXTLOG_SUFFIX)

    for f in manifest["files"]:
        if f["group"] != group or f["type"] not in cfg.segment.inputs:
            continue
        if f.get("superseded"):
            log.info(f"[{group}] 跳过已停用输入: {f['path']}")
            continue
        # 归一化纯文本(本工具从导出派生)已存在时, 素材里的人工纯文本已被取代,
        # 若仍消费它, 同一批消息会被切两遍。
        if normalized_exists and f["type"] == "qq_text" and is_manual_textlog(f["path"]):
            ignored_manual.append(f["path"])
            continue
        by_type.setdefault(f["type"], []).append(wsp.root / f["path"])

    if normalized_exists:
        by_type.setdefault("qq_text", []).append(tl)
        extra_manual = [
            wsp.rel(p) for p in qq_mod.find_existing_textlogs(wsp)
            if group in p.name and wsp.rel(p) not in ignored_manual
        ]
        ignored_manual.extend(extra_manual)
    else:
        for p in qq_mod.find_existing_textlogs(wsp):
            if group in p.name:
                by_type.setdefault("qq_text", []).append(p)

    if ignored_manual:
        log.info(
            f"[{group}] 忽略 {len(ignored_manual)} 个人工纯文本(已被 normalized 取代): "
            + ", ".join(sorted(set(ignored_manual)))
        )

    for t in by_type:
        seen: set[str] = set()
        uniq: list[Path] = []
        for p in by_type[t]:
            key = str(p.resolve()).lower()
            if key not in seen:
                seen.add(key)
                uniq.append(p)
        by_type[t] = sorted(uniq)

    if force_type:
        return (force_type, by_type.get(force_type, [])) if by_type.get(force_type) else (None, [])
    for t in SOURCE_PRIORITY:
        if by_type.get(t):
            others = [k for k in by_type if k != t and by_type[k]]
            if others:
                log.info(f"[{group}] 同时存在 {others}, 按优先级选用 {t} (可用 --type 指定)")
            return t, by_type[t]
    return None, []


def _strategy_for(source_type: str | None, override: str | None, cfg: Config) -> str:
    if override:
        return override
    if source_type == "transcript":
        return cfg.segment.strategy
    if source_type == "qq_text":
        return "date"
    return "line_chunk"


@app.command()
def segment(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="只切指定团"),
    strategy: Optional[str] = typer.Option(None, "--strategy", help="time_window|date|line_chunk"),
    source_type: Optional[str] = typer.Option(None, "--type", help="transcript|qq_text|raw_text"),
    date_merge_lines: Optional[int] = typer.Option(
        None, "--date-merge-lines", help="date 策略的日期合并行数上限(0=一天一段)"
    ),
    force: bool = typer.Option(False, "--force", help="指纹未变也重跑"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M3 切段: 等时间窗(默认) / 按日期(QQ 线) -> 素材/segments/。"""
    cfg, wsp = _ctx(config, ws, "segment")
    log.step(f"segment · {wsp.root}")
    manifest = load_manifest(wsp)
    if manifest is None:
        log.err("缺少 manifest, 请先跑: trpg-agent ingest")
        raise typer.Exit(2)

    groups = [group] if group else [
        g for g in manifest["groups"] if g not in set(manifest.get("superseded_groups") or [])
    ]
    st = StepState(wsp, "segment")
    results: list[dict[str, Any]] = []
    hashes: list[tuple[str, str]] = []

    for g in groups:
        stype, sources = _pick_sources(wsp, cfg, g, manifest, source_type)
        if not sources:
            log.warn(f"[{g}] 无可切段输入(需 transcript/qq_text/raw_text), 跳过")
            continue
        hashes.append((g, combine_hash(
            [(wsp.rel(p), sha256_file(p)) for p in sources] + [("source_type", str(stype))]
        )))
    input_hash = combine_hash(hashes + [("strategy", str(strategy or cfg.segment.strategy)),
                                        ("window", str(cfg.segment.window_s)),
                                        ("logic", str(SEGMENT_LOGIC_VERSION)),
                                        ("date_merge", str(date_merge_lines if date_merge_lines is not None
                                                           else cfg.segment.date_merge_max_lines))])

    if st.is_fresh(input_hash) and not force:
        log.ok(f"输入未变化, 跳过(产物已是最新)。要强制重跑加 --force")
        idx_groups = [r for r in (load_index(wsp, g) for g in groups) if r]
        if json_out:
            typer.echo(json.dumps({"skipped": True, "groups": len(idx_groups)}, ensure_ascii=False))
        return

    st.start(input_hash)
    try:
        for g in groups:
            stype, sources = _pick_sources(wsp, cfg, g, manifest, source_type)
            if not sources:
                continue
            eff = _strategy_for(stype, strategy, cfg)
            res = segment_one(wsp, cfg, g, sources, strategy=eff, date_merge_lines=date_merge_lines)
            res["source_type"] = stype
            results.append(res)
            render_group(res)
    except Exception as e:  # noqa: BLE001
        st.fail(str(e))
        raise

    total_segments = sum(len(r["segments"]) for r in results)
    st.finish(
        outputs=[s["file"] for r in results for s in r["segments"]],
        message=f"{len(results)} 团 / {total_segments} 段",
        extra={"groups": {r["group"]: len(r["segments"]) for r in results},
               "strategy": strategy or cfg.segment.strategy},
    )
    log.ok(f"切段完成: {len(results)} 团 / {total_segments} 段 -> {wsp.rel(wsp.segments)}")
    if json_out:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- transcribe

def _audio_targets(wsp: Workspace, cfg: Config, group: str | None, file: str | None) -> list[tuple[str, Path]]:
    """返回 [(团, 音频路径)]。"""
    if file:
        p = Path(file)
        if not p.is_absolute():
            p = (wsp.root / p)
        if not p.is_file():
            raise FileNotFoundError(f"音频不存在: {p}")
        return [(group or group_from_audio(p), p)]
    manifest = load_manifest(wsp)
    if manifest is None:
        raise FileNotFoundError("缺少 manifest, 请先跑: trpg-agent ingest")
    out: list[tuple[str, Path]] = []
    for f in manifest["files"]:
        if f["type"] != "audio":
            continue
        if group and f["group"] != group:
            continue
        out.append((f["group"], wsp.root / f["path"]))
    return out


def _make_job_progress(wsp: Workspace, job_id: str):
    def cb(p: dict[str, Any]) -> None:
        rec = jobs.load_job(wsp, job_id)
        if rec is None:
            return
        dur = p.get("duration_s") or 0
        pct = round(100.0 * (p.get("audio_at_s") or 0) / dur, 1) if dur else None
        rec.extra["progress"] = {**p, "percent": pct}
        jobs.save_job(wsp, rec)
    return cb


@app.command()
def transcribe(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="团名(默认扫 manifest 里的 audio)"),
    file: Optional[str] = typer.Option(None, "--file", "-f", help="直接指定音频文件"),
    smoke: Optional[int] = typer.Option(None, "--smoke", help="只转开头 N 秒(冒烟测试)"),
    force: bool = typer.Option(False, "--force", help="忽略断点, 从头转"),
    background: bool = typer.Option(False, "--background", "-b", help="脱离式后台运行(可恢复)"),
    job_id: Optional[str] = typer.Option(None, "--job-id", hidden=True, help="内部: 后台任务 id"),
    device: Optional[str] = typer.Option(None, "--device", help="cpu|cuda"),
    model_path: Optional[str] = typer.Option(None, "--model", help="覆盖 config 里的模型"),
    prompt: Optional[str] = typer.Option(
        None, "--prompt",
        help="覆盖 asr.initial_prompt(团专属词表: 角色名/术语; 显著降低专名错字)",
    ),
    window_s: Optional[int] = typer.Option(None, "--window", help="解码窗口秒数"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M2 转写: 窗口化流式解码 + VAD 分批 + 逐行落盘 + 断点续跑。"""
    cfg, wsp = _ctx(config, ws, "transcribe")
    if device:
        cfg.asr.device = device
    if model_path:
        cfg.asr.model_path = model_path
    if prompt:
        # 团专属词表不该挤在 config 里: 一换团就得改配置, 而 initial_prompt 又参与断点指纹,
        # 改一次就把上一个团的断点判废(2026-10-05 实测踩到)。所以允许按次覆盖。
        cfg.asr.initial_prompt = prompt
    if window_s:
        cfg.asr.window_s = window_s

    if background and not job_id:
        argv = [sys.executable, "-m", "trpg_agent", "transcribe",
                "--config", str(find_config(config)), "--ws", str(wsp.root),
                "--background"]
        if group:
            argv += ["--group", group]
        if file:
            argv += ["--file", str(file)]
        if smoke:
            argv += ["--smoke", str(smoke)]
        if force:
            argv += ["--force"]
        if device:
            argv += ["--device", device]
        if model_path:
            argv += ["--model", model_path]
        if prompt:
            argv += ["--prompt", prompt]
        if window_s:
            argv += ["--window", str(window_s)]
        rec = jobs.start_background(wsp, "transcribe", argv, extra={"group": group, "file": file})
        log.ok(f"后台任务已启动: {rec.id} (pid {rec.pid})")
        log.info(f"  跟踪进度: python -m trpg_agent jobs list --ws \"{wsp.root}\"")
        log.info(f"  查看日志: python -m trpg_agent jobs logs {rec.id} --ws \"{wsp.root}\"")
        log.info(f"  中断:     python -m trpg_agent jobs kill {rec.id} --ws \"{wsp.root}\"")
        typer.echo(json.dumps(rec.to_dict(), ensure_ascii=False) if json_out else rec.id)
        return

    log.step(f"transcribe · {wsp.root}")
    try:
        targets = _audio_targets(wsp, cfg, group, file)
    except FileNotFoundError as e:
        log.err(str(e))
        raise typer.Exit(2)
    if not targets:
        log.warn("没有找到音频素材(用 --group 或 --file 指定)")
        raise typer.Exit(2)

    results: list[dict[str, Any]] = []
    failed = False
    # 一个团带多个录音时, 每份录音单独出稿(否则后一份覆盖前一份):
    # 用音频名做 part_tag, 由 segment 的 join_transcripts 按时间偏移接成一条时间轴。
    group_counts: dict[str, int] = {}
    for g, _a in targets:
        group_counts[g] = group_counts.get(g, 0) + 1
    try:
        for g, audio in targets:
            results.append(
                run_transcribe(
                    wsp, cfg, audio, group=g, force=force, smoke=smoke,
                    progress_cb=_make_job_progress(wsp, job_id) if job_id else None,
                    part_tag=audio.stem if group_counts.get(g, 0) > 1 else None,
                )
            )
    except KeyboardInterrupt:
        failed = True
        log.warn("转写被中断(断点已保存)")
    except Exception as e:  # noqa: BLE001
        failed = True
        log.err(f"转写失败: {type(e).__name__}: {e}")

    st = StepState(wsp, "transcribe")
    h = combine_hash(
        [(r["audio"], f"{r['audio_s']:.0f}") for r in results]
        + [("model", cfg.asr.model_path), ("window", str(cfg.asr.window_s))]
    )
    if failed:
        st.start(h)
        st.fail("中断或失败")
    else:
        st.finish(
            outputs=[r["out"] for r in results],
            message=f"{len(results)} 个音频 / {sum(r['segments'] for r in results)} 段",
            extra={"results": results},
        )
    if job_id:
        jobs.mark_finished(wsp, job_id, "failed" if failed else "finished")
    if json_out:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2))
    if failed:
        raise typer.Exit(1)


# --------------------------------------------------------------------------- jobs

jobs_app = typer.Typer(no_args_is_help=True, help="长任务: 查看/日志/中断")
app.add_typer(jobs_app, name="jobs")


@jobs_app.command("list")
def jobs_list(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """列出后台任务(含进度)。"""
    cfg, wsp = _ctx(config, ws, "jobs")
    recs = jobs.list_jobs(wsp)
    if not recs:
        log.info("没有任务记录")
        return
    rows = []
    for r in recs:
        prog = r.extra.get("progress") or {}
        pct = f"{prog.get('percent')}%" if prog.get("percent") is not None else "-"
        rows.append((r.id, f"{r.status:<9} {pct:>7}  {r.kind:<11} {r.started}  pid={r.pid}"))
    log.kv_table("后台任务", rows)
    if json_out:
        typer.echo(json.dumps([r.to_dict() for r in recs], ensure_ascii=False, indent=2))


@jobs_app.command("logs")
def jobs_logs(
    job_id: str = typer.Argument(..., help="任务 id"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    tail: int = typer.Option(40, "--tail", help="显示最后 N 行, 0=全部"),
) -> None:
    """查看任务日志。"""
    cfg, wsp = _ctx(config, ws, "jobs")
    text = jobs.read_log(wsp, job_id, tail=tail)
    if not text:
        log.warn(f"任务 {job_id} 无日志")
        return
    typer.echo(text)


@jobs_app.command("kill")
def jobs_kill(
    job_id: str = typer.Argument(..., help="任务 id"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
) -> None:
    """中断后台任务(整进程树)。"""
    cfg, wsp = _ctx(config, ws, "jobs")
    if not jobs.kill_job(wsp, job_id):
        raise typer.Exit(1)


# --------------------------------------------------------------------------- llm

llm_app = typer.Typer(no_args_is_help=True, help="LLM 后端: 探活 / 模型列表")
app.add_typer(llm_app, name="llm")


@llm_app.command("check")
def llm_check(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    ping: bool = typer.Option(True, "--ping/--no-ping", help="是否做一次最小对话往返"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """逐个 provider 探活: 连通性 / 模型列表 / 最小往返 / tok·s。"""
    cfg, wsp = _ctx(config, ws, "llm")
    log.step(f"llm check · {wsp.root}")
    results: list[dict[str, Any]] = []
    routes = cfg.llm.routes

    for name, prov in cfg.llm.providers.items():
        used_by = [r for r, target in routes.items() if target == name]
        row: dict[str, Any] = {
            "provider": name, "type": prov.type, "model": prov.model,
            "base_url": prov.base_url, "used_by": used_by,
        }
        client = make_llm_client(prov)
        probe = client.probe()
        row["probe"] = probe
        row["ok"] = bool(probe.get("ok"))
        if ping and row["ok"]:
            try:
                res = _llm_ping(prov)
                row.update({"ping_ok": True, "ping_s": round(res.elapsed_s, 2),
                            "ping_tokens": res.completion_tokens,
                            "tok_per_s": res.tok_per_s, "reply": res.text[:40]})
            except Exception as e:  # noqa: BLE001
                row.update({"ping_ok": False, "ping_error": f"{type(e).__name__}: {e}"})
        results.append(row)

        mark = "OK  " if row["ok"] else "FAIL"
        log.info(
            f"[{mark}] {name}  {prov.type}/{prov.model}  @ {prov.base_url}"
            + (f"  被 routes 使用: {', '.join(used_by)}" if used_by else "  (未被 routes 使用)")
        )
        if prov.type == "openai" and not prov.api_key:
            log.warn(f"      环境变量 {prov.api_key_env} 未设置")
        models = probe.get("models")
        if models:
            log.info(f"      可用模型: {', '.join(str(m) for m in models[:12])}")
        if row.get("ping_ok"):
            log.info(f"      最小往返 {row['ping_s']}s · {row.get('tok_per_s')} tok/s · 回复: {row.get('reply')!r}")
        elif row.get("ping_error"):
            log.err(f"      往返失败: {row['ping_error']}")
        elif probe.get("error"):
            log.err(f"      探活失败: {probe['error']}")

    if json_out:
        typer.echo(json.dumps(results, ensure_ascii=False, indent=2, default=str))


def _llm_ping(prov):
    client = make_llm_client(prov)
    return client.chat([{"role": "user", "content": "只回一个字: 好"}], max_tokens=16, temperature=0)


# --------------------------------------------------------------------------- store

@app.command()
def store(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    patch: Optional[str] = typer.Option(None, "--patch", "-p", help="补丁 JSON 路径"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="团名(默认查 .trpg/patches/<团>_patch.json)"),
    apply: bool = typer.Option(False, "--apply", help="回填数据目录(先备份)"),
    allow_production: bool = typer.Option(False, "--allow-production", help="允许写生产库"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M5 入库: 补丁 -> 校验 -> 工作副本 -> 报告/待确认 -> (可选)备份并回填。"""
    cfg, wsp = _ctx(config, ws, "store")
    log.step(f"store · {wsp.root}")
    try:
        result = run_store(
            wsp, cfg,
            patch_path=Path(patch) if patch else None,
            group=group,
            apply=apply,
            allow_production=allow_production,
        )
    except ProductionWriteBlocked as e:
        log.err(str(e))
        raise typer.Exit(3)
    except (FileNotFoundError, ValueError) as e:
        log.err(str(e))
        raise typer.Exit(2)

    st = StepState(wsp, "store")
    h = combine_hash([("patch", sha256_file(Path(patch) if patch else (wsp.patches / f"{result['group']}_patch.json")))])
    st.start(h)
    st.finish(
        outputs=[v for v in (result["plan_path"], result["report"], result["pending"]) if v],
        message=f"{result['group']} 新增角色 {len(result['plan']['new_characters'])} / "
                f"关系 {len(result['plan']['new_relations'])} / 待确认 {len(result['plan']['pending'])}",
        extra={"applied": result["applied"], "written": result["written"]},
    )
    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- status

@app.command()
def status(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """查看工作区: 配置概览 / 各步状态 / 数据量 / manifest。"""
    cfg, wsp = _ctx(config, ws, "status")
    states = all_states(wsp)
    manifest = load_manifest(wsp)
    counts: dict[str, int] = {}
    for kind, key in (("characters", "characters"), ("relations", "relations"),
                      ("players", "players"), ("pl_profiles", "profiles")):
        p = wsp.data_file(kind)
        if p.is_file():
            try:
                counts[kind] = len(json.loads(p.read_text(encoding="utf-8")).get(key, []))
            except (json.JSONDecodeError, OSError):
                counts[kind] = -1
        else:
            counts[kind] = 0

    log.step(f"status · {wsp.root}")
    log.kv_table(
        "工作区",
        [
            ("root", wsp.root),
            ("生产库", "是(写入需授权)" if wsp.is_production else "否"),
            ("数据", wsp.data),
            ("产出", wsp.output),
            ("运行态", wsp.work),
            ("素材", f"{len(manifest['files'])} 文件 / {len(manifest['groups'])} 团" if manifest else "未扫描"),
            ("LLM", f"default={cfg.llm.default} routes.extract={cfg.llm.routes.get('extract')}"),
            ("ASR", f"{cfg.asr.engine} / {Path(cfg.asr.model_path).name or '(未配置)'}"),
        ],
    )
    rows = []
    for name, s in states.items():
        rows.append((name, s.status, s.data.get("message", ""), s.data.get("finished") or "-"))
    log.kv_table("步骤状态", [(f"{a:<10}", f"{b:<8} {c}") for a, b, c, _ in rows])
    log.kv_table(
        "数据量",
        [(k, f"{v} 条" if v >= 0 else "读取失败") for k, v in counts.items()],
    )
    if json_out:
        typer.echo(json.dumps({
            "root": str(wsp.root),
            "is_production": wsp.is_production,
            "counts": counts,
            "steps": {k: {"status": v.status, "message": v.data.get("message", "")} for k, v in states.items()},
            "manifest": {k: v for k, v in (manifest or {}).items() if k != "files"},
        }, ensure_ascii=False, indent=2))


# --------------------------------------------------------------------------- 未实现的步骤

def _todo(step: str, slice_name: str) -> None:
    log.err(f"`{step}` 尚未实现(计划在 {slice_name} 落地)。")
    log.info("切片 1 已交付: ingest / segment / store / status")
    raise typer.Exit(2)


# --------------------------------------------------------------------------- canon

canon_app = typer.Typer(no_args_is_help=True, help="canon: 铁律/称呼规范/已入库名单")
app.add_typer(canon_app, name="canon")


@canon_app.command("build")
def canon_build(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    force: bool = typer.Option(False, "--force", help="连称呼表也重新从模板生成"),
) -> None:
    """固化 canon: 生成/刷新 canon/naming.json 与 canon/roster.json。"""
    cfg, wsp = _ctx(config, ws, "canon")
    r = canon.build(wsp, cfg, force=force)
    for p in r["created"]:
        log.ok(f"生成 {p}")
    roster = json.loads((wsp.root / r["roster"]).read_text(encoding="utf-8"))
    log.ok(f"名单已刷新: {r['roster']} ({roster.get('count', 0)} 个角色)")


@canon_app.command("show")
def canon_show(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="按该团裁剪名单"),
) -> None:
    """预览将注入提炼 prompt 的 canon 块。"""
    cfg, wsp = _ctx(config, ws, "canon")
    block = canon.render_canon_block(wsp, group, roster_scope=cfg.extract.roster_scope)
    typer.echo(block)
    log.info(f"— canon 块 {len(block)} 字（≈{len(block)//2} tokens），注入策略 {cfg.extract.roster_scope}")


# --------------------------------------------------------------------------- extract

def _extract_argv(cfg_path: str, ws_root: str, group: str, opts: dict[str, Any]) -> list[str]:
    argv = [sys.executable, "-m", "trpg_agent", "extract",
            "--config", cfg_path, "--ws", ws_root, "--background", "--group", group]
    for flag, key in (("--segment", "segment"), ("--prefix", "prefix")):
        if opts.get(key) is not None:
            argv += [flag, str(opts[key])]
    for flag, key in (("--base-url", "base_url"), ("--model", "model")):
        if opts.get(key):
            argv += [flag, str(opts[key])]
    if opts.get("force"):
        argv.append("--force")
    if opts.get("segments_only"):
        argv.append("--segments-only")
    if opts.get("consolidate_only"):
        argv.append("--consolidate-only")
    return argv


@app.command()
def extract(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="团名"),
    segment: Optional[int] = typer.Option(None, "--segment", help="只重跑某一段"),
    prefix: Optional[str] = typer.Option(None, "--prefix", help="新角色 id 前缀(默认查 config)"),
    segments_only: bool = typer.Option(False, "--segments-only", help="只做分段提炼, 不汇总"),
    consolidate_only: bool = typer.Option(False, "--consolidate-only", help="只用已有草稿汇总成补丁"),
    force: bool = typer.Option(False, "--force", help="已有提炼也重跑"),
    base_url: Optional[str] = typer.Option(None, "--base-url", help="临时覆盖 LLM 端点(如专用 ollama 实例)"),
    model: Optional[str] = typer.Option(None, "--model", help="临时覆盖模型名"),
    background: bool = typer.Option(False, "--background", "-b", help="脱离式后台运行"),
    job_id: Optional[str] = typer.Option(None, "--job-id", hidden=True),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M4 提炼: canon 注入 + 分段扇出 -> 汇总成入库补丁。"""
    cfg, wsp = _ctx(config, ws, "extract")
    if not group:
        log.err("需要 --group")
        raise typer.Exit(2)
    if base_url or model:
        prov = cfg.llm.provider_for(cfg.extract.model_route)
        if base_url:
            prov.base_url = base_url
        if model:
            prov.model = model
        log.info(f"LLM 端点覆盖: {prov.type}/{prov.model} @ {prov.base_url}")

    if background and not job_id:
        argv = _extract_argv(str(find_config(config)), str(wsp.root), group,
                             {"segment": segment, "prefix": prefix, "force": force,
                              "segments_only": segments_only, "consolidate_only": consolidate_only,
                              "base_url": base_url, "model": model})
        rec = jobs.start_background(wsp, "extract", argv, extra={"group": group})
        log.ok(f"后台任务已启动: {rec.id} (pid {rec.pid})")
        log.info(f"  跟踪: python -m trpg_agent jobs list   ·  日志: jobs logs {rec.id}")
        typer.echo(rec.id if not json_out else json.dumps(rec.to_dict(), ensure_ascii=False))
        return

    log.step(f"extract · {group}")
    failed = False
    try:
        result = run_extract(
            wsp, cfg, group, force=force, only_segment=segment,
            segments_only=segments_only, consolidate_only=consolidate_only, id_prefix=prefix,
        )
    except (FileNotFoundError, ValueError, LLMError) as e:
        failed = True
        log.err(f"提炼失败: {type(e).__name__}: {e}")
        result = {"group": group, "error": str(e)}
    except Exception as e:  # noqa: BLE001
        failed = True
        log.err(f"提炼异常: {type(e).__name__}: {e}")
        result = {"group": group, "error": str(e)}

    st = StepState(wsp, "extract")
    h = combine_hash([("group", group), ("segments", str(result.get("segments", "")))])
    if failed:
        st.start(h)
        st.fail(str(result.get("error")))
    else:
        st.finish(
            outputs=[v for v in (result.get("patch"), result.get("summary_raw")) if v],
            message=f"{group} 补丁 {result.get('counts', {})}",
            extra={"result": result},
        )
    if job_id:
        jobs.mark_finished(wsp, job_id, "failed" if failed else "finished")
    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
    if failed:
        raise typer.Exit(1)


# --------------------------------------------------------------------------- review

@app.command()
def review(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="团名"),
    apply: bool = typer.Option(False, "--apply", help="把裁决文件写回补丁与 canon"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M5-review: 汇总待确认 -> 生成裁决文件 -> (--apply) 固化进 canon。"""
    cfg, wsp = _ctx(config, ws, "review")
    if not group:
        log.err("需要 --group")
        raise typer.Exit(2)
    if apply:
        try:
            result = review_apply(wsp, cfg, group)
        except FileNotFoundError as e:
            log.err(str(e))
            raise typer.Exit(2)
        log.info(f"裁决记录: {wsp.rel(wsp.work / cfg.review.decisions_dir / f'{group}_裁决记录.json')}")
        log.info("下一步: trpg-agent store --group " + group + "   （先看工作副本，确认后加 --apply）")
        if json_out:
            typer.echo(json.dumps(result, ensure_ascii=False, indent=2))
        return

    items = review_collect(wsp, group)
    log.step(f"review · {group} · 待确认 {len(items)} 项")
    if not items:
        log.ok("没有待确认项")
    for line in review_render(items):
        log.info(line)
    path = review_write_template(wsp, cfg, group, items)
    log.ok(f"裁决文件: {wsp.rel(path)}  （编辑 decisions 后可 --apply）")


@app.command()
def visualize(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="只出这个团的关系图/关系网"),
    all_groups: bool = typer.Option(False, "--all", help="为所有团都出关系图"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M6 可视化: 团关系图 HTML + 关系网 md + PL 画像墙 + 杰克档案/宇宙总览。"""
    cfg, wsp = _ctx(config, ws, "visualize")
    log.step(f"visualize · {wsp.root}")
    try:
        result = run_visualize(wsp, cfg, group=group, all_groups=all_groups)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.err(f"可视化失败: {e}")
        raise typer.Exit(2)
    st = StepState(wsp, "visualize")
    st.finish(
        outputs=[r["path"] for r in result["net"]]
                + ([result["pl_wall"]["path"]] if result.get("pl_wall") else [])
                + [d["path"] for d in result["docs"]],
        message=f"关系图 {len(result['net'])} · PL墙 {'有' if result.get('pl_wall') else '无'} · "
                f"文档 {len(result['docs'])}",
    )
    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def export(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M7 KB 包导出: 生成 RAG 友好的 Markdown 包。"""
    cfg, wsp = _ctx(config, ws, "export")
    log.step(f"export · {wsp.root}")
    try:
        result = run_export(wsp, cfg)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        log.err(f"导出失败: {e}")
        raise typer.Exit(2)
    st = StepState(wsp, "export")
    st.finish(outputs=result["written"], message=f"{len(result['written'])} 份 -> {result['out_dir']}")
    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def housekeep(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """M8 收尾: 汇总流程状态/数据量/待确认 -> 收尾清单。"""
    cfg, wsp = _ctx(config, ws, "housekeep")
    log.step(f"housekeep · {wsp.root}")
    result = run_housekeep(wsp, cfg)
    st = StepState(wsp, "housekeep")
    st.finish(outputs=[result["path"]], message=f"数据量 {result['counts']} / 待确认 {result['todo']}")
    if json_out:
        typer.echo(json.dumps(result, ensure_ascii=False, indent=2))


@app.command()
def run(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    group: Optional[str] = typer.Option(None, "--group", "-g", help="只处理该团(切段/提炼/可视化)"),
    patch: Optional[str] = typer.Option(None, "--patch", "-p", help="入库补丁路径"),
    apply: bool = typer.Option(False, "--apply", help="入库时回填数据目录(先备份)"),
    allow_production: bool = typer.Option(False, "--allow-production", help="允许写生产库"),
    llm_base_url: Optional[str] = typer.Option(None, "--base-url", help="LLM 端点覆盖"),
    llm_model: Optional[str] = typer.Option(None, "--model", help="模型覆盖"),
    skip_transcribe: bool = typer.Option(False, "--skip-transcribe"),
    json_out: bool = typer.Option(False, "--json"),
) -> None:
    """一键跑固定工作流: ingest -> [transcribe] -> segment -> extract -> review -> store -> visualize -> export -> housekeep。"""
    cfg, wsp = _ctx(config, ws, "run")
    log.step(f"run · {wsp.root} · 团={group or '(全部)'}")
    steps_done: list[str] = []

    def _invoke(cmd_name: str, **kwargs: Any) -> None:
        fn = {
            "ingest": ingest, "transcribe": transcribe, "segment": segment,
            "extract": extract, "review": review, "store": store,
            "visualize": visualize, "export": export, "housekeep": housekeep,
        }[cmd_name]
        fn(**kwargs)
        steps_done.append(cmd_name)

    _invoke("ingest", config=config, ws=ws, group=None, rebuild=False, json_out=False)

    if not skip_transcribe:
        try:
            _invoke("transcribe", config=config, ws=ws, group=group, file=None, smoke=None,
                    force=False, background=False, job_id=None, device=None, model_path=None,
                    window_s=None, json_out=False)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            log.warn(f"转写步骤跳过: {type(e).__name__}: {e}")

    _invoke("segment", config=config, ws=ws, group=group, strategy=None, source_type=None,
            date_merge_lines=None, force=False, json_out=False)

    if group:
        try:
            _invoke("extract", config=config, ws=ws, group=group, segment=None, prefix=None,
                    segments_only=False, consolidate_only=False, force=False, base_url=llm_base_url,
                    model=llm_model, background=False, job_id=None, json_out=False)
            _invoke("review", config=config, ws=ws, group=group, apply=False, json_out=False)
            _invoke("store", config=config, ws=ws, group=group,
                    patch=patch, apply=apply, allow_production=allow_production, json_out=False)
        except (SystemExit, Exception) as e:  # noqa: BLE001
            log.warn(f"提炼/入库步骤未完成(需人工裁决或 LLM 不可用): {type(e).__name__}: {e}")

    _invoke("visualize", config=config, ws=ws, group=group, all_groups=False, json_out=False)
    _invoke("export", config=config, ws=ws, json_out=False)
    _invoke("housekeep", config=config, ws=ws, json_out=False)

    log.ok("工作流完成: " + " -> ".join(steps_done))
    if json_out:
        typer.echo(json.dumps({"steps": steps_done}, ensure_ascii=False, indent=2))


@app.command()
def web(
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    ws: Optional[str] = typer.Option(None, "--ws", "-w"),
    host: str = typer.Option("127.0.0.1", "--host", help="绑定地址(默认仅本机)"),
    port: int = typer.Option(8765, "--port", "-p"),
    read_only: bool = typer.Option(False, "--read-only", help="禁用一切写操作"),
    reload: bool = typer.Option(False, "--reload", help="开发热重载"),
    background: bool = typer.Option(False, "--background", "-b", help="脱离式常驻(与 DSH/终端会话无关)"),
) -> None:
    """本地 Web 面板: 进度看板 / 待确认裁决 / 产物预览。"""
    cfg, wsp = _ctx(config, ws, "web")
    if background:
        argv = [sys.executable, "-m", "trpg_agent", "web",
                "--config", str(find_config(config)), "--ws", str(wsp.root),
                "--host", host, "--port", str(port)]
        if read_only:
            argv.append("--read-only")
        rec = jobs.start_background(wsp, "web", argv, pass_job_id=False,
                                    extra={"port": port, "url": f"http://{host}:{port}"})
        log.ok(f"面板已在后台常驻: http://{host}:{port}  (pid {rec.pid})")
        log.info(f"  停止: python -m trpg_agent jobs kill {rec.id}")
        log.info(f"  日志: python -m trpg_agent jobs logs {rec.id} --tail 30")
        return
    from trpg_agent.web import serve

    serve(cfg, wsp, host=host, port=port, read_only=read_only, reload=reload)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
