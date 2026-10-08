# -*- coding: utf-8 -*-
"""盘点「哪些角色还没入库」。

思路：把**各团的转写稿**当作证据源，用库里已有的名字/别名做「已认领」集合，
再从转写里捞**高频候选人名**，减掉已认领的 —— 剩下的就是"在剧情里反复出现、但库里没有"的人。

⚠️ 频次统计天然有噪音（"老师""大家"这类会被捞出来），所以这条只用来**生成候选清单**，
   最终要不要入库由主人拍板（项目铁律：玩梗不入库、拿不准进 pending）。

用法：
    .venv\\Scripts\\python.exe tools\\_missing_roles_scan.py [--min 8] [--out 产出\\缺失角色候选.md]
"""
from __future__ import annotations

import os
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

WS = Path(os.environ.get("TRPG_WS", "workspace"))
MATERIAL = WS / "\u7d20\u6750"
DATA = WS / "\u6570\u636e"
REPORTS = WS / ".trpg" / "reports"

# 明显不是人名的噪音词（按出现过的误报补）
STOP = set("""
老师 师父 师傅 大家 我们 你们 他们 她们 咱们 各位 大人 家伙 那个 这个 什么 怎么 为什么
时候 现在 刚才 然后 所以 但是 因为 可以 应该 必须 已经 还是 就是 不是 没有 一个 一些 一边
一起 一下 一样 一直 一定 这里 那里 哪里 东西 地方 事情 问题 办法 感觉 意思 样子 结果
开始 结束 知道 觉得 认为 看到 听到 发现 出现 准备 需要 想要 打算 决定 记得 忘记 明白
先生 女士 小姐 同学 朋友 兄弟 姐妹 哥哥 姐姐 弟弟 妹妹 父亲 母亲 爸爸 妈妈 儿子 女儿
队长 老大 老板 老大 手下 成员 组织 公司 学校 班级 团队 小队 队伍 地图 房间 门口 走廊
攻击 防御 伤害 生命 技能 道具 装备 武器 行动 回合 判定 成功 失败 大成功 大失败 骰子
玩家 主持 场外 剧情 设定 角色 人物 名字 名字 时间 事件 故事 结局 番外 记录 文档 笔记
""".split())

CJK = re.compile(r"[\u4e00-\u9fff]{2,4}")


def load_library_names() -> set[str]:
    doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    names: set[str] = set()
    for c in doc["characters"]:
        for k in ("name", "id"):
            v = c.get(k)
            if v:
                names.add(str(v))
        for a in (c.get("aliases") or []):
            if a:
                names.add(str(a))
        # 「某某（备注）」这种也拆一下
        nm = str(c.get("name") or "")
        m = re.match(r"^([^（(]+)", nm)
        if m and len(m.group(1)) >= 2:
            names.add(m.group(1))
    return {n for n in names if 2 <= len(n) <= 12}


def transcript_files() -> list[Path]:
    return sorted(MATERIAL.glob("*\u8f6c\u5199*.txt"))


def scan(path: Path, known: set[str], min_hits: int) -> Counter:
    try:
        txt = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return Counter()
    # 去掉时间戳标记，只统计台词正文
    txt = re.sub(r"\[\d+\.\d+ -> \d+\.\d+\]", " ", txt)
    cnt: Counter = Counter()
    for w in CJK.findall(txt):
        if w in STOP:
            continue
        cnt[w] += 1
    # 已认领的（库里有 / 库里的名字包含它 / 它包含库里的名字）不算缺
    out: Counter = Counter()
    for w, n in cnt.items():
        if n < min_hits:
            continue
        if w in known:
            continue
        if any(w in k or k in w for k in known if len(k) >= 2):
            continue
        out[w] = n
    return out


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--min", type=int, default=8, help="候选至少出现几次（默认 8）")
    ap.add_argument("--out", default=str(WS / "\u4ea7\u51fa" / "\u7f3a\u5931\u89d2\u8272\u5019\u9009.md"))
    a = ap.parse_args()

    known = load_library_names()
    print(f"库内已知的名字/别名：{len(known)} 个")

    lines = ["# 缺失角色候选清单", "",
             "> 从各团**转写稿**里捞「高频出现、但库内没有」的词。",
             "> ⚠️ 频次统计有噪音，这条只用来**挑候选**；入库与否由主人拍板（玩梗不入库是铁律）。",
             f"> 过滤阈值：出现 ≥ {a.min} 次；已排除 {len(STOP)} 个常见非人名词。", ""]
    grand: Counter = Counter()
    for f in transcript_files():
        group = f.name.split("_")[0]
        cand = scan(f, known, a.min)
        grand.update(cand)
        top = cand.most_common(30)
        print(f"\n=== {f.name} ===")
        print("  " + ("、".join(f"{w}({n})" for w, n in top[:24]) or "（没有明显候选）"))
        lines.append(f"## {group}（{f.name}）")
        lines.append("")
        if top:
            lines.append("| 候选 | 出现次数 |")
            lines.append("|---|---|")
            for w, n in top:
                lines.append(f"| {w} | {n} |")
        else:
            lines.append("（没有超过阈值的候选）")
        lines.append("")

    lines.append("## 全库合并 TOP 60")
    lines.append("")
    lines.append("| 候选 | 总次数 |")
    lines.append("|---|---|")
    for w, n in grand.most_common(60):
        lines.append(f"| {w} | {n} |")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"\n清单 -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
