# -*- coding: utf-8 -*-
"""步骤状态 + 输入指纹: 实现"产物即状态 / 可单独重跑 / 幂等跳过"。

每个步骤写 <work>/state/<step>.json:
    {step, status, input_hash, started, finished, outputs[], message, extra{}}
input_hash 由该步全部输入(路径+内容指纹)算得; 不变则默认跳过执行(--force 强制)。
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from trpg_agent.workspace import Workspace

HASH_CHUNK = 1 << 20


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        while True:
            block = fh.read(HASH_CHUNK)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_json(obj: Any) -> str:
    return sha256_text(json.dumps(obj, ensure_ascii=False, sort_keys=True))


def combine_hash(items: Iterable[tuple[str, str]]) -> str:
    """把 [(标签, 指纹)] 合成一个稳定指纹。"""
    h = hashlib.sha256()
    for label, digest in sorted(items):
        h.update(label.encode("utf-8"))
        h.update(b"\x00")
        h.update(digest.encode("utf-8"))
        h.update(b"\x01")
    return h.hexdigest()[:32]


def _now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class StepState:
    def __init__(self, ws: Workspace, step: str):
        self.ws = ws
        self.step = step
        self.path = ws.state / f"{step}.json"
        self.data: dict[str, Any] = {}
        if self.path.is_file():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                self.data = {}

    @property
    def input_hash(self) -> str | None:
        return self.data.get("input_hash")

    @property
    def status(self) -> str:
        return self.data.get("status", "none")

    def is_fresh(self, input_hash: str) -> bool:
        return self.status == "done" and self.input_hash == input_hash

    def start(self, input_hash: str, extra: dict[str, Any] | None = None) -> None:
        self.data = {
            "step": self.step,
            "status": "running",
            "input_hash": input_hash,
            "started": _now(),
            "finished": None,
            "outputs": [],
            "message": "",
            "extra": extra or {},
        }
        self.save()

    def finish(self, outputs: list[str] | None = None, message: str = "", extra: dict[str, Any] | None = None) -> None:
        self.data["status"] = "done"
        self.data["finished"] = _now()
        self.data["outputs"] = outputs or []
        self.data["message"] = message
        if extra:
            self.data.setdefault("extra", {}).update(extra)
        self.save()

    def fail(self, message: str) -> None:
        self.data["status"] = "failed"
        self.data["finished"] = _now()
        self.data["message"] = message
        self.save()

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def all_states(ws: Workspace) -> dict[str, StepState]:
    order = [
        "ingest", "transcribe", "segment", "extract",
        "review", "store", "visualize", "export", "housekeep",
    ]
    return {s: StepState(ws, s) for s in order}
