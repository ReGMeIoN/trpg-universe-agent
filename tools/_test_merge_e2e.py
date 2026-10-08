# -*- coding: utf-8 -*-
"""角色合并功能回归（2026-10-06）。

服务端语义（要逐条验证）：
  · `src` 被并进 `dst`：**src 消失、dst 保留 id/立绘**；
  · **关系全部重定向** src → dst，重定向后撞上同 (from,to,type) 的重复边丢掉；
  · 自环（合并后 dst—dst）丢掉；
  · 别名 / 出场团 / 标签 / 事件 / 属性 → **并集**；
  · `identity` / `note` 两份都留（标注来源）；
  · 要口令（破坏性操作）；进版本历史（kind=char_merge）。

前端：编辑器里有「🔗 合并」按钮，弹窗能搜索、选中、显示预览。

跑法：先起服务（server/app.py，带 EDIT_TOKEN），再
    .venv\\Scripts\\python.exe tools\\_test_merge_e2e.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()
STAMP = str(int(time.time()))
SRC = "zz_merge_src_" + STAMP
DST = "zz_merge_dst_" + STAMP
HOST1 = "yy_yuxiuli"      # 阳差事录的既有角色（当关系的另一头）
HOST2 = "yy_liulong"
GROUP = "阴阳差事录 超自然怪谈"

spec = importlib.util.spec_from_file_location("_shot", ROOT / "tools" / "_shot.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

PASS, FAIL = [], []


def chk(name, cond, extra=""):
    (PASS if cond else FAIL).append(name)
    print(("  OK  " if cond else "  XX  ") + name + (("   " + str(extra)) if extra else ""))


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE.rstrip("/") + path, method=method)
    if token:
        req.add_header("X-Edit-Token", token)
    data = None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, data, timeout=25) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def all_chars():
    st, d = call("GET", "/api/data?scope=all")
    return {c["id"]: c for c in (d.get("chars") or [])}


def rels_between(ids):
    st, d = call("GET", "/api/data?scope=all")
    return [r for r in (d.get("rels") or []) if r.get("a") in ids or r.get("b") in ids]


def cleanup():
    for cid in (SRC, DST):
        call("DELETE", f"/api/edit/char/{cid}", token=TOKEN)


def setup():
    """造一对"同一个人被建了两份"的假角色：各带别名/团/标签/事件，各连一个宿主。"""
    call("POST", "/api/edit/char", {
        "id": SRC, "name": "合并测试甲", "aliases": ["甲甲"], "groups": [GROUP],
        "tags": ["NPC"], "identity": "甲的身份", "note": "甲的简介",
        "attrs": {"性别": "男"}, "_editor": "合并测试"}, token=TOKEN)
    call("POST", "/api/edit/char", {
        "id": DST, "name": "合并测试乙", "aliases": ["乙乙"], "groups": [GROUP],
        "tags": ["NPC"], "identity": "乙的身份", "note": "乙的简介",
        "attrs": {"性别": "男", "职业": "测试"}, "_editor": "合并测试"}, token=TOKEN)
    # src 连两个宿主；dst 连一个宿主，外加一条与 src 重复的边（用来验重定向去重）
    call("POST", "/api/edit/rel", {"from": SRC, "to": HOST1, "type": "同伙", "strength": "中",
                                   "event": "甲—宿主1", "_editor": "合并测试"}, token=TOKEN)
    call("POST", "/api/edit/rel", {"from": SRC, "to": HOST2, "type": "同伙", "strength": "中",
                                   "event": "甲—宿主2", "_editor": "合并测试"}, token=TOKEN)
    call("POST", "/api/edit/rel", {"from": DST, "to": HOST1, "type": "同伙", "strength": "中",
                                   "event": "乙—宿主1", "_editor": "合并测试"}, token=TOKEN)


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    cleanup()
    setup()
    before = all_chars()
    if SRC not in before or DST not in before:
        print("  XX  测试角色没建起来（检查服务是否在跑）")
        return 1

    print("=== 1. 合并前：两个节点各带自己的关系 ===")
    pre = rels_between({SRC, DST})
    pre_keys = sorted((r["a"], r["b"], r["type"]) for r in pre)
    chk("src 与 dst 都存在", SRC in before and DST in before)
    chk("合并前有 3 条边", len(pre) == 3, pre_keys)

    print("=== 2. 合并要口令 ===")
    st_no, r_no = call("POST", "/api/edit/merge", {"src": SRC, "dst": DST})
    chk("匿名合并被拒（401）", st_no == 401, f"{st_no}")
    st_self, r_self = call("POST", "/api/edit/merge", {"src": DST, "dst": DST}, token=TOKEN)
    chk("src == dst 被拒（400）", st_self == 400, f"{st_self}")

    print("=== 3. 执行合并 ===")
    st, r = call("POST", "/api/edit/merge", {"src": SRC, "dst": DST, "_editor": "合并测试"}, token=TOKEN)
    chk("合并成功", st == 200 and r.get("ok"), f"{st} {r.get('error','')}")
    mg = r.get("merged") or {}
    # src 名下有 2 条边（连两个宿主）→ 应该重定向 2 条
    chk("报告里写了关系重定向数（=src 名下的边数 2）", (mg.get("rels") or 0) == 2,
        json.dumps(mg, ensure_ascii=False))
    chk("报告里写了丢弃数（>=1：dst→宿主1 与重定向过来的撞了）",
        (mg.get("dropped") or 0) >= 1, json.dumps(mg, ensure_ascii=False))

    after = all_chars()
    print("=== 4. 合并后：src 消失、dst 保留 ===")
    chk("src 已被删掉", SRC not in after, SRC)
    chk("dst 还在", DST in after)
    d = after.get(DST) or {}
    chk("别名并集（含 src 的名字与别名）",
        all(x in (d.get("aliases") or []) for x in ["合并测试甲", "甲甲", "乙乙"]),
        d.get("aliases"))
    chk("属性并集（乙原有的 + 甲带过来的）",
        "职业" in (d.get("attrs") or {}) and "性别" in (d.get("attrs") or {}),
        json.dumps(d.get("attrs"), ensure_ascii=False))
    chk("note 两份都留（标注了来源）",
        "甲的简介" in (d.get("note") or "") and "乙的简介" in (d.get("note") or ""),
        (d.get("note") or "")[:80])
    chk("写了合并记录", "合并记录" in (d.get("note") or ""), "")
    chk("merged_from 记下了来源 id", SRC in (d.get("merged_from") or []), d.get("merged_from"))

    print("=== 5. 关系全部改指 dst，且没有重复 ===")
    post = rels_between({DST})
    keys = sorted((x["a"], x["b"], x["type"]) for x in post)
    has_src = any(SRC in (x["a"], x["b"]) for x in post)
    chk("没有任何边还指向 src", not has_src, keys)
    chk("dst 现在有 2 条边（宿主1 去重后 + 宿主2）", len(post) == 2, keys)
    chk("两条边都是 dst 的", all(DST in (x["a"], x["b"]) for x in post), keys)

    print("=== 6. 版本历史里有 char_merge ===")
    st_h, h = call("GET", "/api/history?limit=60", token=TOKEN)
    items = h.get("items") or []
    chk("历史里有 char_merge", any(x.get("kind") == "char_merge" for x in items),
        [x.get("kind") for x in items[:6]])

    print("=== 7. 前端：编辑器里有合并入口 ===")
    drv = m.build_driver(1500, 950)
    try:
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        drv.get(BASE)
        drv.execute_script("localStorage.setItem('sjt-edit-token', arguments[0]);", TOKEN)
        drv.get(BASE + "?r=%d#/edit/%s" % (int(time.time() * 1000), DST))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return !!document.querySelector('#edMergeBtn')"):
                break
            time.sleep(0.3)
        time.sleep(1.5)
        chk("工具栏有「🔗 合并」按钮",
            drv.execute_script("return !!document.querySelector('#edMergeBtn')"))
        drv.execute_script("document.querySelector('#edMergeBtn').click()")
        time.sleep(0.6)
        stm = drv.execute_script("""
          var el = document.querySelector('#edMerge');
          return { on: !!el && el.classList.contains('on'),
                   search: !!document.querySelector('#edMergeSearch'),
                   items: document.querySelectorAll('#edMergeList .ed-mitem').length,
                   go: !!document.querySelector('#edMergeGo'),
                   goDisabled: (document.querySelector('#edMergeGo')||{}).disabled };
        """)
        chk("合并弹窗打开了", stm.get("on"), json.dumps(stm, ensure_ascii=False))
        chk("有搜索框与候选列表", stm.get("search") and stm.get("items", 0) > 0, f"{stm.get('items')} 个候选")
        chk("没选角色前「合并进来」是禁用的", stm.get("goDisabled") is True, "")

        # 选第一个候选 → 预览出现、按钮可用
        drv.execute_script("document.querySelector('#edMergeList .ed-mitem').click()")
        time.sleep(0.4)
        stm2 = drv.execute_script("""
          return { prev: (document.querySelector('#edMergePrev')||{}).textContent || '',
                   goDisabled: (document.querySelector('#edMergeGo')||{}).disabled,
                   sel: document.querySelectorAll('#edMergeList .ed-mitem.on').length };
        """)
        chk("选中后显示预览", len(stm2.get("prev", "")) > 4, stm2.get("prev", "")[:60])
        chk("选中后按钮可用", stm2.get("goDisabled") is False, "")
        # 输入框过滤也要能跑
        drv.execute_script("""
          var i = document.querySelector('#edMergeSearch');
          i.value = '于秀丽'; i.dispatchEvent(new Event('input', {bubbles: true}));
        """)
        time.sleep(0.4)
        filt = drv.execute_script("return document.querySelectorAll('#edMergeList .ed-mitem').length")
        chk("搜索能过滤候选", filt >= 1, f"「于秀丽」→ {filt} 个")
        drv.save_screenshot(str(ROOT / ".tmp" / "shots" / "merge.png"))
        drv.execute_script("document.querySelector('#edMergeClose').click()")
        time.sleep(0.3)
        chk("能关掉弹窗",
            drv.execute_script("return !document.querySelector('#edMerge').classList.contains('on')"))
    finally:
        try:
            drv.quit()
        except Exception:
            pass

    cleanup()
    print("\n截图:", ROOT / ".tmp" / "shots" / "merge.png")
    print(f"结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
