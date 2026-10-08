# -*- coding: utf-8 -*-
"""faster-whisper 窗口化稳健转写。

为什么要窗口化(而不是整段 decode + 一次性 transcribe):
    transcribe_s05.py 的教训 —— faster-whisper 会对传入音频一次性做 STFT,
    7.3h 音频在 16GB 机器上需要 ~7.6GiB 数组, 直接 OOM。
    这里改为: 顺序流式解码 -> 每 window_s 秒切一个窗口(默认 30 分钟, 内存约 115MB)
    -> 窗口内 VAD 找语音块 -> 贪心合并成批(语音 ≤ max_speech_s, 跨度 ≤ max_span_s)
    -> 逐批 transcribe -> 时间戳平移回全文件时间轴。

事件流(生成器 yield 的 dict, 由上层负责落盘/状态/进度):
    model_loaded / window / batch / chunk / window_done / done
"""
from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path
from typing import Any, Iterator

import av
import numpy as np

from trpg_agent.config import AsrCfg

SR = 16000
FILL_REPORT_S = 300  # 窗口填充期每 N 秒音频报一次进度
# 转写逻辑版本: 参与断点参数指纹, 算法变更后旧断点自动失效
ASR_LOGIC_VERSION = 4


def probe_audio(path: Path | str) -> dict[str, Any]:
    """只看容器元数据, 不解码。"""
    with av.open(str(path), mode="r", metadata_errors="ignore") as container:
        stream = container.streams.audio[0]
        duration = None
        if stream.duration and stream.time_base:
            duration = float(stream.duration * stream.time_base)
        elif container.duration:
            duration = container.duration / av.time_base
        return {
            "path": str(path),
            "codec": stream.codec_context.name,
            "sample_rate": stream.sample_rate,
            "channels": stream.channels,
            "duration_s": duration or 0.0,
        }


def merge_batches(chunks: list[dict], cfg: AsrCfg) -> list[tuple[int, int]]:
    """把 VAD 语音块贪心合并成批。"""
    batches: list[tuple[int, int]] = []
    cur_s: int | None = None
    cur_e = 0
    cur_speech = 0.0
    for ch in chunks:
        s, e = int(ch["start"]), int(ch["end"])
        if cur_s is None:
            cur_s, cur_e, cur_speech = s, e, (e - s) / SR
            continue
        gap = (s - cur_e) / SR
        span = (e - cur_s) / SR
        if (
            cur_speech + (e - s) / SR > cfg.batch.max_speech_s
            or span > cfg.batch.max_span_s
            or gap > cfg.vad.gap_break_s
        ):
            batches.append((cur_s, cur_e))
            cur_s, cur_e, cur_speech = s, e, (e - s) / SR
        else:
            cur_e = e
            cur_speech += (e - s) / SR
    if cur_s is not None:
        batches.append((cur_s, cur_e))
    return batches


def cuda_dll_dirs() -> list[str]:
    """找出 pip 装的 CUDA 运行库目录(nvidia-cublas-cu12 / nvidia-cudnn-cu12)。

    为什么要它: 本机没有 CUDA Toolkit, 而 ctranslate2 在 Windows 上是
    `LoadLibrary("cublas64_12.dll")` 按名字加载 —— DLL 不在 PATH 上就报
    "Library cublas64_12.dll is not found or cannot be loaded"(实测踩到, 2026-10-05)。
    nvidia-* wheel 把 DLL 放在 site-packages/nvidia/<pkg>/bin, 默认不在搜索路径里。

    可用环境变量 ASR_CUDA_DLL_DIRS 追加/覆盖(os.pathsep 分隔), 用于救急。
    """
    seen: dict[str, None] = {}
    for entry in list(sys.path):
        if not entry:
            continue
        nv = Path(entry) / "nvidia"
        if not nv.is_dir():
            continue
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc", "cufft"):
            d = nv / sub / "bin"
            if d.is_dir():
                seen[str(d)] = None
    extra = os.environ.get("ASR_CUDA_DLL_DIRS", "")
    for part in extra.split(os.pathsep):
        if part and Path(part).is_dir():
            seen[part] = None
    return list(seen)


def _prepare_cuda_dll_search() -> list[str]:
    """把 CUDA 运行库目录塞进本进程的 DLL 搜索路径(Linux 上无操作)。"""
    if os.name != "nt":
        return []
    dirs = cuda_dll_dirs()
    if not dirs:
        return []
    if hasattr(os, "add_dll_directory"):
        for d in dirs:
            try:
                os.add_dll_directory(d)
            except OSError:
                pass
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join(dirs + ([path] if path else []))
    return dirs


def _load_model(cfg: AsrCfg):
    from faster_whisper import WhisperModel

    target = cfg.model_path or "small"
    return WhisperModel(
        target, device=cfg.device, compute_type=cfg.compute_type, cpu_threads=cfg.cpu_threads
    )


