# -*- coding: utf-8 -*-
"""外貌证据摘要：给「缺立绘」的角色，从编年史里捞与其相关的句子（外貌词优先）。

纪律（Skill trpg-chronicle-pipeline §3）：**先描述，再生图**。
这个工具产出的就是「描述」的证据源，不生成任何图片。

用法:
    python tools/_looks_digest.py --group "阴阳差事录 超自然怪谈" --group "魔法少女育成计划 6" --out <file.md>
"""
from __future__ import annotations

import os
import json
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))    # TRPG关系网
DATA = WS / "\u6570\u636e"                             # 数据
OUT = WS / "\u4ea7\u51fa"                              # 产出

# 外貌/形象相关词：含这些词的句子优先
LOOK_WORDS = [
    "穿", "戴", "长", "短", "高", "矮", "胖", "瘦", "老", "年轻", "岁", "脸", "眼", "瞳",
    "头发", "发色", "白", "黑", "红", "蓝", "绿", "紫", "金", "银", "灰", "粉", "橙", "黄",
    "衣", "裙", "袍", "帽", "鞋", "袜", "披风", "斗篷", "盔甲", "面具", "眼镜", "胡子",
    "身材", "皮肤", "肤", "痣", "疤", "纹身", "尾巴", "耳", "角", "翅膀", "触手", "兽",
    "少女", "少年", "女孩", "男孩", "女", "男", "妇人", "老人", "小孩", "怪物", "妖怪",
    "形象", "样子", "长相", "外貌", "模样", "变身前", "变身后", "形态", "装",
]
SENT_SPLIT = re.compile(r"(?<=[。！？!?\n])")


def split_sentences(text: str) -> list[str]:
    out = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        out.extend(s.strip() for s in SENT_SPLIT.split(line) if s.strip())
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass

    groups = [sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--group"]
    out_path = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else None
    if not groups:
        print(__doc__)
        return 1

    doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    chars = doc["characters"]

    blocks: list[str] = []
    for g in groups:
        chronicle = OUT / f"{g}_\u5267\u60c5\u7f16\u5e74\u53f2.md"   # <g>_剧情编年史.md
        text = chronicle.read_text(encoding="utf-8") if chronicle.is_file() else ""
        sents = split_sentences(text)
        targets = [
            c for c in chars
            if g in (c.get("groups") or []) and not c.get("avatar")
        ]
        blocks.append(f"\n# ===== {g}（编年史 {len(text)} 字 / 缺立绘 {len(targets)} 人）=====\n")
        for c in targets:
            names = [c.get("name") or ""] + [a for a in (c.get("aliases") or []) if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9·]{2,12}", a or "")]
            # 去掉括号后缀，用主名也搜一遍
            base = re.sub(r"（.*?）", "", c.get("name") or "").strip()
            if base and base not in names:
                names.append(base)
            hits, seen = [], set()
            for s in sents:
                if any(n and n in s for n in names):
                    if s in seen:
                        continue
                    seen.add(s)
                    hits.append((any(w in s for w in LOOK_WORDS), s))
            hits.sort(key=lambda t: not t[0])          # 外貌句在前
            picked, total = [], 0
            for is_look, s in hits:
                if total + len(s) > 900:
                    break
                picked.append(s if is_look else "· " + s)
                total += len(s)
            blocks.append(f"\n## {c.get('name')}  [{c.get('id')}]  提及 {len(hits)} 句\n")
            blocks.append(f"- 身份: {c.get('identity') or '(无)'}\n")
            blocks.append(f"- 备注: {(c.get('note') or '(无)')[:500]}\n")
            if c.get("aliases"):
                blocks.append(f"- 别名: {'/'.join(c['aliases'])}\n")
            for s in picked:
                blocks.append(f"  > {s}\n")

    body = "".join(blocks)
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(body, encoding="utf-8")
        print(f"written {out_path} ({len(body)} chars)")
    else:
        print(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
