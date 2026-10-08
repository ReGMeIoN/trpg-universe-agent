# -*- coding: utf-8 -*-
"""切段: 等时间窗(默认) / 按日期(QQ 线)。

输入: 转写稿(带 [start -> end] 行) 或 QQ 纯文本([mm-dd hh:mm] 行) 或 raw 文本。
输出: <root>/素材/segments/<团>_段N_<标签>.txt
      <work>/state/segment_index/<团>.json   (段落索引: 起止秒/行数/大小)
未解析行单独统计并打印, 不静默丢弃。
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any, Iterable

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.workspace import Workspace

TS_LINE_RE = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\s*->\s*(\d+(?:\.\d+)?)\s*\]\s?(.*)$")
QQ_LINE_RE = re.compile(r"^\[(\d{2}-\d{2})\s+(\d{2}:\d{2})\]\s*(.*)$")

# 切段逻辑版本: 参与 input_hash, 算法变更后不会误判"已是最新"
SEGMENT_LOGIC_VERSION = 2


@dataclass
class Segment:
    n: int
    group: str
    label: str
    file: str
    lines: int
    chars: int
    start_s: float | None = None
    end_s: float | None = None
    first_line: str = ""
    last_line: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _mmss(sec: float) -> str:
    """时间标签: 0h10m / 1h03m (带单位, 避免 0103 这类歧义)。"""
    m, _s = divmod(int(sec), 60)
    h, m = divmod(m, 60)
    return f"{h:d}h{m:02d}m"


def parse_ts_lines(lines: list[str]) -> tuple[list[tuple[float, float, str]], int]:
    out: list[tuple[float, float, str]] = []
    unparsed = 0
    for ln in lines:
        m = TS_LINE_RE.match(ln.strip())
        if not m:
            unparsed += 1
            continue
        out.append((float(m.group(1)), float(m.group(2)), ln))
    return out, unparsed


def parse_qq_lines(lines: list[str]) -> tuple[list[tuple[str, str]], int]:
    """返回 [(日期 mm-dd, 原始行)], 未解析数"""
    out: list[tuple[str, str]] = []
    unparsed = 0
    last_date: str | None = None
    for ln in lines:
        m = QQ_LINE_RE.match(ln.strip())
        if m:
            last_date = m.group(1)
            out.append((last_date, ln))
        else:
            if last_date is None:
                unparsed += 1
                continue
            out.append((last_date, ln))  # 续行归上一日期
    return out, unparsed


def segment_time_window(
    lines: list[str], window_s: float, max_lines: int
) -> tuple[list[tuple[str, list[str], float, float]], int]:
    parsed, unparsed = parse_ts_lines(lines)
    if not parsed:
        return [], unparsed
    buckets: dict[int, list[tuple[float, float, str]]] = {}
    for st, en, raw in parsed:
        idx = int(st // window_s)
        buckets.setdefault(idx, []).append((st, en, raw))

    out: list[tuple[str, list[str], float, float]] = []
    for idx in sorted(buckets):
        items = buckets[idx]
        # 单窗行数超上限则再按行切
        chunk: list[tuple[float, float, str]] = []
        for it in items:
            chunk.append(it)
            if len(chunk) >= max_lines:
                out.append(("", [c[2] for c in chunk], chunk[0][0], chunk[-1][1]))
                chunk = []
        if chunk:
            out.append(("", [c[2] for c in chunk], chunk[0][0], chunk[-1][1]))

    result: list[tuple[str, list[str], float, float]] = []
    for _, body, st, en in out:
        result.append((f"{_mmss(st)}-{_mmss(en)}", body, st, en))
    return result, unparsed


def segment_by_date(
    lines: list[str], max_lines: int, date_merge_max_lines: int = 3600
) -> tuple[list[tuple[str, list[str], None, None]], int]:  # type: ignore[type-arg]
    """按日期切段。date_merge_max_lines: 连续日期合并上限(0 = 一天一段)。"""
    parsed, unparsed = parse_qq_lines(lines)
    by_date: dict[str, list[str]] = {}
    order: list[str] = []
    for d, ln in parsed:
        if d not in by_date:
            by_date[d] = []
            order.append(d)
        by_date[d].append(ln)

    def can_merge(cur: list[str], add: list[str]) -> bool:
        if date_merge_max_lines <= 0:
            return False
        return len(cur) + len(add) <= min(date_merge_max_lines, max_lines)

    out: list[tuple[str, list[str], None, None]] = []
    cur_label: str | None = None
    cur_lines: list[str] = []
    for d in order:
        dlines = by_date[d]
        if cur_label is None:
            cur_label, cur_lines = d, list(dlines)
        elif can_merge(cur_lines, dlines):
            cur_lines += dlines
            cur_label = f"{cur_label}~{d}"
        else:
            out.append((cur_label, cur_lines, None, None))
            cur_label, cur_lines = d, list(dlines)
        # 单日自身超上限则硬切
        while len(cur_lines) > max_lines:
            out.append((cur_label, cur_lines[:max_lines], None, None))
            cur_lines = cur_lines[max_lines:]
            cur_label = f"{cur_label}(续)"
    if cur_lines:
        out.append((cur_label or "unknown", cur_lines, None, None))
    return out, unparsed


def segment_line_chunk(lines: list[str], max_lines: int) -> tuple[list[tuple[str, list[str], None, None]], int]:  # type: ignore[type-arg]
    """纯文本无时间轴/无日期: 按行数硬切。"""
    if not lines:
        return [], 0
    out: list[tuple[str, list[str], None, None]] = []
    step = max(1, max_lines)
    for i in range(0, len(lines), step):
        body = lines[i : i + step]
        out.append((f"L{i + 1}-{i + len(body)}", body, None, None))
    return out, 0


def write_segments(
    ws: Workspace,
    group: str,
    blocks: list[tuple[str, list[str], Any, Any]],
    out_dir: Path | None = None,
) -> list[Segment]:
    target = out_dir or ws.segments
    target.mkdir(parents=True, exist_ok=True)
    safe = group.replace("/", "_").replace("\\", "_")
    segs: list[Segment] = []
    for i, (label, body, st, en) in enumerate(blocks, 1):
        fname = f"{safe}_段{i}_{label}.txt" if label else f"{safe}_段{i}.txt"
        path = target / fname
        path.write_text("\n".join(body), encoding="utf-8")
        segs.append(
            Segment(
                n=i,
                group=group,
                label=label,
                file=ws.rel(path),
                lines=len(body),
                chars=sum(len(b) for b in body),
                start_s=st,
                end_s=en,
                first_line=(body[0][:120] if body else ""),
                last_line=(body[-1][:120] if body else ""),
            )
        )
    # 清掉"上次由本工具产出、本次不再产出"的旧段文件。
    # ⚠️ 只依据上次的段索引删除, 绝不用 glob 扫目录 ——
    #    生产库 素材/segments 里存在人工命名的历史段文件(如 异世界大逃杀_段1_2024-07-30.txt),
    #    glob 会误删它们。
    prev = load_index(ws, group) or {}
    prev_files = {s.get("file") for s in prev.get("segments", []) if s.get("file")}
    produced = {s.file for s in segs}
    for stale in sorted(prev_files - produced):
        stale_path = ws.root / stale
        if stale_path.is_file():
            try:
                stale_path.unlink()
                log.warn(f"清理上次产出、本次已过期的段文件: {stale}")
            except OSError:
                pass
    return segs


def write_index(ws: Workspace, group: str, segs: list[Segment], extra: dict[str, Any]) -> Path:
    idx_dir = ws.work / "segments_index"
    idx_dir.mkdir(parents=True, exist_ok=True)
    path = idx_dir / f"{group}.json"
    payload = {
        "group": group,
        "count": len(segs),
        "segments": [s.to_dict() for s in segs],
        **extra,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_index(ws: Workspace, group: str) -> dict[str, Any] | None:
    p = ws.work / "segments_index" / f"{group}.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def join_transcripts(sources: list[Path]) -> tuple[list[str], int, list[dict[str, Any]]]:
    """把同一团的多份转写稿接成一条连续时间轴。

    超大录音常被切成"转写_上/转写_下"两次跑, 两份文件的时间戳都从 0 开始;
    直接拼接会让同一段落里混进两个文件的内容。这里给后续文件加时间偏移
    (偏移量 = 前一份稿子的最后结束时间), 并把行内时间戳改写为全局时间。
    """
    out: list[str] = []
    offset = 0.0
    unparsed = 0
    detail: list[dict[str, Any]] = []
    for i, src in enumerate(sources):
        lines = read_lines(src)
        parsed, bad = parse_ts_lines(lines)
        if not parsed:
            # 整份没有 [起 -> 止] 时间戳(如 QQ 纯文本), 原样接上, 不计未解析
            out.extend(lines)
            detail.append({"file": src.name, "offset_s": offset, "lines": len(lines), "timed": False})
            continue
        unparsed += bad
        for st, en, raw in parsed:
            if offset > 0:
                m = TS_LINE_RE.match(raw.strip())
                body = m.group(3) if m else raw
                out.append(f"[{st + offset:07.2f} -> {en + offset:07.2f}] {body}")
            else:
                out.append(raw)
        last_end = parsed[-1][1]
        detail.append(
            {"file": src.name, "offset_s": round(offset, 2), "lines": len(lines),
             "timed": True, "span": f"{parsed[0][0]:.0f}~{last_end:.0f}s"}
        )
        offset += last_end
    return out, unparsed, detail


def segment_one(
    ws: Workspace,
    cfg: Config,
    group: str,
    sources: Iterable[Path],
    strategy: str | None = None,
    date_merge_lines: int | None = None,
) -> dict[str, Any]:
    """把一个团的输入(可能多个文件)切段; 多文件时按文件顺序拼接后再切。"""
    srcs = list(sources)
    lines: list[str] = []
    used: list[str] = []
    timeline: list[dict[str, Any]] = []
    strategy = strategy or cfg.segment.strategy

    # 多份转写稿: 按连续时间轴拼接(修掉"两份都从 0 开始"的错乱)
    if len(srcs) > 1 and all(p.suffix.lower() in (".txt", ".md") for p in srcs):
        lines, pre_unparsed, timeline = join_transcripts(srcs)
        used = [ws.rel(p) for p in srcs]
    else:
        for src in srcs:
            lines.extend(read_lines(src))
            used.append(ws.rel(src))
        pre_unparsed = 0

    merge_lines = cfg.segment.date_merge_max_lines if date_merge_lines is None else date_merge_lines
    if strategy == "time_window":
        blocks, unparsed = segment_time_window(lines, cfg.segment.window_s, cfg.segment.max_lines)
    elif strategy == "date":
        blocks, unparsed = segment_by_date(lines, cfg.segment.max_lines, merge_lines)
    elif strategy == "line_chunk":
        blocks, unparsed = segment_line_chunk(lines, cfg.segment.max_lines)
    else:
        raise ValueError(f"未知切段策略: {strategy}")
    unparsed += pre_unparsed

    if not blocks:
        return {
            "group": group,
            "segments": [],
            "unparsed": unparsed,
            "sources": used,
            "timeline": timeline,
            "strategy": strategy,
            "note": "无可切分内容(时间戳/日期行未识别)",
        }

    segs = write_segments(ws, group, blocks, cfg.segment.out_dir and ws.segments)
    idx = write_index(
        ws, group, segs,
        {"strategy": strategy, "sources": used, "unparsed_lines": unparsed,
         "total_lines": len(lines), "timeline": timeline,
         "logic_version": SEGMENT_LOGIC_VERSION},
    )
    return {
        "group": group,
        "segments": [s.to_dict() for s in segs],
        "unparsed": unparsed,
        "sources": used,
        "timeline": timeline,
        "strategy": strategy,
        "index": ws.rel(idx),
    }


def render_group(seg_result: dict[str, Any]) -> None:
    log.info(
        f"[{seg_result['group']}] 策略={seg_result['strategy']} "
        f"输入 {len(seg_result['sources'])} 文件 -> {len(seg_result['segments'])} 段 "
        f"(未解析行 {seg_result['unparsed']})"
    )
    for t in seg_result.get("timeline") or []:
        if t.get("offset_s"):
            log.info(f"    ↳ 时间轴偏移 {t['file']} += {t['offset_s']}s (原 {t.get('span', '')})")
    for s in seg_result["segments"]:
        log.info(
            f"  段{s['n']:<2} {s['label']:<14} {s['lines']:>6} 行  "
            f"{s['chars']/1024:>7.1f} KB  {s['file']}"
        )
