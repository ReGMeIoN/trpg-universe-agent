# -*- coding: utf-8 -*-
"""One-shot ASR config benchmark on the head of a real recording.

usage:  python tools/_asr_bench.py <config> [seconds]
config: f16b5 | f16b1 | i8b5 | f16b5_b8 | f16b5_b16 | i8b5_b8

Prints a wall-clock throughput line plus the first few decoded lines so quality
can be eyeballed. One config per process (keeps VRAM accounting honest).
"""
from __future__ import annotations

import gc
import os
import sys
import time
from pathlib import Path

import numpy as np

MODEL = '<工作区>/素材/_whisper_models/large-v3'
AUDIO = (
    '<工作区>/素材'
    "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08\\"
    "\u5b9d\u53ef\u68a6\u5927\u5e08\u4e0e\u7267\u9b42\u4eba\u4e0e\u795e\u79d8\u6d32\u533a"
    "\u4e0e\u6c14\u529f\u5927\u5e08\u4e0e\u52a0\u6cb9\u5973\u4e0e\u591c\u9b54\u4fa0"
    "\u4e0e\u5149\u5934\u7684\u5947\u5999\u5192\u9669.m4a"
)
PROMPT = (
    "\u4ee5\u4e0b\u662f\u666e\u901a\u8bdd\u7684\u8dd1\u56e2\u6e38\u620f\u5bf9\u8bdd\u8bb0\u5f55"
    "\uff0c\u5305\u542b\u4e3b\u6301\u4eba\u4e0e\u73a9\u5bb6\u7684\u89d2\u8272\u626e\u6f14\u53d1\u8a00\u3002"
)
SR = 16000


def _prepare() -> list[str]:
    """Same DLL search-path fixup the adapter does, minus the trpg_agent import."""
    dirs: list[str] = []
    for entry in sys.path:
        if not entry:
            continue
        nv = Path(entry) / "nvidia"
        if not nv.is_dir():
            continue
        for sub in ("cublas", "cudnn", "cuda_runtime", "cuda_nvrtc"):
            d = nv / sub / "bin"
            if d.is_dir():
                dirs.append(str(d))
    for d in dirs:
        try:
            os.add_dll_directory(d)
        except OSError:
            pass
    os.environ["PATH"] = os.pathsep.join(dirs + [os.environ.get("PATH", "")])
    return dirs


def read_pcm(seconds: int) -> np.ndarray:
    import av

    resampler = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=SR)
    out: list[np.ndarray] = []
    got = 0
    need = seconds * SR
    with av.open(AUDIO) as c:
        for frame in c.decode(c.streams.audio[0]):
            frame.pts = None
            r = resampler.resample(frame)
            if r is None:
                continue
            for f in (r if isinstance(r, list) else [r]):
                flat = f.to_ndarray().reshape(-1)
                out.append(flat)
                got += flat.shape[0]
            if got >= need:
                break
    pcm = np.concatenate(out)[:need].astype(np.float32) / 32768.0
    return pcm


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    cfg = sys.argv[1] if len(sys.argv) > 1 else "f16b5"
    seconds = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    _prepare()

    from faster_whisper import BatchedInferencePipeline, WhisperModel

    compute = "int8_float16" if cfg.startswith("i8") else "float16"
    beam = 1 if cfg.startswith("f16b1") else 5
    batch = 0
    if "_b" in cfg.split("b")[-1]:
        batch = int(cfg.split("_b")[-1])

    t0 = time.time()
    model = WhisperModel(MODEL, device="cuda", compute_type=compute, cpu_threads=8)
    t_load = time.time() - t0
    pcm = read_pcm(seconds)
    print(f"cfg={cfg} compute={compute} beam={beam} batch={batch} audio={len(pcm)/SR:.0f}s load={t_load:.1f}s", flush=True)

    t0 = time.time()
    if batch:
        pipe = BatchedInferencePipeline(model=model)
        it, info = pipe.transcribe(
            pcm, language="zh", beam_size=beam, batch_size=batch,
            initial_prompt=PROMPT, vad_filter=False, condition_on_previous_text=False,
        )
    else:
        it, info = model.transcribe(
            pcm, language="zh", beam_size=beam, vad_filter=False, initial_prompt=PROMPT,
        )
    segs = []
    for s in it:
        segs.append((s.start, s.end, s.text.strip()))
    el = time.time() - t0
    print(f"RESULT cfg={cfg} elapsed={el:.1f}s realtime_factor={el/(len(pcm)/SR):.3f} segs={len(segs)}", flush=True)
    for st, en, tx in segs[:6]:
        print(f"  [{st:7.2f}] {tx}", flush=True)
    del model, it, segs
    gc.collect()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
