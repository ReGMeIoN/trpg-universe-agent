# -*- coding: utf-8 -*-
"""编辑 API：自由在线编辑（**无审核**）+ 版本历史 + 回滚。

与提案箱的根本区别：**写进去就是真的**（主人原话：都是一起玩认识的人，不需要审核关）。
所以安全策略换成另外三条：
  1. **入口口令**（一个共享 token）—— 防的是"链接被外人扫到乱改"，不是防朋友；
  2. **每次改动都进版本历史** —— 谁改的、改了什么、什么时候，全留着，任何一版都能回滚；
  3. **危险操作前自动备份** —— 删角色 / 删关系这类，先复制一份数据文件。

数据形状（JSON 权威）：
    characters.json: {"characters": [ {id, name, aliases, groups, tags, kind, played_by,
                                       identity, note, profile, attrs, events, avatar, ...} ]}
    relations.json : {"relations":  [ {from, to, type, type_raw, strength, event} ]}
"""
from __future__ import annotations

import base64
import hmac
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Header, Request
from fastapi.responses import JSONResponse

try:                                     # 包导入（uvicorn server.app:app）与脚本直跑（python server/app.py）都要能用
    from .store import Store, now_iso
except ImportError:
    from store import Store, now_iso      # type: ignore

# ── 常量（与 worker/index.js 的白名单保持一致）──────────────
MAX_TEXT = 4000
MAX_PROFILE = 20000
KIND_ORDER = ["PC", "NPC", "BOSS", "跨团", "KP"]
DEFAULT_COLOR = "#8fa3b8"
# 与 tools/build_net_site.py **完全一致**的建站口径
CORE_GROUPS = ["阴阳差事录 超自然怪谈", "圣剑英雄谭", "魔法少女育成计划 6"]
TYPICAL_PER_GROUP = 3
GROUP_COLOR = {
    "阴阳差事录 超自然怪谈": "#d94b3a", "圣剑英雄谭": "#d8b25a", "魔法少女育成计划 6": "#6fd6c0",
    "魔法少女救赎线": "#c86fd6", "魔法少女木柜子": "#e08a5a", "魔法少女2": "#7fa8e8",
    "魔法少女五": "#e0709a", "魔女裁判厅": "#9aa7b8", "无敌巨鲨大战奈亚拉托提普": "#4fa3c7",
    "致无名者之声": "#6b7f9e", "恋爱与命运的不思议冒险？！": "#e0b0c0",
    "卧槽是伪人群·伪人杀": "#b03a3a", "卧槽是伪人群·雪山狼人杀": "#8a3ab0",
    "卧槽是伪人群·异世界大逃杀": "#3ab07a",
}

router = APIRouter()


def select_site_scope(chars: list, rels: list) -> tuple[list, list]:
    """站点口径。

    ⚠️ **2026-10-06 主人拍板改成「全量」**：之前只挑 ~141 人（核心 + 邻居 + 跨团 + 每团代表），
       结果"以前那些团的角色"根本不在站上。现在**所有角色都上站**，没立绘的也上（前端显示
       「未解封」剪影卡），所以这里只做一件事：**剔除 `confirmed: false` 的**（按项目铁律，
       未确认的角色不算存在）。关系同样只要两端都在的。

       注意：`build_net_site.py` 也要同步成同一口径，否则静态站与服务器数据会对不上。
    """
    kept = [c for c in chars if c.get("id") and c.get("confirmed", True) is not False]
    ids = {c["id"] for c in kept}
    sel_rels = [r for r in rels
                if r.get("from") in ids and r.get("to") in ids
                and r.get("from") != r.get("to")]
    return kept, sel_rels


# ── 依赖：Store 挂在 app.state 上 ──────────────────────────
def _store(request: Request) -> Store:
    return request.app.state.store


def _token(request: Request) -> str:
    return getattr(request.app.state, "edit_token", "") or ""


def _is_editor(request: Request, header_token: str | None) -> bool:
    want = _token(request)
    if not want:
        return False
    return hmac.compare_digest(str(header_token or ""), want)


def need_edit(request: Request, x_edit_token: str | None):
    if not _is_editor(request, x_edit_token):
        return JSONResponse({"ok": False, "error": "需要编辑口令"}, status_code=401)
    return None


# ── 公开写入（2026-10-06 主人拍板：新增条目 / 上传立绘 / 发公告不要口令）──
# 安全网：共享口令保护的「修改/删除/回滚」照旧 + 每次都进版本历史 + 危险操作自动备份。
_RATE: dict[str, list[float]] = {}


def rate_limited(request: Request, bucket: str, limit: int, window_s: int = 600) -> bool:
    """按「客户端 IP + 用途」做粗粒度限流（内存计数，单进程够用）。"""
    ip = (request.client.host if request.client else "") or "?"
    key = f"{bucket}:{ip}"
    now = time.time()
    hits = [t for t in _RATE.get(key, []) if now - t < window_s]
    hits.append(now)
    _RATE[key] = hits
    if len(_RATE) > 4000:                       # 防内存无限涨
        for k in [k for k, v in _RATE.items() if not v or now - max(v) > window_s]:
            _RATE.pop(k, None)
    return len(hits) > limit


