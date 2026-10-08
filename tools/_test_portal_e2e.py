# -*- coding: utf-8 -*-
"""门户 / 免口令新增 / 立绘上传 / 公告 —— 端到端回归（本地 8788）。

要证明的四件事（2026-10-06 主人拍板的口径）：
  1) **新增条目不要口令**：匿名 POST /api/edit/char、/api/edit/rel 能建出来；
  2) **改已有条目仍然要口令**：匿名改同一个角色 → 401；
  3) **立绘上传不要口令**，且上传后 /api/data 里这个角色就带上 avatar；
  4) **公告能发**（无口令）、`/api/history` 里能看到新建记录，`#/portal` 页面能打开并列出。

跑法：先起服务（server/app.py），再
    .venv\\Scripts\\python.exe tools\\_test_portal_e2e.py
"""
from __future__ import annotations

import base64
import importlib.util
import io
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()
# ⚠️ 每次跑用**新 id**：否则上一轮残留的节点会让"新建"变成"更新"，就测不到 char_create 了
CID = "zz_portal_" + str(int(time.time()))

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def call(method, path, body=None, token=None, raw=False):
    req = urllib.request.Request(BASE.rstrip("/") + path, method=method)
    if token:
        req.add_header("X-Edit-Token", token)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=20) as r:
            payload = r.read()
            return r.status, (payload if raw else json.loads(payload.decode("utf-8")))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def png_bytes(w=200, h=300, color=(90, 140, 200)) -> bytes:
    """造一张纯色 PNG（不依赖 PIL，用 zlib 手写最小 PNG）。"""
    import struct
    import zlib

    def chunk(tag, data):
        c = struct.pack(">I", len(data)) + tag + data
        return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b""
    for _ in range(h):
        raw += b"\x00" + bytes(color) * w
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6))
            + chunk(b"IEND", b""))


