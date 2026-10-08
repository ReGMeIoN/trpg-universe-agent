# -*- coding: utf-8 -*-
"""通用「三选一」挑图页生成器（不依赖任何站点，产物放 .trpg/pickpage/ 下，不发布）。

和 `build_site.py` 里的 build_pickpage 是同一个思路，但**与团无关**：
只认「一批候选目录 + 一份锚点表（可选，用来在页面上显示中文外貌描述）」。

用法:
    python tools/_build_pickpage.py \
        --dir  "<NAI库>\\archive\\<批次目录>" \
        --looks "<NAI库>\\trpg_looks_<团>.py" \
        --out   ".trpg\\pickpage\\<批次>-pick.html" \
        --title "两团 NPC 立绘三选一"

主人挑完点「导出 picks」→ 得到 `_picks_portrait.json`（形如 {"<角色id>": "b"}）
→ 再写一个把 picks 落到数据里的脚本（读 `_picks_portrait.json` 后写回 characters.json）。
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
THUMB_W, THUMB_H = 420, 613          # 832×1216 的等比缩略

TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>__TITLE__</title>
<style>
:root{--ink:#07080b;--rule:#232833;--gold:#c9a961;--paper:#e8e9ec;--dim:#878c98}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
 font:14.5px/1.8 "Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif}
header{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:18px;padding:14px 24px;
 background:rgba(7,8,11,.96);border-bottom:1px solid var(--rule);backdrop-filter:blur(10px)}
header h1{margin:0;font-size:16px;letter-spacing:.1em}
header .sp{margin-left:auto;font-size:12.5px;color:var(--dim)}
header button{padding:9px 16px;background:transparent;border:1px solid var(--gold);color:var(--gold);
 cursor:pointer;font-size:13px;letter-spacing:.1em}
header button:hover{background:var(--gold);color:var(--ink)}
main{max-width:1500px;margin:0 auto;padding:26px 24px 140px}
.group{margin:38px 0 0;border-top:1px solid var(--rule);padding-top:18px}
.group>h2{margin:0 0 14px;font-size:15px;letter-spacing:.14em;color:var(--gold);
 font-weight:500;display:flex;align-items:center;gap:12px}
.group>h2 s{display:block;flex:1;height:1px;background:var(--rule);text-decoration:none}
.scene{margin:0 0 30px;padding-top:12px;border-top:1px dashed rgba(35,40,51,.8)}
.scene h3{margin:0 0 4px;font-size:14px;letter-spacing:.06em;font-weight:500}
.scene h3 em{font-style:normal;color:var(--dim);font-size:12px;margin-left:8px;letter-spacing:0}
.scene .hint{font-size:11.5px;color:var(--dim);margin-bottom:8px}
.scene .desc{font-size:12.5px;color:#b9bec9;background:#0c0e13;border-left:2px solid var(--rule);
 padding:8px 12px;margin:0 0 12px;white-space:pre-wrap}
.row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
figure{margin:0;border:1px solid var(--rule);cursor:pointer;position:relative;overflow:hidden;background:#0c0e13}
figure img{width:100%;display:block;aspect-ratio:420/613;object-fit:cover;object-position:top center}
figure figcaption{padding:8px 10px;font:11px/1 monospace;letter-spacing:.16em;color:var(--dim);
 display:flex;gap:10px;align-items:center}
figure .dot{width:9px;height:9px;border:1px solid var(--rule);display:inline-block;flex:0 0 auto}
figure:hover{border-color:#49515f}
figure.on{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold)}
figure.on .dot{background:var(--gold);border-color:var(--gold)}
figure.on figcaption{color:var(--gold)}
@media(max-width:900px){.row{grid-template-columns:1fr}}
.tip{position:fixed;left:0;right:0;bottom:0;padding:14px 24px;background:rgba(7,8,11,.97);
 border-top:1px solid var(--rule);font-size:12.5px;color:var(--dim);display:flex;gap:16px;flex-wrap:wrap}
.tip b{color:var(--gold);font-weight:500}
</style></head><body>
<header>
  <h1>__TITLE__</h1>
  <span class="sp" id="cnt"></span>
  <button id="exp">导出 __PICKSNAME__</button>
</header>
<main id="app"></main>
<div class="tip">
  点图选中（再点一下取消）→ 右上角导出 → 把文件交给
  <b>tools\_apply_npc_portraits.py --picks &lt;文件&gt;</b> 落地。
  <span id="stat"></span>
</div>
<script>
var DATA = __DATA__;
var PICKED = {};
var app = document.getElementById('app');
var TOTAL = 0;
DATA.groups.forEach(function(g){ TOTAL += g.items.length; });
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function groupHtml(g){
  var byKey = {}, order = [];
  g.items.forEach(function(it){
    if (!byKey[it.key]) { byKey[it.key] = []; order.push(it.key); }
    byKey[it.key].push(it);
  });
  var body = order.map(function(k){
    var list = byKey[k];
    var meta = DATA.meta[k] || {};
    var cur = PICKED[k] || meta.preselect || '';
    if (meta.preselect && !PICKED[k]) PICKED[k] = meta.preselect;
    var row = list.map(function(it){
      var on = (cur === it.tag) ? ' on' : '';
      return '<figure class="figure'+on+'" data-k="'+esc(k)+'" data-t="'+it.tag+'">'
        + '<img loading="lazy" src="'+esc(it.src)+'" alt="">'
        + '<figcaption><span class="dot"></span>'+esc(meta.name||k)+' _'+it.tag+'</figcaption></figure>';
    }).join('');
    return '<section class="scene"><h3>'+esc(meta.name||k)+'<em>'+esc(k)+'　'+esc(meta.kind||'')+'</em></h3>'
      + '<div class="hint">'+list.length+' 张候选 · 当前：'+(cur||'未选')+'</div>'
      + (meta.desc ? '<div class="desc">'+esc(meta.desc)+'</div>' : '')
      + '<div class="row">'+row+'</div></section>';
  }).join('');
  return '<section class="group"><h2>'+esc(g.title)+'<s></s></h2>'+body+'</section>';
}
function draw(){
  app.innerHTML = DATA.groups.map(groupHtml).join('');
  var n = Object.keys(PICKED).filter(function(k){return PICKED[k]}).length;
  document.getElementById('cnt').textContent = n + ' / ' + TOTAL + ' 已挑';
  document.getElementById('stat').textContent = n ? '（已挑 ' + n + ' 个）' : '';
}
app.addEventListener('click', function(e){
  var f = e.target.closest('figure'); if(!f) return;
  var k = f.dataset.k, t = f.dataset.t;
  if (PICKED[k] === t) delete PICKED[k]; else PICKED[k] = t;
  draw();
});
document.getElementById('exp').addEventListener('click', function(){
  var blob = new Blob([JSON.stringify(PICKED, null, 1)], {type:'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = '__PICKSNAME__';
  document.body.appendChild(a); a.click(); a.remove();
});
draw();
</script></body></html>
"""


