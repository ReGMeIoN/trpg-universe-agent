# -*- coding: utf-8 -*-
"""Clean extracted card text: strip stray WordprocessingML XML that leaked in.

Why: `_doc_text.extract_docx` walks `word/document.xml` text nodes; for content
wrapped in an `<w:sdt>` (content control) some cards ended up with raw XML in the
extracted text (seen in 魔法少女育成计划 6 / 白萱). This scrubs anything that looks like
a WordprocessingML tag or attribute soup, collapsing the line to its readable text.

usage: python tools/_clean_card_text.py <file-or-dir> [...]
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# <w:xxx ...> / </w:xxx> / <w:pPr .../> 这类标记
TAG = re.compile(r"</?[A-Za-z][\w:.-]*(?:\s[^<>]*)?/?>")
# 裸露的属性串: w:val="..." / w:paraId="..." 等
ATTR = re.compile(r'\s?[A-Za-z][\w:.-]*="[^"]*"')


def clean(text: str) -> tuple[str, int]:
    hits = len(TAG.findall(text))
    out = TAG.sub("", text)
    # 去掉剩下的裸属性(只在明显是 XML 残留的长行上做, 免得误伤正文里的英文引号)
    lines = []
    for ln in out.splitlines():
        if len(ATTR.findall(ln)) >= 3:
            ln = ATTR.sub("", ln)
        lines.append(ln.rstrip())
    return "\n".join(lines), hits


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    targets: list[Path] = []
    for a in sys.argv[1:]:
        p = Path(a)
        if p.is_dir():
            targets += sorted(p.glob("*.txt"))
        elif p.is_file():
            targets.append(p)
    if not targets:
        print(__doc__)
        return 1
    total = 0
    for p in targets:
        raw = p.read_text(encoding="utf-8", errors="replace")
        new, hits = clean(raw)
        if hits:
            p.write_text(new, encoding="utf-8")
            print(f"  cleaned {p.name}: {hits} 个 XML 标记, {len(raw)} -> {len(new)} 字符")
            total += hits
        else:
            print(f"  ok      {p.name}: 无需清理")
    print(f"共清理 {total} 个标记")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
