# -*- coding: utf-8 -*-
"""Download a faster-whisper model snapshot into the local model dir.

Pure-ASCII source on purpose: PowerShell 5.1 mangles inline CJK, so the target
path is built from unicode escapes instead of being typed literally.

usage:  python tools/_dl_whisper_model.py <repo_id> <local_subdir>
        python tools/_dl_whisper_model.py Systran/faster-whisper-large-v3 large-v3
"""
from __future__ import annotations

import os
import sys

MODELS_ROOT = (
    '<工作区>/素材/_whisper_models'
)

ALLOW = ["*.bin", "*.json", "*.txt", "*.md"]


def main() -> int:
    repo = sys.argv[1] if len(sys.argv) > 1 else "Systran/faster-whisper-large-v3"
    sub = sys.argv[2] if len(sys.argv) > 2 else "large-v3"
    target = f"{MODELS_ROOT}\\{sub}"
    print(f"repo   = {repo}")
    print(f"target = {target}", flush=True)

    from huggingface_hub import snapshot_download

    path = snapshot_download(
        repo_id=repo,
        local_dir=target,
        allow_patterns=ALLOW,
        max_workers=4,
    )
    print(f"DONE -> {path}", flush=True)

    import os

    total = 0
    for root, _dirs, files in os.walk(target):
        for f in files:
            total += os.path.getsize(os.path.join(root, f))
    print(f"size = {total / (1 << 20):.1f} MB", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
