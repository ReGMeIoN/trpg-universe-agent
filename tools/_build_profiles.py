# -*- coding: utf-8 -*-
"""把角色卡原文整理成 **wiki 风格的角色设定**（写进生产库的 `profile` 字段）。

设计口径（重要）：
  · **只整理，不编造** —— 所有设定 / 事件 / 台词都必须来自角色卡原文；
    prompt 里明确禁止补设定，模型只做「分节 + 排版 + 标关键词」。
  · 输出是一段 **Markdown 子集**（前端 wiki.js 会安全渲染）：
        ## 小节名        分节（简介 / 背景故事 / 能力与装备 / 人物关系 / 台词 / 杂项）
        - 列表项
        **粗体**  *斜体*  ==关键词==  > 台词
  · 复用 `_doc_text.extract_docx` 读卡（它能绕开 docx 的 zip **CRC 写错**，别再自己踩）。

用法:
    python tools\\_build_profiles.py --list                  # 列出所有卡 + 匹配到的角色
    python tools\\_build_profiles.py --only sjt_liya         # 生成草案并打印（不落盘）
    python tools\\_build_profiles.py --only sjt_liya --apply  # 写回生产库（备份 + 复验）
    python tools\\_build_profiles.py --group 圣剑英雄谭 --apply
    python tools\\_build_profiles.py --file "素材路径.docx" --apply
"""
from __future__ import annotations

import os
import argparse
import json
import re
import shutil
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from io import StringIO
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT / "tools"))
from _doc_text import extract_docx  # noqa: E402

WS = Path(os.environ.get("TRPG_WS", "workspace"))          # TRPG关系网
MATERIAL = WS / "\u7d20\u6750"                              # 素材
DATA = WS / "\u6570\u636e"                                  # 数据
OUT = PROJECT / "\u4ea7\u51fa" / "\u89d2\u8272\u8bbe\u5b9a"  # 产出/角色设定

OLLAMA = "http://127.0.0.1:11434"
MODEL = "qwen2.5:14b"

# 卡文件名主干 → 角色 id（自动匹配不到的手工补这里）
MANUAL_MAP: dict[str, str] = {
    "\u9634\u9633\u5dee\u4e8b\u5f55-\u725b": "pc_niuye",       # 阴阳差事录-牛 → 牛爷（占位，未命中会在 --list 里暴露）
}

# 卡头里这些维度的键值对会被提取进 attrs（而不是占正文）
HEAD_DIMS = {"\u79cd\u65cf", "\u6027\u522b", "HP", "\u5e74\u9f84", "\u804c\u4e1a",
             "\u8eab\u9ad8", "\u4f53\u91cd", "\u9635\u8425", "\u51fa\u8eab", "\u79f0\u53f7",
             "\u4f53\u578b", "\u8eab\u4efd", "\u5916\u8c8c", "\u6027\u683c", "\u6240\u5c5e"}

PROMPT = """你是跑团 wiki 的编辑。下面是一张 TRPG 角色卡的原文，请把它整理成 wiki 风格的角色条目正文。

【铁律】
1. **只整理，不许编造**。所有设定、事件、装备、台词都必须来自下面原文；原文没有的信息一律不要补，
   不要写"可能""大概"，也不要自己编人物关系。
2. **绝对不要压缩成摘要！** 这是设定资料，要让读者看到原文的细节。请**逐段**整理，
   保留原文的描写、心理、动作、场景细节。输出长度应当与原文**相当**（不得少于原文的一半）。
   禁止用"一次冒险中他发现了…"这种一句话概括一整段叙事。
3. **台词**：原文里带引号（“”「」或 "）的话，原样抄进 `> ` 引用块，一句一块，不要改写、不要重复。
4. `## 小节名` **只能**用这 6 个：简介 / 背景故事 / 能力与装备 / 人物关系 / 台词 / 杂项。
   原文里的其他小标题（武器名、技能组、属性表…）**不要**另开 `##`，改成 `- ` 列表项或 **粗体** 行。
5. 原文没有对应内容的小节，**直接省略**，不要为了凑格式硬写。
6. 属性、数值、技能点这类表格数据，用 `- **项**：值` 的形式逐条列出，不要漏。

【输出格式】只使用这套 Markdown 子集，不要代码块包裹，不要前言结语：
- `## 小节名` 分节
- 段落之间空一行；列表用 `- `；子项缩进两格
- `**粗体**` 强调，`*斜体*` 补充
- `==关键词==` 标出**专有名词**（技能名、武器/道具名、地名、组织、称号），首次出现时标
- `> ` 放台词

【角色名】{name}

【角色卡原文】
---
{text}
---

直接输出整理后的正文："""


def norm(s: str) -> str:
    return re.sub(r"[\s()（）\[\]【】!！.。·\-_]+", "", str(s or "")).lower()


def load_chars() -> tuple[dict, list]:
    doc = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    return doc, doc["characters"]


