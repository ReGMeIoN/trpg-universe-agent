# -*- coding: utf-8 -*-
"""Workspace: 一个宇宙库的路径中枢 + 写保护。

目录约定
    <root>/素材/            原始素材(输入)
    <root>/数据/            characters|relations|players|pl_profiles.json(契约资产)
    <root>/产出/            可视化/KB 包等人读产物
    <root>/.trpg/           运行态: state/ jobs/ logs/ patches/ staging/ reports/ canon/
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from trpg_agent.config import Config


class ProductionWriteBlocked(RuntimeError):
    """对生产库的写操作被安全闸拦下。"""


@dataclass
class Workspace:
    root: Path
    data: Path
    output: Path
    material: Path
    work: Path
    # 运行态子目录
    state: Path
    jobs: Path
    logs: Path
    patches: Path
    staging: Path
    reports: Path
    canon: Path
    normalized: Path
    segments: Path
    cfg: Config

    @classmethod
    def from_config(cls, cfg: Config) -> "Workspace":
        w = cfg.workspace
        root = Path(w.root).expanduser().resolve()
        work = (root / w.work_dir).resolve()
        seg = Path(cfg.segment.out_dir)
        seg_abs = seg if seg.is_absolute() else (root / seg)
        return cls(
            root=root,
            data=(root / w.data_dir).resolve(),
            output=(root / w.output_dir).resolve(),
            material=(root / w.material_dir).resolve(),
            work=work,
            state=work / "state",
            jobs=work / "jobs",
            logs=work / "logs",
            patches=work / "patches",
            staging=work / "staging",
            reports=work / cfg.store.report_dir,
            canon=work / "canon",
            normalized=(work / cfg.ingest.normalized_dir).resolve(),
            segments=seg_abs.resolve(),
            cfg=cfg,
        )

    # ---------- 目录 ----------
    def ensure_dirs(self) -> None:
        for d in (
            self.root, self.data, self.output, self.material,
            self.work, self.state, self.jobs, self.logs,
            self.patches, self.staging, self.reports, self.canon,
            self.normalized, self.segments,
        ):
            d.mkdir(parents=True, exist_ok=True)

    # ---------- 展示 ----------
    def rel(self, p: Path | str) -> str:
        p = Path(p)
        try:
            return str(p.resolve().relative_to(self.root)).replace("\\", "/")
        except (ValueError, OSError):
            return str(p)

    # ---------- 安全闸 ----------
    @property
    def is_production(self) -> bool:
        prod = self.cfg.workspace.production_root
        if not prod:
            return False
        try:
            return Path(prod).expanduser().resolve() == self.root
        except OSError:
            return False

    def guard_write(self, what: str) -> None:
        """对生产库的破坏性写入必须显式授权。"""
        if not self.is_production:
            return
        if self.cfg.workspace.allow_production_write:
            return
        raise ProductionWriteBlocked(
            f"拒绝写入生产库 {self.root} ({what})。\n"
            f"  这是防止误改既有 137 角色/128 关系数据的保险。\n"
            f"  确认要写入请二选一:\n"
            f"    1) 加参数 --allow-production\n"
            f"    2) 在 config.yaml 设 workspace.allow_production_write: true"
        )

    def data_file(self, kind: str) -> Path:
        return self.data / f"{kind}.json"
