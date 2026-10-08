# -*- coding: utf-8 -*-
"""单人关系网（ego network）：把一个角色拎到中心，按关系一圈圈往外铺。

与团关系图的区别：团图是**群像**（一圈人 + 弦），本工具是**单人视角**——
中心是主角，第一圈是直接关系人，第二圈是关系人的关系人；跨团邻居也会拉进来。

用法:
    python tools/_ego_net.py --name "于秀丽"                     # 默认 1 跳
    python tools/_ego_net.py --name "于秀丽" --depth 2           # 两跳
    python tools/_ego_net.py --id yy_yuxiuli --depth 2
    python tools/_ego_net.py --name "杰克" --depth 2 --out 产出\\角色网_杰克.html
    python tools/_ego_net.py --name "宽" --list                  # 同名多节点时先看候选
    python tools/_ego_net.py --name "于秀丽" --stats-only        # 只打统计、不出图
    python tools/_ego_net.py --rank 25                           # 全库关系度数排名
    python tools/_ego_net.py --name "宽" --show-kp               # 把 KP 等 in_graph:false 也算进网

口径说明：**关系人（度数）= 不同的直接关系人数；边数 = 关系条数**——
同一对人可以有多条关系（「师徒」+「救命恩人」），两者别混为一谈。
默认**不把 `in_graph: false` 的角色（KP 本人等）算进网里**，与 `--rank` 口径一致。
"""
from __future__ import annotations

import os
import html
import json
import math
import sys
from datetime import datetime
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
OUT = WS / "\u4ea7\u51fa"                              # 产出

STR_ORDER = {"强": 0, "中": 1, "弱": 2, "": 3}
STR_COLOR = {"强": "#d32f2f", "中": "#f57c00", "弱": "#9e9e9e"}


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def avatar_rel(c: dict) -> str | None:
    av = c.get("avatar")
    if not av:
        return None
    p = Path(str(av).replace("\\", "/"))
    try:
        rel = (WS / p).resolve().relative_to(OUT.resolve())
        return "./" + rel.as_posix()
    except (ValueError, OSError):
        return "../" + p.as_posix()


def load():
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    rels = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))["relations"]
    return {c["id"]: c for c in chars}, rels


def resolve(chars: dict, name: str | None, cid: str | None) -> list[str]:
    if cid:
        return [cid] if cid in chars else []
    if not name:
        return []
    exact = [i for i, c in chars.items() if c.get("name") == name]
    if exact:
        return exact
    fuzzy = [i for i, c in chars.items() if name in (c.get("name") or "")]
    if fuzzy:
        return fuzzy
    return [i for i, c in chars.items()
            if any(name == a or name in a for a in (c.get("aliases") or []))]


def nbrs(rels: list[dict], ego: str, allowed: set[str] | None = None) -> dict[str, list[dict]]:
    """ego 的直接关系：{对方 id: [边, ...]}，入边出边都收。"""
    out: dict[str, list[dict]] = {}
    for r in rels:
        a, b = r.get("from"), r.get("to")
        if a == b:
            continue
        other = b if a == ego else (a if b == ego else None)
        if other is None:
            continue
        if allowed is not None and other not in allowed:
            continue
        out.setdefault(other, []).append(r)
    for v in out.values():
        v.sort(key=lambda r: STR_ORDER.get(r.get("strength", ""), 9))
    return out


def bfs(rels: list[dict], ego: str, depth: int, allowed: set[str] | None = None):
    """返回 (dist, parent, ring_edges)。parent 记「谁把他拉进来的」。"""
    dist = {ego: 0}
    parent: dict[str, str] = {}
    level_edges: list[tuple[int, dict]] = []      # (层级, 边)
    frontier = [ego]
    for d in range(1, depth + 1):
        nxt = []
        for u in frontier:
            for v, es in nbrs(rels, u, allowed).items():
                for e in es:
                    level_edges.append((d, e))
                if v not in dist:
                    dist[v] = d
                    parent[v] = u
                    nxt.append(v)
        frontier = nxt
        if not frontier:
            break
    return dist, parent, level_edges