def find_cards() -> list[tuple[str, Path]]:
    """返回 (团名, 卡路径) —— 只认 素材/<团>/*.docx|doc"""
    out: list[tuple[str, Path]] = []
    if not MATERIAL.is_dir():
        return out
    for g in sorted(MATERIAL.iterdir()):
        if not g.is_dir():
            continue
        for f in sorted(g.iterdir()):
            if f.suffix.lower() in (".docx", ".doc", ".docm"):
                out.append((g.name, f))
    return out


def match_char(group: str, card: Path, chars: list) -> dict | None:
    """把卡匹配到角色：先手工表 → 文件名主干 → 名字互相包含。"""
    stem = card.stem
    base = re.sub(r"[\s(（]*(最终版|强化|\d+)[)）]*", "", stem).strip()
    for key in (stem, base):
        cid = MANUAL_MAP.get(key)
        if cid:
            return next((c for c in chars if c.get("id") == cid), None)

    pool = [c for c in chars if group in (c.get("groups") or [])] or chars
    nb, ns = norm(base), norm(stem)
    # 1) 主干与角色名完全一致
    for c in pool:
        if norm(c.get("name")) in (nb, ns):
            return c
    # 2) 主干包含角色名（如「魔法少女威士忌」→「威士忌」）
    cands = []
    for c in pool:
        n = norm(c.get("name"))
        if len(n) >= 2 and (n in nb or n in ns):
            cands.append(c)
    if len(cands) == 1:
        return cands[0]
    # 3) 角色名包含主干
    for c in pool:
        n = norm(c.get("name"))
        if len(nb) >= 2 and nb in n:
            return c
    return None


def read_card(path: Path) -> str:
    try:
        text, _meta = extract_docx(path)
        return text or ""
    except Exception as e:                                  # noqa: BLE001
        print(f"  !! 读卡失败 {path.name}: {e}")
        return ""


def ask_llm(prompt: str, model: str = MODEL, timeout: int = 900) -> str:
    body = json.dumps({
        "model": model, "prompt": prompt, "stream": False,
        "options": {"num_ctx": 32768, "num_predict": 6000, "temperature": 0.25},
    }).encode("utf-8")
    req = urllib.request.Request(OLLAMA + "/api/generate", data=body,
                                 headers={"content-type": "application/json"}, method="POST")
    with urllib.request.urlopen(req, timeout=timeout) as r:
        d = json.loads(r.read().decode("utf-8"))
    return (d.get("response") or "").strip()


def raw_profile(text: str) -> str:
    """**零改写**：把角色卡原文直接转成 profile。

    只做轻量结构识别（全部是规则，不用模型）：
      · 去掉卡头部的元信息（团名横幅、「人物设定」这类）
      · 整行被引号包住、且不太长的 → 台词块 `> `
      · 「种族：X」「HP：20」这类键值行 → 合并进开头一行
      · 其余原样保留分段 —— 一个字都不改
    """
    lines = [l.rstrip() for l in StringIO(text).read().split("\n")]

    def is_noise(l: str) -> bool:
        s = l.strip()
        if not s:
            return False
        if re.match(r"^[-—=＝*＊#\s]{2,}$", s):                 # 分隔线
            return True
        if re.match(r"^[—\-]{0,2}\s*人物设定\s*[—\-]{0,2}$", s):
            return True
        return False

    out: list[str] = []
    attr_out: dict = {}
    head_gone = False
    n_head = 0
    for raw in lines:
        s = raw.strip()
        if not s:
            if out and out[-1] != "":
                out.append("")
            continue
        if is_noise(s):
            continue
        # 卡头的键值行（只处理文件最前面几条）：「圣剑英雄：莉亚  种族：半兽人  性别：雌  HP：20」
        if not head_gone and n_head < 8:
            n_head += 1
            kv = re.findall(r"([\u4e00-\u9fa5A-Za-z]{1,6})\s*[：:]\s*([^\s：:]{1,24})", s)
            if len(kv) >= 2 and len(s) < 120:
                for k, v in kv:
                    if k in HEAD_DIMS:              # 认识的维度 → 进 attrs，不占正文
                        attr_out[k] = v.replace("（", "(").strip()
                continue
        head_gone = True
        # 单行小节标题：「背景故事：」「人物关系：」→ ## 小节
        m = re.match(r"^(背景故事|人物设定|人物关系|关系|能力|技能|装备|经历|简介|设定|"
                     r"外貌|性格|台词|杂项|故事|身世)\s*[：:]\s*$", s)
        if m:
            out.append(f"## {m.group(1)}")
            continue
        if re.match(r"^[—\-]{2,}.*[—\-]{2,}$", s):       # 「——圣剑英雄传——」这类横幅
            continue
        # 台词：整行被一对引号包住
        if re.match(r'^[“"「『].{0,200}[”"」』]$', s):
            out.append("> " + s)
            continue
        out.append(s)
    txt = "\n".join(out).strip()
    txt = re.sub(r"\n{3,}", "\n\n", txt)
    return txt, attr_out