def who(request: Request, body: dict | None = None, x_edit_token: str | None = None) -> str:
    """写入者署名：持口令的写「口令用户」，匿名的按前端给的昵称（内存里存的那个），
    都没有就叫「匿名访客」。"""
    if _is_editor(request, x_edit_token):
        return "编辑者"
    nm = (body or {}).get("_editor")
    nm = str(nm).strip()[:24] if nm else ""
    return nm or "匿名访客"


def ok(**kw) -> JSONResponse:
    return JSONResponse({"ok": True, **kw}, headers={"cache-control": "no-store"})


def bad(msg: str, code: int = 400) -> JSONResponse:
    return JSONResponse({"ok": False, "error": msg}, status_code=code,
                        headers={"cache-control": "no-store"})


# ── 小工具 ─────────────────────────────────────────────────
def s(v, mx: int = 200) -> str:
    return v.strip()[:mx] if isinstance(v, str) else ""


def sarr(v, n: int = 30, mx: int = 80):
    if not isinstance(v, list):
        return None
    return [x.strip()[:mx] for x in v if isinstance(x, str) and x.strip()][:n]


def clean_attrs(raw):
    """{维度: 值}；值可为字符串或数组；None 表示删除该维度。"""
    if not isinstance(raw, dict):
        return None
    out, n = {}, 0
    for k, v in raw.items():
        if n >= 60:
            break
        key = str(k).strip()[:30]
        if not key:
            continue
        if v is None:
            out[key] = None
            n += 1
        elif isinstance(v, str):
            sv = v.strip()[:200]
            if sv:
                out[key] = sv
                n += 1
        elif isinstance(v, list):
            arr = [x.strip()[:200] for x in v if isinstance(x, str) and x.strip()][:20]
            if arr:
                out[key] = arr
                n += 1
    return out or None


def kind_of(c: dict) -> str:
    tags = c.get("tags") or []
    if "KP" in tags:
        return "KP"
    if "跨团" in tags:
        return "跨团"
    if "BOSS" in tags:
        return "BOSS"
    if "PC" in tags:
        return "PC"
    return "NPC"


def merge_attrs(cur: dict, patch: dict) -> dict:
    """attrs 按维度合并（不能整体替换，否则两人先后改不同维度会互相覆盖）。"""
    out = dict(cur or {})
    for k, v in (patch or {}).items():
        if v is None:
            out.pop(k, None)
        else:
            out[k] = v
    return out


def portrait_of(cid: str, portrait_dir: Path, avatar_dir: Path) -> dict | None:
    """立绘：**必须指向站点里真实存在的文件**。

    ⚠️ 踩过的坑：以前直接把生产库 `characters[].avatar` 字段（形如
       `数据\\头像\\阴阳差事录_刘汤.jpg` 的 **Windows 路径**）吐给前端 → 全部 404。
       站点里的立绘是 build 时生成的 `<id>_t.jpg`（缩略）/ `<id>_f.jpg`（大图），
       所以这里按文件名去 assets/portraits 里找。
    """
    for d in (portrait_dir, avatar_dir):
        if not d or not Path(d).is_dir():
            continue
        d = Path(d)
        for suffix, kind in (("_t", "thumb"), ("_f", "full")):
            for ext in (".jpg", ".jpeg", ".png", ".webp"):
                f = d / f"{cid}{suffix}{ext}"
                if f.is_file():
                    other = d / f"{cid}{'_f' if suffix == '_t' else '_t'}{ext}"
                    return {"thumb": f"/assets/portraits/{f.name}",
                            "full": f"/assets/portraits/{other.name if other.is_file() else f.name}"}
        for ext in (".jpg", ".jpeg", ".png", ".webp"):
            f = d / f"{cid}{ext}"
            if f.is_file():
                return {"thumb": f"/assets/portraits/{f.name}",
                        "full": f"/assets/portraits/{f.name}"}
    return None