def placed_layout(dist: dict, parent: dict, ego: str, nodes_by_ring: dict):
    """同心圆布局。

    关键：**按「谁带进来几个孩子」分配角度预算**（不是平均分 2π）——
    平均分的话，某个邻居带了 8 个人时，那 8 个会被挤成一坨、互相压住。
    先把每个一圈节点的预算按 max(1, 孩子数) 加权，再在自己的预算里扇形排开，就不会跨父节点撞车。
    """
    pos: dict[str, tuple[float, float]] = {}
    r1_nodes = list(nodes_by_ring.get(1, []))
    r2_nodes = list(nodes_by_ring.get(2, []))
    n1, n2 = len(r1_nodes), len(r2_nodes)
    av1 = 76 if n1 <= 16 else (62 if n1 <= 26 else 50)
    av2 = max(34, av1 - 22)
    r1 = max(250.0, n1 * (av1 + 26) / (2 * math.pi)) + 30 if n1 else 250.0
    r2 = (r1 + max(190.0, n2 * (av2 + 30) / (2 * math.pi)) + 40) if n2 else r1
    w = h = 2 * (r2 + av2 + 80)
    cx = cy = w / 2

    pos[ego] = (cx, cy)
    kids: dict[str, list[str]] = {}
    for cid in r2_nodes:
        kids.setdefault(parent.get(cid, ego), []).append(cid)

    # 角度预算：按孩子数加权（每个节点自身也算 1 份）
    weights = [max(1, len(kids.get(cid, []))) for cid in r1_nodes]
    total = sum(weights) or 1
    ang1: dict[str, float] = {}
    cursor = -math.pi / 2
    for cid, wt in zip(r1_nodes, weights):
        span = 2 * math.pi * wt / total
        mid = cursor + span / 2
        ang1[cid] = mid
        pos[cid] = (cx + r1 * math.cos(mid), cy + r1 * math.sin(mid))
        cursor += span

    # 在各自预算里扇形排开；相邻两个交错半径，避免标签压在一起
    for cid, wt in zip(r1_nodes, weights):
        cs = kids.get(cid, [])
        if not cs:
            continue
        span = 2 * math.pi * wt / total
        base = ang1[cid]
        k = len(cs)
        use = span * 0.82
        for j, child in enumerate(cs):
            t = (j + 0.5) / k
            a = base - use / 2 + use * t
            rr = r2 + (av2 + 34) * (j % 2)          # 交错半径
            pos[child] = (cx + rr * math.cos(a), cy + rr * math.sin(a))
    return pos, w, h, r1, r2, av1, av2


