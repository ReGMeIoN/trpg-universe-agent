# -*- coding: utf-8 -*-
"""从《剧情编年史》抽取**关系边**，产出待审草稿（只写草稿，不碰生产库）。

为什么要它：`extract` 抽关系的口径极保守（它主要抽角色骨架），实测「魔法少女育成计划 6」
48 个角色只落了 23 条边、**22 个角色连一条边都没有**；编年史里其实明确写着大量关系
（考核官↔学生、师徒、灵宠、宿敌、对手、同谋……）。圣剑英雄谭当年就是靠这一步补的 +22 条边。

与旧的 `_extract_relations_sjt.py` 的区别：
  1. **团名参数化**（`--group`），不再写死；
  2. 会把「当前一条边都没有的孤立角色」单独列给模型，**逐人要求核对**——这是覆盖率的关键；
  3. 目标条数按角色数自适应（约 0.9~1.3 边/人）。

用法:
    .venv\\Scripts\\python.exe tools\\_extract_relations.py --group "魔法少女育成计划 6"
    .venv\\Scripts\\python.exe tools\\_extract_relations.py --group "阴阳差事录 超自然怪谈"
"""
from __future__ import annotations

import os
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import make_llm_client  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
OUT = WS / "\u4ea7\u51fa"                              # 产出
PATCHES = WS / ".trpg" / "patches"
DATA = WS / "\u6570\u636e"                              # 数据

SYSTEM = "你是跑团数据整理员，只输出 JSON。"

PROMPT = """下面是一份 TRPG 跑团《{group}》的剧情材料（{material_label}），以及本团已入库的角色表。
请从中抽取**人物之间的关系**，输出 JSON。

## 可用角色（from/to 只能填这里的 id，绝对不要发明新 id）
{roster}

## 已有关系（**已有边不要重复写**，但可以在已有边之外补更细的关系）
{existing}

## ⚠️ 目前一条边都没有的孤立角色（{n_iso} 人）——**请逐个核对材料**
{isolated}
对这 {n_iso} 人中的每一个，只要材料里有它/他与任何人的**明确互动证据**，就必须至少补一条边；
确实全篇只被提了一嘴、与谁都没互动的，才允许继续孤立。

## 输出格式
{{"relations": [
  {{"from": "xxx_id", "type": "关系类型(如 师徒/辅导对象/考核官与考生/灵宠归属/宿敌/对手/同谋/亲属/上下级/救命恩人)",
    "strength": "强|中|弱", "to": "yyy_id",
    "event": "剧情依据：哪一段/哪条事件、发生了什么（要具体到能被材料原文验证）",
    "confirmed": true}}
]}}

## 硬要求
1. **只写有明确剧情依据的关系**——event 必须说清"哪一段、谁对谁做了什么"。
   仅仅"同场出现"不算关系；但**考官／考核官与考生的考验关系、灵宠归属、搭档、对手对局、
   同队、亲属、师徒**都算，不要漏。
2. 关系**双向有意义时分开写**（A 效忠 B 与 B 命令 A 可各一条），但别为凑数硬造。
3. `confirmed` 一律 true；若依据是玩家推测/转写不清，写 false 并在 event 里说明。
4. 目标规模：本团 {n_char} 个角色，请抽 **{lo}~{hi} 条**，并**优先覆盖上面那 {n_iso} 个孤立角色**。
5. **from/to 必须都取自上面那份「可用角色」**（同一团内的两人）。
6. 只输出 JSON，不要任何说明文字。

## 剧情材料（{material_label}）
{material}
"""


