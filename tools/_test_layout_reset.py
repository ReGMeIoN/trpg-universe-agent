# -*- coding: utf-8 -*-
"""拖动「撤销 / 复位」回归（2026-10-06）。

主人反馈：「拖出去之后放不回去了」→ 本轮加了三层保护，这条脚本逐条验证：
  1) **拖动可撤销**：拖一张卡 → 位置变了 → `Ctrl+Z`（或 ↶ 按钮）→ 回到原位；
  2) **单张复位**：双击卡片 → 这张卡回到自动槽位，别的卡不动；
  3) **一键复位**：工具栏 ⤾ → 所有手工挪动清空、全部回到自动位置；
  4) **界面入口存在**：↶ / ⤾ 两个按钮 + 帮助页里的说明；
  5) **复位后不留残影**：`localStorage` 里的 pos 清空，且零重叠。

跑法：先起服务（server/app.py），再
    .venv\\Scripts\\python.exe tools\\_test_layout_reset.py
"""
from __future__ import annotations

import importlib.util
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
GROUP = "阴阳差事录 超自然怪谈"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def reset_server_layout():
    req = urllib.request.Request(BASE.rstrip("/") + "/api/layout", method="POST")
    req.add_header("X-Edit-Token", TOKEN)
    req.add_header("Content-Type", "application/json")
    import json
    body = json.dumps({"reset": True, "_editor": "layout-reset-test"}).encode("utf-8")
    with urllib.request.urlopen(req, body, timeout=20) as r:
        r.read()


def enter(drv):
    drv.get(BASE + "?r=" + str(int(time.time() * 1000)))
    end = time.time() + 40
    while time.time() < end:
        if drv.execute_script("return !!(window.NET && (window.NET.chars||[]).length)"):
            break
        time.sleep(0.25)
    drv.execute_script("try{localStorage.removeItem('trpg-net-layout');"
                       "localStorage.removeItem('trpg-net-slots');}catch(e){}")
    drv.execute_script("localStorage.setItem('trpg-edit-token', arguments[0]);", TOKEN)
    drv.get(BASE + "?r=%d#/g/%s" % (int(time.time() * 1000), GROUP))
    end = time.time() + 40
    while time.time() < end:
        if drv.execute_script("return document.querySelectorAll('#cards .card').length > 0"):
            break
        time.sleep(0.25)
    time.sleep(1.4)


def coords(drv):
    return drv.execute_script("""
      var o = {};
      document.querySelectorAll('#cards .card').forEach(function (el) {
        o[el.dataset.id] = [Math.round(parseFloat(el.style.left) || 0),
                            Math.round(parseFloat(el.style.top) || 0)];
      });
      return o;
    """)


def dups(o):
    seen, bad = {}, []
    for k, v in o.items():
        key = (v[0], v[1])
        if key in seen:
            bad.append((seen[key], k))
        seen[key] = k
    return bad