def tidy(text: str) -> str:
    """清掉模型偶尔多给的代码块包裹 / 前言。"""
    t = text.strip()
    t = re.sub(r"^```[a-z]*\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    t = re.sub(r"^(好的|以下是|这是)[^\n]*\n+", "", t)
    # 只保留我们支持的语法：把 3 级标题降成 2 级
    t = re.sub(r"(?m)^#{3,}\s*", "## ", t)
    return t.strip()


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="列出卡与匹配结果")
    ap.add_argument("--only", default=None, help="只做一个角色 id")
    ap.add_argument("--group", default=None, help="只做一个团")
    ap.add_argument("--file", default=None, help="直接指定卡文件")
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--apply", action="store_true", help="写回生产库")
    ap.add_argument("--raw", action="store_true",
                    help="零改写：直接把卡原文转成 profile（不用模型、零信息损失）")
    ap.add_argument("--keep", action="store_true", help="保留草案到 产出/角色设定/")
    args = ap.parse_args()

    _doc, chars = load_chars()
    cards = find_cards()
    matched: list[tuple[str, Path, dict | None]] = [(g, p, match_char(g, p, chars)) for g, p in cards]

    if args.list or (not args.only and not args.group and not args.file):
        print(f"角色卡 {len(cards)} 张 → 匹配到角色 {sum(1 for _,_,c in matched if c)} 个\n")
        for g, p, c in matched:
            mark = f"{c.get('id'):<26} {c.get('name')}" if c else "** 未匹配（加进 MANUAL_MAP）**"
            print(f"  [{g}] {p.name:<32} → {mark}")
        print(f"\n角色总数 {len(chars)}；其中已有 profile 的 {sum(1 for c in chars if c.get('profile'))} 个")
        return 0

    todo: list[tuple[str, Path, dict]] = []
    if args.file:
        fp = Path(args.file)
        c = match_char(fp.parent.name, fp, chars)
        if not c:
            print(f"!! 匹配不到角色：{fp.name}")
            return 1
        todo.append((fp.parent.name, fp, c))
    else:
        for g, p, c in matched:
            if not c:
                continue
            if args.only and c.get("id") != args.only:
                continue
            if args.group and g != args.group:
                continue
            todo.append((g, p, c))

    if not todo:
        print("没有要处理的卡。")
        return 0
    print(f"待处理 {len(todo)} 张卡（模型 {args.model}）\n")

    results: dict[str, str] = {}
    result_attrs: dict[str, dict] = {}
    for i, (g, path, c) in enumerate(todo, 1):
        cid, name = c.get("id"), c.get("name")
        text = read_card(path)
        if not text.strip():
            print(f"[{i}/{len(todo)}] {name} 卡是空的，跳过")
            continue
        if args.raw:
            # 零改写：不用模型，直接把原文搬进来（只做轻量结构识别）
            out, extra = raw_profile(text)
            result_attrs[cid] = extra
            note = "原文直搬（零改写）"
        else:
            print(f"[{i}/{len(todo)}] {name}（{cid}）· 卡 {len(text)} 字 → 生成中…")
            t0 = time.time()
            try:
                out = tidy(ask_llm(PROMPT.format(name=name, text=text[:24000]), args.model))
            except urllib.error.URLError as e:
                print(f"  !! Ollama 调用失败：{e}")
                return 1
            note = f"LLM 整理（{args.model}，{time.time() - t0:.0f}s）"
        if not out:
            print("  !! 内容为空，跳过")
            continue
        results[cid] = out
        heads = re.findall(r"(?m)^##\s*(.+)$", out)
        print(f"[{i}/{len(todo)}] {name}（{cid}）· 卡 {len(text)} 字 → {len(out)} 字 · {note}" +
              (f" · 分节：{'、'.join(heads)}" if heads else ""))

    if not results:
        return 0

    OUT.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if not args.apply or args.keep:
        for cid, txt in results.items():
            (OUT / f"{cid}.md").write_text(txt, encoding="utf-8")
        print(f"\n草案已写入 {OUT}")

    if args.only and not args.apply:
        cid = next(iter(results))
        print(f"\n===== {cid} 草案预览 =====\n")
        print(results[cid][:3000])
        return 0

    if not args.apply:
        print("\n(dry-run；加 --apply 写回生产库)")
        return 0

    cf = DATA / "characters.json"
    bdir = DATA / f"_bak_profile_{stamp}"
    bdir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cf, bdir / cf.name)
    n = 0
    n_attr = 0
    for c in chars:
        cid = c.get("id")
        if cid in results:
            c["profile"] = results[cid]
            c["profile_src"] = "角色卡"
            n += 1
            extra = result_attrs.get(cid) or {}
            if extra:
                at = c.get("attrs") if isinstance(c.get("attrs"), dict) else {}
                for k, v in extra.items():
                    at.setdefault(k, v)          # 卡头信息进 attrs；已有值不覆盖
                c["attrs"] = at
                n_attr += 1
    cf.write_text(json.dumps(_doc, ensure_ascii=False, indent=2), encoding="utf-8")

    chk = json.loads(cf.read_text(encoding="utf-8"))["characters"]
    with_p = sum(1 for c in chk if c.get("profile"))
    print(f"\n已写入（备份 {bdir}）")
    print(f"  本次更新 {n} 个角色（另 {n_attr} 个补了卡头属性）· 全库带 profile 的 {with_p}/{len(chk)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
