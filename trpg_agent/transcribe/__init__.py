# -*- coding: utf-8 -*-
"""transcribe 编排: 解析音频 -> 断点状态 -> 逐行落盘 -> 进度/ETA -> 可中断可恢复。

产物:
    <素材>/<团名>_转写.txt          逐行追加落盘(中断不丢)
    <work>/state/transcribe_<slug>.json   断点状态(音频指纹 + 参数指纹 + 下一个窗口/批)
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from trpg_agent import log
from trpg_agent.config import AsrCfg, Config
from trpg_agent.ingest import _split_loose_name
from trpg_agent.transcribe.quality import QualityFilter
from trpg_agent.workspace import Workspace

HASH_CHUNK = 1 << 20
FINGERPRINT_BYTES = 1 << 20  # 首尾各 1MB 参与指纹(避免对 884MB 全量哈希)
TAG_MAX = 40  # 多录音团里, 单份转写稿文件名里带的音频标签长度上限


def _safe_tag(stem: str) -> str:
    """音频名 -> 可安全入文件名的短标签。"""
    tag = "".join(ch if ch not in '\\/:*?"<>|' else "_" for ch in stem).strip(" .")
    return tag[:TAG_MAX] or "part"


def out_path_for(ws: Workspace, cfg: Config, group: str, part_tag: str | None = None) -> Path:
    """一个团一份转写稿; 同一团有多个录音时, 每份录音一份稿(part_tag=音频名)。

    为什么需要 part_tag: 一个团带两份录音(如某团的上下半场)时,
    若都写 <团>_转写.txt, 后一份会把前一份覆盖掉(实测过的坑, 2026-10-05)。
    多份稿子由 segment 的 join_transcripts 按时间偏移接成一条时间轴。
    """
    if part_tag:
        return ws.material / f"{group}__{_safe_tag(part_tag)}{cfg.asr.out_suffix}.txt"
    return ws.material / f"{group}{cfg.asr.out_suffix}.txt"


def state_path_for(ws: Workspace, group: str, part_tag: str | None = None) -> Path:
    safe = "".join(ch if ch.isalnum() else "_" for ch in group)[:60]
    if part_tag:
        safe = f"{safe}__{_safe_tag(part_tag)}"[:120]
    return ws.work / "state" / f"transcribe_{safe}.json"


def group_from_audio(path: Path) -> str:
    return _split_loose_name(path.stem)


def audio_fingerprint(path: Path) -> dict[str, Any]:
    size = path.stat().st_size
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        h.update(fh.read(FINGERPRINT_BYTES))
        if size > 2 * FINGERPRINT_BYTES:
            fh.seek(size - FINGERPRINT_BYTES)
            h.update(fh.read(FINGERPRINT_BYTES))
    return {
        "path": str(path),
        "size": size,
        "mtime": int(path.stat().st_mtime),
        "edge_sha256": h.hexdigest()[:32],
    }


def params_fingerprint(cfg: AsrCfg, smoke: int) -> dict[str, Any]:
    from trpg_agent.adapters import asr_faster_whisper as _fw

    return {
        "logic_version": getattr(_fw, "ASR_LOGIC_VERSION", 0),
        "engine": cfg.engine,
        "model_path": cfg.model_path,
        "device": cfg.device,
        "compute_type": cfg.compute_type,
        "cpu_threads": cfg.cpu_threads,
        "language": cfg.language,
        "beam_size": cfg.beam_size,
        "batched": cfg.batched,
        "batch_size": cfg.batch_size,
        "condition_on_previous_text": cfg.condition_on_previous_text,
        "initial_prompt": cfg.initial_prompt,
        "window_s": cfg.window_s,
        "vad": cfg.vad.model_dump(),
        "batch": cfg.batch.model_dump(),
        "smoke_seconds": smoke,
        "filter_prompt_leak": cfg.filter_prompt_leak,
        "filter_repeats": cfg.filter_repeats,
    }


def load_state(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_state(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = dict(payload)
    payload["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _count_lines(path: Path) -> int:
    if not path.is_file():
        return 0
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        return sum(1 for _ in fh)


def run_transcribe(
    ws: Workspace,
    cfg: Config,
    audio: Path,
    group: str | None = None,
    force: bool = False,
    smoke: int | None = None,
    progress_cb: Callable[[dict[str, Any]], None] | None = None,
    part_tag: str | None = None,
) -> dict[str, Any]:
    from trpg_agent.adapters import get_asr_engine, probe_audio

    audio = audio.resolve()
    if not audio.is_file():
        raise FileNotFoundError(f"音频不存在: {audio}")
    group = group or group_from_audio(audio)
    smoke_s = int(smoke if smoke is not None else cfg.asr.smoke_seconds or 0)
    out_path = out_path_for(ws, cfg, group, part_tag)
    st_path = state_path_for(ws, group, part_tag)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    meta = probe_audio(cfg.asr.engine, audio)
    duration = float(meta.get("duration_s") or 0)
    fp_audio = audio_fingerprint(audio)
    fp_params = params_fingerprint(cfg.asr, smoke_s)

    prev = load_state(st_path)
    resume: dict[str, Any] | None = None
    done_segments = 0
    resume_offset: int | None = None
    if (
        prev
        and not force
        and prev.get("audio") == fp_audio
        and prev.get("params") == fp_params
        and out_path.is_file()
    ):
        resume = prev.get("next") or None
        done_segments = int(prev.get("segments") or 0)
        resume_offset = prev.get("resume_offset")
        if resume and (resume.get("window_index") or resume.get("batch_index")):
            log.ok(
                f"检测到断点: 从窗口 {resume.get('window_index')} / 批 {resume.get('batch_index')} 续跑 "
                f"(已完成 {done_segments} 段)"
            )
        else:
            resume = None
        if resume is not None and prev.get("resume_offset") is None:
            # 旧版断点没有偏移信息: 无法安全截断(该批可能已写了一半) -> 宁可重跑
            log.warn("断点缺少字节偏移信息(旧版本产物), 为保证不出现重复行, 从头重跑")
            resume = None
    if resume is None:
        if out_path.exists():
            log.warn(f"重新开始转写, 覆盖旧产物: {ws.rel(out_path)}")
        out_path.write_text("", encoding="utf-8")
        done_segments = 0
        resume_offset = None
    elif resume_offset is not None:
        # 截断到上一个批的起点: 该批会完整重做, 不留下半截内容
        size = out_path.stat().st_size
        if resume_offset > size:
            log.warn(f"断点偏移 {resume_offset} 大于产物大小 {size}, 从 0 开始")
            resume_offset = 0
        if resume_offset < size:
            with open(out_path, "r+b") as fh:
                fh.truncate(resume_offset)
            log.warn(f"已截断产物到断点偏移 {resume_offset} 字节(该批将重做, 避免重复行)")

    log.kv_table(
        f"转写 [{group}]",
        [
            ("音频", f"{ws.rel(audio)} ({meta.get('codec')} {meta.get('sample_rate')}Hz {meta.get('channels')}ch)"),
            ("时长", f"{duration/3600:.2f} 小时 ({duration/60:.1f} 分钟)" if duration else "未知"),
            ("模型", f"{cfg.asr.model_path or 'small'} / {cfg.asr.device} / {cfg.asr.compute_type}"),
            ("窗口", f"{cfg.asr.window_s}s  批上限 语音{cfg.asr.batch.max_speech_s}s 跨度{cfg.asr.batch.max_span_s}s"),
            ("输出", ws.rel(out_path)),
            ("断点文件", ws.rel(st_path)),
            ("冒烟", f"前 {smoke_s} 秒" if smoke_s else "全量"),
        ]
        + ([("多录音分片", part_tag)] if part_tag else []),
    )

    engine = get_asr_engine(cfg.asr.engine)
    t0 = time.time()
    segments = done_segments
    qf = QualityFilter(
        initial_prompt=cfg.asr.initial_prompt,
        filter_leak=cfg.asr.filter_prompt_leak,
        filter_repeats=cfg.asr.filter_repeats,
        similarity_threshold=cfg.asr.leak_similarity,
    )
    last_state = {"window_index": 0, "batch_index": 0}
    final: dict[str, Any] = {}
    state_payload = {
        "group": group, "audio": fp_audio, "params": fp_params,
        "out": ws.rel(out_path), "next": resume or {"window_index": 0, "batch_index": 0},
        "segments": segments, "audio_at_s": 0.0, "status": "running",
    }
    save_state(st_path, state_payload)

    try:
        with open(out_path, "a", encoding="utf-8") as fh:
            for ev in engine.iter_events(audio, cfg.asr, resume=resume, smoke_seconds=smoke_s):
                kind = ev["kind"]
                if kind == "batch_start":
                    # 记录本批起点的字节偏移; 半途崩溃后续跑会截断到这里重做整批,
                    # 避免"部分写入的批 + 重跑整批"造成重复行。
                    state_payload.update(
                        {"resume_offset": fh.tell(), "segments": segments,
                         "next": {"window_index": ev["window"], "batch_index": ev["batch"]}}
                    )
                    save_state(st_path, state_payload)
                    last_state = {"window_index": ev["window"], "batch_index": ev["batch"]}
                    continue
                if kind == "chunk":
                    if not qf.accept(ev["start"], ev["text"]):
                        continue
                    fh.write(f"[{ev['start']:07.2f} -> {ev['end']:07.2f}] {ev['text']}\n")
                    fh.flush()
                    segments += 1
                    if segments % max(1, cfg.asr.state_every) == 0:
                        state_payload.update(
                            {"segments": segments, "audio_at_s": round(ev["end"], 1),
                             "next": last_state}
                        )
                        save_state(st_path, state_payload)
                        log.info(
                            f"进度: {segments} 段, 音频至 {ev['end']/60:.1f} 分钟 "
                            f"(窗口 {last_state['window_index']}, 已用 {(time.time()-t0)/60:.1f} 分钟)"
                        )
                elif kind == "model_loaded":
                    extra = ""
                    if ev.get("cuda_dll_dirs"):
                        extra += f"  cuda_dll={len(ev['cuda_dll_dirs'])} 个目录"
                    if ev.get("batched"):
                        extra += f"  批式推理 batch={cfg.asr.batch_size}"
                    log.ok(f"模型加载完成 {ev['seconds']}s ({ev.get('model')}){extra}")
                elif kind == "window":
                    log.info(
                        f"窗口 {ev['window']} (起 {ev['base_s']/60:.0f} 分钟): "
                        f"{ev['speech_chunks']} 个语音块 -> {ev['batches']} 批 / 语音 {ev['speech_s']/60:.1f} 分钟"
                    )
                elif kind == "batch":
                    if ev.get("skipped"):
                        continue
                    bc = ev.get("batch_count") or 1
                    nxt = (
                        {"window_index": ev["window"], "batch_index": ev["batch"] + 1}
                        if ev["batch"] + 1 < bc
                        else {"window_index": ev["window"] + 1, "batch_index": 0}
                    )
                    last_state = nxt
                    state_payload.update(
                        {"segments": segments, "audio_at_s": round(ev.get("audio_at") or 0, 1), "next": nxt}
                    )
                    save_state(st_path, state_payload)
                    if progress_cb:
                        progress_cb(
                            {"segments": segments, "audio_at_s": state_payload["audio_at_s"],
                             "window": ev["window"], "batch": ev["batch"], "batch_count": bc,
                             "duration_s": duration}
                        )
                elif kind == "window_done":
                    last_state = {"window_index": ev["window"] + 1, "batch_index": 0}
                    state_payload.update({"segments": segments, "next": last_state})
                    save_state(st_path, state_payload)
                elif kind == "fill":
                    # 窗口填充期进度: 长窗口否则会静默十几分钟
                    log.info(
                        f"解码中: 已解码 {ev['decoded_s']/60:.1f} 分钟 "
                        f"(窗口 {ev['window']} 填充 {ev['percent_fill']}%)"
                    )
                    if progress_cb:
                        progress_cb(
                            {"segments": segments, "audio_at_s": ev["decoded_s"],
                             "duration_s": duration, "phase": "decode"}
                        )
                elif kind == "warn":
                    log.warn(ev.get("message", ""))
                elif kind == "done":
                    final = ev
    except KeyboardInterrupt:
        state_payload.update({"segments": segments, "next": last_state, "status": "interrupted"})
        save_state(st_path, state_payload)
        log.warn(f"已中断。再跑同一条命令会从窗口 {last_state['window_index']} 续跑")
        raise

    elapsed = time.time() - t0
    state_payload.update({"segments": segments, "next": last_state, "status": "done",
                          "audio_at_s": round(final.get("audio_s") or 0, 1),
                          "quality": qf.summary()})
    save_state(st_path, state_payload)
    total = int(final.get("audio_s") or duration or 0)
    for line in qf.render():
        log.info(line)
    log.ok(
        f"[{group}] 转写完成: {segments} 段 / 音频 {total/3600:.2f} 小时 / "
        f"语音 {final.get('speech_s', 0)/3600:.2f} 小时 / 耗时 {elapsed/60:.1f} 分钟 "
        f"({elapsed/max(total,1):.3f}x 实时)"
        + ("（冒烟模式, 已截断）" if final.get("truncated") else "")
    )
    return {
        "group": group,
        "audio": str(audio),
        "out": ws.rel(out_path),
        "state": ws.rel(st_path),
        "part_tag": part_tag,
        "segments": segments,
        "audio_s": total,
        "speech_s": final.get("speech_s", 0),
        "elapsed_s": round(elapsed, 1),
        "realtime_factor": round(elapsed / max(total, 1), 3),
        "truncated": bool(final.get("truncated")),
        "resumed_from": resume,
        "quality": qf.summary(),
    }
