# -*- coding: utf-8 -*-
"""Wait until a group's transcription state files all report status=done.

Why: transcription of a multi-recording group runs for hours; a watcher job that exits
the moment the work is finished is cheaper than polling the harness every few minutes.
Also exits early (rc=1) when the log stops growing for STALL_MIN minutes, so a hung run
does not silently eat the whole night.

usage: python tools/_wait_transcribe.py --group "魔法少女育成计划 6" [--log <log>] [--hours 5]
"""
from __future__ import annotations

import os
import argparse
import json
import sys
import time
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
STATE = WS / ".trpg" / "state"
STALL_MIN = 25


def states_for(group: str) -> list[dict]:
    out = []
    for p in STATE.glob("transcribe_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("group") == group:
            d["_file"] = p.name
            out.append(d)
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--log", default=None)
    ap.add_argument("--hours", type=float, default=5.0)
    ap.add_argument("--expect", type=int, default=0, help="预期录音数(0=不校验)")
    args = ap.parse_args()

    log = Path(args.log) if args.log else None
    deadline = time.time() + args.hours * 3600
    last_size = -1
    last_change = time.time()
    while time.time() < deadline:
        st = states_for(args.group)
        done = [s for s in st if s.get("status") == "done"]
        running = [s for s in st if s.get("status") == "running"]
        ok_count = args.expect and len(st) >= args.expect
        if st and not running and (ok_count or not args.expect):
            for s in sorted(st, key=lambda x: x["_file"]):
                print(f"DONE {s['_file']} segments={s.get('segments')} "
                      f"audio_at={round(float(s.get('audio_at_s') or 0)/60,1)}min")
            print(f"ALL DONE ({len(done)} 个录音)")
            return 0
        if log and log.is_file():
            size = log.stat().st_size
            if size != last_size:
                last_size = size
                last_change = time.time()
            elif (time.time() - last_change) / 60 > STALL_MIN:
                print(f"STALL: 日志 {STALL_MIN} 分钟没增长，可能已卡死: {log}")
                for s in st:
                    print(f"  {s['_file']}: status={s.get('status')} "
                          f"next={s.get('next')} segments={s.get('segments')}")
                return 1
        time.sleep(60)
    print("TIMEOUT: 超过等待上限仍未完成")
    for s in states_for(args.group):
        print(f"  {s['_file']}: status={s.get('status')} next={s.get('next')}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
