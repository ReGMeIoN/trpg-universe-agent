# -*- coding: utf-8 -*-
"""团关系图 HTML(群像网状, 内联 SVG + 头像 + 点击弹窗详情)。

移植自既有 gen_net.py(已实盘验证): 无外部依赖(不依赖 ECharts/CDN), 离线可用。
配置: visualize.net_engine = legacy_svg(默认) | echarts(v0.3)
"""
from __future__ import annotations

import html
import json
import math
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.workspace import Workspace

STR_COLOR = {"强": "#d32f2f", "中": "#f57c00", "弱": "#9e9e9e"}
CANVAS_W, CANVAS_H = 1080, 880
RADIUS = 330
AVATAR = 76


def _esc(s: Any) -> str:
    return html.escape(str(s))


def _avatar_rel(c: dict[str, Any], ws: Workspace) -> str | None:
    """头像路径改写为相对产出目录的路径(原有数据里是相对库根的 `数据\\头像\\x.jpg`)。"""
    av = c.get("avatar")
    if not av:
        return None
    p = Path(str(av).replace("\\", "/"))
    try:
        rel = (ws.root / p).resolve().relative_to(ws.output.resolve())
        return "./" + rel.as_posix()
    except (ValueError, OSError):
        return "../" + p.as_posix()


def in_group(c: dict[str, Any], keyword: str) -> bool:
    return any(keyword in g for g in (c.get("groups") or []))


def build(ws: Workspace, group: str, out_name: str | None = None, exclude: set[str] | None = None) -> dict[str, Any]:
    chars_doc = json.loads(ws.data_file("characters").read_text(encoding="utf-8"))
    rels_doc = json.loads(ws.data_file("relations").read_text(encoding="utf-8"))
    chars = {c["id"]: c for c in chars_doc.get("characters", [])}
    rels = rels_doc.get("relations", [])
    exclude = exclude or set()

    # 主持人本人不入图(铁律 3): 由 tags/in_graph 决定
    def visible(c: dict[str, Any]) -> bool:
        if c["id"] in exclude:
            return False
        if c.get("in_graph") is False:
            return False
        return in_group(c, group)

    node_ids = [cid for cid, c in chars.items() if visible(c) and cid not in exclude]

    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for r in rels:
        a, b = r.get("from"), r.get("to")
        if a in node_ids and b in node_ids and a != b:
            key = tuple(sorted([a, b]))
            if key not in seen:
                seen.add(key)
                edges.append(r)

    cx, cy = CANVAS_W / 2, CANVAS_H / 2 - 10
    pos: dict[str, tuple[float, float]] = {}
    for i, cid in enumerate(node_ids):
        ang = -math.pi / 2 + 2 * math.pi * i / max(len(node_ids), 1)
        pos[cid] = (cx + RADIUS * math.cos(ang), cy + RADIUS * math.sin(ang))

    svg_edges: list[str] = []
    for e in edges:
        x1, y1 = pos[e["from"]]
        x2, y2 = pos[e["to"]]
        mx, my = (x1 + x2) / 2, (y1 + y2) / 2
        col = STR_COLOR.get(e.get("strength"), "#9e9e9e")
        width = 2 if e.get("strength") == "强" else 1.5
        svg_edges.append(
            f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{col}" '
            f'stroke-width="{width}" opacity="0.75"/>'
        )
        svg_edges.append(
            f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" font-size="10" fill="#666" '
            f'transform="translate(0,-5)">{_esc(e.get("type", ""))}</text>'
        )

    details: dict[str, Any] = {}
    for cid in node_ids:
        c = chars[cid]
        details[cid] = {
            "name": c.get("name", ""),
            "identity": c.get("identity", ""),
            "note": c.get("note", ""),
            "groups": c.get("groups", []),
            "avatar": _avatar_rel(c, ws),
            "played_by": c.get("played_by", "") or c.get("played_by_alt", ""),
            "events": c.get("events", []),
        }

    node_html: list[str] = []
    for cid in node_ids:
        c = chars[cid]
        x, y = pos[cid]
        av = _avatar_rel(c, ws)
        av_el = (
            f'<img src="{_esc(av)}" class="avatar clickable" onclick="openModal(\'{cid}\')" title="点击查看详情">'
            if av
            else f'<div class="avatar noimg clickable" onclick="openModal(\'{cid}\')" title="点击查看详情">?</div>'
        )
        cross = ' <span class="cross">跨</span>' if "跨团" in (c.get("tags") or []) else ""
        kp = ' <span class="kp">KP</span>' if "KP" in (c.get("tags") or []) else ""
        node_html.append(
            f'<div class="node" style="left:{x - 55:.0f}px;top:{y - 62:.0f}px">'
            f"{av_el}<div class=\"name\">{_esc(c['name'])}{cross}{kp}</div>"
            f'<div class="role">{_esc(str(c.get("identity", ""))[:12])}</div></div>'
        )

    rel_rows: list[str] = []
    for e in edges:
        a = chars.get(e["from"], {}).get("name", e["from"])
        b = chars.get(e["to"], {}).get("name", e["to"])
        rel_rows.append(
            f'<tr><td>{_esc(a)}</td>'
            f'<td class="rtype">{_esc(e.get("type", ""))}'
            f'<span class="s-{_esc(e.get("strength", "弱"))}">{_esc(e.get("strength", ""))}</span></td>'
            f'<td>{_esc(b)}</td><td class="event">{_esc(e.get("event", ""))}</td></tr>'
        )

    details_json = json.dumps(details, ensure_ascii=False).replace("</", "<\\/")
    page = _PAGE.format(
        title=_esc(group),
        subtitle=f"共 {len(node_ids)} 名角色 · {len(edges)} 条关系 · 点击头像查看角色详情 · 标「跨」=跨团",
        svg_edges="".join(svg_edges),
        nodes="".join(node_html),
        rel_rows="".join(rel_rows),
        n_edges=len(edges),
        details_json=details_json,
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )

    ws.output.mkdir(parents=True, exist_ok=True)
    out = ws.output / (out_name or f"{group}_关系图.html")
    out.write_text(page, encoding="utf-8")
    log.ok(f"关系图: {ws.rel(out)} ({len(node_ids)} 节点 / {len(edges)} 边)")
    return {"path": ws.rel(out), "nodes": len(node_ids), "edges": len(edges)}


