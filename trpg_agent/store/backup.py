# -*- coding: utf-8 -*-
"""写前备份: 沿用既有约定 <name>.bak_<stage>_<YYYYmmdd_HHMMSS>, 并按保留数清理。"""
from __future__ import annotations

import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Iterable

BAK_RE = re.compile(r"\.bak_")


def backup_path_for(path: Path, stage: str, when: datetime | None = None) -> Path:
    stamp = (when or datetime.now()).strftime("%Y%m%d_%H%M%S")
    return path.with_name(f"{path.name}.bak_{stage}_{stamp}")


def backup_file(path: Path, stage: str, keep: int = 10) -> Path | None:
    """备份单个数据文件; 不存在则跳过。返回备份路径。"""
    if not path.is_file():
        return None
    dst = backup_path_for(path, stage)
    shutil.copy2(path, dst)
    if keep > 0:
        prune_backups(path, keep)
    return dst


def list_backups(path: Path) -> list[Path]:
    parent = path.parent
    if not parent.is_dir():
        return []
    return sorted(
        (p for p in parent.iterdir() if p.is_file() and p.name.startswith(path.name + ".bak_")),
        key=lambda p: p.name,
    )


def prune_backups(path: Path, keep: int) -> list[Path]:
    """保留最近 keep 个备份, 返回被删除的列表。"""
    baks = list_backups(path)
    if keep <= 0 or len(baks) <= keep:
        return []
    removed = []
    for old in baks[:-keep]:
        try:
            old.unlink()
            removed.append(old)
        except OSError:
            pass
    return removed


def backup_many(paths: Iterable[Path], stage: str, keep: int = 10) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in paths:
        dst = backup_file(p, stage, keep)
        if dst:
            out[str(p)] = str(dst)
    return out