def load_looks(path: Path | None) -> dict:
    if not path or not path.is_file():
        return {}
    spec = importlib.util.spec_from_file_location("_looks_mod", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    return dict(getattr(mod, "LOOKS", {}) or {})


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    a = sys.argv
    src = Path(a[a.index("--dir") + 1])
    out = Path(a[a.index("--out") + 1])
    if not out.is_absolute():
        out = ROOT / out
    title = a[a.index("--title") + 1] if "--title" in a else "立绘三选一"
    looks = load_looks(Path(a[a.index("--looks") + 1]) if "--looks" in a else None)
    picks_name = a[a.index("--picks-name") + 1] if "--picks-name" in a else "_picks_portrait.json"

    if not src.is_dir():
        print(f"!! 候选目录不存在: {src}")
        return 1
    thumb_dir = out.parent / "thumbs"
    thumb_dir.mkdir(parents=True, exist_ok=True)

    keys: dict[str, dict] = {}
    for p in sorted(src.glob("*_[abc].png")):
        cid, tag = p.stem[:-2], p.stem[-1]
        keys.setdefault(cid, {"group": None, "items": []})
        keys[cid]["items"].append((tag, p))

    groups: dict[str, dict] = {}
    meta: dict[str, dict] = {}
    made = 0
    for cid, info in keys.items():
        info_items = info["items"]
        lk = looks.get(cid) or {}
        gname = lk.get("group") or "未分组"
        g = groups.setdefault(gname, {"id": gname, "title": f"{gname}（{0} 人）", "items": []})
        for tag, p in info_items:
            thumb = thumb_dir / f"{cid}_{tag}.jpg"
            if not thumb.is_file() or thumb.stat().st_mtime < p.stat().st_mtime:
                try:
                    Image.open(p).convert("RGB").resize((THUMB_W, THUMB_H), Image.LANCZOS).save(
                        thumb, "JPEG", quality=82, optimize=True)
                    made += 1
                except Exception as e:  # noqa: BLE001
                    print(f"  !! 缩略图失败 {p.name}: {type(e).__name__}: {e}")
                    continue
            rel = Path("thumbs") / thumb.name
            g["items"].append({"key": cid, "tag": tag, "src": rel.as_posix()})
        meta[cid] = {"name": lk.get("name") or cid, "kind": lk.get("kind", ""),
                     "desc": lk.get("desc", ""), "preselect": "a"}

    total = sum(len(g["items"]) for g in groups.values())
    for g in groups.values():
        n = len({i["key"] for i in g["items"]})
        g["title"] = f"{g['title'].split('（')[0]}（{n} 人 × 3 候选）"
    order = list(groups.values())

    html = (TMPL.replace("__TITLE__", title)
            .replace("__PICKSNAME__", picks_name)
            .replace("__DATA__", json.dumps({"groups": order, "meta": meta}, ensure_ascii=False)))
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"挑图页: {out}")
    print(f"  分组 {len(order)} · 角色 {len(meta)} · 候选 {total} 张（新做缩略图 {made}）")
    for g in order:
        print(f"   - {g['title']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
