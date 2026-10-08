# -*- coding: utf-8 -*-
"""Extract readable text from legacy Word .doc (OLE2 binary) — pure Python, no COM.

Why pure Python: Word COM automation hangs under a restricted sandbox (cross-process
ALPC over named pipes is blocked), and the host has no antiword/catdoc/LibreOffice.

How: parse the OLE2 compound file, pull the **WordDocument stream** (text lives there;
images/embeds live in other streams and are the main noise source), then scan for
UTF-16 text runs (both byte orders, both phases, best quality wins). This is a
best-effort reader for character sheets — good for names/setting prose, NOT a
byte-exact converter.

Usage:
    .venv\\Scripts\\python.exe tools\\_doc_text.py <in.doc> [<out.txt>]
    .venv\\Scripts\\python.exe tools\\_doc_text.py --dir <dir> [--out-dir <dir>]
    .venv\\Scripts\\python.exe tools\\_doc_text.py --probe <in.doc>   # stream listing only
"""
from __future__ import annotations

import re
import struct
import sys
from pathlib import Path

FREE = (0xFFFFFFFE, 0xFFFFFFFF)
OLE_SIG = b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"


# --------------------------------------------------------------------------- OLE2
class Ole:
    def __init__(self, data: bytes):
        if data[:8] != OLE_SIG:
            raise ValueError("not an OLE2 compound file")
        self.data = data
        self.sector_size = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_sector_size = 1 << struct.unpack_from("<H", data, 0x20)[0]
        self.num_fat = struct.unpack_from("<I", data, 0x2C)[0]
        self.dir_start = struct.unpack_from("<I", data, 0x30)[0]
        self.mini_cutoff = struct.unpack_from("<I", data, 0x38)[0]
        self.mini_fat_start = struct.unpack_from("<I", data, 0x3C)[0]
        self.num_mini_fat = struct.unpack_from("<I", data, 0x40)[0]
        self.difat_start = struct.unpack_from("<I", data, 0x44)[0]
        self.num_difat = struct.unpack_from("<I", data, 0x48)[0]
        self._load_fat()
        self._load_dir()
        self._load_mini()

    def _sector(self, n: int) -> bytes:
        off = 512 + n * self.sector_size
        return self.data[off:off + self.sector_size]

    def _load_fat(self) -> None:
        difat = list(struct.unpack_from("<109I", self.data, 0x4C))
        sec = self.difat_start
        guard = 0
        while sec not in FREE and guard < self.num_difat + 8:
            chunk = self._sector(sec)
            vals = list(struct.unpack_from("<%dI" % (self.sector_size // 4), chunk, 0))
            difat.extend(vals[:-1])
            sec = vals[-1]
            guard += 1
        self.fat: list[int] = []
        for fs in difat:
            if fs in FREE:
                continue
            if self.num_fat and len(self.fat) // (self.sector_size // 4) >= self.num_fat:
                break
            chunk = self._sector(fs)
            self.fat.extend(struct.unpack_from("<%dI" % (self.sector_size // 4), chunk, 0))

    def _chain(self, start: int, fat: list[int]) -> list[int]:
        out: list[int] = []
        cur = start
        guard = 0
        while cur not in FREE and guard < 200000:
            out.append(cur)
            if cur >= len(fat):
                break
            cur = fat[cur]
            guard += 1
        return out

    def _read_fat_chain(self, start: int, size: int) -> bytes:
        out = bytearray()
        for n in self._chain(start, self.fat):
            out += self._sector(n)
            if len(out) >= size:
                break
        return bytes(out[:size])

    def _load_dir(self) -> None:
        raw = self._read_fat_chain(self.dir_start, 1 << 30)
        self.entries: list[dict] = []
        for i in range(0, len(raw) - 127, 128):
            e = raw[i:i + 128]
            nlen = struct.unpack_from("<H", e, 0x40)[0]
            typ = e[0x42]
            if typ == 0:
                continue
            name = e[:max(0, nlen - 2)].decode("utf-16-le", "replace") if nlen >= 2 else ""
            self.entries.append({
                "name": name,
                "type": typ,
                "start": struct.unpack_from("<I", e, 0x74)[0],
                "size": struct.unpack_from("<Q", e, 0x78)[0] & 0xFFFFFFFF,
            })

    def _load_mini(self) -> None:
        root = next((e for e in self.entries if e["type"] == 5), None)
        self.mini_fat: list[int] = []
        self.mini_stream = b""
        if not root:
            return
        mf = self._read_fat_chain(
            self.mini_fat_start,
            max(self.num_mini_fat, 1) * self.sector_size,
        )
        if mf:
            self.mini_fat = list(struct.unpack_from("<%dI" % (len(mf) // 4), mf, 0))
        self.mini_stream = self._read_fat_chain(root["start"], root["size"])

    def _read_mini_chain(self, start: int, size: int) -> bytes:
        out = bytearray()
        for n in self._chain(start, self.mini_fat):
            off = n * self.mini_sector_size
            out += self.mini_stream[off:off + self.mini_sector_size]
            if len(out) >= size:
                break
        return bytes(out[:size])

    def stream(self, name: str) -> bytes | None:
        e = next((x for x in self.entries if x["name"] == name and x["type"] == 2), None)
        if not e:
            return None
        if e["size"] < self.mini_cutoff and self.mini_fat:
            return self._read_mini_chain(e["start"], e["size"])
        return self._read_fat_chain(e["start"], e["size"])


# --------------------------------------------------------------- text extraction
def _printable(code: int) -> bool:
    if 0x20 <= code <= 0x7E:
        return True
    if code in (0x0A, 0x0D, 0x09):
        return True
    for lo, hi in ((0x4E00, 0x9FFF), (0x3400, 0x4DBF), (0x3000, 0x303F),
                   (0xFF00, 0xFFEF), (0x2000, 0x206F), (0x3040, 0x30FF)):
        if lo <= code <= hi:
            return True
    return 0x00B7 <= code <= 0x00BB


def _runs(data: bytes, phase: int, big_endian: bool, min_len: int = 4) -> list[str]:
    out: list[str] = []
    buf: list[int] = []
    i = phase
    n = len(data)
    while i + 1 < n:
        lo, hi = data[i], data[i + 1]
        code = (lo << 8) | hi if big_endian else (lo | (hi << 8))
        if _printable(code):
            buf.append(code)
            i += 2
            continue
        if len(buf) >= min_len:
            out.append("".join(chr(c) for c in buf))
        buf = []
        i += 1 if (lo == 0 or hi == 0) else 2
    if len(buf) >= min_len:
        out.append("".join(chr(c) for c in buf))
    return out


_CJK = re.compile(r"[\u4e00-\u9fff]")

# 高频常用字 + 中文标点: 真实正文密布; "错位读取"/图片字节凑出的生僻字串几乎命中不了
_COMMON = set(
    "的一是不了人我在有他这为之大来以个中上们到说国和地也子时道出而要于就下得可你年生自"
    "会那后能对着事其里所去行过家十用发天如然作方成者多日都三小军二无同么经法当起与好看"
    "学进种将还分此心前面又定见只主没公从很真给几被但位次呢吧吗因由点两问最间手力实外头"
    "面身体气东西南北水火土金木生死活走跑站坐吃喝笑哭想要做买卖打杀剑刀魔法神明暗黑白天"
    "夜晚风雷雪云海岛城村路门开关注打斗战死伤兄弟父母老师学生自己名字样式力量"
    "，。、！？：；「」『』（）《》—…“”‘’·"
)
_STOPWORDS = ("的", "了", "是", "我", "你", "他", "们", "不", "在", "有",
              "这", "那", "就", "和", "与", "被", "把", "个")


def quality_score(runs: list[str]) -> float:
    text = "".join(runs)
    if not text:
        return 0.0
    common = sum(1 for ch in text if ch in _COMMON)
    stop = sum(text.count(w) for w in _STOPWORDS)
    return (common + stop * 2) / len(text)


def _keep(run: str) -> bool:
    if len(run) < 4:
        return False
    if len(_CJK.findall(run)) < 2:
        return False
    common = sum(1 for ch in run if ch in _COMMON)
    return common >= 2 and common / len(run) >= 0.25


def _scan_best(blobs: list[bytes]) -> list[str]:
    best: list[str] = []
    best_score = 0.0
    for blob in blobs:
        if not blob:
            continue
        for phase in (0, 1):
            for big_endian in (False, True):
                runs = [r for r in _runs(blob, phase, big_endian) if _keep(r)]
                s = quality_score(runs)
                if s > best_score:
                    best, best_score = runs, s
    return best


def extract_doc(path: Path) -> tuple[str, dict]:
    data = path.read_bytes()
    meta: dict = {"streams": [], "source": "whole-file"}
    blobs = [data]
    try:
        ole = Ole(data)
        meta["streams"] = [f"{e['name']}:{e['size']}" for e in ole.entries if e["type"] == 2]
        wd = ole.stream("WordDocument")
        if wd:
            blobs = [wd]
            meta["source"] = f"WordDocument({len(wd)} bytes)"
    except (ValueError, struct.error, IndexError) as e:
        meta["ole_error"] = f"{type(e).__name__}: {e}"
    runs = _scan_best(blobs)
    lines: list[str] = []
    for r in runs:
        r = r.replace("\r", "\n").strip()
        if r:
            lines.append(r)
    return "\n".join(lines), meta


def extract_docx(path: Path) -> tuple[str, dict]:
    """Extract .docx body text (zip + word/document.xml), no python-docx needed."""
    import html
    import zipfile

    meta: dict = {"source": "docx(document.xml)"}
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile) as e:
        return "", {"source": f"docx failed: {type(e).__name__}: {e}"}
    xml = re.sub(r"</w:p\s*>", "\n", xml)
    # 段落内的多个 run(<w:t>) 必须直接拼接, 否则每行会被切碎
    lines: list[str] = []
    for para in xml.split("\n"):
        text = "".join(html.unescape(t) for t in re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S))
        text = text.replace("\t", " ").strip()
        if text:
            lines.append(text)
    return "\n".join(lines), meta


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        return 1
    if args[0] == "--probe":
        p = Path(args[1])
        ole = Ole(p.read_bytes())
        print(f"{p.name}: sector={ole.sector_size} minicut={ole.mini_cutoff}")
        for e in ole.entries:
            kind = {1: "storage", 2: "stream", 5: "root"}.get(e["type"], str(e["type"]))
            print(f"  {kind:<8} {e['size']:>10}  {e['name']}")
        return 0
    if args[0] == "--dir":
        src = Path(args[1])
        out_dir = Path(args[args.index("--out-dir") + 1]) if "--out-dir" in args else None
        targets = sorted(p for p in src.iterdir() if p.suffix.lower() in (".doc", ".docx"))
    else:
        targets = [Path(args[0])]
        out_dir = Path(args[1]).parent if len(args) > 1 else None
    if not targets:
        print("no .doc/.docx files")
        return 2
    for p in targets:
        if p.suffix.lower() == ".docx":
            text, meta = extract_docx(p)
        else:
            text, meta = extract_doc(p)
        dest = (out_dir / (p.stem + ".txt")) if out_dir else p.with_suffix(".doc.txt")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
        print(f"OK  {p.name} -> {dest}  ({len(text)} chars, src={meta['source']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