# ══════════════════════════════════════════════════════════
# 读：数据（前端用它替代静态 data.js）
# ══════════════════════════════════════════════════════════
@router.get("/api/data")
async def api_data(request: Request, scope: str = "site", limit: int = 0):
    """`scope=site`（默认）→ 按建站口径**选角**（约 135 人，和静态站一致）；
       `scope=all` → 全量（编辑器列表用它）。"""
    st = _store(request)
    d = st.load()
    all_chars, all_rels = d["characters"], d["relations"]

    if scope == "all":
        chars, rels = all_chars, all_rels
    else:
        chars, rels = select_site_scope(all_chars, all_rels)
    if limit > 0:
        chars = chars[:limit]

    by_id = {c.get("id"): c for c in chars}
    deg: dict[str, int] = {}
    for r in rels:
        deg[r.get("from")] = deg.get(r.get("from"), 0) + 1
        deg[r.get("to")] = deg.get(r.get("to"), 0) + 1

    portrait_dir = Path(getattr(request.app.state, "portrait_dir", "") or "")
    avatar_dir = Path(getattr(request.app.state, "avatar_dir", "") or "")
    out_chars = []
    for c in chars:
        cid = c.get("id")
        av = portrait_of(cid, portrait_dir, avatar_dir)
        # ⚠️ 绝不要把生产库的 `avatar` 字段（Windows 路径）当 URL 吐给前端 —— 一定 404。
        #    找不到图就留 None，前端会显示「未解封」剪影卡，比破图好。
        out_chars.append({
            "id": cid, "name": c.get("name") or cid,
            "aliases": c.get("aliases") or [],
            "groups": c.get("groups") or [],
            "tags": [t for t in (c.get("tags") or []) if t != "待确认"],
            "kind": kind_of(c),
            "played_by": c.get("played_by") or "",
            "identity": c.get("identity") or "",
            "note": c.get("note") or "",
            "profile": c.get("profile") or "",
            "profile_src": c.get("profile_src") or "",
            "attrs": c.get("attrs") or {},
            "events": c.get("events") or [],
            "degree": deg.get(cid, 0),
            "avatar": av,
            "in_graph": c.get("in_graph", True),
            "created_at": c.get("created_at") or "",
            "updated_at": c.get("updated_at") or "",
            "merged_from": c.get("merged_from") or [],     # 合并来源（谁被并进它了）
        })

    out_rels = [{"a": r.get("from"), "b": r.get("to"), "type": r.get("type") or "",
                 "raw": r.get("type_raw") or "", "strength": r.get("strength") or "",
                 "event": r.get("event") or ""} for r in rels]

    gc: dict[str, int] = {}
    for c in out_chars:
        for g in (c["groups"] or ["(未分组)"]):
            gc[g] = gc.get(g, 0) + 1
    groups = [{"name": g, "count": n} for g, n in sorted(gc.items(), key=lambda kv: (-kv[1], kv[0]))]

    return ok(
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        chars=out_chars, rels=out_rels, groups=groups, kinds=KIND_ORDER,
        stats=st.stats(),
    )


@router.get("/api/layout")
async def api_layout_get(request: Request):
    """**布局账本**：`数据/layout.json` 里的人工微调（拖动换位）。

    自动槽位由前端按 `(名字, id)` 稳定哈希分配（见 `tools/_auto_layout.py`），
    服务端**不存**每个人的绝对位置；`pos` 里存的是**相对自动槽位的偏移 [dx, dy]**——
    这样即使某个团的人数变了、槽位坐标整体挪了，人工微调仍然跟着这张卡走。

    读接口不要口令（布局本来就是给人看的）；写接口要口令。
    """
    st = _store(request)
    doc = st.load_layout()
    idmap = {c.get("id"): (c.get("name") or c.get("id")) for c in st.load()["characters"]}
    manual = {}
    for key, members in (doc.get("manual") or {}).items():
        manual[key] = {idmap.get(i, i): p for i, p in (members or {}).items()}
    return ok(layout={
        "version": int(doc.get("version") or 1),
        "updated": doc.get("updated") or "",
        "dept": doc.get("entity_pos") or {},
        "pos": doc.get("pos") or {},          # 角色 id -> [dx, dy]
        "slots": doc.get("slot_of") or {},    # 成员键（名字\0id）-> 绝对槽位号（只增不改）
        "entity": manual,                     # 实体名 -> {成员名: [dx, dy]}
        "next_slot": int(doc.get("next_slot") or 0),
    })


@router.post("/api/layout")
async def api_layout_set(request: Request, x_edit_token: str | None = Header(default=None)):
    """写布局账本。body 三键都可选：

    - `pos`    : {角色id: [dx, dy]} —— **拖动换位的偏移**（前端主力）
    - `dept`   : {实体key: [x, y]} —— 整团挪位（预留）
    - `entity` : {实体key: {成员id: [dx, dy]}} —— 团内按成员微调（预留）
    """
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    body = await request.json()

    def pair(v):
        try:
            if isinstance(v, dict):
                return [float(v["x"]), float(v["y"])]
            return [float(v[0]), float(v[1])]
        except (TypeError, ValueError, KeyError, IndexError):
            return None

    def collect(raw, limit):
        out = {}
        if not isinstance(raw, dict):
            return out
        for k, v in list(raw.items())[:limit]:
            p = pair(v)
            if p:
                out[str(k)[:160]] = p
        return out

    clean_pos = collect(body.get("pos"), 4000)
    clean_dept = collect(body.get("dept"), 400)
    clean_slots = {}
    raw_slots = body.get("slots") or {}
    if isinstance(raw_slots, dict):
        for k, v in list(raw_slots.items())[:6000]:
            try:
                clean_slots[str(k)[:160]] = int(v)
            except (TypeError, ValueError):
                continue
    clean_ent = {}
    raw_ent = body.get("entity") or {}
    if isinstance(raw_ent, dict):
        for k, members in list(raw_ent.items())[:400]:
            if isinstance(members, dict):
                clean_ent[str(k)[:160]] = collect(members, 400)

    # 「全部清空」= 复位排版：`reset:true` 显式要求，**或者 pos/slots/entity 全传空**。
    # ⚠️ 上一版对"全空"直接报 400，导致前端「复位排版」的同步请求被拒 ——
    #    本地清了、服务器还留着旧位置（回归里表现为"复位后刷新又跑回去了"）。
    if body.get("reset") or not (clean_pos or clean_dept or clean_ent or clean_slots):
        st = _store(request)
        st.save_layout(lambda d: (d.update(pos={}, entity_pos={}, manual={}, slot_of={}, next_slot=0), None)[-1])
        return ok(changed=1, reset=True, layout=st.load_layout())

    st = _store(request)
    idmap = {c.get("name") or c.get("id"): c.get("id") for c in st.load()["characters"]}

    def mutate(d):
        d.setdefault("pos", {}).update(clean_pos)
        d.setdefault("entity_pos", {}).update(clean_dept)
        manual = d.setdefault("manual", {})
        for key, members in clean_ent.items():
            manual.setdefault(key, {}).update({idmap.get(m, m): p for m, p in members.items()})
        if clean_slots:
            slot_of = d.setdefault("slot_of", {})
            slot_of.update(clean_slots)
            d["next_slot"] = max([int(d.get("next_slot") or 0)] + [v + 1 for v in slot_of.values()])

    n = st.save_layout(mutate, editor=s(body.get("_editor"), 40) or "编辑者")
    return ok(changed=n, written={"pos": len(clean_pos), "dept": len(clean_dept),
                                  "entity": len(clean_ent), "slots": len(clean_slots)},
              layout=st.load_layout())


