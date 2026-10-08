# -*- coding: utf-8 -*-
"""专项核对：妮娜·可可 / 莉亚·岩心 / 飒飒米 在转写稿里的戏份。

背景：这三位 PC 的名字在转写里 0 次被点名（转写没有说话人分离，且录音里常用 PL 昵称），
所以主编年史里他们几乎空白。本工具逐段扫原始转写，**只报有明确依据**的出场。

用法:
    .venv\\Scripts\\python.exe tools\\_trace_pcs_sjt.py [--force]
"""
from __future__ import annotations

import os
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import make_llm_client  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "圣剑英雄谭"
OUT_DIR = WS / ".trpg" / "extracts"
REPORT = WS / ".trpg" / "reports" / f"{GROUP}_三PC戏份核对.md"

SYSTEM = "你是跑团记录核对员，只输出 JSON。"

PROMPT = """这是一段 TRPG《圣剑英雄谭》的跑团录音转写稿（多人混说、ASR 错字很多，没能分离说话人）。

我们要核对**三名 PC 在本段的戏份**（他们几乎没被叫过角色名，可能用昵称/职业/第三人称代指）：

1. **飒飒米**（PL=pd）—— 提夫林吟游诗人，音之圣剑「小尤里」，理念「事不关己，只是一味传唱着英雄的故事」。
   线索：转写里疑以「一忧四人」（=吟游诗人）出现，会**唱诗/传唱英雄故事**。
2. **妮娜·可可**（PL=往）—— 人造人，炎之圣剑「血」，曾是女巫瑟莱娅的造物、屠村后守墓。
   线索：与**女巫、人造人、人偶、血、村庄/墓碑、教堂**相关。
3. **莉亚·岩心**（PL=ReGMeIoN）—— 半兽人，土系魔法师，土之圣剑「无双天下磁场爆破剑」，爱捏泥巴/土偶。
   线索：与**泥巴、陶土、土偶、石碗、地缝、磁场**相关；另有「地牙?」「劳昌?」两名待核。

请逐条找出本段里**可能属于这三人**的发言或行动，只输出 JSON：

{{"findings": [
  {{"who": "飒飒米|妮娜·可可|莉亚·岩心",
    "at": "时间戳(秒)",
    "quote": "转写原文（照抄，不要改写）",
    "why": "为什么归给他/她（依据）",
    "confidence": "high|medium|low"}}
]}}

硬要求：
- **只报有依据的**：没有把握就用 medium/low，并且 why 里说明只是推测；
- 本段若确实找不到，就返回空数组，不要硬凑；
- quote 必须是转写稿里真实存在的原句（照抄），不要自己润色；
- 只输出 JSON。

转写稿：

"""


def scan(client, seg: Path, max_tokens: int) -> tuple[str, list, int]:
    text = seg.read_text(encoding="utf-8", errors="replace")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": PROMPT + text}],
        json_schema={"type": "object", "properties": {"findings": {"type": "array"}},
                     "required": ["findings"]},
        max_tokens=max_tokens,
    )
    body = res.text.strip()
    if body.startswith("```"):
        body = body.split("```")[1]
        body = body.split("\n", 1)[1] if "\n" in body else body
    try:
        doc = json.loads(body)
    except json.JSONDecodeError:
        return seg.name, [], res.completion_tokens
    return seg.name, doc.get("findings") or [], res.completion_tokens


def _arg_int(flag: str, default: int) -> int:
    if flag in sys.argv:
        try:
            return int(sys.argv[sys.argv.index(flag) + 1])
        except (IndexError, ValueError):
            pass
    return default


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    force = "--force" in sys.argv
    # deepseek-flash 推理型: 段6 实测 reasoning 吃满 32000 -> 默认给 64000
    max_tokens = _arg_int("--max-tokens", 64000)
    cfg = load_config(ROOT / "config.yaml")
    prov = cfg.llm.provider_for(cfg.extract.model_route)
    client = make_llm_client(prov)

    segs = sorted((WS / ".trpg" / "segments").glob(f"{GROUP}_段*.txt"))
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for s in segs:
        tag = s.stem.split("_")[-1]
        out = OUT_DIR / f"{GROUP}_三PC核对_{tag}.json"
        if out.is_file() and not force:
            print(f"  跳过（已有）{out.name}")
            continue
        todo.append((s, out))

    if todo:
        print(f"扫描 {len(todo)} 段 ...")
        with ThreadPoolExecutor(max_workers=max(1, int(cfg.extract.concurrency))) as ex:
            futs = {ex.submit(scan, client, s, max_tokens): (s, out) for s, out in todo}
            for fut in as_completed(futs):
                s, out = futs[fut]
                try:
                    name, findings, _ = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  !! {s.name}: {type(e).__name__}: {e}")
                    continue
                out.write_text(json.dumps({"segment": s.name, "findings": findings},
                                          ensure_ascii=False, indent=2), encoding="utf-8")
                print(f"  OK {out.name}: {len(findings)} 条")

    # 合并报告
    rows: list[tuple[str, dict]] = []
    for s in segs:
        tag = s.stem.split("_")[-1]
        f = OUT_DIR / f"{GROUP}_三PC核对_{tag}.json"
        if not f.is_file():
            continue
        for x in (json.loads(f.read_text(encoding="utf-8")).get("findings") or []):
            rows.append((tag, x))
    lines = [f"# {GROUP} · 三 PC 戏份核对（飒飒米 / 妮娜·可可 / 莉亚·岩心）\n",
             f"- 由 `tools/_trace_pcs_sjt.py` 逐段扫描原始转写稿得出；共 **{len(rows)}** 条",
             "- 置信度：high=依据明确 / medium=较可能 / low=仅推测（**low 不建议直接入库**）\n"]
    for tag, x in sorted(rows, key=lambda t: (t[1].get("who", ""), t[1].get("at", ""))):
        lines.append(f"### [{tag}] {x.get('who')} @ {x.get('at')}  ({x.get('confidence')})\n")
        lines.append(f"- 原文：{x.get('quote')}")
        lines.append(f"- 依据：{x.get('why')}\n")
    REPORT.write_text("\n".join(lines), encoding="utf-8")
    from collections import Counter

    cnt = Counter(x.get("who") for _, x in rows)
    conf = Counter(x.get("confidence") for _, x in rows)
    print(f"\nOK 报告: {REPORT} ({len(rows)} 条)")
    print("  按人:", dict(cnt))
    print("  按置信度:", dict(conf))
    return 0


if __name__ == "__main__":
    sys.exit(main())
