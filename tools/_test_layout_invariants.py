# -*- coding: utf-8 -*-
"""布局不变量测试（函数级 · 单次注入版）。

为什么要"单次注入"：上一版把断言拆成十几次 execute_script，msedgedriver 在返回
带 `\\u0000` 的键名时崩过一次（而且每次都跨进程传一遍完整布局对象，又慢又脆）。
现在把整段测试塞进浏览器跑一次，只把结论（布尔 + 少量样本）传回来。

断言：
  1) 确定性 —— 同一团连算两次，坐标与槽位完全一致；
  2) 零重叠 —— 不同角色不落在同一格；
  3) 只增不改 —— 往团里加人、加关系，已有成员的**槽位号与坐标都不动**；
  4) 加塞 6 个人之后，最初那批人的位置仍然没动。

跑法：先起本地服务（server/app.py），再
    .venv\\Scripts\\python.exe .tmp\\test_layout_invariants.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
GROUP = "阴阳差事录 超自然怪谈"

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

SUITE = r"""
return (function () {
  var out = { steps: [], ok: 0, bad: 0 };
  function chk(name, cond, extra) {
    out.steps.push({ name: name, ok: !!cond, extra: extra === undefined ? '' : String(extra) });
    if (cond) out.ok++; else out.bad++;
  }
  var G = arguments[0], APP = window.APP, N = window.NET;
  if (!APP || !APP.layoutOf) return { fatal: 'APP not ready' };

  function clean(lay) {                      // 键里含 \u0000，先换成 | 免得序列化出问题
    var p = {}, s = {};
    Object.keys(lay.pos).forEach(function (k) { p[k] = lay.pos[k]; });
    Object.keys(lay.slotOf).forEach(function (k) { s[k.replace('\u0000', '|')] = lay.slotOf[k]; });
    return { pos: p, slots: s };
  }
  function cells(lay) {
    var seen = {}, dup = 0, n = 0;
    Object.keys(lay.pos).forEach(function (k) {
      n++; var c = lay.pos[k][0] + ':' + lay.pos[k][1];
      if (seen[c]) dup++; seen[c] = 1;
    });
    return { n: n, cells: Object.keys(seen).length, dup: dup };
  }
  function addChar(id, name, groups) {
    var c = { id: id, name: name, groups: groups, tags: ['NPC'], kind: 'NPC', played_by: '',
              identity: '', note: '', aliases: [], events: [], degree: 0, avatar: null,
              is_core: true, attrs: {} };
    N.chars.push(c); APP.CH.set(id, c); APP.ADJ.set(id, []);
    return c;
  }
  function addRel(a, b) {
    var r = { a: a, b: b, type: '\u540c\u4f19', raw: '', strength: '\u4e2d', event: 'test' };
    N.rels.push(r);
    if (APP.ADJ.get(a)) APP.ADJ.get(a).push({ o: b, r: r, out: true });
    if (APP.ADJ.get(b)) APP.ADJ.get(b).push({ o: a, r: r, out: false });
  }

  var A = clean(APP.layoutOf(G));
  var B = clean(APP.layoutOf(G));
  chk('\u786e\u5b9a\u6027\uff1a\u8fde\u7b97\u4e24\u6b21\u5750\u6807\u5b8c\u5168\u4e00\u81f4', JSON.stringify(A.pos) === JSON.stringify(B.pos));
  chk('\u786e\u5b9a\u6027\uff1a\u8fde\u7b97\u4e24\u6b21\u69fd\u4f4d\u5b8c\u5168\u4e00\u81f4', JSON.stringify(A.slots) === JSON.stringify(B.slots));
  var c0 = cells(A);
  chk('\u57fa\u7ebf\u96f6\u91cd\u53e0', c0.dup === 0, JSON.stringify(c0));
  chk('\u62ff\u5230\u4e86\u6210\u5458', Object.keys(A.pos).length > 5, Object.keys(A.pos).length + ' \u4eba');

  // 加一个新人
  addChar('zz_probe_a', '\u5e03\u5c40\u63a2\u9488\u7532', [G]);
  var C = clean(APP.layoutOf(G));
  var moved = Object.keys(A.slots).filter(function (k) { return C.slots[k] !== undefined && A.slots[k] !== C.slots[k]; });
  chk('\u52a0\u4e00\u4e2a\u65b0\u89d2\u8272\uff1a\u8001\u6210\u5458\u69fd\u4f4d\u96f6\u53d8\u5316', moved.length === 0, moved.slice(0, 5).join(','));
  var movedPos = Object.keys(A.pos).filter(function (k) { return C.pos[k] && (A.pos[k][0] !== C.pos[k][0] || A.pos[k][1] !== C.pos[k][1]); });
  chk('\u52a0\u4e00\u4e2a\u65b0\u89d2\u8272\uff1a\u8001\u6210\u5458\u5750\u6807\u96f6\u53d8\u5316', movedPos.length === 0, movedPos.slice(0, 5).join(','));
  chk('\u52a0\u4eba\u540e\u4ecd\u7136\u96f6\u91cd\u53e0', cells(C).dup === 0, JSON.stringify(cells(C)));

  // 加关系
  var ids = Object.keys(C.pos).filter(function (k) { return k.indexOf('\u5e03\u5c40\u63a2\u9488\u7532') !== 0; });
  addRel('zz_probe_a', ids[0]); addRel('zz_probe_a', ids[1]);
  var D = clean(APP.layoutOf(G));
  var moved2 = Object.keys(C.slots).filter(function (k) { return D.slots[k] !== undefined && C.slots[k] !== D.slots[k]; });
  chk('\u52a0\u4e24\u6761\u5173\u7cfb\uff1a\u69fd\u4f4d\u96f6\u53d8\u5316', moved2.length === 0, moved2.slice(0, 5).join(','));
  var movedPos2 = Object.keys(C.pos).filter(function (k) { return D.pos[k] && (C.pos[k][0] !== D.pos[k][0] || C.pos[k][1] !== D.pos[k][1]); });
  chk('\u52a0\u4e24\u6761\u5173\u7cfb\uff1a\u5750\u6807\u96f6\u53d8\u5316', movedPos2.length === 0, movedPos2.slice(0, 5).join(','));
  chk('\u52a0\u5173\u7cfb\u540e\u4ecd\u7136\u96f6\u91cd\u53e0', cells(D).dup === 0);

  // 再塞 5 个人
  for (var i = 0; i < 5; i++) addChar('zz_probe_' + i, '\u5e03\u5c40\u63a2\u9488' + i, [G]);
  var E = clean(APP.layoutOf(G));
  var moved3 = Object.keys(A.slots).filter(function (k) { return E.slots[k] !== undefined && A.slots[k] !== E.slots[k]; });
  chk('\u585e 6 \u4e2a\u4eba\u540e\uff1a\u6700\u521d\u90a3\u6279\u4eba\u69fd\u4f4d\u4ecd\u7136\u96f6\u53d8\u5316', moved3.length === 0, moved3.slice(0, 5).join(','));
  var ce = cells(E);
  chk('\u585e 6 \u4e2a\u4eba\u540e\u4ecd\u7136\u96f6\u91cd\u53e0', ce.dup === 0, JSON.stringify(ce));
  out.final = { cards: ce.n, cells: ce.cells, maxSlot: Math.max.apply(null, Object.keys(E.slots).map(function (k) { return E.slots[k]; })) };

  // 清掉探针
  ['zz_probe_a', 'zz_probe_0', 'zz_probe_1', 'zz_probe_2', 'zz_probe_3', 'zz_probe_4'].forEach(function (id) {
    N.chars = N.chars.filter(function (c) { return c.id !== id; });
    APP.CH.delete(id); APP.ADJ.delete(id);
    for (var j = N.rels.length - 1; j >= 0; j--) if (N.rels[j].a === id || N.rels[j].b === id) N.rels.splice(j, 1);
  });
  return out;
})(arguments[0]);
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    drv = m.build_driver(1500, 950)
    try:
        drv.set_page_load_timeout(60)
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                            {"source": "try{localStorage.removeItem('trpg-net-layout');"
                                       "localStorage.removeItem('trpg-net-slots');}catch(e){}"})
        drv.get(BASE)
        import time
        end = time.time() + 40
        ok = False
        while time.time() < end:
            if drv.execute_script("return !!(window.APP && window.APP.layoutOf)"):
                ok = True
                break
            time.sleep(0.25)
        if not ok:
            print("  XX  APP 没就绪")
            return 1
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("const b=document.querySelector('#boot');"
                                  "return !b || getComputedStyle(b).display==='none'"):
                break
            time.sleep(0.25)
        res = drv.execute_script(SUITE, GROUP)
        if res.get("fatal"):
            print("  XX  " + res["fatal"])
            return 1
        for st in res["steps"]:
            print(("  OK  " if st["ok"] else "  XX  ") + st["name"] + (("   " + st["extra"]) if st["extra"] else ""))
        print("  --  最终：" + json.dumps(res.get("final", {}), ensure_ascii=False))
        print(f"\n结果: {res['ok']} 通过 / {res['bad']} 失败")
        return 1 if res["bad"] else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
