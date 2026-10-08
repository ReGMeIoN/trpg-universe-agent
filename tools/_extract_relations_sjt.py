# -*- coding: utf-8 -*-
"""从《剧情编年史》抽取**关系**，产出待审草稿（不写库）。

背景：extract 的口径保守，26 个角色只剩 7 条关系边；编年史里其实有大量明确的人物关系。
本工具让 LLM 按编年史抽关系，**只写草稿**给主人过目。

用法:
    .venv\\Scripts\\python.exe tools\\_extract_relations_sjt.py
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

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "圣剑英雄谭"
CHRONICLE = WS / "产出" / f"{GROUP}_剧情编年史.md"
DRAFT = WS / ".trpg" / "patches" / f"{GROUP}_relations_draft.json"

SYSTEM = "你是跑团数据整理员，只输出 JSON。"

PROMPT = """下面是一份 TRPG 跑团《{group}》的剧情编年史（时间线纪要），以及本团已入库的角色表。
请从中抽取**人物之间的关系**，输出 JSON。

## 可用角色（from/to 只能填这里的 id，不要发明新 id）
{roster}

## 已有关系（不要重复这些）
{existing}

## 输出格式
{{"relations": [
  {{"from": "sjt_xxx", "type": "关系类型(如 师徒/仇敌/君臣/同乡/决斗对手/被附身/效忠/同伴)",
    "strength": "强|中|弱", "to": "sjt_yyy",
    "event": "剧情依据：哪一段、发生了什么（要具体，能被编年史原文验证）",
    "confirmed": true}}
]}}

## 硬要求
1. **只抽有明确剧情依据的关系**——每条 event 必须写清"在哪一节、谁对谁做了什么"；
   仅仅"同场出现"不算关系，不要写。
2. 关系要**双向都有意义时分开写**（如 A 效忠 B 与 B 命令 A 可各写一条），但不要凑数。
3. `confirmed` 一律写 true；如果依据是玩家推测/转写不清，则写 false 并在 event 里说明。
4. 尽量覆盖主要人物（PC 之间、PC 与主要 NPC、NPC 之间、敌对关系），预计 20~40 条。
5. 只输出 JSON，不要任何说明文字。

## 剧情编年史
{chronicle}
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    cfg = load_config(ROOT / "config.yaml")
    prov = cfg.llm.provider_for(cfg.extract.model_route)
    client = make_llm_client(prov)

    chars_doc = json.loads((WS / "数据" / "characters.json").read_text(encoding="utf-8"))
    rels_doc = json.loads((WS / "数据" / "relations.json").read_text(encoding="utf-8"))
    mine = [c for c in chars_doc["characters"] if GROUP in (c.get("groups") or [])]
    roster = "\n".join(
        f"- {c['id']} | {c['name']} | tags={c.get('tags')} | 扮演={c.get('played_by')}"
        for c in sorted(mine, key=lambda c: c["id"])
    )
    ids = {c["id"] for c in mine}
    existing = "\n".join(
        f"- {r['from']} --{r.get('type')}--> {r['to']}"
        for r in rels_doc["relations"]
        if r.get("from") in ids and r.get("to") in ids
    ) or "(本团目前没有已入库关系)"

    chronicle = CHRONICLE.read_text(encoding="utf-8")
    print(f"编年史 {len(chronicle)} 字 · 本团角色 {len(mine)} 个 · 已有关系 "
          f"{len(existing.splitlines())} 条")
    print("调用 LLM 抽取关系 ...")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": PROMPT.format(
             group=GROUP, roster=roster, existing=existing, chronicle=chronicle)}],
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
        return 1

    rels = doc.get("relations") or []
    bad = [r for r in rels if r.get("from") not in ids or r.get("to") not in ids]
    good = [r for r in rels if r.get("from") in ids and r.get("to") in ids]
    names = {c["id"]: c["name"] for c in mine}
    print(f"\n抽出 {len(rels)} 条（合法 {len(good)} / 非法端点 {len(bad)}）")
    for r in good:
        flag = "" if r.get("confirmed", True) else "  [待确认]"
        print(f"  {names.get(r['from'], r['from'])} --{r.get('type')}--"
              f"({r.get('strength')})--> {names.get(r['to'], r['to'])}{flag}")
        print(f"      依据: {(r.get('event') or '')[:110]}")
    for r in bad:
        print(f"  !! 端点不在本团: {r.get('from')} -> {r.get('to')}")

    DRAFT.write_text(json.dumps({"group": GROUP, "relations": good}, ensure_ascii=False, indent=2),
                     encoding="utf-8")
    print(f"\n草稿已写: {DRAFT}（未入库；确认后再合并进补丁）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
