# -*- coding: utf-8 -*-
"""给站点的每个剧情小节切一段原声（低码率 mono mp3）。

- 时间戳从 site/data/story.json 的 section.time 取；段1–3 是 MM:SS，段4–6 是 H:MM（编年史口径）
- 输出 site/assets/audio/<key>.mp3（24kHz mono 48kbps，约 26 秒 ≈ 150KB）

用法:
    .venv\\Scripts\\python.exe tools\\build_audio.py            # 全部
    .venv\\Scripts\\python.exe tools\\build_audio.py --only 段6  # 只补某段
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

SITE = ROOT / "site"
AUDIO = Path(os.environ.get("TRPG_WS", "workspace") / '素材' / '圣剑英雄谭.mp3')
CLIP_S = 26.0
RATE = 24000


def to_seconds(seg_tag: str, stamp: str) -> float | None:
    m = re.match(r"^(\d{1,3}):(\d{2})$", (stamp or "").strip())
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    seg_no = int(re.sub(r"\D", "", seg_tag) or "1")
    if seg_no >= 4:          # 段4–6 的编年史口径是 H:MM
        return a * 3600 + b * 60
    return a * 60 + b        # 段1–3 是 MM:SS


def clip(src: Path, start: float, dst: Path) -> bool:
    import av

    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with av.open(str(src)) as inp:
            st = inp.streams.audio[0]
            inp.seek(int(max(0.0, start) * 1_000_000), backward=True)
            out = av.open(str(dst), mode="w", format="mp3")
            ost = out.add_stream("mp3", rate=RATE, layout="mono", bit_rate=48000)
            res = av.audio.resampler.AudioResampler(format="s16", layout="mono", rate=RATE)
            end = start + CLIP_S
            for frame in inp.decode(st):
                t = frame.time
                if t is None:
                    continue
                if t > end:
                    break
                if t + frame.samples / st.rate < start:
                    continue
                got = res.resample(frame)
                for rf in (got if isinstance(got, list) else [got]):
                    if rf is None:
                        continue
                    for pkt in ost.encode(rf):
                        out.mux(pkt)
            for pkt in ost.encode(None):
                out.mux(pkt)
            out.close()
        return dst.is_file() and dst.stat().st_size > 2000
    except Exception as e:  # noqa: BLE001
        print(f"    !! {dst.name}: {type(e).__name__}: {e}")
        return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只处理某段（如 段6）")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    story = json.loads((SITE / "data" / "story.json").read_text(encoding="utf-8"))
    ok = skip = fail = 0
    total = 0
    for seg in story["segments"]:
        if args.only and args.only not in seg["tag"]:
            continue
        for s in seg["sections"]:
            key = s["key"]
            dst = SITE / "assets" / "audio" / f"{key}.mp3"
            if dst.is_file() and not args.force:
                skip += 1
                total += dst.stat().st_size
                continue
            sec = to_seconds(seg["tag"], s.get("time", ""))
            if sec is None:
                print(f"  ?? {key}: 时间戳无法解析 {s.get('time')!r}")
                continue
            if clip(AUDIO, sec, dst):
                ok += 1
                total += dst.stat().st_size
                print(f"  OK {key} @{int(sec)//60}:{int(sec)%60:02d} -> {dst.stat().st_size//1024} KB")
            else:
                fail += 1
    print(f"\n完成: 新切 {ok} / 已有 {skip} / 失败 {fail} · 合计 {total/1e6:.1f} MB -> {SITE/'assets'/'audio'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