def cleanup():
    call("DELETE", f"/api/edit/char/{CID}", token=TOKEN)
    st, r = call("GET", "/api/announce?limit=200")
    for it in (r.get("items") or []):
        if str(it.get("text", "")).startswith("回归测试公告"):
            call("POST", "/api/announce/delete", {"id": it.get("id")}, token=TOKEN)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    cleanup()

    print("=== 1. 新增条目不需要口令 ===")
    st, r = call("POST", "/api/edit/char", {
        "id": CID, "name": "门户探针", "groups": ["阴阳差事录 超自然怪谈"], "tags": ["NPC"],
        "identity": "门户回归测试", "note": "由 tools/_test_portal_e2e.py 临时创建", "_editor": "回归测试"
    })
    chk("匿名新建角色成功", st == 200 and r.get("ok") and r.get("created"), f"{st} {r.get('error','')}")
    st2, r2 = call("POST", "/api/edit/rel", {
        "from": CID, "to": "yy_yuxiuli", "type": "同伙", "strength": "中",
        "event": "门户回归测试", "_editor": "回归测试"
    })
    chk("匿名新建关系成功", st2 == 200 and r2.get("ok"), f"{st2} {r2.get('error','')}")

    print("=== 2. 改已有角色仍然要口令 ===")
    st3, r3 = call("POST", "/api/edit/char", {"id": CID, "name": "偷偷改名", "_editor": "坏人"})
    chk("匿名改已有角色被拒（401）", st3 == 401, f"{st3}")
    st4, r4 = call("POST", "/api/edit/char", {"id": CID, "name": "正经改名"}, token=TOKEN)
    chk("持口令改角色成功", st4 == 200 and r4.get("ok"), f"{st4}")
    st5, _ = call("DELETE", f"/api/edit/char/{CID}")
    chk("匿名删角色被拒（401）", st5 == 401, f"{st5}")

    print("=== 3. 立绘上传不需要口令，且立刻生效 ===")
    data_url = "data:image/png;base64," + base64.b64encode(png_bytes()).decode("ascii")
    st6, r6 = call("POST", "/api/upload/portrait", {"id": CID, "data": data_url, "_editor": "回归测试"})
    chk("匿名上传立绘成功", st6 == 200 and r6.get("ok"), f"{st6} {r6.get('error','')}")
    st7, d7 = call("GET", "/api/data?scope=all")
    hit = next((c for c in d7.get("chars", []) if c["id"] == CID), None)
    chk("上传后该角色带上 avatar", bool(hit and hit.get("avatar")), (hit or {}).get("avatar"))
    if hit and hit.get("avatar"):
        for k in ("thumb", "full"):
            u = hit["avatar"].get(k)
            stx, _ = call("GET", urlparse_path(u), raw=True)
            chk(f"立绘文件可访问（{k}）", stx == 200, f"{u} -> {stx}")

    print("=== 4. 公告：无口令可发，有口令可删 ===")
    st8, r8 = call("POST", "/api/announce", {"text": "回归测试公告：门户上线自检", "_editor": "回归测试"})
    chk("匿名发公告成功", st8 == 200 and r8.get("ok"), f"{st8} {r8.get('error','')}")
    st9, r9 = call("GET", "/api/announce?limit=10")
    chk("公告能读回来", any("回归测试公告" in str(x.get("text", "")) for x in (r9.get("items") or [])))
    nid = next((x["id"] for x in (r9.get("items") or []) if "回归测试公告" in str(x.get("text", ""))), None)
    st10, _ = call("POST", "/api/announce/delete", {"id": nid})
    chk("匿名删公告被拒（401）", st10 == 401, f"{st10}")
    st11, _ = call("POST", "/api/announce/delete", {"id": nid}, token=TOKEN)
    chk("持口令删公告成功", st11 == 200, f"{st11}")

    print("=== 5. 版本历史里能看到这些写入 ===")
    st12, r12 = call("GET", "/api/history?limit=300")
    items = r12.get("items") or r12.get("history") or []
    kinds = [x.get("kind") for x in items]
    chk("历史里有 char_create", "char_create" in kinds,
        f"共 {len(kinds)} 条 · 最近 6 条 {kinds[:6]}")
    chk("历史里有 portrait", "portrait" in kinds, "")
    chk("历史里有 rel_create", "rel_create" in kinds, "")
    chk("历史里有这位回归测试建立的角色", any(x.get("target") == CID for x in items), "")

    print("=== 6. 站点口径 = 全量（没立绘的也上）===")
    st13, d13 = call("GET", "/api/data?scope=site")
    n_site = len(d13.get("chars", []))
    no_av = sum(1 for c in d13.get("chars", []) if not c.get("avatar"))
    chk("站点口径是全量（>250 人）", n_site > 250, f"{n_site} 人")
    chk("没立绘的角色也在站点里（留空剪影）", no_av > 50, f"{no_av} 人无图")

    print("=== 7. 门户页在浏览器里能打开 ===")
    drv = m.build_driver(1400, 900)
    try:
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.get(BASE + "?r=" + str(int(time.time() * 1000)) + "#/portal")
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return !!(window.NET && (window.NET.chars||[]).length)"):
                break
            time.sleep(0.25)
        time.sleep(5.5)
        st14 = drv.execute_script("""
          var el = document.querySelector('#portal');
          return { on: !!el && el.classList.contains('on'),
                   rows: document.querySelectorAll('#pvRecent .pt-row').length,
                   tabs: !!document.querySelector('#ptNew') && !!document.querySelector('#ptAnn'),
                   nick: !!document.querySelector('#ptNick'),
                   home: (document.querySelector('#home')||{}).className };
        """)
        chk("门户面板打开（#/portal）", st14.get("on"), json.dumps(st14, ensure_ascii=False))
        chk("最近改动有内容", st14.get("rows", 0) > 0, f"{st14.get('rows')} 行")
        chk("首页没有盖住门户", "on" not in str(st14.get("home")), st14.get("home"))
        # 切到「新增条目」和「公告栏」
        drv.execute_script("document.querySelector('#ptNew').click()")
        time.sleep(0.5)
        dbg = drv.execute_script("""
          var v = document.querySelector('#pvNew');
          return { cls: v ? v.className : null,
                   pnId: !!document.querySelector('#pnId'),
                   file: !!document.querySelector('#pnFile'),
                   tabOn: document.querySelector('#ptNew').className };
        """)
        chk("新增条目页有表单 + 立绘上传", bool(dbg.get("pnId") and dbg.get("file") and "on" in str(dbg.get("cls"))),
            json.dumps(dbg, ensure_ascii=False))
        drv.execute_script("document.querySelector('#ptAnn').click()")
        time.sleep(0.5)
        dbg2 = drv.execute_script("""
          var v = document.querySelector('#pvAnn');
          return { cls: v ? v.className : null, ta: !!document.querySelector('#ptAnnText') };
        """)
        chk("公告栏页有发帖框", bool(dbg2.get("ta") and "on" in str(dbg2.get("cls"))),
            json.dumps(dbg2, ensure_ascii=False))
        drv.save_screenshot(str(ROOT / ".tmp" / "shots" / "portal.png"))
        # 点顶栏门户按钮也应能打开
        drv.get(BASE + "?r=" + str(int(time.time() * 1000)))
        time.sleep(5.5)
        drv.execute_script("document.querySelector('#btnPortal').click()")
        time.sleep(0.6)
        chk("顶栏 ☰ 按钮能打开门户",
            drv.execute_script("return document.querySelector('#portal').classList.contains('on')"))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    cleanup()
    print(f"\n结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
    return 1 if FAIL else 0


def urlparse_path(u: str) -> str:
    from urllib.parse import urlsplit
    return urlsplit(u).path or u


if __name__ == "__main__":
    raise SystemExit(main())