@router.get("/api/meta")
async def api_meta(request: Request):
    """编辑器要用的元信息：所有 tag 维度/值、创作者、团、关系类型。"""
    st = _store(request)
    d = st.load()
    dims: dict[str, dict[str, int]] = {}
    creators: dict[str, int] = {}
    groups: dict[str, int] = {}
    types: dict[str, int] = {}
    tags: dict[str, int] = {}
    for c in d["characters"]:
        for k, v in (c.get("attrs") or {}).items():
            vals = v if isinstance(v, list) else [v]
            for x in vals:
                if x in (None, ""):
                    continue
                dims.setdefault(k, {})
                dims[k][str(x)] = dims[k].get(str(x), 0) + 1
        if c.get("played_by"):
            creators[c["played_by"]] = creators.get(c["played_by"], 0) + 1
        for g in (c.get("groups") or []):
            groups[g] = groups.get(g, 0) + 1
        for t in (c.get("tags") or []):
            tags[t] = tags.get(t, 0) + 1
    for r in d["relations"]:
        if r.get("type"):
            types[r["type"]] = types.get(r["type"], 0) + 1

    def top(dd: dict[str, int], n: int = 200):
        return [k for k, _ in sorted(dd.items(), key=lambda kv: (-kv[1], kv[0]))[:n]]

    return ok(
        dims={k: top(v, 300) for k, v in sorted(dims.items())},
        dim_values=dims,
        creators=top(creators), groups=top(groups, 100), types=top(types),
        tags=top(tags, 40), kinds=KIND_ORDER,
    )


# ══════════════════════════════════════════════════════════
# 写：角色
# ══════════════════════════════════════════════════════════
def _apply_char(c: dict, body: dict) -> list[str]:
    """把 body 里的字段写进角色对象，返回改动过的字段名。"""
    touched = []
    for key, mx in (("name", 80), ("identity", 600), ("note", MAX_TEXT),
                    ("profile", MAX_PROFILE), ("profile_src", 120), ("played_by", 80)):
        if key in body:
            v = s(body.get(key), mx)
            if v != (c.get(key) or ""):
                c[key] = v
                touched.append(key)
    for key in ("aliases", "groups", "tags"):
        if key in body:
            v = sarr(body.get(key), 30, 80) or []
            if v != (c.get(key) or []):
                c[key] = v
                touched.append(key)
    if "attrs" in body:
        patch = clean_attrs(body.get("attrs"))
        if patch is not None:
            merged = merge_attrs(c.get("attrs"), patch)
            if merged != (c.get("attrs") or {}):
                c["attrs"] = merged
                touched.append("attrs")
    if "avatar" in body and isinstance(body["avatar"], (str, type(None))):
        c["avatar"] = body["avatar"] or ""
        touched.append("avatar")
    if touched:
        c["updated_at"] = now_iso()          # 门户「最近改动」排序用
    return touched