def drag_first(drv):
    """把第一张卡拖到第二张卡身上，返回被拖的 id。

    ⚠️ `pointerup` 必须派发到**被拖的那个元素**上 —— 真浏览器里指针捕获会把它送回去；
       之前图省事派发到目标卡上，结果 pointerup 根本没进到拖动元素的 handler，
       于是"拖了但账本没写"，白白误判成功能坏了（2026-09-06 回归踩到）。
    """
    return drv.execute_script("""
      var cards = [...document.querySelectorAll('#cards .card')];
      if (cards.length < 2) return null;
      var a = cards[0], b = cards[1];
      var ra = a.getBoundingClientRect(), rb = b.getBoundingClientRect();
      function press(el, x, y, t) {
        el.dispatchEvent(new PointerEvent(t, { bubbles: true, cancelable: true, pointerId: 1,
          pointerType: 'mouse', button: 0, buttons: 1, clientX: x, clientY: y }));
      }
      press(a, ra.left + ra.width/2, ra.top + ra.height/2, 'pointerdown');
      press(a, ra.left + ra.width/2 + 12, ra.top + ra.height/2 + 12, 'pointermove');
      press(a, rb.left + rb.width/2, rb.top + rb.height/2, 'pointermove');
      press(a, rb.left + rb.width/2, rb.top + rb.height/2, 'pointerup');
      return a.dataset.id;
    """)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    reset_server_layout()
    drv = m.build_driver(1500, 950)
    try:
        drv.set_page_load_timeout(60)
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        # ⚠️ 一定要清磁盘缓存：否则浏览器可能继续跑**上一版的 app.js**
        #    （表现是"函数明明写了却 undefined"，2026-10-06 在这儿卡了半天）
        drv.execute_cdp_cmd("Network.clearBrowserCache", {})
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        enter(drv)

        print("=== 0. 界面入口 ===")
        ui = drv.execute_script("""
          return { undo: !!document.querySelector('#btnUndo'),
                   reset: !!document.querySelector('#btnReset'),
                   help: (document.querySelector('#helpsheet')||{}).innerHTML || '' };
        """)
        chk("工具栏有「↶ 撤销」按钮", ui.get("undo"))
        chk("工具栏有「⤾ 复位排版」按钮", ui.get("reset"))
        chk("帮助页写了拖动/复位/撤销说明",
            ("复位" in ui.get("help", "")) and ("撤销" in ui.get("help", "")))

        print("=== 1. 拖动 → 位置变了 ===")
        base = coords(drv)
        dragged = drag_first(drv)
        time.sleep(1.2)
        after = coords(drv)
        chk("拖动生效（有卡换位）", bool(dragged) and after.get(dragged) != base.get(dragged),
            f"{dragged}: {base.get(dragged)} -> {after.get(dragged)}")
        chk("拖动后零重叠", not dups(after), dups(after)[:2])
        st = drv.execute_script("return { n: Object.keys((window.__layoutAdj||{}).pos||{}).length, "
                                "undoDisabled: (document.querySelector('#btnUndo')||{}).disabled };")
        chk("账本里记了 1 处手工位置", st.get("n") == 1, st)
        chk("「撤销」按钮此时可用", st.get("undoDisabled") is False)

        print("=== 2. Ctrl+Z 撤销上一次拖动 ===")
        # ⚠️ 要在**捕获阶段**监听才收得到合成事件（真浏览器里文档级 keydown 在冒泡阶段就够，
        #    但派发到 document 的合成事件只有捕获监听器会响）—— 2026-10-06 踩过。
        drv.execute_script("""
          window.__z = false;
          document.addEventListener('keydown', function (e) {
            if (e.ctrlKey && String(e.key).toLowerCase() === 'z') window.__z = true;
          }, true);
          document.dispatchEvent(new KeyboardEvent('keydown',
            { key: 'z', ctrlKey: true, bubbles: true, cancelable: true }));
        """)
        time.sleep(1.3)
        seen = drv.execute_script("return !!window.__z")
        undone = coords(drv)
        chk("Ctrl+Z 事件确实到达了页面", seen, "")
        chk("撤销后回到原位", undone.get(dragged) == base.get(dragged),
            f"期望 {base.get(dragged)}，实际 {undone.get(dragged)}")
        st2 = drv.execute_script("return Object.keys((window.__layoutAdj||{}).pos||{}).length")
        chk("账本里的手工位置被清掉", st2 == 0, st2)

        print("=== 3. 单张复位（双击） ===")
        dragged2 = drag_first(drv)
        time.sleep(1.2)
        mid = coords(drv)
        chk("再次拖动生效", mid.get(dragged2) != base.get(dragged2),
            f"{mid.get(dragged2)} vs {base.get(dragged2)}")
        drv.execute_script("""
          var el = document.querySelector('#cards .card[data-id="' + arguments[0] + '"]');
          el.dispatchEvent(new MouseEvent('dblclick', { bubbles: true, cancelable: true }));
        """, dragged2)
        time.sleep(1.2)
        single = coords(drv)
        chk("双击后这张卡回到自动位置", single.get(dragged2) == base.get(dragged2),
            f"期望 {base.get(dragged2)}，实际 {single.get(dragged2)}")
        others_moved = [k for k in base if k != dragged2 and k in single and base[k] != single[k]]
        chk("其它卡片没被连累", not others_moved, others_moved[:3])

        print("=== 4. 一键复位全部 ===")
        # 拖两张，造出两条手工位置
        d1 = drag_first(drv)
        time.sleep(0.9)
        d2 = drag_first(drv)
        time.sleep(1.2)
        n_before = drv.execute_script("return Object.keys((window.__layoutAdj||{}).pos||{}).length")
        chk("现在有手工位置（>=1）", n_before >= 1, n_before)
        drv.execute_script("document.querySelector('#btnReset').click()")
        time.sleep(1.3)
        n_after = drv.execute_script("return Object.keys((window.__layoutAdj||{}).pos||{}).length")
        chk("一键复位后账本清空", n_after == 0, n_after)
        final = coords(drv)
        moved = [k for k in base if k in final and base[k] != final[k]]
        chk("所有卡片都回到自动位置", not moved, moved[:4])
        chk("复位后零重叠", not dups(final), dups(final)[:2])

        print("=== 5. 复位已同步到服务器 ===")
        import json
        time.sleep(1.2)                    # 等 POST /api/layout 落地（它是异步发的）
        req = urllib.request.Request(BASE.rstrip("/") + "/api/layout")
        req.add_header("X-Edit-Token", TOKEN)
        with urllib.request.urlopen(req, timeout=20) as r:
            lay = (json.loads(r.read().decode("utf-8")) or {}).get("layout") or {}
        chk("服务器账本里的手工位置也清空了", not (lay.get("pos") or {}), list((lay.get("pos") or {}).keys())[:3])

        drv.save_screenshot(str(ROOT / ".tmp" / "shots" / "layout_reset.png"))
        print("\n结果: %d 通过 / %d 失败" % (len(PASS), len(FAIL)))
        return 1 if FAIL else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
