# -*- coding: utf-8 -*-
"""生成《圣剑英雄谭 · 剧情编年史》：逐段详录剧情，而不是只抽角色/关系骨架。

为什么要它：extract 的口径是「角色/关系为纲」，6 段 100KB 的剧情最后只剩 42 条角色事件、
7 条关系 —— 主线（收剑历程、四骑士、最终战）没有成篇。本工具用同一批转写稿，
逐段产出**时间线式的详细纪要**，再拼成一份人读的编年史。

用法:
    .venv\\Scripts\\python.exe tools\\_chronicle_sjt.py            # 已有段落跳过, 只补缺
    .venv\\Scripts\\python.exe tools\\_chronicle_sjt.py --force    # 全部重跑
"""
from __future__ import annotations

import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import make_llm_client  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "圣剑英雄谭"
OUT_DIR = WS / ".trpg" / "extracts"
CHRONICLE = WS / "产出" / f"{GROUP}_剧情编年史.md"

SYSTEM = "你是跑团记录整理员，工作是把口语化的跑团录音转写稿整理成可读的剧情纪要。"

PROMPT = """下面是一段 TRPG 跑团录音的转写稿（每行形如 `[秒数 -> 秒数] 文本`，多人混说、有错字）。
请把它整理成**详细的剧情纪要**，供日后查证与复盘。

**本团已确认的人名对照（务必使用）**：
- KP（主持人）= 菌羊；ReGMeIoN 在本团是玩家（PL），不是 KP
- PC 与 PL：妮娜·可可=往、流星亚什=雪人、八重樱=宽、莉亚·岩心=ReGMeIoN、飒飒米=pd；
  琉珈·深谣 实为 NPC（由 KP 菌羊扮演）
- **转写里的「地牙?」「劳昌?」（也写作「牢仓?」）都指 莉亚·岩心（ReGMeIoN）**，直接按此归人
- **「结刻?」= 杰克（cross_jieke）**；**「石痕剑格?」不存在**（ASR 错字/幻觉，不采信）
- **火红骑士（吞星同款）不算天启四骑士之一**

硬要求：
1. 按时间顺序分小节，每节标题写成 `### [时:分] 小节名`（时:分 = 该节起始时间戳换算，如 [42:10]）。
2. **提到玩家时写成「角色名（PL名）」**，例如「八重樱（宽）」「妮娜·可可（往）」；
   只出现 PL 名而无法确定对应角色时写「宽?」；NPC 直接写名字（如「皇帝奥古斯都」「威尔娜」）。
3. 每节写清楚：**在哪、谁在场、发生了什么、怎么结束的**。战斗要写过程与结果（谁被打倒、用了什么手段）。
4. 关键台词、决定、承诺、赌注、线索、道具/圣剑的得失，尽量原话引用并标时间戳。
5. **玩家场外闲聊、规则讨论、玩梗一律不写**；只有影响剧情的信息才写。
6. 转写错字/听不清的名字照抄并在后面加 `?`，不要自己编一个更通顺的名字。
7. 不要写成抽象总结或评价，要写成"谁对谁做了什么、为什么、结果如何"的具体叙述。
8. 篇幅 **2500~5000 字**，宁详勿略；但不要复述原文，要整理成通顺的叙述。

只输出纪要正文（Markdown），不要任何前言、说明或"以下是..."。

转写稿：

"""


def chronicle_one(client, seg: Path, max_tokens: int) -> tuple[str, str, int, int]:
    text = seg.read_text(encoding="utf-8", errors="replace")
    res = client.chat(
        [{"role": "system", "content": SYSTEM},
         {"role": "user", "content": PROMPT + text}],
        max_tokens=max_tokens,
    )
    return seg.name, res.text, res.prompt_tokens, res.completion_tokens


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
    # deepseek-flash 是推理型: 实测段1/段4 的 reasoning 就能吃满 32000 -> content 空。
    # 默认给足 64000 预算; 仍不够时可 --max-tokens 再调, 或把段再切细。
    max_tokens = _arg_int("--max-tokens", 64000)
    cfg = load_config(ROOT / "config.yaml")
    route = cfg.extract.model_route
    prov = cfg.llm.provider_for(route)
    print(f"后端 {prov.type}/{prov.model} · 并发 {cfg.extract.concurrency} · max_tokens={max_tokens}")
    if not prov.api_key:
        print(f"!! 环境变量 {prov.api_key_env} 未设置")
        return 1
    client = make_llm_client(prov)

    segs = sorted((WS / ".trpg" / "segments").glob(f"{GROUP}_段*.txt"))
    if not segs:
        print("没有分段文件")
        return 1

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    todo = []
    for s in segs:
        out = OUT_DIR / f"{GROUP}_剧情纪要_{s.stem.split('_')[-1]}.md"
        if out.is_file() and not force and out.stat().st_size > 500:
            print(f"  跳过（已有）{out.name}")
            continue
        todo.append((s, out))

    tin = tout = 0
    if todo:
        print(f"开始生成 {len(todo)} 段剧情纪要 ...")
        with ThreadPoolExecutor(max_workers=max(1, int(cfg.extract.concurrency))) as ex:
            futs = {ex.submit(chronicle_one, client, s, max_tokens): (s, out) for s, out in todo}
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
                print(f"  OK {out.name}: {len(body)} 字 ({pi} in / {co} out)")
    print(f"token 合计: 输入 {tin} / 输出 {tout}")

    # 合并
    parts = [f"# {GROUP} · 剧情编年史\n",
             f"> 由 `tools/_chronicle_sjt.py` 依据 `素材/{GROUP}_转写.txt`（6 段、6.28 小时）生成；"
             f"生成时间 {datetime.now():%Y-%m-%d %H:%M}。\n"
             f"> 口径：只记剧情内发生的事，场外闲聊/规则讨论/玩梗不入；转写错字照抄并加 `?`。\n"]
    for s in segs:
        tag = s.stem.split("_")[-1]
        out = OUT_DIR / f"{GROUP}_剧情纪要_{tag}.md"
        if not out.is_file():
            continue
        parts.append(f"\n\n---\n\n## {tag}（{s.stem.split('_')[-2]}）\n")
        parts.append(out.read_text(encoding="utf-8").strip())
    CHRONICLE.parent.mkdir(parents=True, exist_ok=True)
    CHRONICLE.write_text("\n".join(parts), encoding="utf-8")
    print(f"OK 编年史: {CHRONICLE} ({CHRONICLE.stat().st_size} 字节)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