@router.post("/api/edit/char")
async def edit_char(request: Request, x_edit_token: str | None = Header(default=None)):
    """新增/修改角色。

    ⚠️ **2026-10-06 主人拍板**：**新增条目不要口令**（新增角色 / 新增关系 / 上传立绘 / 发公告）。
       修改已有角色、删除、回滚 **仍然要口令** —— 也就是「能盖楼、不能拆楼」。
       公开写入的护栏：同 IP 限流 + 每条都进版本历史（可回滚）+ 危险操作前自动备份。
    """
    body = await request.json()
    cid0 = s(body.get("id"), 64)
    st0 = _store(request)
    is_new = bool(cid0) and not any(c.get("id") == cid0 for c in st0.load()["characters"])
    if not is_new:
        guard = need_edit(request, x_edit_token)      # 改已有的才要口令
        if guard:
            return guard
    elif rate_limited(request, "newchar", 40):        # 匿名新建：10 分钟 40 条
        return bad("新建太频繁了，歇一会儿再试", 429)
    st = _store(request)
    cid = s(body.get("id"), 64)
    if not cid:
        return bad("必须给 id")
    if not re.match(r"^[A-Za-z0-9_\-]{2,64}$", cid):
        return bad("id 只能用字母/数字/下划线/连字符（2–64 位）")
    editor = who(request, body, x_edit_token)
    created = {"flag": False}

    # ⚠️ 必须用**可变容器**取 kind：`st.save(..., kind=ctx["kind"], ...)` 里的下标求值
    #    发生在 mutate 执行**之前**（Python 先算实参再调用），所以只能把容器本身传下去。
    #    这就是「新建的角色在版本历史里被记成 char_update」的根因。
    ctx = {"kind": "char_update"}

    def mutate(cdoc, rdoc):
        chars = cdoc["characters"]
        hit = next((c for c in chars if c.get("id") == cid), None)
        if hit is None:
            hit = {"id": cid, "name": cid, "groups": [], "tags": [], "attrs": {},
                   "events": [], "confirmed": True, "created_at": now_iso()}
            chars.append(hit)
            created["flag"] = True
            ctx["kind"] = "char_create"
        created["touched"] = _apply_char(hit, body)

    rev = st.save(mutate, editor=editor, note=s(body.get("_note"), 200),
                  kind=lambda: ctx["kind"], target=cid,
                  summary=lambda: (f"{'新建' if created['flag'] else '修改'}角色 {cid}"
                                   f"（{('、'.join(created.get('touched') or [])) or '无字段变化'}）"))
    if rev < 0:
        return ok(rev=None, changed=False, message="没有实际变化")
    return ok(rev=rev, created=created["flag"], touched=created.get("touched") or [])


