# -*- coding: utf-8 -*-
"""编辑器改版回归（2026-10-06）。

主人这轮的要求：
  1) 档案页**只留一个编辑入口**（原来三个「建议修改/建议关系/建议删除」全删）；
  2) 点它**直接跳这个角色的编辑器**（`#/edit/<id>`）；
  3) 编辑器里**有上传立绘的地方**；
  4) 编辑界面放在**角色立绘右边**，像看角色卡一样编辑。

跑法：先起服务（server/app.py，带 EDIT_TOKEN），再
    .venv\\Scripts\\python.exe tools\\_test_editor_card.py
"""
from __future__ import annotations

import base64
import importlib.util
import json
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path

ROOT = Path(Path(__file__).resolve().parents[1])
BASE = "http://127.0.0.1:8788/"
TOKEN = (ROOT / ".trpg" / "wiki_admin_token.txt").read_text(encoding="utf-8").strip()
CID = "td_dianyu"            # 一个真实存在、且**没有立绘**的角色 —— 正好用来测"补立绘"

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
        with urllib.request.urlopen(req, data, timeout=20) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {}


def png_bytes(w=240, h=360, color=(120, 90, 200)) -> bytes:
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + \
               struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    raw = b"".join(b"\x00" + bytes(color) * w for _ in range(h))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 6)) + chunk(b"IEND", b""))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    drv = m.build_driver(1500, 950)
    try:
        drv.execute_cdp_cmd("Network.setCacheDisabled", {"cacheDisabled": True})
        drv.execute_cdp_cmd("Emulation.setEmulatedMedia",
                            {"features": [{"name": "prefers-reduced-motion", "value": "no-preference"}]})
        # 先"登录"编辑器（改已有条目要口令；这一步等价于朋友拿到口令后填了一次）
        drv.get(BASE)
        drv.execute_script("localStorage.setItem('sjt-edit-token', arguments[0]);", TOKEN)
        time.sleep(1)

        print("=== 1. 档案页：只剩一个编辑入口 ===")
        drv.get(BASE + "?r=%d#/c/%s" % (int(time.time() * 1000), CID))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return document.querySelectorAll('#wikiBar [data-wb]').length > 0"):
                break
            time.sleep(0.25)
        time.sleep(4)
        bar = drv.execute_script("""
          var out = [];
          document.querySelectorAll('#wikiBar [data-wb]').forEach(function (b) {
            out.push([b.dataset.wb, b.textContent.trim()]);
          });
          return { btns: out, dosOn: (document.querySelector('#dossier')||{}).className };
        """)
        kinds = [b[0] for b in bar["btns"]]
        chk("档案页有操作条", bool(kinds), json.dumps(bar["btns"], ensure_ascii=False))
        chk("不再有「建议修改 / 建议关系 / 建议删除」",
            not any(k in ("del", "rel") for k in kinds) and
            not any("建议" in t for _, t in bar["btns"]), kinds)
        chk("有一个编辑入口（data-wb=edit）", "edit" in kinds, kinds)
        chk("档案页确实打开了", "on" in str(bar["dosOn"]), bar["dosOn"])

        print("=== 2. 点它 → 直接跳到这个角色的编辑器 ===")
        drv.execute_script("document.querySelector('#wikiBar [data-wb=\"edit\"]').click()")
        time.sleep(1.5)
        st = drv.execute_script("""
          return { hash: location.hash,
                   edOn: (document.querySelector('#editor')||{}).className,
                   dosOn: (document.querySelector('#dossier')||{}).className };
        """)
        chk("hash 跳到了 #/edit/<id>", ("#/edit/" + CID) in st["hash"], st["hash"])
        chk("编辑器面板已打开", "on" in str(st["edOn"]), st["edOn"])
        # 编辑器要能压住档案页（z-index），否则"看着像没打开"。
        # 取**卡片内容区**的中点（不是左上角 —— 那儿是标题栏，被头部的 h3 命中是正常的）
        cover = drv.execute_script("""
          var ed = document.querySelector('#editor .ed-card');
          if (!ed) return null;
          var r = ed.getBoundingClientRect();
          var x = r.left + r.width * 0.5, y = r.top + r.height * 0.5;
          var el = document.elementFromPoint(x, y);
          var inEditor = false, node = el;
          while (node && node !== document.body) {
            if (node.id === 'editor' || node.closest('#editor')) { inEditor = true; break; }
            node = node.parentNode;
          }
          return { top: el ? (el.className || el.tagName) : null, inEditor: inEditor };
        """)
        chk("编辑器在最上层（没被档案页盖住）",
            cover and cover.get("inEditor"), json.dumps(cover, ensure_ascii=False))

        print("=== 3. 卡面式布局：立绘在左、表单在右 ===")
        end = time.time() + 25
        while time.time() < end:
            if drv.execute_script("return !!document.querySelector('#edArtCard')"):
                break
            time.sleep(0.25)
        time.sleep(1)
        layout = drv.execute_script("""
          var art = document.querySelector('#edArtCard');
          var right = document.querySelector('#edRight');
          var wrap = document.querySelector('.ed-cardwrap');
          if (!art || !right || !wrap) return { ok: false };
          var ra = art.getBoundingClientRect(), rr = right.getBoundingClientRect();
          var cs = getComputedStyle(wrap);
          return { ok: true, display: cs.display,
                   artX: Math.round(ra.left), artW: Math.round(ra.width),
                   rightX: Math.round(rr.left), rightW: Math.round(rr.width),
                   artBeforeRight: ra.left + ra.width <= rr.left + 2 };
        """)
        chk("有卡面容器（左立绘 / 右表单）", layout.get("ok"), json.dumps(layout, ensure_ascii=False))
        chk("用的是两栏布局（grid）", layout.get("display") == "grid", layout.get("display"))
        chk("立绘在表单左边", layout.get("artBeforeRight") is True,
            f"art x={layout.get('artX')} w={layout.get('artW')} / right x={layout.get('rightX')}")

        print("=== 4. 有上传立绘的入口，且覆盖层能传上去 ===")
        up = drv.execute_script("""
          var b = document.querySelector('#edArtUp'), f = document.querySelector('#edArtFile');
          return { btn: !!b, btnText: b ? b.textContent.trim() : '',
                   file: !!f, accept: f ? f.getAttribute('accept') : '',
                   box: !!document.querySelector('.ed-artbox') };
        """)
        chk("编辑器里有「上传 / 更换立绘」按钮", up["btn"] and "立绘" in up["btnText"],
            json.dumps(up, ensure_ascii=False))
        chk("有 file input 且限定图片类型", up["file"] and "image" in str(up["accept"]), up["accept"])
        st_up, r_up = call("POST", "/api/upload/portrait", {
            "id": CID,
            "data": "data:image/png;base64," + base64.b64encode(png_bytes()).decode("ascii"),
            "_editor": "编辑器回归测试"})
        chk("上传接口（免口令）成功", st_up == 200 and r_up.get("ok"), f"{st_up} {r_up.get('error','')}")

        # 刷新页面，确认编辑器里显示的是新立绘
        drv.get(BASE + "?r=%d#/edit/%s" % (int(time.time() * 1000), CID))
        end = time.time() + 40
        while time.time() < end:
            if drv.execute_script("return !!document.querySelector('.ed-art-img')"):
                break
            time.sleep(0.3)
        time.sleep(1.5)
        art2 = drv.execute_script("""
          var im = document.querySelector('.ed-art-img');
          return { has: !!im, src: im ? im.getAttribute('src') : '',
                   name: (document.querySelector('.ed-artname')||{}).textContent || '' };
        """)
        chk("编辑器左侧显示出立绘", art2["has"], art2["src"])
        chk("立绘指向该角色的图", CID in str(art2["src"]), art2["src"])

        print("=== 5. 没有立绘的角色显示占位（未解封）===")
        st_p, d_p = call("GET", "/api/data?scope=all")
        noavatar = [c for c in (d_p.get("chars") or []) if not c.get("avatar")]
        chk("库里仍有缺立绘的角色", len(noavatar) > 0, f"{len(noavatar)} 人")
        if noavatar:
            cid2 = noavatar[0]["id"]
            drv.get(BASE + "?r=%d#/edit/%s" % (int(time.time() * 1000), cid2))
            time.sleep(7)
            ph = drv.execute_script("return { ph: !!document.querySelector('.ed-art-ph'), "
                                    "id: (document.querySelector('.ed-artid')||{}).textContent || '' };")
            chk(f"缺图角色显示占位块（{cid2}）", bool(ph["ph"]), json.dumps(ph, ensure_ascii=False))

        drv.save_screenshot(str(ROOT / ".tmp" / "shots" / "editor_card.png"))
        print("\n截图:", ROOT / ".tmp" / "shots" / "editor_card.png")
        print(f"结果: {len(PASS)} 通过 / {len(FAIL)} 失败")
        return 1 if FAIL else 0
    finally:
        try:
            drv.quit()
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
