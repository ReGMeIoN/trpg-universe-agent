# -*- coding: utf-8 -*-
"""Probe an audio file with PyAV: duration + which timestamps fail to decode.

Usage:
    .venv\\Scripts\\python.exe tools\\_probe_audio.py <audio> [--at 20,340,355,360,365,370,375]
"""
from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    path = Path(args[0])
    minutes = [20, 340, 355, 358, 360, 362, 365, 370, 375]
    if "--at" in args:
        minutes = [float(x) for x in args[args.index("--at") + 1].split(",")]

    import av  # PyAV (faster-whisper dependency)

    print(f"file: {path}  size={path.stat().st_size}")
    try:
        container = av.open(str(path))
    except Exception as e:  # noqa: BLE001
        print(f"open failed: {type(e).__name__}: {e}")
        return 2
    print(f"format: {container.format.name}  duration: {container.duration}")
    for s in container.streams:
        print(f"  stream #{s.index} {s.type} codec={getattr(s.codec_context, 'name', '?')} "
              f"rate={getattr(s, 'rate', None)} channels={getattr(s.codec_context, 'channels', None)}")
    if container.duration:
        print(f"container duration: {container.duration / 1_000_000 / 60:.2f} min")

    if "--tail" in args:
        start = float(args[args.index("--tail") + 1])
        print(f"--- continuous decode from {start} min to EOF ---")
        stream = container.streams.audio[0]
        try:
            container.seek(int(start * 60 * 1_000_000), backward=True)
        except Exception as e:  # noqa: BLE001
            print(f"seek failed: {type(e).__name__}: {e}")
        count = 0
        last_s = None
        err = None
        try:
            for frame in container.decode(stream):
                count += 1
                if frame.pts is not None and frame.time_base:
                    last_s = float(frame.pts * frame.time_base)
        except Exception as e:  # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
        print(f"frames={count} last_frame_at={last_s if last_s is None else round(last_s / 60, 2)} min")
        print(f"error={err}")
        container.close()
        return 0

    for m in minutes:
        t = m * 60
        ok, note = True, ""
        try:
            container.seek(int(t * 1_000_000), backward=True)
            got = 0
            for frame in container.decode(audio=0):
                got += 1
                if got >= 5:
                    break
            if got == 0:
                ok, note = False, "no frames after seek"
        except Exception as e:  # noqa: BLE001
            ok, note = False, f"{type(e).__name__}: {e}"
        print(f"  {m:>6.1f} min  {'OK  ' if ok else 'FAIL'} {note}")
    container.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