@router.post("/api/edit/merge")
async def merge_char(request: Request, x_edit_token: str | None = Header(default=None)):
    """**合并两个角色**（同一个人的两份条目）—— 2026-10-06 新增。

    语义（写清楚，免得以后自己搞混）：
      · `src` 是被吃掉的那个（合并后消失），`dst` 是留下的那个（保留它的 id / 主名字 / 立绘）；
      · **关系全部重定向** src → dst；重定向后若与已有边完全重复（from/to/type 相同）则丢掉那条重复的；
      · 自环（dst—dst）与自指边直接丢弃；
      · 别名 / 出场团 / 系统标签 / 事件 / 属性标签 做**并集**；
      · `identity` / `note` / `profile` 用「 —— 」拼接并标注来源（两份都想留）；
      · `played_by` 只在 dst 为空时继承 src；**立绘**同理（dst 没图才接管 src 的）；
      · 全部动作 + 合并来源写进版本历史，可一键回滚。

    要口令（合并是破坏性操作：会删掉一个节点）。
    body: {src: "<id>", dst: "<id>", _editor: "谁"}
    """
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    body = await request.json()
    src = s(body.get("src"), 64)
    dst = s(body.get("dst"), 64)
    if not src or not dst:
        return bad("必须给 src 与 dst")
    if src == dst:
        return bad("合并的两个 id 不能相同")
    st = _store(request)
    st.backup("merge_char")
    info: dict = {"rels": 0, "dropped": 0, "alias": 0, "groups": 0, "events": 0}

    def merge_attrs(a: dict, b: dict) -> dict:
        out = dict(a or {})
        for k, v in (b or {}).items():
            if k not in out or out[k] in (None, "", []):
                out[k] = v
            elif isinstance(v, list) and isinstance(out[k], list):
                out[k] = out[k] + [x for x in v if x not in out[k]]
            elif isinstance(v, str) and isinstance(out[k], str) and v not in out[k]:
                out[k] = out[k] + "、" + v
        return out

    def mutate(cdoc, rdoc):
        chars = cdoc["characters"]
        a = next((c for c in chars if c.get("id") == src), None)
        b = next((c for c in chars if c.get("id") == dst), None)
        if a is None or b is None:
            raise ValueError("要合并的两个角色都得存在")
        # 幂等保护：万一 mutate 被重放（store 内部可能再跑一遍），第二次直接跳过，
        # 否则关系会被"自己撞自己"再丢一遍、计数也会虚高。
        if b.get("merged_from") and src in (b.get("merged_from") or []):
            info["replay"] = info.get("replay", 0) + 1
            return

        # ① 别名并集
        al = list(b.get("aliases") or [])
        for x in [a.get("name")] + list(a.get("aliases") or []):
            if x and x != b.get("name") and x not in al:
                al.append(x)
                info["alias"] += 1
        b["aliases"] = al

        # ② 团 / 标签并集
        for key, cnt in (("groups", "groups"), ("tags", "tags")):
            cur = list(b.get(key) or [])
            for x in (a.get(key) or []):
                if x and x not in cur:
                    cur.append(x)
                    info[cnt] += 1
            b[key] = cur

        # ③ 文本字段：两份都留，标注来源
        for f, label in (("identity", "身份"), ("note", "简介"), ("profile", "详细设定")):
            av, bv = (a.get(f) or "").strip(), (b.get(f) or "").strip()
            if av and av != bv:
                if not bv:
                    b[f] = av
                elif av not in bv and bv not in av:
                    b[f] = f"{bv}\n\n—— 【{label}·并入「{a.get('name')}」】——\n{av}"

        # ④ 只在 dst 为空时继承的字段
        for f in ("played_by", "avatar"):
            if not (b.get(f) or "").strip() and (a.get(f) or "").strip():
                b[f] = a[f]

        # ⑤ 事件并集（按 group 合并 items）
        ev = {g.get("group"): list(g.get("items") or []) for g in (b.get("events") or [])}
        for g in (a.get("events") or []):
            gk = g.get("group")
            cur = ev.setdefault(gk, [])
            for it in (g.get("items") or []):
                if it and it not in cur:
                    cur.append(it)
                    info["events"] += 1
        b["events"] = [{"group": k, "items": v} for k, v in ev.items() if v]

        # ⑥ attrs 并集
        b["attrs"] = merge_attrs(b.get("attrs"), a.get("attrs"))

        # ⑦ 关系重定向。
        # ⚠️ 两个坑（都在回归里踩到了）：
        #    1) **只处理「端点涉及 src」的边**，其余边原样保留 ——
        #       上一版顺手对整张表去重、还把所有自环都删了，把库内既有的
        #       `g2_bimu→g2_bimu(一体同源)` 自环也吃掉了；
        #    2) **重定向过来的边优先**：被合并的那份常常更完整（事件写得更细），
        #       所以遇到同 key 的重复边，丢的是 dst 原来的那条。
        base = [r for r in (rdoc.get("relations") or [])
                if r.get("from") != src and r.get("to") != src]
        moved = [r for r in (rdoc.get("relations") or [])
                 if r.get("from") == src or r.get("to") == src]
        keep: list = []
        seen: set = set()
        for r in base:
            keep.append(r)
            seen.add((r.get("from"), r.get("to"), r.get("type")))
        for r in moved:
            f_, t_ = r.get("from"), r.get("to")
            if f_ == src:
                f_ = dst
            if t_ == src:
                t_ = dst
            info["rels"] += 1
            if f_ == t_:                         # 自环：只有"合并后才出现"的才丢
                info["dropped"] += 1
                continue
            k = (f_, t_, r.get("type"))
            if k in seen:                        # 与 dst 原有边重复 → 丢 dst 那条，留这条
                info["dropped"] += 1
                keep = [x for x in keep
                        if (x.get("from"), x.get("to"), x.get("type")) != k]
            seen.add(k)
            r["from"], r["to"] = f_, t_
            keep.append(r)
        rdoc["relations"] = keep

        # ⑧ 记一笔来源 + 删掉 src
        stamp = datetime.now().strftime("%Y-%m-%d")
        b["note"] = (b.get("note") or "") + \
            f"\n\n【合并记录 {stamp}】已并入 `{src}`（{a.get('name')}）——" \
            f"关系重定向 {info['rels']} 处 · 丢弃重复/自环 {info['dropped']} 条。"
        b["merged_from"] = list(b.get("merged_from") or []) + [src]
        cdoc["characters"] = [c for c in chars if c.get("id") != src]

    try:
        rev = st.save(mutate, editor=who(request, body, x_edit_token),
                      kind="char_merge", target=dst,
                      summary=lambda: (f"合并角色 {src} → {dst}"
                                       f"（关系 {info['rels']} 处，丢重复 {info['dropped']} 条）"))
    except ValueError as e:
        return bad(str(e))
    return ok(rev=rev, merged={"src": src, "dst": dst, **info})


@router.delete("/api/edit/char/{cid}")
async def delete_char(cid: str, request: Request, editor: str = "",
                      x_edit_token: str | None = Header(default=None)):
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    st = _store(request)
    st.backup("del_char")
    info = {"rels": 0, "found": False}

    def mutate(cdoc, rdoc):
        chars = cdoc["characters"]
        info["found"] = any(c.get("id") == cid for c in chars)
        cdoc["characters"] = [c for c in chars if c.get("id") != cid]
        before = len(rdoc["relations"])
        rdoc["relations"] = [r for r in rdoc["relations"]
                             if r.get("from") != cid and r.get("to") != cid]
        info["rels"] = before - len(rdoc["relations"])

    if not any(c.get("id") == cid for c in st.load()["characters"]):
        return bad("角色不存在", 404)
    rev = st.save(mutate, editor=editor or "匿名", kind="char_delete", target=cid,
                  summary=f"删除角色 {cid}（连带 {info['rels']} 条关系）")
    return ok(rev=rev, removed_relations=info["rels"])


