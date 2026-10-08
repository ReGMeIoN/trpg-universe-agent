# -*- coding: utf-8 -*-
"""关系类型受控词表：把自由的 `type` 归并成标准类型（原串保留进 `type_raw`）。

为什么必须做（2026-10-05 实测）：**442 条边有 387 个不同的 `type` 串**，最多的「对手」也只出现 15 次，
其中 239 个还是「A/B」这种复合写法。→ 任何按关系类型做的分组统计都是失真的。

⚠️ **必须同时改补丁**：`store` 的去重键是 `(from, to, type)`。
只改 `relations.json` 而不改 `.trpg/patches/*_patch.json`，下次 `store --apply`
会把补丁里那些「旧 type」的边当成**新关系再加一遍**（本项目的经典坑）。

用法:
    python tools/_relation_vocab.py --dump-types            # 导出全部原始 type（含计数与样例）到 .trpg/reports/
    python tools/_relation_vocab.py --suggest               # 让 LLM 把每个原始 type 映射到标准类型 → 存 mapping
    python tools/_relation_vocab.py --report                # 看归并前后的分布对照（不改数据）
    python tools/_relation_vocab.py --apply                 # 落盘（relations.json + 补丁 + 草稿，写前备份）
"""
from __future__ import annotations

import os
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WS = Path(os.environ.get("TRPG_WS", "workspace"))     # TRPG关系网
DATA = WS / "\u6570\u636e"                              # 数据
PATCHES = WS / ".trpg" / "patches"
REPORTS = WS / ".trpg" / "reports"
VOCAB = DATA / "\u5173\u7cfb\u7c7b\u578b\u53d7\u63a7\u8bcd\u8868.json"   # 关系类型受控词表.json

# ── 标准类型（受控词表）────────────────────────────────────────────────
# 依据实际数据设计，覆盖：血缘 / 授业 / 合作 / 从属 / 敌对 / 竞争 / 考核 /
# 援护 / 伤害 / 支配 / 情感 / 友谊 / 交易 / 归属 / 情报 / 同位体 / 代演 / 背叛 / 其他
CANON: dict[str, str] = {
    "亲属": "血缘或婚姻关系（兄妹、父子、家族）",
    "师徒": "授业与传承（师徒、师生、教导、训练、辅导对象、考核官的指导）",
    "合作": "并肩作战或同盟（同队、联军、搭档、同僚、同伴、战术配合）",
    "从属": "上下级与主从（上级、下属、隶属、指挥、统领、受雇）",
    "敌对": "对立与冲突（敌对、宿敌、仇敌、攻击、袭击、宣战、厮杀、戒备、警惕）",
    "竞争": "非致命的较量（对手、决斗、比赛、赌局、对决）",
    "考核": "考验与审核（考核官与考生、审核官、试炼、迷宫考核、引路）",
    "裁决": "裁判与审判（裁判/警告、审判官、宣判、处刑裁定）",
    "援护": "救援与保护（救援、救场、守护、疗伤、治疗、庇护、救命恩人）",
    "伤害": "造成伤害或死亡（击杀、杀害、屠杀、处决、重伤、致死）",
    "支配": "操纵与控制（脑控、夺舍、附身、洗脑、封印、诅咒、施咒、吞噬）",
    "追查": "调查追捕与寻找（调查对象、寻人执念、追踪、追捕、追杀者体系、审查）",
    "情感": "爱慕、崇拜与恋爱（恋爱、暗恋、告白、CP、情侣、崇拜、仰慕）",
    "友谊": "友情与羁绊（朋友、挚友、羁绊、室友、知己、互相信任）",
    "旧识": "旧日相识（旧识、故人、旧团故人、前同事、以前认识）",
    "交易": "委托与买卖（委托、交易、赠予、补给、租赁、军火商交易）",
    "归属": "灵宠/使魔/召唤物的归属（灵宠归属、使役、召唤、成为灵宠）",
    "情报": "告知与揭发（告知、揭发、供出、线索、指引、透露）",
    "同位体": "跨宇宙同一人（同位体、同一玩家、同一角色、疑似同一人）",
    "一体同源": "同一存在的不同形态／分裂／灵魂来源（一体两面、二人一体合体、本体分裂源、灵魂来源／前世、命运绑定）",
    "代演": "KP 代演与扮演（主持人代演 NPC、扮演/代演）",
    "背叛": "背叛与欺骗（背叛、欺骗、谎言、假规则、反水）",
    "关联": "依据很弱或明标『待确认』的关联（关联（待确认）、潜在关联、背景关联、跨世界关联）",
    "其他": "实在无法归入以上任何一类的一次性描述",
}

SYSTEM = "你是跑团数据整理员，只输出 JSON。"