def build_events_material(mine: list[dict], group: str) -> str:
    """没有编年史的团：用 `characters.json` 的 身份/备注/events 拼出剧情材料。

    这批团的 events 是**逐条带出处的**（「段N …」「XX战：…」），信息量足够推关系，
    而且每条的出处都能直接写进 `event` 字段做依据。
    """
    blocks = []
    for c in sorted(mine, key=lambda x: str(x.get("id", ""))):
        lines = [f"### {c.get('name')}（id={c.get('id')}）"]
        if c.get("aliases"):
            lines.append(f"- 别名：{'、'.join(c['aliases'])}")
        if c.get("identity"):
            lines.append(f"- 身份：{c['identity']}")
        if c.get("note"):
            lines.append(f"- 备注：{c['note']}")
        ev_lines = []
        for ev in c.get("events") or []:
            src = ev.get("group") or "?"
            for it in ev.get("items") or []:
                ev_lines.append(f"    - [{src}] {it}")
        if ev_lines:
            lines.append("- 事件：")
            lines.extend(ev_lines)
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def run(group: str, source: str = "auto") -> dict:
    """抽一个团的关系 → 写草稿。返回统计（供 driver 汇总）。

    source: auto（有编年史就用编年史，否则退化为 events）| chronicle | events
    """
    chronicle_path = OUT / f"{group}_\u5267\u60c5\u7f16\u5e74\u53f2.md"    # <团>_剧情编年史.md
    use = source
    if use == "auto":
        use = "chronicle" if chronicle_path.is_file() else "events"
    if use == "chronicle" and not chronicle_path.is_file():
        print(f"!! 找不到编年史: {chronicle_path}")
        return {"group": group, "ok": False, "reason": "no chronicle"}
    draft_path = PATCHES / f"{group}_relations_draft.json"

    cfg = load_config(ROOT / "config.yaml")
    prov = cfg.llm.provider_for(cfg.extract.model_route)
    client = make_llm_client(prov)

    chars_doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    rels_doc = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))
    mine = [c for c in chars_doc["characters"] if group in (c.get("groups") or [])]
    if not mine:
        print(f"!! [{group}] 库里没有这个团的角色")
        return {"group": group, "ok": False, "reason": "no characters"}
    ids = {c["id"] for c in mine}
    roster = "\n".join(
        f"- {c['id']} | {c['name']} | tags={c.get('tags')} | 扮演={c.get('played_by')} | "
        f"身份={c.get('identity')}"
        for c in sorted(mine, key=lambda c: c["id"]))
    inner = [r for r in rels_doc["relations"]
             if r.get("from") in ids and r.get("to") in ids]
    existing = "\n".join(
        f"- {r['from']} --{r.get('type')}--> {r['to']}  ({r.get('event', '')[:40]})"
        for r in inner) or "(本团目前没有已入库关系)"
    deg: dict[str, int] = {i: 0 for i in ids}
    for r in inner:
        deg[r["from"]] = deg.get(r["from"], 0) + 1
        deg[r["to"]] = deg.get(r["to"], 0) + 1
    isolated = [c for c in mine if deg.get(c["id"], 0) == 0]
    iso_txt = "\n".join(
        f"- {c['id']} | {c['name']} | 身份={c.get('identity')} | 备注={(c.get('note') or '')[:120]}"
        for c in sorted(isolated, key=lambda c: c["id"])) or "（无）"

    if use == "chronicle":
        material = chronicle_path.read_text(encoding="utf-8")
        label = f"剧情编年史，{len(material)} 字"
    else:
        material = build_events_material(mine, group)
        label = "角色身份/备注/事件纪要（本团没有编年史，用库里的事件条目）"
    lo = int(len(mine) * 0.9)
    hi = int(len(mine) * 1.4)
    print(f"[{group}] 材料={use} {len(material)} 字 · 角色 {len(mine)} · 已有边 {len(inner)} "
          f"· 孤立 {len(isolated)} · 目标 {lo}~{hi} 条")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": PROMPT.format(
             group=group, roster=roster, existing=existing, isolated=iso_txt,
             n_iso=len(isolated), n_char=len(mine), lo=lo, hi=hi,
             material_label=label, material=material)}],
        json_schema={"type": "object", "properties": {"relations": {"type": "array"}},
                     "required": ["relations"]},
        max_tokens=32000,
    )
    print(f"  {res.prompt_tokens} in / {res.completion_tokens} out "
          f"(reasoning {res.reasoning_tokens}) / {res.elapsed_s:.0f}s")
    text = res.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.split("\n", 1)[1] if "\n" in text else text
    try:
        doc = json.loads(text)
    except json.JSONDecodeError as e:
        print(f"!! JSON 解析失败: {e}\n{text[:800]}")
        return {"group": group, "ok": False, "reason": "bad json"}

    rels = doc.get("relations") or []
    have = {(r.get("from"), r.get("to"), r.get("type")) for r in inner}
    good, dup, bad = [], [], []
    for r in rels:
        if r.get("from") not in ids or r.get("to") not in ids:
            bad.append(r)
            continue
        if (r.get("from"), r.get("to"), r.get("type")) in have:
            dup.append(r)
            continue
        good.append(r)
    names = {c["id"]: c["name"] for c in mine}
    print(f"  抽出 {len(rels)} 条 → 可用 {len(good)} / 重复 {len(dup)} / 端点非法 {len(bad)}")
    for r in good:
        flag = "" if r.get("confirmed", True) else "  [待确认]"
        print(f"    {names.get(r['from'], r['from'])} --{r.get('type')}--"
              f"({r.get('strength')})--> {names.get(r['to'], r['to'])}{flag}")

    covered = {r["from"] for r in good} | {r["to"] for r in good}
    still = [c["name"] for c in isolated if c["id"] not in covered]
    print(f"  孤立覆盖: {len(isolated) - len(still)}/{len(isolated)}"
          f"（仍无新边的: {'、'.join(still) if still else '无'}）")

    PATCHES.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(
        json.dumps({"group": group, "relations": good}, ensure_ascii=False, indent=2),
        encoding="utf-8")
    print(f"  草稿: {draft_path.name}（未入库）")
    return {"group": group, "ok": True, "source": use, "new": len(good),
            "dup": len(dup), "bad": len(bad), "iso_before": len(isolated),
            "iso_left": len(still)}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    argv = sys.argv
    if "--group" not in argv:
        print(__doc__)
        return 1
    group = argv[argv.index("--group") + 1]
    source = argv[argv.index("--source") + 1] if "--source" in argv else "auto"
    r = run(group, source)
    return 0 if r.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