# ══════════════════════════════════════════════════════════
# 写：关系
# ══════════════════════════════════════════════════════════
@router.post("/api/edit/rel")
async def edit_rel(request: Request, x_edit_token: str | None = Header(default=None)):
    """新增/修改关系。新增**不要口令**；改已有关系要口令。"""
    body = await request.json()
    st = _store(request)
    a, b = s(body.get("from"), 64), s(body.get("to"), 64)
    if not a or not b:
        return bad("必须给 from / to")
    if a == b:
        return bad("不能连自己（自环）")
    old_type = s(body.get("old_type"), 60)          # 改类型时用旧类型定位
    exists = any(r.get("from") == a and r.get("to") == b and
                 (old_type == "" or r.get("type") == old_type)
                 for r in st.load()["relations"])
    if exists:
        guard = need_edit(request, x_edit_token)
        if guard:
            return guard
    elif rate_limited(request, "newrel", 60):
        return bad("新增关系太频繁了，歇一会儿再试", 429)
    strength = s(body.get("strength"), 10) or "中"
    new_type = s(body.get("type"), 60) or "其他"
    event = s(body.get("event"), MAX_TEXT)
    raw = s(body.get("type_raw"), 120)
    editor = who(request, body, x_edit_token)
    res = {"mode": ""}

    def mutate(cdoc, rdoc):
        ids = {c.get("id") for c in cdoc["characters"]}
        if a not in ids or b not in ids:
            raise ValueError("端点角色不存在")
        rels = rdoc["relations"]
        idx = None
        for i, r in enumerate(rels):
            if r.get("from") == a and r.get("to") == b and (not old_type or r.get("type") == old_type):
                idx = i
                break
        if idx is None:
            for i, r in enumerate(rels):
                if r.get("from") == a and r.get("to") == b:
                    idx = i
                    break
        if idx is None:
            rels.append({"from": a, "to": b, "type": new_type, "strength": strength,
                         "event": event, "type_raw": raw, "confirmed": True})
            res["mode"] = "create"
        else:
            r = rels[idx]
            r.update({"type": new_type, "strength": strength, "event": event})
            if raw:
                r["type_raw"] = raw
            res["mode"] = "update"

    try:
        rev = st.save(mutate, editor=editor, note=s(body.get("_note"), 200),
                      kind="rel_create" if res["mode"] != "update" else "rel_update",
                      target=f"{a}|{b}",
                      summary=f"{'新建' if res['mode'] != 'update' else '修改'}关系 "
                              f"{a} —{new_type}→ {b}")
    except ValueError as e:
        return bad(str(e))
    return ok(rev=rev, mode=res["mode"])


@router.post("/api/edit/rel/delete")
async def delete_rel(request: Request, x_edit_token: str | None = Header(default=None)):
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    body = await request.json()
    st = _store(request)
    a, b = s(body.get("from"), 64), s(body.get("to"), 64)
    ty = s(body.get("type"), 60)
    found = {"n": 0}

    def mutate(cdoc, rdoc):
        kept = []
        for r in rdoc["relations"]:
            if r.get("from") == a and r.get("to") == b and (not ty or r.get("type") == ty):
                found["n"] += 1
                continue
            kept.append(r)
        rdoc["relations"] = kept

    rev = st.save(mutate, editor=s(body.get("_editor"), 40) or "匿名",
                  kind="rel_delete", target=f"{a}|{b}", summary=f"删除关系 {a} → {b}")
    if found["n"] == 0:
        return bad("没找到这条关系", 404)
    return ok(rev=rev, removed=found["n"])


# ══════════════════════════════════════════════════════════
# 版本历史 / 回滚
# ══════════════════════════════════════════════════════════
@router.get("/api/history")
async def api_history(request: Request, limit: int = 100, target: str | None = None):
    st = _store(request)
    return ok(items=st.history(limit=max(1, min(500, limit)), target=target))


@router.get("/api/history/{rev}")
async def api_history_one(rev: int, request: Request):
    st = _store(request)
    r = st.get_rev(rev)
    if not r:
        return bad("版本不存在", 404)
    return ok(**r)


@router.post("/api/rollback")
async def api_rollback(request: Request, x_edit_token: str | None = Header(default=None)):
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    body = await request.json()
    st = _store(request)
    try:
        rev = st.rollback(int(body.get("rev")), editor=s(body.get("_editor"), 40) or "匿名",
                          note=s(body.get("_note"), 200))
    except (KeyError, ValueError, TypeError) as e:
        return bad(str(e), 404)
    return ok(rev=rev)


