# -*- coding: utf-8 -*-
"""全库文本检索(含 docx 正文): 排查"某个名字/台词到底在不在库里"。

为什么需要它(2026-10-03 待办 4 "米裕" 卡住的根因):
  - 素材里的角色卡是 .docx(压缩包), grep / Select-String 读不到正文;
  - 中文文本编码混杂(UTF-8 / GB18030 / UTF-16), 直接读会乱码或漏命中。

用法(项目根目录):
    .venv\\Scripts\\python.exe tools\\find_text_in_library.py 米裕 米玉 米雨
    .venv\\Scripts\\python.exe tools\\find_text_in_library.py --root "<工作区>" 米裕
    .venv\\Scripts\\python.exe tools\\find_text_in_library.py --out .tmp\\find.md 米裕

退出码: 0 = 至少一处命中, 2 = 一处没有(方便脚本串联)。
"""
from __future__ import annotations

import argparse
import html
import re
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

SKIP_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__",
    "_whisper_models", "qq-chat-exporter", "napcat", "NapCatQQ",
    "_headless_profile", "_headless_profile2",
    # 派生/运行态目录: 报告与暂存区里出现的名字不算"库里存在"的证据,
    # 而且它们会把上一次检索报告本身扫进来(自我引用污染, 实测踩过)。
    ".trpg", ".tmp",
}
TEXT_EXTS = {
    ".txt", ".md", ".json", ".csv", ".tsv", ".html", ".htm", ".xml",
    ".yaml", ".yml", ".log", ".srt", ".ass", ".vtt", ".py", ".ps1", ".js",
}
DOCX_EXTS = {".docx"}
DOC_LEGACY_EXTS = {".doc"}
LEGACY_EXTS = {".xls", ".ppt", ".pdf", ".odt"}

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _doc_text import extract_doc, extract_docx  # noqa: E402  (同目录工具: OLE2/docx 正文提取)

_w_t = re.compile(r"<w:t[^>]*>(.*?)</w:t>", re.S)
_w_par = re.compile(r"</w:p\s*>")


def _decode(raw: bytes) -> tuple[str | None, str]:
    """尽力解码: BOM -> UTF-8 -> GB18030。二进制返回 (None, 原因)。"""
    if raw.startswith(b"\xef\xbb\xbf"):
        try:
            return raw.decode("utf-8-sig"), "utf-8-sig"
        except UnicodeDecodeError:
            pass
    if raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
        try:
            return raw.decode("utf-16"), "utf-16"
        except UnicodeDecodeError:
            pass
    if b"\x00" in raw[:4096]:
        return None, "二进制(含 NUL)"
    for enc in ("utf-8", "gb18030"):
        try:
            return raw.decode(enc), enc
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", "replace"), "latin-1(兜底)"


def read_text_file(p: Path, max_bytes: int) -> tuple[str | None, str]:
    if p.stat().st_size > max_bytes:
        return None, f"超过大小上限({p.stat().st_size} bytes)"
    return _decode(p.read_bytes())


def read_docx(p: Path) -> tuple[str | None, str]:
    """(已由 _doc_text.extract_docx 取代, 保留薄包装以防外部引用)"""
    return extract_docx(p)


def iter_files(roots: list[Path]):
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if any(part in SKIP_DIRS for part in p.parts):
                continue
            yield p


def main() -> int:
    try:  # 控制台按 UTF-8 输出, 免得中文/符号在 GBK 控制台上炸掉
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="全库文本检索(含 docx 正文)")
    ap.add_argument("names", nargs="*", help="要检索的名字/词(可多个)")
    ap.add_argument("--names-file", help="每行一个词的清单文件")
    ap.add_argument("--root", action="append", default=[],
                    help="检索根目录(可重复); 默认=config 的 workspace.root + 本仓库 docs")
    ap.add_argument("--out", help="报告路径(默认 <ws>/.trpg/reports/名称检索_<词>.md)")
    ap.add_argument("--max-mb", type=int, default=64, help="单文件大小上限(MB)")
    ap.add_argument("--literal", action="store_true", help="按字面量匹配(默认即字面量, 保留兼容)")
    args = ap.parse_args()

    names = list(args.names)
    if args.names_file:
        names += [ln.strip() for ln in Path(args.names_file).read_text(encoding="utf-8").splitlines()
                  if ln.strip()]
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        print("需要至少一个检索词。")
        return 1

    cfg = load_config(ROOT / "config.yaml")
    ws = Workspace.from_config(cfg)
    roots = [Path(r) for r in args.root] or [ws.root, ROOT / "docs"]
    out = Path(args.out) if args.out else (ws.reports / f"名称检索_{names[0]}.md")
    out.parent.mkdir(parents=True, exist_ok=True)

    max_bytes = args.max_mb * 1024 * 1024
    hits: dict[str, list[tuple[str, int, str]]] = defaultdict(list)
    scanned = 0
    skipped: list[tuple[str, str]] = []
    legacy: list[str] = []

    for p in iter_files(roots):
        ext = p.suffix.lower()
        if ext in LEGACY_EXTS:
            legacy.append(str(p))
            continue
        if ext in DOC_LEGACY_EXTS:
            text, _meta = extract_doc(p)      # OLE2 WordDocument 流 + UTF-16 扫描
        elif ext in DOCX_EXTS:
            text, _meta = extract_docx(p)
        elif ext in TEXT_EXTS:
            text, note = read_text_file(p, max_bytes)
        else:
            continue
        scanned += 1
        if text is None:
            skipped.append((str(p), note))
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for name in names:
                if name in line:
                    hits[name].append((str(p), i, line.strip()[:300]))

    total = sum(len(v) for v in hits.values())
    lines: list[str] = []
    lines.append(f"# 名称检索报告 · {' / '.join(names)}\n")
    lines.append(f"- 检索根: {', '.join(str(r) for r in roots)}")
    lines.append(f"- 扫描文本文件: {scanned} 个(含 docx 正文提取)")
    lines.append(f"- 命中: {total} 处 / {len({h[0] for v in hits.values() for h in v})} 个文件")
    for name in names:
        lines.append(f"- 「{name}」: {len(hits[name])} 处")
    if legacy:
        lines.append(f"- [警告] 未解析的旧格式/PDF: {len(legacy)} 个(需要额外转换工具)")
    lines.append("")
    for name in names:
        lines.append(f"## 「{name}」")
        if not hits[name]:
            lines.append("(无命中)")
            lines.append("")
            continue
        lines.append("")
        for path, ln, text in hits[name]:
            lines.append(f"- `{path}`:{ln} — {text}")
        lines.append("")
    if legacy:
        lines.append("## 未解析清单")
        for x in legacy:
            lines.append(f"- {x}")
        lines.append("")
    if skipped:
        lines.append("## 跳过(二进制/超限)")
        for x, why in skipped[:50]:
            lines.append(f"- {x} — {why}")
        lines.append("")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"扫描 {scanned} 个文本文件; 命中 {total} 处; 报告 -> {out}")
    for name in names:
        print(f"  「{name}」: {len(hits[name])} 处")
    if legacy:
        print(f"  [警告] {len(legacy)} 个旧格式/PDF 未被解析")
    return 0 if total else 2


if __name__ == "__main__":
    sys.exit(main())