PROMPT = """下面是一份跑团角色关系库里的**关系类型原始写法**清单（每条后面是出现次数）。
请把每一个原始写法映射到**给定的一组标准类型**里的一个。

## 标准类型（只能用这些 key，不要发明新类型）
{canon}

## 映射规则
1. 看**词义**判断，不要看出现次数；同一个标准类型可以映射很多个原始写法。
2. 原始写法里带「/」的复合串（如「战术击杀」「旧识/对手」），**取最主要的那个语义**。
3. 「考核官/通过者」「考官与考生」这类明确是"考验关系"的 → 归 `考核`。
4. 「同一玩家(pd)」「疑似同一人」「同位体」→ 归 `同位体`（注意：这是**玩家/角色的同一性**，不是剧情关系）。
5. 「主持人代演NPC」「扮演/代演」→ 归 `代演`。
6. 「同一玩家(pd)」「疑似同一人」「同位体」→ 归 `同位体`（注意：这是**玩家/角色的同一性**，不是剧情关系）。
   而「二人一体」「一体两面」「本体分裂源」「灵魂来源／前世」是**同一存在的不同形态** → 归 `一体同源`。
7. 「主持人代演NPC」「扮演/代演」→ 归 `代演`；「裁判/警告」「审判/宣判」→ 归 `裁决`。
8. 「旧识」「故人」「旧团故人」→ 归 `旧识`；「调查对象」「寻人」「追踪」「追捕」→ 归 `追查`。
9. `其他` 只留**真正无法归类的一次性描述**，请尽量少用（目标：占比 ≤ 5%）。
   凡是带「待确认」但语义上确实是某种关联的 → 归 `关联`（不是 `其他`）。
10. 输出里的 key 必须与上面清单**逐字一致**，一个都不能漏、不能多。

## 输出格式
{{"mapping": {{"原始写法1": "标准类型", "原始写法2": "标准类型", ...}}}}

## 原始写法清单（共 {n} 个）
{types}
"""


def _load():
    chars = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))["characters"]
    doc = json.loads((DATA / "relations.json").read_text(encoding="utf-8"))
    return {c["id"]: c for c in chars}, doc


