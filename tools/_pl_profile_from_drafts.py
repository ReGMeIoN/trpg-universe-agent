# -*- coding: utf-8 -*-
"""Build PL profiles for the new groups out of the per-segment drafts' 「PL 表现」 sections.

canon 铁律第 8 条要求「每个 PL 建档案，线下团是 PL 个性最真实的样本」；extract 的段草稿里
已经逐段写了「PL 表现（说话风格/RP风格/印象/高光时刻）」，但那是散在 7~12 个 md 里的，没人汇总。

本工具做两件事：
  1. 机械抽取：把每个 PL 在各段的原文汇总成 `profile_updates[].add_impressions`
  2. --distill：再让 LLM 逐 PL 蒸馏出 speaking_style / rp_style / highlights，
     写进 `append_speaking_style` / `append_rp_style` / `add_impressions`

usage:
    python tools/_pl_profile_from_drafts.py --groups "阴阳差事录 超自然怪谈" "魔法少女育成计划 6"
    python tools/_pl_profile_from_drafts.py --groups ... --distill --apply
"""
from __future__ import annotations

import os
import argparse
import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

WS = Path(os.environ.get("TRPG_WS", "workspace"))
DRAFTS = WS / ".trpg" / "extracts"
PATCHES = WS / ".trpg" / "patches"

# draft 里出现的 PL 写法 -> 规范名（规范名再映射到 uid）
PL_ALIASES = {
    "ReGMeIoN": "ReGMeIoN", "reh": "ReGMeIoN", "\u7262\u660c": "ReGMeIoN", "\u8001\u660c": "ReGMeIoN",
    "\u4e3b\u4eba": "ReGMeIoN", "\u5c0f\u660c": "ReGMeIoN",
    "pd": "pd", "PD": "pd", "KP": "pd", "kp": "pd", "\u6708\u57ce\u51db\u7eea": "pd",
    "\u96ea\u4eba": "\u96ea\u4eba", "\u949f\u677e\u6797": "\u96ea\u4eba", "\u7802\u72fc\u771f\u5948": "\u96ea\u4eba",
    "\u5f80": "\u5f80", "\u6768\u747e\u5ba3": "\u5f80",
    "\u83cc\u7f8a": "\u83cc\u7f8a", "\u519b\u9633": "\u83cc\u7f8a", "\u541b\u7f8a": "\u83cc\u7f8a", "\u4fca\u9633": "\u83cc\u7f8a",
    "\u51e4\u6a31\u59ec": "\u83cc\u7f8a",
    "\u5bbd": "\u5bbd", "\u8584\u8377\u7cd6": "\u5bbd",
    "\u4fca\u677e": "\u4fca\u677e",
    "\u725b\u7237": "\u725b\u7237", "\u725b": "\u725b\u7237",
}
UID = {
    "ReGMeIoN": "u_1hcxJopFPAX4FqHw244Dgg",
    "pd": "u_WXSj6Z3i1SCeuaJKoDrh6A",
    "\u96ea\u4eba": "u_iNPT6i4TzRDATnGdKzr3Mg",
    "\u5f80": "u_9Kb8IIw3_sOBpESFP8IJpA",
    "\u83cc\u7f8a": "u_OVHNJ1ZkshyGSOsm6DHJyw",
    "\u5bbd": "u_DODMKVWsHhZcbZfiB6AOMQ",
    "\u4fca\u677e": "u_local_junsong",
    "\u725b\u7237": "u_local_niuye",
}

HEAD = re.compile(r"^##\s*PL\s*\u8868\u73b0")          # ## PL 表现
LINE = re.compile(r"^-\s*(.+)$")
NAME = re.compile(r"^\**\s*([^：:（(\u3001]{1,12}?)\s*\**\s*(?:[（(][^）)]*[）)])?\s*[：:]")


def drafts_of(group: str) -> list[Path]:
    return sorted(DRAFTS.glob(f"{group}_\u6bb5*_\u63d0\u70bc.md"))


def seg_no(path: Path) -> str:
    m = re.search(r"_\u6bb5(\d+)_", path.name)
    return m.group(1) if m else "?"


def collect(group: str) -> dict[str, list[str]]:
    """返回 {规范 PL 名: [原文行, ...]}"""
    out: dict[str, list[str]] = {}
    for p in drafts_of(group):
        text = p.read_text(encoding="utf-8", errors="replace")
        lines = text.splitlines()
        inside = False
        for ln in lines:
            if HEAD.match(ln.strip()):
                inside = True
                continue
            if inside and ln.startswith("## "):
                break
            if not inside:
                continue
            m = LINE.match(ln.strip())
            if not m:
                continue
            body = m.group(1)
            nm = NAME.match(body)
            if not nm:
                continue
            raw = nm.group(1).strip()
            canon = PL_ALIASES.get(raw)
            if not canon:
                continue
            out.setdefault(canon, []).append(f"\u6bb5{seg_no(p)}: {body}")
    return out


