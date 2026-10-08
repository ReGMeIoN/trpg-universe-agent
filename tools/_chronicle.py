# -*- coding: utf-8 -*-
"""通用版剧情编年史生成器（`_chronicle_sjt.py` 的团无关重构）。

用法:
    python tools/_chronicle.py --group "阴阳差事录 超自然怪谈"
    python tools/_chronicle.py --group X --force --max-tokens 64000 --concurrency 6

与 `_chronicle_sjt.py` 的区别:
- 团名/段数/时长不再写死; 团专属口径从 `.trpg/prompts/chronicle_<团名>.md` 读取
  (没有该文件也能跑, 只是少了人名对照的硬约束)。
- 段落按「段N」的数字排序(字符串排序会让 段10 排在 段2 前面)。
- 汇总页头写明来源、生成时间与口径。
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import make_llm_client  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
WORK = WS / ".trpg"
SEG_DIR = WORK / "segments"
OUT_DIR = WORK / "extracts"
PROMPT_DIR = WORK / "prompts"

SYSTEM = "你是跑团记录整理员，工作是把口语化的跑团录音转写稿整理成可读的剧情纪要。"

BASE = """下面是一段 TRPG 跑团录音的转写稿（每行形如 `[秒数 -> 秒数] 文本`，多人混说、有错字）。
请把它整理成**详细的剧情纪要**，供日后查证与复盘。

{{GROUP_RULES}}

硬要求：
1. 按时间顺序分小节，每节标题写成 `### [时:分] 小节名`（时:分 = 该节起始时间戳换算，如 [42:10]）。
2. 提到玩家时写成「角色名（PL名）」；只出现 PL 名而无法确定对应角色时写成「PL名?」；
   NPC 直接写名字。**PL 未确认的团**就只写角色名，不要猜 PL。
3. 每节写清楚：**在哪、谁在场、发生了什么、怎么结束的**。战斗要写过程与结果。
4. 关键台词、决定、承诺、赌注、线索、道具的得失，尽量原话引用并标时间戳。
5. **玩家场外闲聊、规则讨论、玩梗一律不写**；只有影响剧情的信息才写。
6. 转写错字/听不清的名字照抄并在后面加 `?`，不要自己编一个更通顺的名字。
7. 不要写成抽象总结或评价，要写成"谁对谁做了什么、为什么、结果如何"的具体叙述。
8. 篇幅 **2000~5000 字**，宁详勿略；但不要复述原文，要整理成通顺的叙述。

只输出纪要正文（Markdown），不要任何前言、说明或"以下是..."。

转写稿：

"""

SEG_RE = re.compile(r"_段(\d+)")


def seg_index(path: Path) -> int:
    m = SEG_RE.search(path.stem)
    return int(m.group(1)) if m else 0


def chronicle_one(client, seg: Path, prompt: str, max_tokens: int):
    text = seg.read_text(encoding="utf-8", errors="replace")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": prompt + text}],
        max_tokens=max_tokens,
    )
    return seg.name, res.text, res.prompt_tokens, res.completion_tokens


def load_group_rules(group: str) -> str:
    p = PROMPT_DIR / f"chronicle_{group}.md"
    if p.is_file():
        return p.read_text(encoding="utf-8").strip()
    return "（本团无专属口径文件，人名一律以转写里出现过的写法为准，拿不准加 `?`。）"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True)
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--max-tokens", type=int, default=64000,
                    help="deepseek-flash 是推理型, reasoning 会吃预算; 给小了 content 为空")
    ap.add_argument("--concurrency", type=int, default=None)
    ap.add_argument("--min-bytes", type=int, default=500, help="已有纪要小于该字节数视为失败产物")
    args = ap.parse_args()
    group = args.group

    cfg = load_config(ROOT / "config.yaml")
    prov = cfg.llm.provider_for(cfg.extract.model_route)
    conc = args.concurrency or int(cfg.extract.concurrency)
    print(f"团={group} 后端={prov.type}/{prov.model} 并发={conc} max_tokens={args.max_tokens}")
    if not prov.api_key:
        print(f"!! 环境变量 {prov.api_key_env} 未设置")
        return 1

    segs = sorted(SEG_DIR.glob(f"{group}_段*.txt"), key=seg_index)
    if not segs:
        print(f"没有分段文件: {SEG_DIR / (group + '_段*.txt')}")
        return 1
    print(f"分段 {len(segs)} 段: " + ", ".join(s.name for s in segs))

    prompt = BASE.replace("{{GROUP_RULES}}", load_group_rules(group))
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    todo: list[tuple[Path, Path]] = []
    for s in segs:
        out = OUT_DIR / f"{group}_剧情纪要_段{seg_index(s)}.md"
        if out.is_file() and not args.force and out.stat().st_size > args.min_bytes:
            print(f"  跳过（已有）{out.name}")
            continue
        todo.append((s, out))

    client = make_llm_client(prov)
    tin = tout = 0
    if todo:
        print(f"开始生成 {len(todo)} 段剧情纪要 ...")
        with ThreadPoolExecutor(max_workers=max(1, conc)) as ex:
            futs = {ex.submit(chronicle_one, client, s, prompt, args.max_tokens): (s, out)
                    for s, out in todo}
            for fut in as_completed(futs):
                s, out = futs[fut]
                try:
                    name, body, pi, co = fut.result()
                except Exception as e:  # noqa: BLE001
                    print(f"  !! {s.name}: {type(e).__name__}: {e}")
                    continue
                out.write_text(body, encoding="utf-8")
                tin += pi
                tout += co
                print(f"  OK {out.name}: {len(body)} 字 ({pi} in / {co} out)", flush=True)
    print(f"token 合计: 输入 {tin} / 输出 {tout}")

    hours = _audio_hours(group)
    parts = [
        f"# {group} · 剧情编年史\n",
        f"> 由 `tools/_chronicle.py` 依据 `素材/{group}_转写.txt`"
        + (f"（{len(segs)} 段、{hours:.2f} 小时录音）" if hours else f"（{len(segs)} 段）")
        + f"生成；生成时间 {datetime.now():%Y-%m-%d %H:%M}。\n"
        "> 口径：只记剧情内发生的事，场外闲聊/规则讨论/玩梗不入；转写错字照抄并加 `?`。\n",
    ]
    for s in segs:
        out = OUT_DIR / f"{group}_剧情纪要_段{seg_index(s)}.md"
        if not out.is_file():
            continue
        label = s.stem.split(f"{group}_段{seg_index(s)}_")[-1]
        parts.append(f"\n\n---\n\n## 段{seg_index(s)}（{label}）\n")
        parts.append(out.read_text(encoding="utf-8").strip())
    dest = WS / "产出" / f"{group}_剧情编年史.md"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("\n".join(parts), encoding="utf-8")
    print(f"OK 编年史: {dest} ({dest.stat().st_size} 字节)")
    return 0


def _audio_hours(group: str) -> float:
    """从断点状态 / 段落索引里取录音总时长(拿不到就返回 0)。"""
    total = 0.0
    st = WORK / "state"
    for p in st.glob("transcribe_*.json"):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if d.get("group") == group:
            total = max(total, float(d.get("audio_at_s") or 0) / 3600)
    return total


if __name__ == "__main__":
    raise SystemExit(main())