def _load_batched(model: Any, cfg: AsrCfg):
    """批式推理包装(可选)。失败就退回逐批推理, 不让一个优化点毁掉整段转写。"""
    if not cfg.batched:
        return None
    try:
        from faster_whisper import BatchedInferencePipeline

        return BatchedInferencePipeline(model=model)
    except Exception:  # noqa: BLE001
        return None


def _transcribe_batch(engine: Any, model: Any, pcm: "np.ndarray", cfg: AsrCfg,
                      clips: list[dict[str, float]] | None = None):
    """返回 (segments_iter, info)。engine 非空时走 BatchedInferencePipeline。

    ⚠️ 批式管线的 clip_timestamps 语义(实测源码 faster_whisper/transcribe.py:396-451):
       每个 clip 只取前 30 秒 —— 所以必须把 VAD 语音块(本身都远短于 30s)逐块喂进去,
       不能塞一整段长音频。传了 clip_timestamps 就走 VAD 分支被忽略。
    """
    kwargs: dict[str, Any] = {
        "language": cfg.language,
        "beam_size": cfg.beam_size,
        "initial_prompt": cfg.initial_prompt or None,
    }
    if engine is not None:
        if clips:
            kwargs["vad_filter"] = False
            kwargs["clip_timestamps"] = clips
        else:
            kwargs["vad_filter"] = True
        # ⚠️ 批式管线用 clip_timestamps 时, 每个 clip 只解码前 30 秒(源码 transcribe.py:438);
        #    长于 30s 的 VAD 语音块会被截断丢内容 —— 本机实测该管线整体劣于逐批推理,
        #    见 config.py 里 asr.batched 的注释。这里保留实现只为将来换硬件再试。
        return engine.transcribe(
            pcm, batch_size=max(1, int(cfg.batch_size)),
            condition_on_previous_text=False, **kwargs,
        )
    return model.transcribe(
        pcm, vad_filter=False,
        condition_on_previous_text=cfg.condition_on_previous_text, **kwargs,
    )


