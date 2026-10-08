# -*- coding: utf-8 -*-
"""拖动换位的轻量端到端验证（只查内联坐标，不查屏幕矩形）。

断言：
  1) 拖动后**内联 left/top 无重复**（布局坐标层面零重叠）；
  2) 拖动结果写进服务器布局账本；
  3) 刷新页面后，被拖的卡仍停在新位置，且仍然零重叠。
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
GROUP = "阴阳差事录 超自然怪谈"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()
CW, CHh = 120, 180

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def api(method, path, body=None):
    req = urllib.request.Request(BASE.rstrip("/") + path, method=method)
    req.add_header("X-Edit-Token", TOKEN)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, data, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def coords(drv):
    return drv.execute_script("""
      var o = {};
      document.querySelectorAll('#cards .card').forEach(function (el) {
        o[el.dataset.id] = [Math.round(parseFloat(el.style.left) || 0), Math.round(parseFloat(el.style.top) || 0)];
      });
      return o;
    """)


def dups(o):
    seen, bad = {}, []
    for k, v in o.items():
        key = (v[0], v[1])
        if key in seen:
            bad.append((seen[key], k, v))
        seen[key] = k
    return bad


def wait_view(drv, group, timeout=45):
    drv.get(BASE + "#/g/" + group)
    end = time.time() + timeout
    while time.time() < end:
        try:
            if drv.execute_script("return document.querySelectorAll('#cards .card').length > 0"):
                return True
        except Exception:
            pass
        time.sleep(0.25)
    return False


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    api("POST", "/api/layout", {"reset": True, "_editor": "drag-test"})
    drv = m.build_driver(1500, 950)
    try:
        drv.set_page_load_timeout(60)
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                            {"source": "try{localStorage.removeItem('trpg-net-layout');"
                                       "localStorage.removeItem('trpg-net-slots');}catch(e){}"})
        if not wait_view(drv, GROUP):
            chk("卡片网加载", False, "超时")
            return 1
        chk("卡片网加载", True)
        before = coords(drv)
        chk("基线零重叠", not dups(before), dups(before)[:2])
        # 拖动要写回服务器，需要编辑器口令（等价于"编辑者登录过"）
        drv.execute_script("localStorage.setItem('trpg-edit-token', arguments[0]);", TOKEN)

        info = drv.execute_script("""
          var cards = [...document.querySelectorAll('#cards .card')];
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
          return { id: a.dataset.id, pos: (window.__layoutAdj||{}).pos||{} };
        """)
        chk("拖动交互生效（有账本记录）", bool(info.get("pos")), list(info.get("pos", {}).keys()))
        time.sleep(1.0)
        after = coords(drv)
        chk("拖动后内联坐标零重叠", not dups(after), dups(after)[:2])
        chk("被拖的卡确实换位了",
            after.get(info["id"]) != before.get(info["id"]),
            f"{before.get(info['id'])} -> {after.get(info['id'])}")

        layout = api("GET", "/api/layout")["layout"]
        chk("拖动写进服务器账本", bool(layout.get("pos")), list(layout.get("pos", {}).keys()))

        if not wait_view(drv, GROUP):
            chk("刷新后加载", False)
        else:
            again = coords(drv)
            chk("刷新后内联坐标零重叠", not dups(again), dups(again)[:2])
            chk("刷新后被拖的卡仍在新位置",
                again.get(info["id"]) == after.get(info["id"]),
                f"expect {after.get(info['id'])} got {again.get(info['id'])}")

        api("POST", "/api/layout", {"reset": True, "_editor": "drag-test"})
        print(f"\n结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
        return 1 if FAIL else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