def collect_types(rels: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for r in rels:
        t = (r.get("type") or "").strip()
        d = out.setdefault(t, {"count": 0, "samples": []})
        d["count"] += 1
        ev = (r.get("event") or "").strip()
        if ev and len(d["samples"]) < 3:
            d["samples"].append(ev[:70])
    return out


def dump_types(rels: list[dict]) -> int:
    types = collect_types(rels)
    dst = REPORTS / "关系类型_原始清单.json"
    dst.write_text(json.dumps(types, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"原始 type 共 {len(types)} 个 → {dst}")
    multi = [t for t in types if "/" in t or "／" in t or "、" in t]
    print(f"  含「/」等复合写法：{len(multi)} 个")
    for t, n in sorted(types.items(), key=lambda kv: -kv[1]["count"])[:15]:
        print(f"    {n['count']:>4}  {t}")
    return 0


def load_vocab() -> dict:
    if VOCAB.is_file():
        return json.loads(VOCAB.read_text(encoding="utf-8"))
    return {"canon": CANON, "mapping": {}}


def suggest(rels: list[dict]) -> int:
    from trpg_agent.adapters import make_llm_client
    from trpg_agent.config import load_config

    types = collect_types(rels)
    cfg = load_config(ROOT / "config.yaml")
    client = make_llm_client(cfg.llm.provider_for(cfg.extract.model_route))
    canon_txt = "\n".join(f"- {k}：{v}" for k, v in CANON.items())
    lst = "\n".join(f"- {t or '(空)'}  ×{d['count']}" for t, d in
                    sorted(types.items(), key=lambda kv: -kv[1]["count"]))
    print(f"让 LLM 把 {len(types)} 个原始 type 映射到 {len(CANON)} 个标准类型 ...")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": PROMPT.format(canon=canon_txt, n=len(types), types=lst)}],
        json_schema={"type": "object", "properties": {"mapping": {"type": "object"}},
                     "required": ["mapping"]},
        max_tokens=32000,
    )
    print(f"  {res.prompt_tokens} in / {res.completion_tokens} out / {res.elapsed_s:.0f}s")
    text = res.text.strip()
    if text.startswith("```"):
        text = text.split("```")[1]
        text = text.split("\n", 1)[1] if "\n" in text else text
    doc = json.loads(text)
    mapping = {str(k).strip(): str(v).strip() for k, v in (doc.get("mapping") or {}).items()}

    missing = [t for t in types if t not in mapping]
    extra = [k for k in mapping if k not in types]
    badval = {k: v for k, v in mapping.items() if v not in CANON}
    print(f"  覆盖 {len(types) - len(missing)}/{len(types)}"
          f" / 漏 {len(missing)} / 多 {len(extra)} / 非法目标 {len(badval)}")
    for t in missing[:10]:
        print(f"    漏: {t}")
    for k, v in list(badval.items())[:10]:
        print(f"    非法: {k} -> {v}")

    VOCAB.write_text(json.dumps({"canon": CANON, "mapping": mapping,
                                 "generated": datetime.now().strftime("%Y-%m-%d %H:%M")},
                                ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  词表已写: {VOCAB}")
    return 0 if not (missing or badval) else 1


def norm_type(t: str, mapping: dict) -> str:
    t = (t or "").strip()
    return mapping.get(t) or mapping.get(t, "其他")


def report(rels: list[dict]) -> int:
    vocab = load_vocab()
    mapping = vocab.get("mapping") or {}
    if not mapping:
        print("!! 还没有 mapping，先跑 --suggest")
        return 1
    from collections import Counter
    before = Counter((r.get("type") or "").strip() for r in rels)
    after = Counter(norm_type(r.get("type"), mapping) for r in rels)
    print(f"归并前：{len(before)} 个不同 type 串（{len(rels)} 条边）")
    print(f"归并后：{len(after)} 个标准类型")
    print(f"\n{'标准类型':<10}{'条数':>6}{'占比':>8}   合并了")
    print("-" * 60)
    for t, n in after.most_common():
        merged = sum(1 for k, v in mapping.items() if v == t)
        print(f"{t:<10}{n:>6}{n * 100 // max(1, len(rels)):>7}%   由 {merged} 个原始写法合并")
    un = [k for k, v in mapping.items() if v == "其他"]
    if un:
        print(f"\n归入「其他」的原始写法（{len(un)} 个）:")
        for k in sorted(un, key=lambda k: -before[k]):
            print(f"    ×{before[k]:<4}{k}")
    return 0


def apply(write: bool) -> int:
    vocab = load_vocab()
    mapping = vocab.get("mapping") or {}
    if not mapping:
        print("!! 还没有 mapping，先跑 --suggest")
        return 1
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    changed = {"relations": 0, "patches": 0, "drafts": 0}

    # ① 生产库
    rf = DATA / "relations.json"
    doc = json.loads(rf.read_text(encoding="utf-8"))
    for r in doc.get("relations", []):
        raw = (r.get("type") or "").strip()
        new = norm_type(raw, mapping)
        if new != raw:
            r["type"] = new
            r.setdefault("type_raw", raw)
            changed["relations"] += 1
    print(f"relations.json：改 {changed['relations']}/{len(doc.get('relations', []))} 条")

    # ② 补丁（不改会有重复边风险）
    patch_files = sorted(PATCHES.glob("*_patch.json"))
    for p in patch_files:
        pd = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for r in pd.get("relations") or []:
            raw = (r.get("type") or "").strip()
            new = norm_type(raw, mapping)
            if new != raw:
                r["type"] = new
                r.setdefault("type_raw", raw)
                n += 1
        if n:
            if write:
                shutil.copy2(p, p.with_suffix(f".json.bak_vocab_{stamp}"))
                p.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
            changed["patches"] += n
            print(f"  {p.name}: {n} 条")
    # ③ 关系草稿
    for p in sorted(PATCHES.glob("*_relations_draft.json")):
        pd = json.loads(p.read_text(encoding="utf-8"))
        n = 0
        for r in pd.get("relations") or []:
            raw = (r.get("type") or "").strip()
            new = norm_type(raw, mapping)
            if new != raw:
                r["type"] = new
                r.setdefault("type_raw", raw)
                n += 1
        if n:
            if write:
                shutil.copy2(p, p.with_suffix(f".json.bak_vocab_{stamp}"))
                p.write_text(json.dumps(pd, ensure_ascii=False, indent=2), encoding="utf-8")
            changed["drafts"] += n
            print(f"  {p.name}: {n} 条")

    print(f"\n合计：relations {changed['relations']} · 补丁 {changed['patches']} · 草稿 {changed['drafts']}")
    if not write:
        print("\n(dry-run; 加 --write 生效)")
        return 0
    shutil.copy2(rf, rf.with_name(f"{rf.name}.bak_vocab_{stamp}"))
    rf.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    # 复验
    chk = json.loads(rf.read_text(encoding="utf-8"))
    bad = [r for r in chk["relations"] if r.get("type") not in CANON]
    print(f"\n已写入（备份 *.bak_vocab_{stamp}）；复验：非法 type {len(bad)} 条")
    return 0 if not bad else 1


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    a = sys.argv
    chars, doc = _load()
    rels = doc.get("relations", [])
    if "--dump-types" in a:
        return dump_types(rels)
    if "--suggest" in a:
        return suggest(rels)
    if "--report" in a:
        return report(rels)
    if "--apply" in a:
        return apply(write="--write" in a)
    if "--canon" in a:
        for k, v in CANON.items():
            print(f"{k:<8}{v}")
        return 0
    print(__doc__)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