SYSTEM = "\u4f60\u662f\u8dd1\u56e2\u8bb0\u5f55\u6574\u7406\u5458\uff0c\u4e13\u95e8\u628a\u201c\u73a9\u5bb6\u5728\u684c\u8fb9\u7684\u771f\u5b9e\u8868\u73b0\u201d\u51dd\u7ec3\u6210\u4eba\u7269\u753b\u50cf\u3002"
PROMPT = """下面是同一个 PL 在跑团录音转写里被记录下来的表现（按团、按段汇总，转写可能有错字）。
请提炼这个 PL 的**桌边画像**，输出 JSON。**必须按团分键**，键名照抄给定的团名：

{{"speaking_style": {{"<团名A>": "说话风格（口头禅/语速/嗓门/玩梗习惯/场外吐槽频率，2~4 句）",
                     "<团名B>": "…"}},
 "rp_style": {{"<团名A>": "RP 风格（扮演投入度/爱整活/认真型/划水型/演出设计，2~4 句）",
               "<团名B>": "…"}},
 "highlights": [{{"group": "<团名A>", "text": "本团最出彩的表现"}},
                {{"group": "<团名B>", "text": "…"}}]}}

要求：
1. **只依据下面的材料**，不要编造；材料里说“待确认”的就照实写“待确认”。
2. 某个团里这个 PL 没有可判断的材料时，**不要造**，直接写「（本团无足够材料）」。
3. 不要在文本里再写团名前缀（键名已经表达了归属）。
4. 不要复述剧情节，聚焦“作为玩家/桌边人的表现”。
5. 只输出 JSON，不要任何解释。

可用团名：{groups}

材料：

"""


def distill(client, pl: str, lines: list[str], groups: list[str], max_tokens: int) -> dict:
    body = "\n".join(f"- {x}" for x in lines)
    head = PROMPT.replace("{groups}", "\u3001".join(groups))
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": head + f"PL：{pl}\n\n{body}"}],
        max_tokens=max_tokens,
    )
    txt = res.text.strip()
    m = re.search(r"\{.*\}", txt, re.S)
    if not m:
        raise ValueError(f"没拿到 JSON: {txt[:120]!r}")
    return json.loads(m.group(0))


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--groups", nargs="+", required=True)
    ap.add_argument("--distill", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=8000)
    args = ap.parse_args()

    per_group = {g: collect(g) for g in args.groups}
    for g, d in per_group.items():
        print(f"{g}: 命中 {len(d)} 名 PL -> " + ", ".join(f"{k}×{len(v)}" for k, v in d.items()))

    distilled: dict[str, dict] = {}
    if args.distill:
        from trpg_agent.adapters import make_llm_client
        from trpg_agent.config import load_config

        cfg = load_config(ROOT / "config.yaml")
        client = make_llm_client(cfg.llm.provider_for(cfg.extract.model_route))
        merged: dict[str, list[str]] = {}
        for g, d in per_group.items():
            for pl, lines in d.items():
                merged.setdefault(pl, []).extend(f"\u300a{g}\u300b{x}" for x in lines)
        for pl, lines in merged.items():
            try:
                distilled[pl] = distill(client, pl, lines, args.groups, args.max_tokens)
                ss = distilled[pl].get("speaking_style")
                keys = list(ss) if isinstance(ss, dict) else "?"
                print(f"  蒸馏 OK {pl}: 分团键 {keys}")
            except Exception as e:  # noqa: BLE001
                print(f"  !! 蒸馏失败 {pl}: {type(e).__name__}: {e}")

    # 写进两团补丁的 profile_updates
    for g in args.groups:
        p = PATCHES / f"{g}_patch.json"
        if not p.is_file():
            print(f"!! 缺补丁 {p.name}")
            continue
        patch = json.loads(p.read_text(encoding="utf-8"))
        fu = {x.get("uid"): x for x in (patch.get("profile_updates") or [])}
        n_imp = n_style = 0
        for pl, lines in per_group[g].items():
            uid = UID.get(pl)
            if not uid:
                continue
            rec = fu.setdefault(uid, {"uid": uid})
            imps = rec.setdefault("add_impressions", [])
            for x in lines:
                entry = f"\u300a{g}\u300b{x}"
                if entry not in imps:
                    imps.append(entry)
                    n_imp += 1
            dis = distilled.get(pl) or {}
            # 只取属于本团的键（模型按团分键输出）
            for field, key in (("append_speaking_style", "speaking_style"),
                               ("append_rp_style", "rp_style")):
                val = dis.get(key)
                if isinstance(val, dict):
                    val = val.get(g)
                if not val or "\u65e0\u8db3\u591f\u6750\u6599" in str(val):
                    continue
                add = f"\u300a{g}\u300b{val}".strip()
                if add not in (rec.get(field) or ""):
                    rec[field] = ((rec.get(field) or "") + "\n" + add).strip()
                    if field == "append_speaking_style":
                        n_style += 1
            for h in dis.get("highlights") or []:
                if not isinstance(h, dict):
                    continue
                if h.get("group") != g:
                    continue
                add = f"\u300a{g}\u300b\u9ad8\u5149\uff1a{h.get('text')}"
                if add not in imps:
                    imps.append(add)
                    n_imp += 1
        patch["profile_updates"] = list(fu.values())
        print(f"{g}: 追加印象 {n_imp} 条 · 风格 {n_style} 名 PL")
        if args.apply:
            bak = p.with_name(p.name + f".bak_plprose_{datetime.now():%Y%m%d_%H%M%S}")
            shutil.copy2(p, bak)
            p.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"  已写入 {p.name}（备份 {bak.name}）")
    if not args.apply:
        print("\n(dry-run; 加 --apply 写入)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