def rank(chars: dict, rels: list[dict], top: int, group: str | None) -> int:
    """按「直接关系人数」排全库名次（统计视角）。"""
    allowed = {i for i, c in chars.items()
               if c.get("in_graph") is not False
               and (not group or group in (c.get("groups") or []))}
    rows = []
    for i in allowed:
        d = nbrs(rels, i, allowed)          # 本团/全库范围内的直接关系
        if not d:
            continue
        ego_groups = set(chars[i].get("groups") or [])
        cross = sum(1 for j in d if not (set(chars[j].get("groups") or []) & ego_groups))
        strong = sum(1 for es in d.values() if any(e.get("strength") == "强" for e in es))
        nedges = sum(len(es) for es in d.values())
        rows.append((len(d), strong, cross, nedges, i))
    rows.sort(key=lambda r: (-r[0], -r[1], -r[2], chars[r[4]].get("name", "")))
    scope = f"《{group}》范围内" if group else "全库"
    print(f"\n=== 关系度数排名（{scope}，Top {top}）===")
    print(f"{'#':<4}{'角色':<20}{'关系人':>6}{'强':>5}{'跨团':>6}{'边数':>6}  出场团")
    print("-" * 92)
    for n, (deg, st, cr, ne, i) in enumerate(rows[:top], 1):
        c = chars[i]
        print(f"{n:<4}{c.get('name',''):<20}{deg:>6}{st:>5}{cr:>6}{ne:>6}  "
              f"{'、'.join(c.get('groups') or [])}")
    print(f"\n（共 {len(rows)} 个有关系的角色；「关系人」= 不同的直接关系人数，"
          f"「边数」= 关系条数，同一对人可有多种关系）")
    print("看某个人的网：--name \"<角色名>\" --depth 2")
    return 0


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    a = sys.argv
    name = a[a.index("--name") + 1] if "--name" in a else None
    cid = a[a.index("--id") + 1] if "--id" in a else None
    depth = int(a[a.index("--depth") + 1]) if "--depth" in a else 1
    depth = max(1, min(3, depth))
    stats_only = "--stats-only" in a
    group = a[a.index("--group") + 1] if "--group" in a else None

    chars, rels = load()

    if "--rank" in a:
        top = int(a[a.index("--rank") + 1]) if a.index("--rank") + 1 < len(a) else 20
        return rank(chars, rels, top, group)

    cands = resolve(chars, name, cid)
    if not cands:
        print(f"!! 找不到角色: {name or cid}")
        return 1
    if "--list" in a or len(cands) > 1:
        print(f"「{name or cid}」匹配到 {len(cands)} 个节点：")
        for i in cands:
            c = chars[i]
            print(f"  {i:<30}{c.get('name',''):<20} 出场团={'、'.join(c.get('groups') or [])}")
        if "--list" in a or cid is None:
            print("\n用 --id <id> 指定要看哪一个。")
            return 0 if "--list" in a else 2
    ego = cands[0]
    c0 = chars[ego]

    # 口径与 `--rank` 保持一致：**默认不把 `in_graph:false` 的角色（KP 本人等）算进网里**，
    # 想看就加 --show-kp。两边口径不一致的话，排名里的度数和单页里的度数会对不上。
    allowed = {i for i, c in chars.items() if c.get("in_graph") is not False}
    if "--show-kp" in a:
        allowed |= {i for i, c in chars.items() if c.get("in_graph") is False}
    dist, parent, level_edges = bfs(rels, ego, depth, allowed)
    ring = {0: [ego]}
    for d in (1, 2, 3):
        ring[d] = sorted([i for i, v in dist.items() if v == d],
                         key=lambda i: (STR_ORDER.get(
                             (nbrs(rels, ego, allowed).get(i) or [{}])[0].get("strength", ""), 9),
                             chars[i].get("name", "")))
    # 只保留用得到的层级
    keep = {d: ring.get(d, []) for d in range(0, min(depth, max(dist.values(), default=0)) + 1)}

    # ── 统计 ──────────────────────────────────────────────────────────
    direct = nbrs(rels, ego, allowed)
    strong = sum(1 for es in direct.values() if any(e.get("strength") == "强" for e in es))
    n_edges = sum(len(es) for es in direct.values())
    groups = {}
    for i in direct:
        for g in (chars[i].get("groups") or []):
            groups[g] = groups.get(g, 0) + 1
    ego_groups = set(c0.get("groups") or [])
    cross = [i for i in direct if not (set(chars[i].get("groups") or []) & ego_groups)]
    two_hop = [i for i, v in dist.items() if v == 2]
    # 共同联系人：ego 的邻居彼此之间也算邻居
    common = {}
    for i in direct:
        ci = set(nbrs(rels, i, allowed)) - {ego}
        common[i] = sorted(ci & set(direct), key=lambda x: chars[x].get("name", ""))

    print(f"\n=== 角色网 · {c0.get('name')}  [{ego}] ===")
    print(f"身份   : {c0.get('identity') or '-'}")
    print(f"出场团 : {'、'.join(c0.get('groups') or []) or '-'}")
    print(f"扮演   : {c0.get('played_by') or '-'}")
    print(f"\n直接关系人 : {len(direct)} 人（其中「强」关系 {strong} 人）")
    print(f"关系条数   : {n_edges} 条（同一对人可有多种关系）")
    print(f"跨团邻居   : {len(cross)} 人" + (f" —— {'、'.join(chars[i].get('name','') for i in cross[:8])}" if cross else ""))
    if depth >= 2:
        print(f"二跳可达   : {len(two_hop)} 人（新增，不含直接关系人）")
    print(f"邻居所属团 : " + " · ".join(f"{g} {n}" for g, n in
                                    sorted(groups.items(), key=lambda kv: -kv[1])))
    print("\n直接关系人清单：")
    for i in sorted(direct, key=lambda x: (STR_ORDER.get((direct[x][0].get("strength") or ""), 9),
                                           chars[x].get("name", ""))):
        es = direct[i]
        types = " / ".join(f"{e.get('type')}[{e.get('strength')}]" for e in es)
        cm = f"  共同联系人 {len(common[i])}" if common[i] else ""
        print(f"  · {chars[i].get('name',''):<20}{types:<46}{cm}")
    if depth >= 2:
        print("\n二跳新增：")
        for i in sorted(two_hop, key=lambda x: chars[x].get("name", "")):
            print(f"  · {chars[i].get('name',''):<20}← 经 {chars.get(parent.get(i,''),{}).get('name','')}")

    if stats_only:
        return 0

    # ── 出图 ─────────────────────────────────────────────────────────
    pos, W, H, r1, r2, av1, av2 = placed_layout(dist, parent, ego, keep)
    nodes_show = [i for d in sorted(keep) for i in keep[d]]
    show = set(nodes_show)
    edges = [e for _, e in level_edges if e.get("from") in show and e.get("to") in show]
    # 去重（同一对人只画一次主线，其余关系进表格）
    drawn: set[tuple[str, str]] = set()
    svg = []
    for e in sorted(edges, key=lambda e: STR_ORDER.get(e.get("strength", ""), 9)):
        a1, b1 = e["from"], e["to"]
        k = tuple(sorted([a1, b1]))
        if k in drawn:
            continue
        drawn.add(k)
        x1, y1 = pos[a1]
        x2, y2 = pos[b1]
        col = STR_COLOR.get(e.get("strength"), "#9e9e9e")
        wid = 2.6 if e.get("strength") == "强" else (1.8 if e.get("strength") == "中" else 1.2)
        dim = 0.85 if ego in (a1, b1) else 0.42
        svg.append(f'<line x1="{x1:.0f}" y1="{y1:.0f}" x2="{x2:.0f}" y2="{y2:.0f}" stroke="{col}" '
                   f'stroke-width="{wid}" opacity="{dim}"/>')
        if ego in (a1, b1) or (a1 in keep.get(1, []) and b1 in keep.get(2, [])) or \
           (b1 in keep.get(1, []) and a1 in keep.get(2, [])):
            big = ego in (a1, b1)
            # 本人那圈标签往对方那边挪一点（t=0.62），否则十几条标签全堆在圆心糊成一团；
            # 描白边（paint-order:stroke）让标签压在线上也读得出来。
            t = 0.62 if big else 0.5
            if not big and a1 in keep.get(2, []):
                t = 0.42          # 二圈标签靠近孩子一侧
            mx = x1 + (x2 - x1) * t
            my = y1 + (y2 - y1) * t
            arrow = ("→ " if a1 == ego else "← ") if big else ""
            svg.append(f'<text x="{mx:.0f}" y="{my:.0f}" text-anchor="middle" '
                       f'font-size="{11 if big else 9}" fill="{"#555" if big else "#999"}" '
                       f'stroke="#fffdf8" stroke-width="3" paint-order="stroke" '
                       f'transform="translate(0,-4)">{esc(arrow + (e.get("type") or ""))}</text>')

    node_html = []
    for i in nodes_show:
        c = chars[i]
        x, y = pos[i]
        av = avatar_rel(c)
        d = dist[i]
        size = 108 if d == 0 else (av1 if d == 1 else av2)
        half = (size + 34) / 2 + 6
        el = (f'<img src="{esc(av)}" class="avatar" onclick="openModal(\'{i}\')" title="点击查看详情">'
              if av else f'<div class="avatar noimg" onclick="openModal(\'{i}\')">?</div>')
        badge = ""
        if d == 0:
            badge = '<span class="bg self">本人</span>'
        elif not (set(c.get("groups") or []) & ego_groups):
            badge = '<span class="bg cross">跨团</span>'
        node_html.append(
            f'<div class="node d{d}" style="left:{x - half:.0f}px;top:{y - half - 8:.0f}px;'
            f'width:{size + 34:.0f}px" data-size="{size}">'
            f'{el}<div class="name">{esc(c.get("name"))}{badge}</div>'
            f'<div class="role">{esc(str(c.get("identity") or "")[:10])}</div></div>')

    rows = []
    for i in sorted(direct, key=lambda x: (STR_ORDER.get((direct[x][0].get("strength") or ""), 9),
                                           chars[x].get("name", ""))):
        c = chars[i]
        for e in direct[i]:
            fwd = "→" if e.get("from") == ego else "←"
            rows.append(
                f'<tr><td><b>{esc(c.get("name"))}</b><div class="g">{esc("、".join(c.get("groups") or []))}</div></td>'
                f'<td class="rtype">{fwd} {esc(e.get("type"))}'
                f'<span class="s-{esc(e.get("strength","弱"))}">{esc(e.get("strength",""))}</span></td>'
                f'<td class="event">{esc(e.get("event"))}</td>'
                f'<td class="cm">{esc("、".join(chars[x].get("name","") for x in common[i])) or "-"}</td></tr>')

    details = {}
    for i in nodes_show:
        c = chars[i]
        details[i] = {"name": c.get("name", ""), "identity": c.get("identity", ""),
                      "note": c.get("note", ""), "groups": c.get("groups", []),
                      "avatar": avatar_rel(c), "played_by": c.get("played_by", ""),
                      "events": c.get("events", [])}

    out = Path(a[a.index("--out") + 1]) if "--out" in a else OUT / f"角色网_{c0.get('name')}.html"
    if not out.is_absolute():
        out = WS / out
    out.parent.mkdir(parents=True, exist_ok=True)
    page = _PAGE.format(
        title=esc(c0.get("name")), ego=c0.get("name"),
        subtitle=(f"{esc(c0.get('identity') or '')} · 出场团 {'、'.join(c0.get('groups') or [])} · "
                  f"直接关系人 {len(direct)} · 跨团 {len(cross)}"
                  + (f" · 二跳可达 {len(two_hop)}" if depth >= 2 else "")),
        canvas_w=int(W), canvas_h=int(H), cx=int(W / 2), cy=int(H / 2),
        svg="".join(svg), nodes="".join(node_html),
        ring1=f"{r1:.0f}", ring2=f"{r2:.0f}", holes=len(direct), n_edges=n_edges,
        rows="".join(rows), details_json=json.dumps(details, ensure_ascii=False).replace("</", "<\\/"),
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"), depth=depth,
    )
    out.write_text(page, encoding="utf-8")
    print(f"\n出图: {out}  ({len(nodes_show)} 节点 / {len(drawn)} 连线 · 画布 {int(W)}×{int(H)})")
    return 0