_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{title} 关系网</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; background: #f7f5f0; margin: 0; color: #333; }}
h1 {{ text-align: center; padding: 20px 0 4px; font-size: 22px; }}
.sub {{ text-align: center; color: #888; font-size: 13px; margin-bottom: 18px; }}
.chart {{ position: relative; width: 1080px; height: 880px; margin: 0 auto; background: #fffdf8; border-radius: 12px; box-shadow: 0 2px 12px rgba(0,0,0,.06); }}
.chart svg {{ position: absolute; inset: 0; width: 100%; height: 100%; }}
.node {{ position: absolute; width: 110px; text-align: center; }}
.avatar {{ width: 76px; height: 76px; border-radius: 50%; object-fit: cover; border: 3px solid #fff; box-shadow: 0 2px 8px rgba(0,0,0,.25); display: block; margin: 0 auto; background: #ddd; }}
.noimg {{ line-height: 76px; color: #999; font-size: 26px; }}
.clickable {{ cursor: pointer; }}
.clickable:hover {{ transform: scale(1.08); transition: .15s; }}
.name {{ font-size: 12px; font-weight: 700; margin-top: 3px; line-height: 1.3; }}
.cross {{ background: #d32f2f; color: #fff; font-size: 9px; padding: 0 3px; border-radius: 3px; }}
.kp {{ background: #1565c0; color: #fff; font-size: 9px; padding: 0 3px; border-radius: 3px; }}
.role {{ font-size: 10px; color: #999; }}
.list {{ width: 1080px; margin: 24px auto 40px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.06); border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 13px; text-align: left; }}
th {{ background: #4a4a4a; color: #fff; }}
.rtype {{ font-weight: 700; color: #b3541e; }}
.s-强 {{ margin-left:4px; background:#d32f2f; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-中 {{ margin-left:4px; background:#f57c00; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-弱 {{ margin-left:4px; background:#8e8e8e; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.event {{ color: #777; font-size: 12px; }}
.overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 100; }}
.overlay.show {{ display: flex; align-items: center; justify-content: center; }}
.modal {{ background: #fff; width: 860px; max-width: 92vw; max-height: 88vh; border-radius: 14px; box-shadow: 0 8px 40px rgba(0,0,0,.35); display: flex; overflow: hidden; }}
.modal-left {{ width: 300px; min-width: 300px; background: #f0ece4; display: flex; align-items: center; justify-content: center; }}
.modal-left img {{ width: 100%; height: 100%; object-fit: contain; }}
.modal-left .noimg {{ font-size: 60px; color: #bbb; }}
.modal-right {{ flex: 1; padding: 22px 24px; overflow-y: auto; max-height: 88vh; }}
.modal-right h2 {{ margin: 0 0 6px; font-size: 22px; }}
.modal-right .ident {{ color: #8a6d3b; font-size: 13px; margin-bottom: 8px; }}
.modal-right .meta {{ font-size: 12px; color: #777; margin-bottom: 10px; }}
.modal-right .note {{ font-size: 13px; color: #444; background: #faf6ef; border-left: 3px solid #d4a017; padding: 8px 10px; border-radius: 4px; margin-bottom: 14px; }}
.ev-group {{ margin-bottom: 12px; }}
.ev-group .gname {{ font-size: 13px; font-weight: 700; color: #5e35b1; margin-bottom: 4px; }}
.ev-group ul {{ margin: 0; padding-left: 18px; }}
.ev-group li {{ font-size: 12.5px; line-height: 1.7; color: #444; }}
.close {{ position: absolute; top: 12px; right: 16px; font-size: 26px; cursor: pointer; color: #999; background: none; border: none; }}
.foot {{ text-align:center; color:#aaa; font-size:11px; padding-bottom:24px; }}
</style></head><body>
<h1>{title} 人物关系网（群像）</h1>
<div class="sub">{subtitle}</div>
<div class="chart">
<svg width="1080" height="880">{svg_edges}</svg>
{nodes}
</div>
<div class="list">
<h2 style="font-size:16px;margin:0 0 10px;">关系清单（{n_edges}条）</h2>
<table>
<tr><th style="width:15%">人物A</th><th style="width:22%">关系</th><th style="width:15%">人物B</th><th>事件依据</th></tr>
{rel_rows}
</table>
</div>
<div class="overlay" id="overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-left" id="mLeft"></div>
    <div class="modal-right" id="mRight"></div>
  </div>
</div>
<div class="foot">由 trpg-agent 生成 · {generated}</div>
<script>
const DETAILS = {details_json};
function openModal(id) {{
  const d = DETAILS[id];
  if (!d) return;
  document.getElementById('mLeft').innerHTML = d.avatar
    ? `<img src="${{d.avatar}}" alt="立绘">` : '<div class="noimg">❓</div>';
  let evHtml = '';
  for (const g of (d.events || [])) {{
    evHtml += `<div class="ev-group"><div class="gname">${{g.group}}</div><ul>` +
      (g.items || []).map(i => `<li>${{i}}</li>`).join('') + '</ul></div>';
  }}
  if (!evHtml) evHtml = '<div class="ev-group" style="color:#999">（暂无事件记录）</div>';
  document.getElementById('mRight').innerHTML =
    '<h2>' + d.name + '</h2>' +
    (d.identity ? `<div class="ident">${{d.identity}}</div>` : '') +
    (d.played_by ? `<div class="meta">扮演：${{d.played_by}}</div>` : '') +
    `<div class="meta">出场团：${{(d.groups||[]).join('、')}}</div>` +
    (d.note ? `<div class="note">${{d.note}}</div>` : '') +
    '<div style="font-weight:700;margin-bottom:6px">📜 经历事件</div>' + evHtml;
  document.getElementById('overlay').classList.add('show');
}}
function closeModal() {{ document.getElementById('overlay').classList.remove('show'); }}
document.addEventListener('keydown', e => {{ if (e.key === 'Escape') closeModal(); }});
</script>
</body></html>"""
