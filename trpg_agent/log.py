# -*- coding: utf-8 -*-
"""控制台 + 文件双写日志。所有模块统一从这里输出, 保证可观测性。"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.table import Table

# Windows 控制台默认 GBK, 强制 UTF-8 避免中文乱码/崩溃
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # pragma: no cover
        pass

console = Console(highlight=False, soft_wrap=False)

_LOG_FILE: Path | None = None


def bind_log_file(path: Path) -> Path:
    """把日志同时落盘到 <work>/logs/<name>.log。"""
    global _LOG_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    _LOG_FILE = path
    return path


def _file_write(level: str, msg: str) -> None:
    if _LOG_FILE is None:
        return
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(f"{stamp} [{level}] {msg}\n")
    except OSError:
        pass


def step(msg: str) -> None:
    console.rule(f"[bold cyan]{msg}", align="left")
    _file_write("STEP", msg)


def info(msg: str) -> None:
    console.print(msg)
    _file_write("INFO", msg)


def ok(msg: str) -> None:
    console.print(f"[green]OK[/green] {msg}")
    _file_write("OK", msg)


def warn(msg: str) -> None:
    console.print(f"[yellow]WARN[/yellow] {msg}")
    _file_write("WARN", msg)


def err(msg: str) -> None:
    console.print(f"[red]ERR[/red] {msg}")
    _file_write("ERROR", msg)


def kv_table(title: str, rows: list[tuple[Any, Any]]) -> None:
    table = Table(title=title, show_header=False, box=None)
    table.add_column(style="dim")
    table.add_column(style="bold")
    for k, v in rows:
        table.add_row(str(k), str(v))
    console.print(table)
    _file_write("TABLE", title + " | " + "; ".join(f"{k}={v}" for k, v in rows))