def iter_events(
    audio_path: Path | str,
    cfg: AsrCfg,
    resume: dict[str, Any] | None = None,
    smoke_seconds: int = 0,
) -> Iterator[dict[str, Any]]:
    from faster_whisper.vad import VadOptions, get_speech_timestamps

    audio_path = Path(audio_path)
    resume = resume or {}
    use_resume = bool(cfg.resume and resume)
    resume_window = int(resume.get("window_index") or 0) if use_resume else 0
    resume_batch = int(resume.get("batch_index") or 0) if use_resume else 0

    t_model = time.time()
    dll_dirs = _prepare_cuda_dll_search() if str(cfg.device).startswith("cuda") else []
    model = _load_model(cfg)
    engine = _load_batched(model, cfg)
    yield {
        "kind": "model_loaded",
        "seconds": round(time.time() - t_model, 1),
        "model": cfg.model_path,
        "cuda_dll_dirs": dll_dirs,
        "batched": engine is not None,
    }

    window_s = max(60, int(cfg.window_s))
    window_samples = window_s * SR
    limit_samples = int(smoke_seconds * SR) if smoke_seconds and smoke_seconds > 0 else 0

    vad_params = VadOptions(
        min_silence_duration_ms=cfg.vad.min_silence_ms,
        speech_pad_ms=cfg.vad.speech_pad_ms,
    )

    container = av.open(str(audio_path), mode="r", metadata_errors="ignore")
    stream = container.streams.audio[0]
    start_window = resume_window if (use_resume and cfg.seek_on_resume and resume_window > 0) else 0
    if start_window > 0:
        try:
            container.seek(int(start_window * window_s * av.time_base), backward=True)
        except (OSError, ValueError) as e:
            yield {"kind": "warn", "message": f"seek 失败, 从头解码跳过已转录部分: {e}"}
            start_window = 0

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SR)
    # ⚠️ 预分配窗口缓冲, 逐帧写入。
    #    早期版本用 np.concatenate([buf, frame]) 逐帧拼接, 是 O(n²):
    #    1800s 窗口 8.4 万帧 -> 累计拷贝 TB 级内存, 首窗要 20 分钟才出来。
    window = np.empty(window_samples, dtype=np.float32)
    fill = 0
    window_index = start_window
    # 续跑时会 seek 到窗口起点, 所以"已解码样本数"要从绝对位置起算;
    # 否则进度百分比从 0 重算(实测: 已到窗口 11 却显示 6.6%)。
    decoded_samples = start_window * window_s * SR
    segments = 0
    speech_total = 0.0
    last_report = 0.0
    t_start = time.time()
    truncated = False

    def process_window(w: np.ndarray, widx: int, skip: bool) -> Iterator[dict[str, Any]]:
        nonlocal speech_total
        base_s = widx * window_s
        if skip:
            yield {"kind": "window_done", "window": widx, "batches": 0, "speech_s": 0.0, "skipped": True}
            return
        chunks = get_speech_timestamps(w, vad_params)
        batches = merge_batches(chunks, cfg)
        yield {
            "kind": "window", "window": widx, "base_s": base_s,
            "speech_chunks": len(chunks), "batches": len(batches),
            "speech_s": round(sum((c["end"] - c["start"]) for c in chunks) / SR, 1),
        }
        for bi, (bs, be) in enumerate(batches):
            if widx == resume_window and bi < resume_batch:
                yield {"kind": "batch", "window": widx, "batch": bi, "batch_count": len(batches),
                       "audio_at": base_s + be / SR, "skipped": True}
                continue
            seg_iter, _info = _transcribe_batch(
                engine, model, w[bs:be], cfg,
                clips=[
                    {"start": (c["start"] - bs) / SR, "end": (c["end"] - bs) / SR}
                    for c in chunks
                    if c["start"] >= bs and c["end"] <= be
                ],
            )
            # 批开始事件: 上层据此记录"该批开始时的输出文件字节偏移"。
            # 半途崩溃时, 续跑会先截断到该偏移, 避免同一批被追加两遍。
            yield {"kind": "batch_start", "window": widx, "batch": bi, "batch_count": len(batches)}
            batch_base = base_s + bs / SR
            for seg in seg_iter:
                text = (seg.text or "").strip()
                if not text:
                    continue
                yield {
                    "kind": "chunk",
                    "start": batch_base + seg.start,
                    "end": batch_base + seg.end,
                    "text": text,
                }
            del seg_iter
            yield {
                "kind": "batch", "window": widx, "batch": bi, "batch_count": len(batches),
                "audio_at": base_s + be / SR, "skipped": False,
            }
        speech_total += sum((c["end"] - c["start"]) for c in chunks) / SR
        yield {"kind": "window_done", "window": widx, "batches": len(batches), "skipped": False}

    # 解码容错: 音频文件尾部损坏时(实测某 6 小时录音最后 0.7 分钟),
    # container.decode() 迭代到坏包会抛 InvalidDataError。旧版直接让整段转写判失败,
    # 已经解码进内存的十几分钟音频被白白丢掉。现在: 坏包停手, 已解码部分照常出结果。
    # 注意: "一点都没解出来"仍然按失败抛出, 不允许静默产出空稿。
    decode_error: str | None = None
    try:
        frame_iter = container.decode(stream)
        while True:
            try:
                frame = next(frame_iter)
            except StopIteration:
                break
            except MemoryError:
                raise
            except Exception as e:  # noqa: BLE001 — av 的 InvalidDataError 等
                if decoded_samples <= 0 and fill == 0:
                    raise
                decode_error = f"{type(e).__name__}: {e}"
                break
            frame.pts = None
            resampled = resampler.resample(frame)
            if resampled is None:
                continue
            frames = resampled if isinstance(resampled, list) else [resampled]
            for f in frames:
                arr = f.to_ndarray()
                flat = arr.reshape(-1)
                n = flat.shape[0]
                decoded_samples += n
                pos = 0
                while pos < n:
                    take = min(window_samples - fill, n - pos)
                    window[fill : fill + take] = flat[pos : pos + take].astype(np.float32) / 32768.0
                    fill += take
                    pos += take
                    if fill == window_samples:
                        yield from process_window(window, window_index, skip=window_index < resume_window)
                        window_index += 1
                        fill = 0
                        last_report = float(window_index * window_s * SR)
                    elif decoded_samples - last_report >= FILL_REPORT_S * SR:
                        # 窗口填充期的进度(避免长窗口"静默"十几分钟)
                        last_report = float(decoded_samples)
                        yield {"kind": "fill", "decoded_s": decoded_samples / SR,
                               "window": window_index, "percent_fill": round(100.0 * fill / window_samples, 1)}
            if limit_samples and decoded_samples >= limit_samples:
                truncated = True
                break
        if decode_error:
            yield {"kind": "warn",
                   "message": f"解码在文件尾部中断, 已保留到此为止的音频({decode_error})"}
        # 尾窗必须处理(冒烟模式下这就是唯一的窗口; 全量模式下是最后不足一个窗口的余量)
        if fill > int(SR * 0.5):
            yield from process_window(window[:fill], window_index, skip=window_index < resume_window)
            window_index += 1
    finally:
        container.close()
        del resampler
        gc.collect()

    total_samples = window_index * window_s * SR
    yield {
        "kind": "done",
        "segments": 0,  # 由上层统计
        "windows": window_index,
        "audio_s": decoded_samples / SR,
        "speech_s": round(speech_total, 1),
        "elapsed_s": round(time.time() - t_start, 1),
        "truncated": truncated,
        "decode_error": decode_error,
    }
