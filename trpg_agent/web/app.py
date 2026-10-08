# -*- coding: utf-8 -*-
"""本地 Web 面板后端(FastAPI)。

设计原则:
- **薄壳**: 不新增业务逻辑, 全部复用 CLI 已有的模块(jobs / review / canon / 数据文件)。
- **默认只读**: 唯一的写操作是「启动任务」「保存裁决」; 回填数据必须显式传 apply=true。
- **本地优先**: 默认只绑 127.0.0.1; 路径一律校验落在工作区内; 绝不下发任何密钥。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from trpg_agent import __version__, jobs, log
from trpg_agent.config import Config
from trpg_agent.data_utils import char_groups, collect_groups, find_dirty_group_values
from trpg_agent.ingest import load_manifest
from trpg_agent.review import apply_decisions, collect as review_collect, decisions_path
from trpg_agent.segment import load_index
from trpg_agent.state import all_states
from trpg_agent.workspace import Workspace

WEB_DIR = Path(__file__).resolve().parent
DIST_DIR = WEB_DIR.parent.parent / "web" / "dist"

STEPS = ("ingest", "transcribe", "segment", "extract", "review", "store",
         "visualize", "export", "housekeep")


class JobRequest(BaseModel):
    step: str
    group: str | None = None
    apply: bool = False
    allow_production: bool = False
    force: bool = False
    smoke: int | None = None
    all_groups: bool = False
    base_url: str | None = None
    model: str | None = None


class DecisionItem(BaseModel):
    target: str | None = None
    index: int | None = None
    action: str
    note: str | None = None
    field: str | None = None
    value: Any = None
    canonical: str | None = None
    variant: str | None = None


class DecisionsBody(BaseModel):
    decisions: list[DecisionItem] = []


def _safe_path(ws: Workspace, rel: str) -> Path:
    """把相对路径解析到工作区内; 越界一律拒绝。"""
    p = (ws.root / rel).resolve()
    try:
        p.relative_to(ws.root.resolve())
    except ValueError as e:
        raise HTTPException(400, f"路径越界: {rel}") from e
    if not p.is_file():
        raise HTTPException(404, f"文件不存在: {rel}")
    return p


def _load_json(path: Path, default: Any = None) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, FileNotFoundError):
        return default


def _data_counts(ws: Workspace) -> dict[str, int]:
    out: dict[str, int] = {}
    for kind, key in (("characters", "characters"), ("relations", "relations"),
                      ("players", "players"), ("pl_profiles", "profiles")):
        doc = _load_json(ws.data_file(kind), {})
        out[kind] = len(doc.get(key, [])) if isinstance(doc, dict) else 0
    return out


def _group_rows(ws: Workspace) -> list[dict[str, Any]]:
    """团列表: 段数 / 补丁 / 报告 / 待确认数量 —— 面板首屏的核心数据。"""
    chars = (_load_json(ws.data_file("characters"), {}) or {}).get("characters", [])
    manifest = load_manifest(ws) or {}
    by_group: dict[str, dict[str, Any]] = {}

    def row(g: str) -> dict[str, Any]:
        return by_group.setdefault(g, {
            "group": g, "characters": 0, "segments": 0, "has_patch": False,
            "has_report": False, "pending": 0, "extracts": 0,
        })

    for g in collect_groups(chars):
        row(g)["characters"] = sum(1 for c in chars if g in char_groups(c))
    for g in manifest.get("groups", []):
        row(g)

    idx_dir = ws.work / "segments_index"
    if idx_dir.is_dir():
        for p in sorted(idx_dir.glob("*.json")):
            idx = _load_json(p, {}) or {}
            row(p.stem)["segments"] = len(idx.get("segments") or [])

    if ws.patches.is_dir():
        for p in sorted(ws.patches.glob("*_patch.json")):
            g = p.name[: -len("_patch.json")]
            row(g)["has_patch"] = True
            patch = _load_json(p, {}) or {}
            row(g)["pending"] = len(patch.get("pending") or [])

    if ws.reports.is_dir():
        for p in sorted(ws.reports.glob("*_入库报告.md")):
            row(p.name[: -len("_入库报告.md")])["has_report"] = True

    ex_dir = ws.work / "extracts"
    if ex_dir.is_dir():
        for g, r in by_group.items():
            r["extracts"] = len(list(ex_dir.glob(f"{g}_段*_提炼.md")))
    return sorted(by_group.values(), key=lambda r: (-r["segments"], r["group"]))


def create_app(cfg: Config, ws: Workspace, *, allow_write: bool = True) -> FastAPI:
    app = FastAPI(title="TRPG-Universe Agent", version=__version__)
    app.add_middleware(
        CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
        allow_methods=["*"], allow_headers=["*"],
    )
    state = {"cfg": cfg, "ws": ws, "allow_write": allow_write}

    # ---------------- 概览 ----------------
    @app.get("/api/workspace")
    def workspace_info() -> dict[str, Any]:
        return {
            "root": str(ws.root),
            "data": str(ws.data),
            "output": str(ws.output),
            "work": str(ws.work),
            "is_production": ws.is_production,
            "allow_production_write": cfg.workspace.allow_production_write,
            "writable": state["allow_write"],
            "version": __version__,
        }

    @app.get("/api/status")
    def status() -> dict[str, Any]:
        manifest = load_manifest(ws) or {}
        dirty = find_dirty_group_values(
            (_load_json(ws.data_file("characters"), {}) or {}).get("characters", [])
        )
        return {
            "counts": _data_counts(ws),
            "steps": {k: {"status": v.status, "message": v.data.get("message", "")}
                      for k, v in all_states(ws).items()},
            "manifest": {k: v for k, v in manifest.items() if k != "files"},
            "data_hygiene": {"dirty_group_values": dirty},
            "llm": {
                "default": cfg.llm.default,
                "routes": cfg.llm.routes,
                "providers": {
                    name: {"type": p.type, "model": p.model, "base_url": p.base_url,
                           "has_key": bool(p.api_key), "key_env": p.api_key_env}
                    for name, p in cfg.llm.providers.items()
                },
            },
        }

    @app.get("/api/groups")
    def groups() -> list[dict[str, Any]]:
        return _group_rows(ws)

    # ---------------- 任务 ----------------
    @app.get("/api/jobs")
    def job_list() -> list[dict[str, Any]]:
        return [r.to_dict() for r in jobs.list_jobs(ws)]

    @app.get("/api/jobs/{job_id}/log")
    def job_log(job_id: str, tail: int = Query(200, ge=0, le=5000)) -> dict[str, Any]:
        return {"id": job_id, "log": jobs.read_log(ws, job_id, tail=tail)}

    @app.post("/api/jobs/{job_id}/kill")
    def job_kill(job_id: str) -> dict[str, Any]:
        if not state["allow_write"]:
            raise HTTPException(403, "服务以只读模式启动")
        ok = jobs.kill_job(ws, job_id)
        return {"killed": ok}

    @app.post("/api/jobs")
    def job_start(req: JobRequest = Body(...)) -> dict[str, Any]:
        if not state["allow_write"]:
            raise HTTPException(403, "服务以只读模式启动")
        if req.step not in STEPS and req.step != "run":
            raise HTTPException(400, f"未知步骤: {req.step}")
        cfg_path = str(Path(cfg.workspace.root))  # 仅用于日志
        # 注意: 本服务自己就把子进程做成脱离式后台进程, 所以**不要**再传 CLI 的 --background
        # (那会二次 spawn); --job-id 只有 transcribe/extract 支持, 其余步骤由步骤 state 判定完成。
        supports_job_id = req.step in ("transcribe", "extract")
        argv = [sys.executable, "-m", "trpg_agent", req.step, "--ws", str(ws.root)]
        if req.group:
            argv += ["--group", req.group]
        if req.step == "transcribe":
            if req.force:
                argv.append("--force")
            if req.smoke:
                argv += ["--smoke", str(req.smoke)]
        if req.step == "extract":
            if req.force:
                argv.append("--force")
            if req.base_url:
                argv += ["--base-url", req.base_url]
            if req.model:
                argv += ["--model", req.model]
        if req.step == "store":
            if req.apply:
                argv.append("--apply")
            if req.allow_production:
                argv.append("--allow-production")
        if req.step == "visualize" and req.all_groups:
            argv.append("--all")
        if req.step == "review" and not req.group:
            raise HTTPException(400, "review 需要指定团")
        rec = jobs.start_background(
            ws, req.step, argv, pass_job_id=supports_job_id,
            extra={"group": req.group, "step": req.step, "requested_apply": bool(req.apply)},
        )
        log.info(f"web 启动任务 {rec.id}: {' '.join(argv[3:])}  ({cfg_path})")
        return rec.to_dict()

    # ---------------- 待确认裁决 ----------------
    @app.get("/api/review/{group}")
    def review_get(group: str) -> dict[str, Any]:
        items = review_collect(ws, group)
        dp = decisions_path(ws, cfg, group)
        existing = _load_json(dp, None)
        return {"group": group, "items": items, "decisions_file": ws.rel(dp),
                "decisions": (existing or {}).get("decisions", []) if existing else []}

    @app.post("/api/review/{group}")
    def review_save(group: str, body: DecisionsBody = Body(...)) -> dict[str, Any]:
        if not state["allow_write"]:
            raise HTTPException(403, "服务以只读模式启动")
        dp = decisions_path(ws, cfg, group)
        dp.parent.mkdir(parents=True, exist_ok=True)
        payload = {"group": group,
                   "_说明": ["action: accept/reject/set/merge; accept/reject/set 需 target+index; "
                             "merge 需 canonical+variant"],
                   "decisions": [d.model_dump(exclude_none=True) for d in body.decisions]}
        dp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": len(body.decisions), "file": ws.rel(dp)}

    @app.post("/api/review/{group}/apply")
    def review_apply(group: str) -> dict[str, Any]:
        if not state["allow_write"]:
            raise HTTPException(403, "服务以只读模式启动")
        try:
            return apply_decisions(ws, cfg, group)
        except FileNotFoundError as e:
            raise HTTPException(404, str(e)) from e
        except json.JSONDecodeError as e:
            raise HTTPException(400, f"裁决文件不是合法 JSON: {e}") from e

    # ---------------- 产物 ----------------
    @app.get("/api/patches/{group}")
    def patch_get(group: str) -> Any:
        p = ws.patches / f"{group}_patch.json"
        if not p.is_file():
            raise HTTPException(404, f"没有补丁: {group}")
        return _load_json(p, {})

    @app.get("/api/reports/{group}")
    def report_get(group: str, kind: str = Query("report", pattern="^(report|pending|batch)$")) -> dict[str, Any]:
        if kind == "pending":
            p = ws.reports / f"{group}_待确认.md"
        elif kind == "batch":
            cands = sorted(ws.reports.glob("批量提炼_*.md"))
            p = cands[-1] if cands else ws.reports / "_none.md"
        else:
            p = ws.reports / f"{group}_入库报告.md"
        if not p.is_file():
            raise HTTPException(404, f"没有这个报告: {p.name}")
        return {"path": ws.rel(p), "markdown": p.read_text(encoding="utf-8")}

    @app.get("/api/products")
    def products() -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        if ws.output.is_dir():
            for p in sorted(ws.output.rglob("*")):
                if p.is_file() and p.suffix.lower() in (".html", ".md"):
                    out.append({"path": ws.rel(p), "name": p.name, "suffix": p.suffix.lower(),
                                "size": p.stat().st_size,
                                "mtime": p.stat().st_mtime})
        return out

    @app.get("/api/product")
    def product(path: str = Query(...)) -> Any:
        p = _safe_path(ws, path)
        if p.suffix.lower() == ".html":
            return HTMLResponse(p.read_text(encoding="utf-8", errors="replace"))
        return {"path": ws.rel(p), "markdown": p.read_text(encoding="utf-8", errors="replace")}

    @app.get("/api/segments/{group}")
    def segments(group: str) -> dict[str, Any]:
        idx = load_index(ws, group)
        if not idx:
            raise HTTPException(404, f"没有段索引: {group}")
        return idx

    @app.get("/api/extract/{group}/{n}")
    def extract_md(group: str, n: int) -> dict[str, Any]:
        p = ws.work / "extracts" / f"{group}_段{n}_提炼.md"
        if not p.is_file():
            raise HTTPException(404, "没有这段提炼")
        return {"path": ws.rel(p), "markdown": p.read_text(encoding="utf-8")}

    # ---------------- 静态前端 ----------------
    # 构建产物挂载: /assets/* 与 /favicon.ico 等; 首页单独返回 index.html
    if (DIST_DIR / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=DIST_DIR / "assets"), name="assets")
    dist_root = DIST_DIR if DIST_DIR.is_dir() else None

    @app.get("/", response_class=HTMLResponse)
    def index() -> Any:
        idx = DIST_DIR / "index.html"
        if idx.is_file():
            return HTMLResponse(idx.read_text(encoding="utf-8"))
        return HTMLResponse(
            "<h2>前端尚未构建</h2><p>在 <code>web/</code> 下执行 "
            "<code>npm install &amp;&amp; npm run build</code>, 或开发模式 "
            "<code>npm run dev</code> (Vite 默认 5173 端口, 已配置代理到本服务)。</p>"
            "<p>API 可用: <a href='/docs'>/docs</a></p>"
        )

    @app.get("/{name:path}")
    def static_files(name: str) -> Any:
        """兜底: 托管 dist 下的其它静态文件(图标等); 未命中则 404。"""
        if dist_root is None:
            raise HTTPException(404, "前端未构建")
        p = (dist_root / name).resolve()
        try:
            p.relative_to(dist_root.resolve())
        except ValueError as e:
            raise HTTPException(400, "路径越界") from e
        if p.is_file():
            return FileResponse(p)
        raise HTTPException(404, name)

    return app


def build_argv_preview(req: JobRequest) -> list[str]:
    """(调试用) 展示 web 会怎么拼 CLI 参数。"""
    return [req.step, req.group or "", str(req.force), str(req.apply)]