_PAGE = """<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8">
<title>{title} · 角色网</title>
<style>
body {{ font-family: "Microsoft YaHei", sans-serif; background: #f7f5f0; margin: 0; color: #333; }}
h1 {{ text-align: center; padding: 20px 0 4px; font-size: 23px; margin: 0; }}
.sub {{ text-align: center; color: #888; font-size: 13px; margin: 6px 0 14px; }}
.legend {{ text-align: center; font-size: 12px; color: #777; margin-bottom: 16px; }}
.legend i {{ display:inline-block; width:22px; height:3px; vertical-align:middle; margin:0 4px 0 14px; }}
.chart {{ position: relative; margin: 0 auto 26px; background: #fffdf8; border-radius: 14px;
          box-shadow: 0 2px 14px rgba(0,0,0,.07); overflow: auto; max-width: 96vw; }}
.chart svg {{ position: absolute; left: 0; top: 0; }}
.node {{ position: absolute; text-align: center; }}
.avatar {{ border-radius: 50%; object-fit: cover; border: 3px solid #fff;
           box-shadow: 0 2px 10px rgba(0,0,0,.28); display: block; margin: 0 auto; background: #ddd; cursor: pointer; }}
.avatar:hover {{ transform: scale(1.07); transition: .15s; }}
.d0 .avatar {{ border-color: #c9a961; box-shadow: 0 0 0 4px rgba(201,169,97,.28), 0 3px 14px rgba(0,0,0,.3); }}
.d1 .avatar {{ width: 76px; height: 76px; }}
.d2 .avatar {{ width: 54px; height: 54px; }}
.d0 .avatar {{ width: 108px; height: 108px; }}
.noimg {{ background:#e8e8e8; color:#aaa; text-align:center; }}
.d0 .noimg {{ line-height:108px; font-size:40px; }}
.d1 .noimg {{ line-height:76px; font-size:28px; }}
.d2 .noimg {{ line-height:54px; font-size:20px; }}
.name {{ font-size: 12.5px; font-weight: 700; margin-top: 4px; line-height: 1.25; }}
.d2 .name {{ font-size: 11px; }}
.role {{ font-size: 10px; color: #aaa; }}
.bg {{ font-size: 9px; padding: 0 3px; border-radius: 3px; margin-left: 3px; vertical-align: 1px; }}
.bg.self {{ background:#c9a961; color:#fff; }}
.bg.cross {{ background:#d32f2f; color:#fff; }}
.list {{ width: 1180px; max-width: 96vw; margin: 0 auto 40px; }}
table {{ width: 100%; border-collapse: collapse; background: #fff; box-shadow: 0 2px 8px rgba(0,0,0,.06);
         border-radius: 8px; overflow: hidden; }}
th, td {{ padding: 8px 10px; border-bottom: 1px solid #eee; font-size: 13px; text-align: left; vertical-align: top; }}
th {{ background: #4a4a4a; color: #fff; }}
.rtype {{ font-weight: 700; color: #b3541e; white-space: nowrap; }}
.s-强 {{ margin-left:4px; background:#d32f2f; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-中 {{ margin-left:4px; background:#f57c00; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.s-弱 {{ margin-left:4px; background:#8e8e8e; color:#fff; padding:1px 5px; border-radius:8px; font-size:10px; }}
.event {{ color: #777; font-size: 12px; }}
.g {{ font-size: 11px; color: #aaa; }}
.cm {{ font-size: 12px; color: #5e35b1; }}
.overlay {{ display: none; position: fixed; inset: 0; background: rgba(0,0,0,.55); z-index: 100; }}
.overlay.show {{ display: flex; align-items: center; justify-content: center; }}
.modal {{ background: #fff; width: 860px; max-width: 92vw; max-height: 88vh; border-radius: 14px;
          box-shadow: 0 8px 40px rgba(0,0,0,.35); display: flex; overflow: hidden; position: relative; }}
.modal-left {{ width: 300px; min-width: 300px; background: #f0ece4; display: flex; align-items: center; justify-content: center; }}
.modal-left img {{ width: 100%; height: 100%; object-fit: contain; }}
.modal-left .noimg2 {{ font-size: 60px; color: #bbb; }}
.modal-right {{ flex: 1; padding: 22px 24px; overflow-y: auto; max-height: 88vh; }}
.modal-right h2 {{ margin: 0 0 6px; font-size: 22px; }}
.modal-right .ident {{ color: #8a6d3b; font-size: 13px; margin-bottom: 8px; }}
.modal-right .meta {{ font-size: 12px; color: #777; margin-bottom: 10px; }}
.modal-right .note {{ font-size: 13px; color: #444; background: #faf6ef; border-left: 3px solid #d4a017;
                      padding: 8px 10px; border-radius: 4px; margin-bottom: 14px; }}
.ev-group {{ margin-bottom: 12px; }}
.ev-group .gname {{ font-size: 13px; font-weight: 700; color: #5e35b1; margin-bottom: 4px; }}
.ev-group ul {{ margin: 0; padding-left: 18px; }}
.ev-group li {{ font-size: 12.5px; line-height: 1.7; color: #444; }}
.close {{ position: absolute; top: 8px; right: 14px; font-size: 26px; cursor: pointer; color: #999;
          background: none; border: none; z-index: 2; }}
.foot {{ text-align:center; color:#aaa; font-size:11px; padding-bottom:24px; }}
</style></head><body>
<h1>{title} · 角色关系网</h1>
<div class="sub">{subtitle}</div>
<div class="legend">
  关系强度：<i style="background:#d32f2f"></i>强 <i style="background:#f57c00"></i>中 <i style="background:#9e9e9e"></i>弱
  &nbsp;·&nbsp; 箭头方向：→ 主语是 TA，← TA 是宾语 &nbsp;·&nbsp; 画布 {canvas_w}×{canvas_h}（可滚动）&nbsp;·&nbsp; 第 {depth} 跳
</div>
<div class="chart" style="width:{canvas_w}px;height:{canvas_h}px">
  <svg width="{canvas_w}" height="{canvas_h}">
    <circle cx="{cx}" cy="{cy}" r="{ring1}" fill="none" stroke="#eee" stroke-dasharray="4 6"/>
    {svg}
  </svg>
  {nodes}
</div>
<div class="list">
  <h2 style="font-size:16px;margin:0 0 10px;">{ego} 的直接关系（{n_edges} 条 → {holes} 人）</h2>
  <table>
    <tr><th style="width:16%">关系人</th><th style="width:20%">关系</th><th>事件依据</th><th style="width:18%">共同联系人</th></tr>
    {rows}
  </table>
</div>
<div class="overlay" id="overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <button class="close" onclick="closeModal()">×</button>
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
    ? `<img src="${{d.avatar}}" alt="立绘">` : '<div class="noimg2">❓</div>';
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


if __name__ == "__main__":
    raise SystemExit(main())
