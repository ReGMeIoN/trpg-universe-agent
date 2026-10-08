# -*- coding: utf-8 -*-
"""PL 画像墙 HTML(可展开卡片)。移植自既有 gen_pl_viz.py。"""
from __future__ import annotations

import html
import json
from datetime import datetime
from typing import Any

from trpg_agent import log
from trpg_agent.workspace import Workspace

EMOJI = {
    "ReGMeIoN": "🐋", "牢昌": "🐋", "pd": "🎲", "雪人": "⛄", "往": "🎭",
    "菌羊": "🦊", "宽": "🍬", "牛爷": "🐂", "阿翔": "🪓", "卡尼三三": "🔍",
    "阿蓝": "🔵", "小满": "🌙", "老鸦": "🪶", "阿澈": "🎩",
}


def _esc(s: Any) -> str:
    return html.escape(str(s))


def _avatar_rel(p: dict[str, Any], ws: Workspace) -> str | None:
    av = p.get("avatar")
    if not av:
        return None
    rel = str(av).replace("\\", "/")
    return "./" + rel if not rel.startswith("..") else rel


def build(ws: Workspace, out_name: str = "PL画像可视化.html") -> dict[str, Any]:
    profiles = json.loads(ws.data_file("pl_profiles").read_text(encoding="utf-8")).get("profiles", [])
    cards: list[str] = []
    for p in profiles:
        emoji = EMOJI.get(p.get("name"), "👤")
        av = _avatar_rel(p, ws)
        av_html = (
            f'<div class="pl-avatar"><img src="{_esc(av)}" alt="头像"></div>'
            if av
            else f'<div class="pl-avatar noimg">{emoji}</div>'
        )
        groups = p.get("groups_played") or []
        cards.append(
            f'''<div class="pl-card" onclick="this.classList.toggle('open')">
      <div class="pl-head">
        {av_html}
        <div class="pl-info">
          <div class="pl-name">{_esc(p.get('name'))}</div>
          <div class="pl-alias">{_esc(' / '.join(p.get('aliases') or []))}</div>
          <div class="pl-groups">{_esc('；'.join(groups))}</div>
        </div>
        <div class="pl-arrow">▼</div>
      </div>
      <div class="pl-body">
        <div class="sec"><h4>🎴 PL的卡</h4>{''.join(f'<div class="cardline">{_esc(c.get("group"))}：<b>{_esc(c.get("role"))}</b></div>' for c in (p.get("cards") or []))}</div>
        <div class="sec"><h4>💬 说话风格</h4><p>{_esc(p.get('speaking_style') or '')}</p></div>
        <div class="sec"><h4>🎭 RP风格</h4><p>{_esc(p.get('rp_style') or '')}</p></div>
        {'<div class="sec"><h4>👀 人物印象</h4><ul>' + ''.join(f'<li>{_esc(i)}</li>' for i in (p.get('impressions') or [])) + '</ul></div>' if p.get('impressions') else ''}
        {'<div class="sec"><h4>🏆 高光时刻</h4><ul>' + ''.join(f'<li>{_esc(h)}</li>' for h in (p.get('highlights') or [])) + '</ul></div>' if p.get('highlights') else ''}
      </div>
    </div>'''
        )

    page = _PAGE.format(
        cards="".join(cards),
        count=len(profiles),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
    )
    ws.output.mkdir(parents=True, exist_ok=True)
    out = ws.output / out_name
    out.write_text(page, encoding="utf-8")
    log.ok(f"PL 画像墙: {ws.rel(out)} ({len(profiles)} 位 PL)")
    return {"path": ws.rel(out), "profiles": len(profiles)}


_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>PL 玩家画像墙</title>
<style>
body {{ font-family:"Microsoft YaHei",sans-serif; background:#f2efe9; margin:0; color:#333; }}
h1 {{ text-align:center; padding:26px 0 4px; font-size:24px; }}
.sub {{ text-align:center; color:#888; font-size:13px; margin-bottom:20px; }}
.wrap {{ max-width:1100px; margin:0 auto; padding:0 20px 60px; display:grid; grid-template-columns:repeat(2,1fr); gap:16px; }}
.pl-card {{ background:#fff; border-radius:14px; box-shadow:0 2px 10px rgba(0,0,0,.07); overflow:hidden; cursor:pointer; transition:.2s; }}
.pl-card:hover {{ box-shadow:0 4px 16px rgba(0,0,0,.12); }}
.pl-head {{ display:flex; align-items:center; gap:12px; padding:12px 16px; }}
.pl-avatar {{ width:42px; height:42px; border-radius:50%; background:#e8e2d4; display:flex; align-items:center; justify-content:center; font-size:22px; flex-shrink:0; overflow:hidden; }}
.pl-avatar img {{ width:100%; height:100%; object-fit:cover; }}
.noimg {{ color:#999; }}
.pl-info {{ flex:1; min-width:0; }}
.pl-name {{ font-size:15px; font-weight:700; }}
.pl-alias {{ font-size:11px; color:#999; margin-top:1px; }}
.pl-groups {{ font-size:10.5px; color:#8a6d3b; margin-top:3px; }}
.pl-arrow {{ color:#bbb; font-size:14px; }}
.pl-body {{ display:none; padding:0 18px 18px; border-top:1px solid #f0ece2; }}
.pl-card.open .pl-body {{ display:block; }}
.pl-card.open .pl-arrow {{ transform:rotate(180deg); }}
.sec {{ margin-top:12px; }}
.sec h4 {{ margin:0 0 4px; font-size:13px; color:#5e35b1; }}
.sec p, .sec li {{ font-size:12.5px; line-height:1.7; color:#555; }}
.sec ul {{ margin:0; padding-left:18px; }}
.cardline {{ font-size:12.5px; color:#555; padding:2px 0; }}
.cardline b {{ color:#333; }}
.foot {{ text-align:center; color:#aaa; font-size:11px; padding-bottom:24px; }}
</style></head><body>
<h1>🎭 PL 玩家画像墙</h1>
<div class="sub">共 {count} 位 PL · 点击卡片展开完整档案 · 记录：卡 / 说话风格 / RP风格 / 印象 / 高光</div>
<div class="wrap">
{cards}
</div>
<div class="foot">由 trpg-agent 生成 · {generated}</div>
</body></html>"""