# ══════════════════════════════════════════════════════════
# 立绘上传
# ══════════════════════════════════════════════════════════
@router.post("/api/upload/portrait")
async def upload_portrait(request: Request, x_edit_token: str | None = Header(default=None)):
    """立绘上传：用 **base64 JSON**（不引入 python-multipart 依赖）。

    ⚠️ **2026-10-06 主人拍板：上传立绘不要口令**（"缺图的角色谁都能补一张"）。
       护栏：同 IP 限流（10 分钟 30 张）+ 12MB 上限 + 只认 png/jpg/webp + 落盘前真解码一次。

    body: {id: "sjt_liya", data: "data:image/png;base64,...."}
    """
    if rate_limited(request, "upload", 30):
        return bad("上传太频繁了，歇一会儿再试", 429)
    body = await request.json()
    cid = s(body.get("id"), 64)
    if not re.match(r"^[A-Za-z0-9_\-]{2,64}$", cid):
        return bad("角色 id 非法")
    m = re.match(r"^data:image/(png|jpe?g|webp);base64,(.+)$", str(body.get("data") or ""), re.S)
    if not m:
        return bad("只支持 png / jpg / webp 的 base64 data URL")
    ext = {"jpeg": ".jpg", "jpg": ".jpg", "png": ".png", "webp": ".webp"}[m.group(1)]
    try:
        blob = base64.b64decode(m.group(2), validate=False)
    except Exception:
        return bad("base64 解不开")
    if len(blob) > 12 * 1024 * 1024:
        return bad("图太大了（上限 12MB）")
    if len(blob) < 64:
        return bad("图太小了，可能不是图片")

    out_dir = Path(request.app.state.portrait_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dst = out_dir / f"{cid}{ext}"
    dst.write_bytes(blob)

    # 立即生成站内要用的两个尺寸（卡片 300×450 / 档案 620×930，2:3 居中偏上保头）。
    # 前端 data 里的 avatar 直接指这两个文件，所以上传完刷新就能看到，不用等重跑构建。
    try:
        from PIL import Image
        im = Image.open(dst).convert("RGB")
        w, h = im.size
        for suffix, tw, q in (("_t.jpg", 300, 82), ("_f.jpg", 620, 86)):
            nh = int(tw * 3 / 2)
            target = tw / nh
            if w / h > target:
                nw = int(h * target)
                box = ((w - nw) // 2, 0, (w - nw) // 2 + nw, h)
            else:
                nh2 = int(w / target)
                top = max(0, int((h - nh2) * 0.12))
                box = (0, top, w, top + nh2)
            im.crop(box).resize((tw, nh), Image.LANCZOS).save(
                out_dir / f"{cid}{suffix}", "JPEG", quality=q, optimize=True, progressive=True)
        web = f"/assets/portraits/{cid}_f.jpg"
    except Exception:  # noqa: BLE001
        web = f"/assets/portraits/{cid}{ext}"      # PIL 不在/图坏了：至少留原图

    st = _store(request)

    def mutate(cdoc, rdoc):
        hit = next((c for c in cdoc["characters"] if c.get("id") == cid), None)
        if hit is not None:
            hit["avatar"] = f"数据\\头像\\{cid}{ext}"
    rev = st.save(mutate, editor=who(request, body, x_edit_token), kind="portrait",
                  target=cid, summary=f"上传立绘 {cid}（{len(blob) // 1024} KB）")
    return ok(rev=rev, url=web, bytes=len(blob))


# ══════════════════════════════════════════════════════════
# 公告板（**不要口令**：谁都能贴一条，主人删的时候才要口令）
# ══════════════════════════════════════════════════════════
@router.get("/api/announce")
async def announce_list(request: Request, limit: int = 50):
    st = _store(request)
    doc = st.load_announcements()
    items = sorted(doc.get("items", []), key=lambda x: x.get("ts", ""), reverse=True)
    return ok(updated=doc.get("updated", ""), items=items[:max(1, min(limit, 200))])


@router.post("/api/announce")
async def announce_add(request: Request, x_edit_token: str | None = Header(default=None)):
    """发一条公告。**不要口令**（主人 2026-10-06 拍板），限流 10 分钟 20 条。"""
    if rate_limited(request, "announce", 20):
        return bad("发布太频繁了，歇一会儿再试", 429)
    body = await request.json()
    text = s(body.get("text"), 1000)
    if not text:
        return bad("公告内容不能为空")
    who_ = who(request, body, x_edit_token)
    st = _store(request)
    made = {}

    def mutate(doc):
        nid = int(doc.get("next_id") or 1)
        doc["next_id"] = nid + 1
        made.update({"id": nid, "ts": now_iso(), "who": who_, "text": text,
                     "kind": s(body.get("kind"), 20) or "notice"})
        doc.setdefault("items", []).append(made)
        doc["items"] = doc["items"][-300:]          # 只留最近 300 条

    st.save_announcements(mutate, editor=who_)
    return ok(item=made)


@router.post("/api/announce/delete")
async def announce_delete(request: Request, x_edit_token: str | None = Header(default=None)):
    """删公告**要口令**（防止别人把公告栏清空）。"""
    guard = need_edit(request, x_edit_token)
    if guard:
        return guard
    body = await request.json()
    nid = int(body.get("id") or 0)
    st = _store(request)
    info = {"before": 0}

    def mutate(doc):
        info["before"] = len(doc.get("items", []))
        doc["items"] = [x for x in doc.get("items", []) if int(x.get("id") or 0) != nid]

    st.save_announcements(mutate, editor="编辑者")
    return ok(removed=1 if info["before"] != len(st.load_announcements().get("items", [])) else 0)


# ══════════════════════════════════════════════════════════
# 编辑器登录（口令校验，前端存 localStorage）
# ══════════════════════════════════════════════════════════
@router.post("/api/edit/login")
async def edit_login(request: Request):
    body = await request.json()
    if _is_editor(request, body.get("token")):
        return ok(editor=s(body.get("editor"), 40) or "匿名")
    return bad("口令不对", 401)


@router.get("/api/edit/ping")
async def edit_ping(request: Request, x_edit_token: str | None = Header(default=None)):
    """编辑器用它判断口令还有效没（以及是否有口令保护）。"""
    st = _store(request)
    return ok(protected=bool(_token(request)), authed=_is_editor(request, x_edit_token),
              stats=st.stats())
