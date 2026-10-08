# -*- coding: utf-8 -*-
"""网站布局稳定性回归（2026-10-06 重写布局后新立）。

要证明的三件事：
  1) **卡片零重叠** —— 同一视图里任意两张卡的矩形不相交（含边界容差）；
  2) **只增不改** —— 新增一个角色 / 新增一条关系之后，原有卡片的坐标**一个像素都不动**；
  3) **人工微调可持久化** —— 拖动换位写进 `/api/layout`，刷新后仍在。

跑法（先起本地服务）：
    .venv\\Scripts\\python.exe server\\app.py            # 127.0.0.1:8788（数据用 server/data）
    .venv\\Scripts\\python.exe .tmp\\test_layout_stable.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()
PROBE_NAME = "布局探针"
OUT = ROOT / ".tmp" / "shots" / "layout"
GROUP = "阴阳差事录 超自然怪谈"
NEW_ID = "zz_layout_probe"

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def wait_for(drv, js, timeout=30.0, step=0.25):
    end = time.time() + timeout
    while time.time() < end:
        try:
            v = drv.execute_script(js)
        except Exception:
            v = None
        if v:
            return v
        time.sleep(step)
    raise TimeoutError(js)


def enter(drv, group: str):
    """进卡片网并等它画完。

    ⚠️ 先 `get(BASE)` 再落 hash：只改 hash 的导航**不会重新拉 /api/data**，
       于是"服务器刚加的角色"在页面上看不见（第一次跑测试就被这条坑了）。
    """
    drv.get(BASE + "?r=" + str(int(time.time() * 1000)))     # 强制整页重载（只改 hash 不会重拉数据）
    wait_for(drv, "return !!window.NET && (window.NET.chars||[]).length>0")
    drv.get(BASE + "#/g/" + group)
    wait_for(drv, "const b=document.querySelector('#boot');"
                  "return !b || getComputedStyle(b).display==='none'", 40)
    ok = True
    try:
        wait_for(drv, "return document.querySelectorAll('#cards .card').length>0", 10)
    except TimeoutError:
        ok = False
        drv.execute_script("window.openEntity(arguments[0])", group)
        wait_for(drv, "return document.querySelectorAll('#cards .card').length>0", 20)
    time.sleep(1.2)                    # 等入场动画与 fitBox 稳定
    return ok


def snapshot(drv):
    """捞出每张卡的 id / 内联样式坐标 / 屏幕矩形。

    ⚠️ 重叠判定用 `left/top`（布局坐标，卡片是 CW×CHh），**不用屏幕矩形**：
       fitBox 会给世界加 scale，正交缩放一样能算出"屏幕重叠"，但那是缩放后的视觉，
       不是布局重叠；而且动画途中量矩形还会受 transform 影响（踩过一次误判）。"""
    return drv.execute_script("""
      const out = [];
      document.querySelectorAll('#cards .card').forEach(el => {
        const r = el.getBoundingClientRect();
        out.push({ id: el.dataset.id, left: parseFloat(el.style.left)||0, top: parseFloat(el.style.top)||0,
                   w: r.width, h: r.height, sl: r.left, st: r.top });
      });
      return out;
    """)


def overlap_report(cards, cw=120, chh=180):
    """按**布局坐标**两两比对（左闭右开、留 1px 容差）。"""
    bad = []
    for i in range(len(cards)):
        for j in range(i + 1, len(cards)):
            a, b = cards[i], cards[j]
            dx = abs(a["left"] - b["left"])
            dy = abs(a["top"] - b["top"])
            if dx < cw - 1 and dy < chh - 1:
                bad.append((a["id"], b["id"], round(cw - dx, 1), round(chh - dy, 1)))
    return bad


def api(method: str, path: str, body=None):
    import urllib.request
    req = urllib.request.Request(BASE.rstrip("/") + path, method=method)
    req.add_header("X-Edit-Token", TOKEN)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def cleanup():
    try:
        api("DELETE", f"/api/edit/char/{NEW_ID}")
    except Exception:
        pass


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    OUT.mkdir(parents=True, exist_ok=True)
    cleanup()
    # 每次从**干净账本**开始：上一次跑测试留下的手改位置会污染下一次（绝对值 vs 偏移的旧账本尤其如此）
    api("POST", "/api/layout", {"reset": True, "_editor": "layout-test"})
    drv = m.build_driver(1500, 950)
    try:
        drv.set_page_load_timeout(60)
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.set_window_size(1500, 950)
        # ⚠️ 布局账本只在**开跑时清一次**：槽位账本要跟着这次会话活着。
        #    每次重载都清 = 每次重新按哈希分配槽位，那就永远测不出「只增不改」。
        drv.get(BASE)
        drv.execute_script("try{localStorage.removeItem('trpg-net-layout');"
                           "localStorage.removeItem('trpg-net-slots');}catch(e){}")
        # 拖动测试要写回服务器 → 先“登录”一次编辑器（等价于编辑者已登录）
        drv.execute_script("localStorage.setItem('trpg-edit-token', arguments[0]);", TOKEN)

        print("=== 1. 基线：卡片零重叠 ===")
        route_ok = enter(drv, GROUP)
        chk("深链 #/g/<团> 能直接渲染卡片网（路由无短路）", route_ok, "未渲染，已用兜底 openEntity")
        base = snapshot(drv)
        chk("卡片网画出来了", len(base) > 5, f"{len(base)} 张")
        bad = overlap_report(base)
        chk("基线无重叠", not bad, bad[:3] if bad else "")
        drv.save_screenshot(str(OUT / "1_baseline.png"))

        print("=== 2. 加一个新角色：已有卡片必须原地不动 ===")
        # ⚠️ 新角色要先有一条关系才会被「选角」收进站点（select_site_scope 的口径），
        #    否则它在 /api/data?scope=site 里根本不出现，断言就没意义。
        api("POST", "/api/edit/char", {"id": NEW_ID, "name": PROBE_NAME,
                                       "groups": [GROUP], "tags": ["NPC"], "identity": "布局稳定性测试用",
                                       "note": "由 .tmp/test_layout_stable.py 临时创建", "_editor": "layout-test"})
        api("POST", "/api/edit/rel", {"from": NEW_ID, "to": "yy_yuxiuli", "type": "同伙",
                                      "strength": "中", "event": "布局稳定性测试（第1条）", "_editor": "layout-test"})
        api("POST", "/api/edit/rel", {"from": NEW_ID, "to": "yy_liulong", "type": "同伙",
                                      "strength": "中", "event": "布局稳定性测试（第0条）", "_editor": "layout-test"})
        scope = api("GET", "/api/data?scope=site")
        chk("探针角色已被选角收进站点数据", any(c["id"] == NEW_ID for c in scope["chars"]),
            f"{len(scope['chars'])} 人")
        enter(drv, GROUP)
        after = snapshot(drv)
        chk("新角色进来了", any(c["id"] == NEW_ID for c in after), f"{len(after)} 张")
        old_ids = {c["id"] for c in base}
        moved = []
        for c in after:
            if c["id"] in old_ids:
                prev = next(x for x in base if x["id"] == c["id"])
                if abs(prev["left"] - c["left"]) > 0.6 or abs(prev["top"] - c["top"]) > 0.6:
                    moved.append((c["id"], prev["left"], c["left"], prev["top"], c["top"]))
        chk("新增角色后**零张**老卡移位", not moved, moved[:3] if moved else "")
        bad2 = overlap_report(after)
        chk("加人后仍然零重叠", not bad2, bad2[:3] if bad2 else "")
        drv.save_screenshot(str(OUT / "2_after_new_char.png"))

        print("=== 3. 再加一条关系：位置同样不能动 ===")
        api("POST", "/api/edit/rel", {"from": NEW_ID, "to": "yy_zhixing", "type": "同伙",
                                      "strength": "中", "event": "布局稳定性测试（第2条）", "_editor": "layout-test"})
        enter(drv, GROUP)
        after2 = snapshot(drv)
        moved2 = []
        for c in after2:
            if c["id"] in old_ids:
                prev = next(x for x in base if x["id"] == c["id"])
                if abs(prev["left"] - c["left"]) > 0.6 or abs(prev["top"] - c["top"]) > 0.6:
                    moved2.append(c["id"])
        chk("新增关系后**零张**老卡移位", not moved2, moved2[:3] if moved2 else "")
        chk("加关系后仍然零重叠", not overlap_report(after2), "")
        drv.save_screenshot(str(OUT / "3_after_new_rel.png"))

        print("=== 4. 拖动换位 → 写回服务器 → 刷新仍在 ===")
        api("POST", "/api/layout", {"reset": True, "_editor": "layout-test"})   # 只清人工偏移，**不清槽位账本**
        drv.execute_script("localStorage.removeItem('trpg-net-layout');")
        enter(drv, GROUP)
        drv.execute_script("localStorage.setItem('trpg-edit-token', arguments[0]);"
                           "localStorage.setItem('trpg_edit_token', arguments[0]);", TOKEN)
        moved_ok = drv.execute_script("""
          const cards = [...document.querySelectorAll('#cards .card')];
          if (cards.length < 2) return 'need2';
          const a = cards[0], b = cards[1];
          const ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
          const ida = a.dataset.id;
          const press = (el, x, y, type) => el.dispatchEvent(new PointerEvent(type, {
            bubbles: true, cancelable: true, pointerId: 1, pointerType: 'mouse', button: 0, buttons: 1,
            clientX: x, clientY: y }));
          press(a, ra.left + ra.width/2, ra.top + ra.height/2, 'pointerdown');
          press(a, ra.left + ra.width/2 + 12, ra.top + ra.height/2 + 12, 'pointermove');
          press(a, rb.left + rb.width/2, rb.top + rb.height/2, 'pointermove');
          press(a, rb.left + rb.width/2, rb.top + rb.height/2, 'pointerup');
          return ida;
        """)
        chk("拖动交互跑通（能拿到被拖的卡）", moved_ok not in (None, "need2"), moved_ok)
        time.sleep(1.2)                    # 等 POST /api/layout 落地
        adj_local = drv.execute_script("return (window.__layoutAdj||{}).pos||{}")
        chk("拖动结果已记进本地账本", bool(adj_local), list(adj_local.keys())[:3])
        layout = api("GET", "/api/layout")["layout"]
        chk("拖动已写进服务器布局账本", bool(layout.get("pos")), list(layout.get("pos", {}).keys())[:3])
        enter(drv, GROUP)
        after3 = snapshot(drv)
        dragged = [c for c in after3 if c["id"] == moved_ok]
        chk("刷新后仍然存在这张卡（位置由账本覆盖）", bool(dragged), moved_ok)
        bad3 = overlap_report(after3)
        chk("刷新后仍零重叠", not bad3, bad3[:3] if bad3 else "")
        drv.save_screenshot(str(OUT / "4_after_drag.png"))

        print("=== 5. 清场 ===")
        api("POST", "/api/layout", {"reset": True, "_editor": "layout-test"})
        drv.execute_script("localStorage.removeItem('trpg-net-layout');"
                           "localStorage.removeItem('trpg-edit-token');"
                           "localStorage.removeItem('trpg_edit_token');")
        cleanup()
        print(f"\n结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
        return 1 if FAIL else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
