# -*- coding: utf-8 -*-
"""跑团宇宙 · 提案箱 API（自托管版 / FastAPI + SQLite）
================================================================
与 Cloudflare Worker 版（`worker/index.js`）**行为一致** ——
同一套自测脚本 `.tmp/test_wiki_api.py` 两边都能跑通，方便随时切换或搬回来。

设计上和 Worker 版保持一致的三条底线：
  1. 访客提交一律落 `pending`，**绝不直接改生产库**；
  2. 字段白名单裁剪 + 长度截断 + 同 IP 限流（只存 IP 的 SHA-256）；
  3. 管理端点必须带 `x-admin-token`，比较用常数时间。

用法
----
    # 方式 A：直接跑（**同时托管 site/ 静态文件**，单进程就能出整站，适合小服务器/试水）
    .venv\\Scripts\\python.exe -m uvicorn server.app:app --host 0.0.0.0 --port 8788

    # 方式 B：本文件直接执行（等价于上面，参数写死更省事）
    .venv\\Scripts\\python.exe server\\app.py

    # 方式 C：只出 API，静态交给 nginx（设 NO_SITE=1）

环境变量
--------
    ADMIN_TOKEN   管理员口令（**必填**，不设则审核端点一律 401）
    WIKI_DB       SQLite 文件路径（默认 server/wiki.db）
    SITE_DIR      静态站点目录（默认 ../site）
    NO_SITE       设为 1 则不托管静态（纯 API）
    PORT/HOST     方式 B 的监听地址（默认 0.0.0.0:8788）

迁移线上数据见 `tools/_export_d1.py` 与 `server/README.md`。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sqlite3
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

try:                                     # 作为包导入（uvicorn server.app:app / python -m server.app）
    from .edit_api import router as edit_router
    from .store import Store
except ImportError:                      # 直接被当成脚本跑（python server/app.py）时没有包上下文
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from edit_api import router as edit_router      # type: ignore
    from store import Store                          # type: ignore

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent

DB_PATH = Path(os.environ.get("WIKI_DB") or (HERE / "wiki.db"))
SITE_DIR = Path(os.environ.get("SITE_DIR") or (ROOT / "site"))
# 权威数据（人可读 JSON）—— 默认放 server/data/，可挂到你自己的目录
DATA_DIR = Path(os.environ.get("WIKI_DATA") or (HERE / "data"))
# 立绘：上传的图直接落进站点的 assets/portraits/，前端按 /assets/portraits/<id>.<ext> 取
PORTRAIT_DIR = Path(os.environ.get("PORTRAIT_DIR") or (SITE_DIR / "assets" / "portraits"))
# 既有头像目录（trpg_agent 生产库），用来给还没上传立绘的角色兜底
AVATAR_DIR = Path(os.environ.get("AVATAR_DIR") or "")
NO_SITE = os.environ.get("NO_SITE", "") not in ("", "0", "false", "False")
ADMIN_TOKEN = os.environ.get("ADMIN_TOKEN", "")
EDIT_TOKEN = os.environ.get("EDIT_TOKEN") or ADMIN_TOKEN

KINDS = {"char_update", "char_create", "char_delete",
         "rel_update", "rel_create", "rel_delete"}
MAX_BODY = 16 * 1024
MAX_TEXT = 4000
RATE_WINDOW = 10 * 60
RATE_MAX = 8

SCHEMA = """
CREATE TABLE IF NOT EXISTS suggestions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kind        TEXT    NOT NULL,
  target_id   TEXT,
  payload     TEXT    NOT NULL,
  reason      TEXT,
  author      TEXT,
  status      TEXT    NOT NULL DEFAULT 'pending',
  created_at  TEXT    NOT NULL,
  reviewed_at TEXT,
  review_note TEXT,
  ip_hash     TEXT
);
CREATE INDEX IF NOT EXISTS idx_sugg_status ON suggestions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sugg_target ON suggestions(target_id);
CREATE INDEX IF NOT EXISTS idx_sugg_ip     ON suggestions(ip_hash, created_at DESC);
"""

# ── 数据库（单文件 SQLite；单进程够用，多 worker 见 README 的说明）──
_db_lock = threading.Lock()
_conn: sqlite3.Connection | None = None


def db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        _conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
        _conn.row_factory = sqlite3.Row
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def rows(sql: str, args: tuple = ()) -> list[dict]:
    with _db_lock:
        cur = db().execute(sql, args)
        return [dict(r) for r in cur.fetchall()]


def one(sql: str, args: tuple = ()) -> dict | None:
    r = rows(sql, args)
    return r[0] if r else None


def write(sql: str, args: tuple = ()) -> int:
    with _db_lock:
        cur = db().execute(sql, args)
        db().commit()
        return cur.rowcount


# ── 工具 ────────────────────────────────────────────────────
def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256hex(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def safe_parse(s: str):
    try:
        return json.loads(s)
    except Exception:
        return {}


def s(v, mx: int = 200) -> str:
    return v.strip()[:mx] if isinstance(v, str) else ""


def sarr(v, n: int = 20, mx: int = 80):
    if not isinstance(v, list):
        return None
    out = [x.strip()[:mx] for x in v if isinstance(x, str) and x.strip()]
    return out[:n]


def clean_attrs(raw):
    """结构化属性标签 `{维度: 值}`；值可为字符串或字符串数组，值为 None 表示**删除该维度**。"""
    if not isinstance(raw, dict):
        return None
    out: dict = {}
    n = 0
    for k, v in raw.items():
        if n >= 40:                       # 维度数量上限
            break
        key = str(k).strip()[:30]
        if not key:
            continue
        if v is None:
            out[key] = None
            n += 1
        elif isinstance(v, str):
            sv = v.strip()[:120]
            if sv:
                out[key] = sv
                n += 1
        elif isinstance(v, list):
            arr = [x.strip()[:120] for x in v if isinstance(x, str) and x.strip()][:12]
            if arr:
                out[key] = arr
                n += 1
    return out or None


def clean_payload(kind: str, raw) -> dict | None:
    """按 kind 做字段白名单裁剪 —— 不认识的字段一律丢弃。"""
    if not isinstance(raw, dict):
        return None
    out: dict = {}

    def put(k, v):
        if v not in (None, ""):
            out[k] = v

    if kind.startswith("char_"):
        put("id", s(raw.get("id"), 64))
        put("name", s(raw.get("name"), 80))
        put("identity", s(raw.get("identity"), 400))
        put("note", s(raw.get("note"), MAX_TEXT))
        put("profile", s(raw.get("profile"), 12000))     # wiki 正文，比 note 宽
        put("played_by", s(raw.get("played_by"), 80))
        for key, val in (("aliases", sarr(raw.get("aliases"))),
                         ("groups", sarr(raw.get("groups"))),
                         ("tags", sarr(raw.get("tags"), 10, 40))):
            if val is not None:
                put(key, val)
        at = clean_attrs(raw.get("attrs"))
        if at:
            put("attrs", at)
    else:
        put("from", s(raw.get("from"), 64))
        put("to", s(raw.get("to"), 64))
        put("type", s(raw.get("type"), 60))
        put("strength", s(raw.get("strength"), 10))
        put("event", s(raw.get("event"), MAX_TEXT))
        put("raw", s(raw.get("raw"), 120))

    if kind in ("char_delete", "rel_delete"):
        return out
    return out or None


# ── 限流（内存窗口；单进程内准确，多 worker 会各算各的，见 README）──
_hits: dict[str, list[float]] = {}
_hits_lock = threading.Lock()


def rate_ok(ip_hash: str) -> bool:
    now = time.time()
    with _hits_lock:
        arr = [t for t in _hits.get(ip_hash, []) if now - t < RATE_WINDOW]
        if len(arr) >= RATE_MAX:
            _hits[ip_hash] = arr
            return False
        arr.append(now)
        _hits[ip_hash] = arr
        return True


def client_ip(request: Request) -> str:
    xff = request.headers.get("x-forwarded-for", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else ""


def is_admin(request: Request) -> bool:
    if not ADMIN_TOKEN:
        return False
    got = request.headers.get("x-admin-token", "")
    return hmac.compare_digest(got, ADMIN_TOKEN)


app = FastAPI(title="跑团宇宙 · wiki 服务端", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
    allow_headers=["content-type", "x-admin-token", "x-edit-token"],
)

# ── 自由编辑层：权威数据（JSON）+ 版本历史（SQLite）+ 编辑路由 ──
# 与提案箱并存：提案箱是「建议」，这里是「直接改」——主人要的是后者。
app.state.store = Store(DATA_DIR, DB_PATH)
app.state.edit_token = EDIT_TOKEN
app.state.portrait_dir = PORTRAIT_DIR
app.state.avatar_dir = AVATAR_DIR
app.include_router(edit_router)


def ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw}, headers={"cache-control": "no-store"})


def bad(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=code,
                        headers={"cache-control": "no-store"})


@app.get("/api/stats")
async def api_stats():
    m = {"pending": 0, "approved": 0, "rejected": 0}
    for r in rows("SELECT status, COUNT(*) AS n FROM suggestions GROUP BY status"):
        m[r["status"]] = r["n"]
    return ok(**m)


@app.get("/api/overrides")
async def api_overrides():
    items = rows("""SELECT id, kind, target_id, payload, author, created_at
                      FROM suggestions WHERE status='approved'
                     ORDER BY reviewed_at ASC, id ASC""")
    out = [{"id": x["id"], "kind": x["kind"], "target_id": x["target_id"],
            "payload": safe_parse(x["payload"]), "author": x["author"], "at": x["created_at"]}
           for x in items]
    return ok(count=len(out), items=out)


@app.get("/api/suggestions")
async def api_suggestions(request: Request, status: str = "approved", limit: int = 100):
    if status not in ("pending", "approved", "rejected"):
        return bad("status 非法")
    if status != "approved" and not is_admin(request):
        return bad("需要管理员口令", 401)
    limit = max(1, min(200, limit))
    items = rows("""SELECT * FROM suggestions WHERE status=?
                     ORDER BY created_at DESC, id DESC LIMIT ?""", (status, limit))
    for x in items:
        x["payload"] = safe_parse(x["payload"])
        x.pop("ip_hash", None)
    return ok(status=status, count=len(items), items=items)


@app.post("/api/suggest")
async def api_suggest(request: Request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return bad("请求体过大（上限 16KB）")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return bad("JSON 解析失败")
    if not isinstance(body, dict):
        return bad("请求体必须是 JSON 对象")

    kind = s(body.get("kind"), 20)
    if kind not in KINDS:
        return bad("kind 非法")

    payload = clean_payload(kind, body.get("payload"))
    if not payload:
        return bad("没有可用的字段内容")

    target = s(body.get("target_id") or payload.get("id") or payload.get("from"), 64) or None
    if kind == "char_update" and not target:
        return bad("char_update 必须带 target_id")
    if kind.startswith("rel_") and not (payload.get("from") and payload.get("to")):
        return bad("关系类建议必须带 from / to")

    ip_hash = sha256hex("wiki|" + client_ip(request))
    if not rate_ok(ip_hash):
        return bad(f"提交太频繁（10 分钟内最多 {RATE_MAX} 条），歇一会儿再来", 429)

    with _db_lock:
        cur = db().execute(
            """INSERT INTO suggestions (kind,target_id,payload,reason,author,status,created_at,ip_hash)
               VALUES (?,?,?,?,?,'pending',?,?)""",
            (kind, target, json.dumps(payload, ensure_ascii=False),
             s(body.get("reason"), 600), s(body.get("author"), 40), now_iso(), ip_hash))
        db().commit()
        sid = cur.lastrowid
    return ok(id=sid, status="pending")


@app.post("/api/review")
async def api_review(request: Request):
    if not is_admin(request):
        return bad("需要管理员口令", 401)
    raw = await request.body()
    if len(raw) > MAX_BODY:
        return bad("请求体过大（上限 16KB）")
    try:
        body = json.loads(raw.decode("utf-8") or "{}")
    except Exception:
        return bad("JSON 解析失败")

    try:
        sid = int(body.get("id"))
    except Exception:
        return bad("id / action 非法")
    action = s(body.get("action"), 12)
    if action not in ("approve", "reject", "reopen"):
        return bad("id / action 非法")

    status = {"approve": "approved", "reject": "rejected", "reopen": "pending"}[action]
    n = write("UPDATE suggestions SET status=?, reviewed_at=?, review_note=? WHERE id=?",
              (status, None if action == "reopen" else now_iso(),
               s(body.get("note"), 300), sid))
    if n == 0:
        return bad("找不到该条建议", 404)
    return ok(id=sid, status=status)


# ── 静态站点（可选）＋ SPA 回退 ──────────────────────────────
class SPAStatics(StaticFiles):
    """未知路径回落 index.html —— 对应 Cloudflare 的 single-page-application。"""

    async def get_response(self, path, scope):
        try:
            return await super().get_response(path, scope)
        except StarletteHTTPException as e:
            if e.status_code == 404:
                return await super().get_response("index.html", scope)
            raise


if not NO_SITE and SITE_DIR.is_dir():
    app.mount("/", SPAStatics(directory=str(SITE_DIR), html=True), name="site")


def main() -> int:
    """方式 B：直接执行本文件。"""
    import uvicorn
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8788"))
    if not ADMIN_TOKEN:
        print("!! 未设 ADMIN_TOKEN：审核端点会一律返回 401（提交不受影响）", file=sys.stderr)
    print(f"DB   : {DB_PATH}")
    print(f"SITE : {'(不托管)' if NO_SITE else SITE_DIR}")
    print(f"LISTEN http://{host}:{port}/")
    uvicorn.run(app, host=host, port=port, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
