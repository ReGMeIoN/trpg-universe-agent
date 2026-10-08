# -*- coding: utf-8 -*-
"""关系类型画像：受控词表归并之后才做得出来的统计（产物是一张离线 HTML）。

回答这些问题：
  · 全库的关系类型构成是什么？（以前 387 个乱串，做不了）
  · 每个团的"关系性格"有什么不同？（敌对多还是合作多）
  · **团内关系 vs 跨团关系** 的类型分布差异
  · 每个类型里最典型的代表（取强度最高、事件最长的边）
  · 强/中/弱 在类型上怎么分布

用法:
    python tools/_relation_profile.py [--out 产出\\关系类型画像.html]
"""
from __future__ import annotations

import os
import html
import json
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
OUT = WS / "\u4ea7\u51fa"                              # 产出

STR_ORDER = {"强": 0, "中": 1, "弱": 2, "": 3}
PALETTE = ["#c0392b", "#d35400", "#b7950b", "#27ae60", "#16a085", "#2980b9",
           "#8e44ad", "#c2185b", "#7f8c8d", "#2c3e50"]


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def bar(n: int, mx: int, color: str) -> str:
    w = 0 if not mx else max(2, int(220 * n / mx))
    return (f'<span class="bar" style="width:{w}px;background:{color}"></span>')


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    chars = {c["id"]: c for c in
             json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]}
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    vocab = json.loads((DATA / "\u5173\u7cfb\u7c7b\u578b\u53d7\u63a7\u8bcd\u8868.json")
                       .read_text(encoding="utf-8"))
    canon = vocab.get("canon") or {}
    name = {i: c.get("name") or i for i, c in chars.items()}

    types = Counter(r.get("type") or "?" for r in rels)
    raw_count = len({(r.get("type_raw") or r.get("type") or "").strip() for r in rels})
    mx = max(types.values()) if types else 1

    # 每个团的主导类型
    by_group: dict[str, Counter] = defaultdict(Counter)
    for r in rels:
        a, b = chars.get(r.get("from"), {}), chars.get(r.get("to"), {})
        for g in set(a.get("groups") or []) & set(b.get("groups") or []):
            by_group[g][r.get("type") or "?"] += 1
    # 跨团 vs 团内
    inside, cross = [], []
    for r in rels:
        a = set(chars.get(r.get("from"), {}).get("groups") or [])
        b = set(chars.get(r.get("to"), {}).get("groups") or [])
        (inside if a & b else cross).append(r)

    # 每类的代表
    reps: dict[str, list[dict]] = defaultdict(list)
    for r in rels:
        reps[r.get("type") or "?"].append(r)
    for t in reps:
        reps[t].sort(key=lambda r: (STR_ORDER.get(r.get("strength") or "", 9),
                                    -(len(r.get("event") or ""))))

    gmx = max((sum(c.values()) for c in by_group.values()), default=1)
    rows = []
    for g, c in sorted(by_group.items(), key=lambda kv: -sum(kv[1].values())):
        tot = sum(c.values())
        top = c.most_common(4)
        chips = "".join(
            f'<span class="chip">{esc(t)} <b>{n}</b></span>' for t, n in top)
        rows.append(
            f'<tr><td class="gname">{esc(g)}</td><td class="num">{tot}</td>'
            f'<td class="barcell">{bar(tot, gmx, "#2980b9")}</td>'
            f'<td>{chips}</td></tr>')

    def dist(lst: list[dict]) -> str:
        c = Counter(r.get("type") or "?" for r in lst)
        m = max(c.values()) if c else 1
        return "".join(
            f'<div class="drow"><span class="dt">{esc(t)}</span>'
            f'<span class="bar" style="width:{max(2, int(200 * n / m))}px;background:#8e44ad"></span>'
            f'<span class="dn">{n}</span></div>' for t, n in c.most_common(8))

    # 跨团边太少时（说明"跑团宇宙"其实高度同团），直接把清单列出来更有用
    cross_rows = []
    for r in sorted(cross, key=lambda r: STR_ORDER.get(r.get("strength") or "", 9)):
        a, b = chars.get(r.get("from"), {}), chars.get(r.get("to"), {})
        cross_rows.append(
            f'<tr><td>{esc(name.get(r["from"]))}<div class="ev">{"、".join(a.get("groups") or [])}</div></td>'
            f'<td class="tname">{esc(r.get("type"))}'
            f'<span class="s-{esc(r.get("strength") or "弱")}">{esc(r.get("strength") or "")}</span></td>'
            f'<td>{esc(name.get(r["to"]))}<div class="ev">{"、".join(b.get("groups") or [])}</div></td>'
            f'<td class="def">{esc((r.get("event") or "")[:120])}</td></tr>')

    type_rows = []
    for i, (t, n) in enumerate(types.most_common()):
        color = PALETTE[i % len(PALETTE)]
        ex = ""
        if reps[t]:
            r = reps[t][0]
            ex = (f'<div class="ex">{esc(name.get(r["from"], r["from"]))} → '
                  f'{esc(name.get(r["to"], r["to"]))}'
                  f'<span class="s-{esc(r.get("strength") or "弱")}">{esc(r.get("strength") or "")}</span>'
                  f'<span class="ev">{esc((r.get("event") or "")[:90])}</span></div>')
        detail = ""
        if t in ("其他",) and reps[t]:
            others = sorted({(r.get("type_raw") or "").strip() for r in reps[t]})
            detail = f'<div class="ev">原始写法：{esc("、".join(others))}</div>'
        type_rows.append(
            f'<tr><td class="tname" style="border-left:6px solid {color}">{esc(t)}</td>'
            f'<td class="num">{n}</td><td class="barcell">{bar(n, mx, color)}</td>'
            f'<td class="def">{esc(canon.get(t, ""))}{detail}{ex}</td></tr>')

    strong = Counter(r.get("strength") or "?" for r in rels)
    page = _PAGE.format(
        n_rel=len(rels), n_type=len(types), n_raw=raw_count,
        n_inside=len(inside), n_cross=len(cross),
        type_rows="".join(type_rows), group_rows="".join(rows),
        in_dist=dist(inside), cross_dist=dist(cross), cross_rows="".join(cross_rows),
        strong_txt=" / ".join(f"{k} {v}" for k, v in
                              sorted(strong.items(), key=lambda kv: STR_ORDER.get(kv[0], 9))),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    out = OUT / "\u5173\u7cfb\u7c7b\u578b\u753b\u50cf.html"      # 关系类型画像.html
    out.write_text(page, encoding="utf-8")
    print(f"出图: {out}")
    print(f"  边 {len(rels)} · 标准类型 {len(types)} · 原始写法 {raw_count}")
    print(f"  团内边 {len(inside)} / 跨团边 {len(cross)} · 强度 {dict(strong)}")
    print("  类型构成: " + "、".join(f"{t} {n}" for t, n in types.most_common(8)))
    return 0


_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>关系类型画像</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; background: #f7f5f0; margin: 0; color: #333; }}
h1 {{ text-align: center; padding: 22px 0 4px; font-size: 23px; margin: 0; }}
.sub {{ text-align: center; color: #888; font-size: 13px; margin: 6px 0 22px; }}
.wrap {{ width: 1200px; max-width: 96vw; margin: 0 auto 40px; }}
h2 {{ font-size: 16px; margin: 30px 0 10px; padding-left: 8px; border-left: 4px solid #c9a961; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
         box-shadow: 0 2px 8px rgba(0,0,0,.06); overflow: hidden; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 13px; text-align: left; vertical-align: top; }}
th {{ background: #4a4a4a; color: #fff; font-weight: 500; }}
.num {{ text-align: right; font-variant-numeric: tabular-nums; color: #555; width: 52px; }}
.barcell {{ width: 235px; }}
.bar {{ display: inline-block; height: 12px; border-radius: 6px; vertical-align: middle; }}
.tname {{ font-weight: 700; color: #b3541e; white-space: nowrap; width: 90px; }}
.def {{ color: #666; font-size: 12.5px; }}
.ex {{ margin-top: 4px; color: #444; font-size: 12px; }}
.ev {{ color: #999; font-size: 11.5px; margin-left: 8px; }}
.gname {{ font-weight: 600; width: 200px; }}
.chip {{ display:inline-block; background:#f0ece4; border-radius: 10px; padding: 1px 8px;
         margin: 0 4px 3px 0; font-size: 12px; }}
.chip b {{ color: #b3541e; }}
.card {{ background:#fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,.06); padding: 14px 18px; }}
.two {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
.drow {{ margin: 3px 0; }}
.dt {{ display:inline-block; width: 68px; font-size: 12.5px; }}
.dn {{ margin-left: 8px; color: #777; font-size: 12px; }}
.s-强 {{ margin-left:4px; background:#d32f2f; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-中 {{ margin-left:4px; background:#f57c00; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-弱 {{ margin-left:4px; background:#8e8e8e; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.foot {{ text-align:center; color:#aaa; font-size:11px; padding-bottom:24px; }}
</style></head><body>
<h1>关系类型画像</h1>
<div class="sub">
  受控词表归并之后才做得出来的统计 · {n_rel} 条边 · 原始写法 <b>{n_raw}</b> 种 → 标准类型 <b>{n_type}</b> 个
  · 强度 {strong_txt} · 由 trpg-agent 生成 {generated}
</div>
<div class="wrap">

<h2>一、类型构成（按条数）</h2>
<table>
  <tr><th>标准类型</th><th class="num">条数</th><th class="barcell">分布</th><th>定义与代表</th></tr>
  {type_rows}
</table>

<h2>二、各团的「关系性格」（团内关系）</h2>
<table>
  <tr><th>团</th><th class="num">条数</th><th class="barcell">规模</th><th>主导关系类型（Top4）</th></tr>
  {group_rows}
</table>

<h2>三、团内关系 vs 跨团关系</h2>
<div class="two">
  <div class="card">
    <div style="font-weight:700;margin-bottom:8px">团内关系（{n_inside} 条）</div>
    {in_dist}
  </div>
  <div class="card">
    <div style="font-weight:700;margin-bottom:8px">跨团关系（{n_cross} 条）</div>
    {cross_dist}
  </div>
</div>
<div class="def" style="margin: 10px 2px 14px">
  口径：<b>跨团关系 = 两人的出场团没有任何交集</b>。
  数字这么小本身就是结论——「跑团宇宙」的绝大多数关系其实都发生在团内，
  真正的跨界边寥寥无几，所以逐条列出来比画分布更有用。
</div>
<table>
  <tr><th style="width:20%">角色A（出场团）</th><th style="width:14%">关系</th>
      <th style="width:20%">角色B（出场团）</th><th>事件依据</th></tr>
  {cross_rows}
</table>

</div>
<div class="foot">由 trpg-agent 生成 · {generated}</div>
</body></html>"""


if __name__ == "__main__":
    raise SystemExit(main())
