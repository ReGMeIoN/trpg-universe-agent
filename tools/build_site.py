# -*- coding: utf-8 -*-
"""把「圣剑英雄谭」的资料编译成静态站（site/）所需的数据与素材。

产出：
    site/index.html / app.js / style.css        （前端，手写在同目录）
    site/data/story.json                        编年史 → 三幕 / 段 / 小节 / 正文
    site/data/roster.json                       本团 26 个角色（含头像路径、事件、关系数）
    site/data/relations.json                    本团关系边
    site/data/meta.json                         站点标题、世界观、统计
    site/assets/avatars/<原名>.jpg              头像/立绘（压缩到最长边 1000px）
    site/relations.html                         现成的关系图（路径改写后）

用法:
    .venv\\Scripts\\python.exe tools\\build_site.py
"""
from __future__ import annotations

import os
import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

WS_PATH = Path(os.environ.get("TRPG_WS", "workspace"))
GROUP = "圣剑英雄谭"
SITE = ROOT / "site"

SEG_RE = re.compile(r"^##\s+(.+?)（(段\d)）\s*$")
SEC_RE = re.compile(r"^###\s+(\[[^\]]+\])?\s*(.+?)\s*$")
APPENDIX_RE = re.compile(r"^##\s+附")

# 三幕划分（与 docs/圣剑英雄谭-交付说明.md 的总纲一致）
# mood = 该幕绘本放映时选的 BGM 情绪（对应 素材/bgm/ 的前缀分类）
ACTS = [
    {"id": "act1", "title": "第一幕 · 受命与第一把圣剑", "mood": "calm",
     "subtitle": "王城受命 · 雷之国 · 收徒威尔娜",
     "segments": ["段1"],
     "summary": "皇帝奥古斯都·烈灰命六人集齐十一把圣剑对抗天启四骑士，赐下地图与羽毛定牌；"
                "第一站雷之国遭遇古人侵袭，八重樱（宽）收下送剑少女威尔娜，雷之圣剑与她共鸣。"},
    {"id": "act2", "title": "第二幕 · 光 · 时间 · 火", "mood": "epic",
     "subtitle": "光之教皇国 · 海底三试炼 · 雪人故国",
     "segments": ["段2", "段3"],
     "summary": "光之教皇国决斗选出维克托、饥荒来袭时他拔起光之圣剑；海底教人族以过去/现在/未来三试炼"
                "换取时间圣剑；雪人故国遭火红骑士袭击，妮娜·可可（往）以血系作战将他爆头。"},
    {"id": "act3", "title": "第三幕 · 雪山 · 瘟疫 · 死亡与终局", "mood": "dark",
     "subtitle": "矮人国 · 冰晶圣兽 · 破桥抉择 · 虚空圣殿 · 亡云村庄 · 修正世界",
     "segments": ["段4", "段5", "段6"],
     "summary": "战争骑士带走了维克托的手与流星亚什全族；矮人国求学、雪山取得水晶圣剑；"
                "破桥三票引爆瘟疫村庄；虚空圣殿接过第十一把·虚无之剑；亡云村庄斩灭死亡骑士；"
                "真相揭晓后众人被迫成为新四骑士，流星亚什拒绝堕落，十一剑齐聚修正世界。"},
]

# 分段级情绪覆盖（没写就跟着所属幕；终章单独给 final）
SEG_MOOD = {"段6": "final", "段2": "epic", "段5": "sad"}

INTRO = (
    "人类王国为首的大陆上有十一个国度，诸族共存。直到**天启四骑士**——饥荒、战争、瘟疫、死亡——"
    "从天而降，所过之处国家毁灭。皇帝把希望寄托在**十一把圣剑**上，命六位圣剑使踏上收集之旅。"
    "而在这趟旅程的尽头，等着他们的是十二位贤者的旧账、以及一个需要被「修正」的世界。"
)

FACTION_OF = {
    "PC": "圣剑使", "NPC": "NPC", "BOSS": "天灾",
}


def load_env():
    cfg = load_config(ROOT / "config.yaml")
    ws = Workspace.from_config(cfg)
    if not ws.root.is_dir():
        raise SystemExit(f"找不到工作区 {ws.root}")
    return cfg, ws


def build_story(ws: Workspace) -> dict:
    chron = ws.output / f"{GROUP}_剧情编年史.md"
    lines = chron.read_text(encoding="utf-8").splitlines()
    segments: dict[str, dict] = {}
    order: list[str] = []
    cur_seg = None
    cur_sec = None
    stop = False
    for raw in lines:
        line = raw.rstrip()
        if APPENDIX_RE.match(line):          # 「附：三 PC 补录」「附二：答疑校正表」不进正编
            stop = True
        if stop:
            continue
        m = SEG_RE.match(line)
        if m:
            label, tag = m.group(1), m.group(2)
            cur_seg = {"id": tag, "tag": tag, "label": label, "sections": []}
            segments[tag] = cur_seg
            order.append(tag)
            cur_sec = None
            continue
        m = SEC_RE.match(line)
        if m and cur_seg is not None:
            stamp, title = (m.group(1) or "").strip("[]"), m.group(2)
            cur_sec = {"time": stamp, "title": title, "body": []}
            cur_seg["sections"].append(cur_sec)
            continue
        if cur_sec is not None and line.strip():
            cur_sec["body"].append(line.strip())
    for tag in order:
        for i, s in enumerate(segments[tag]["sections"], 1):
            s["key"] = f"{tag}_{i:03d}"      # CG / 原声 按这个 key 命名
            body = s["body"] if isinstance(s["body"], list) else [s["body"]]
            s["body"] = clean_text("\n".join(body))
            s["title"] = clean_text(s["title"])
    acts = []
    for a in ACTS:
        segs = [t for t in a["segments"] if t in segments]
        if not segs:
            continue
        acts.append({**a, "segments": segs,
                     "section_count": sum(len(segments[t]["sections"]) for t in segs)})
    # 段级情绪：SEG_MOOD 覆盖 > 所属幕的 mood（前端据此切 BGM）
    for a in acts:
        for t in a["segments"]:
            segments[t]["mood"] = SEG_MOOD.get(t, a.get("mood", "calm"))
    return {"acts": acts, "segments": [segments[t] for t in order]}


# ---------------------------------------------------------------- 正文清洗
# 编年史是给"内部查证"写的，带了一堆读者不需要的东西：时间戳引用、元说明、编者注。
# 站点是给人读故事的，这里统一洗掉（只删这些杂质，不动剧情）。
_NOTE_KEYWORDS = ("主人确认", "2026-", "修正：", "待确认", "存疑", "不采信", "原稿误记")


def _drop_paren_notes(t: str) -> str:
    """按括号配平删除"编者注"括号块（能处理括号内再套括号的情况）。"""
    out: list[str] = []
    i, n = 0, len(t)
    while i < n:
        if t[i] in "（(":
            depth, j = 0, i
            while j < n:
                if t[j] in "（(":
                    depth += 1
                elif t[j] in "）)":
                    depth -= 1
                    if depth == 0:
                        break
                j += 1
            block = t[i:j + 1] if j < n else t[i:]
            if any(k in block for k in _NOTE_KEYWORDS):
                i = j + 1
                continue
        out.append(t[i])
        i += 1
    return "".join(out)


# 与 KP 逐条核对后确认的术语（canon「答疑校正表」的子集）—— 正文一律用确认写法
TERM_FIX = [
    ("黄泳多", "煌炎国"), ("虚空镇店", "虚空圣殿"), ("虚空神殿", "虚空圣殿"),
    ("80铁饭", "80铁砧"), ("格洛斯达", "格洛斯塔"), ("无龙茶", "乌龙茶"),
    ("写者之实", "贤者之石"), ("血者之实", "贤者之石"),
    ("色蛮亚", "瑟莱娅·阿尔根"), ("色蛮", "瑟莱娅·阿尔根"), ("瑟蛮", "瑟莱娅·阿尔根"),
    ("艳术", "鼹鼠人"), ("焰术", "鼹鼠人"), ("炎术", "鼹鼠人"),
    ("士兮", "四骑士"), ("贤将", "铁匠"), ("铁将", "铁匠"), ("高文", "高温"),
    ("爱人国", "矮人国"), ("吉祖哥", "肌肉哥"), ("死鬼", "尸鬼"),
    ("牛家", "刘家"), ("南斯洛特", "兰斯洛特"), ("维克多", "维克托"),
    ("天地四骑士", "天启四骑士"), ("天骑四骑士", "天启四骑士"),
    ("天底四骑士", "天启四骑士"), ("天气四骑士", "天启四骑士"),
    ("PC们", "众人"), ("pc们", "众人"),
]


def clean_text(t: str) -> str:
    if not t:
        return ""
    for a, b in TERM_FIX:
        t = t.replace(a, b)
    ts = r"\d{2,}(?:\.\d+)?\s*(?:[-–—~至到]\s*\d{2,}(?:\.\d+)?)?\s*[?？]{0,2}"
    # 1) 括号包着的时间戳（含 [123-456] / [3876.08] / （15135-15137） / （约8462-8699） / （[7372.??]））
    t = re.sub(rf"[（(]\s*\[?\s*约?\s*{ts}\]?\s*[)）]", "", t)
    t = re.sub(rf"[（(]\s*约?\s*{ts}[)）]", "", t)
    t = re.sub(r"[（(]\s*\[\s*\d[^\]]{0,12}\]\s*[)）]", "", t)   # 兜底：括号里只有时间戳
    t = re.sub(r"（\s*\d{2,}\s*）", "", t)
    # 2) 裸露的时间戳 [123-456] / [3876.08] / [11319] / [7372.??]
    t = re.sub(rf"\[\s*约?\s*{ts}\]", "", t)
    t = re.sub(r"\[\s*\d[^\]]{0,12}\]", "", t)
    # 3) 编者注 / 查证性括号块
    t = _drop_paren_notes(t)
    # 4) 元说明措辞
    t = re.sub(r"KP\s*描述\s*[：:]\s*", "", t)
    t = re.sub(r"转写(?:里|中)?(?:有人判断|提到|出现)[：:]?\s*", "", t)
    t = re.sub(r"转写(?:里|中)(?:他|她|有人)?说[：:]?\s*", "", t)
    t = re.sub(r"转写(?:里|中)的?", "", t)
    t = re.sub(r"(?:相关)?名字在转写中作", "名字写作", t)
    t = re.sub(r"（?\s*音近写法待确认\s*）?", "", t)
    t = re.sub(r"（\s*(?:段\s*\d+\s*[，,、]?\s*)*\s*）", "", t)
    # 5) 清残渣
    t = re.sub(r"[（(]\s*[)）]", "", t)
    t = re.sub(r"（\s*[，、；]\s*", "（", t)
    t = re.sub(r"[，,]\s*([。！？；])", r"\1", t)
    t = re.sub(r"[，,]{2,}", "，", t)
    t = re.sub(r"[ \t]{2,}", " ", t)
    t = re.sub(r"\n{3,}", "\n\n", t)
    t = re.sub(r"^[，、；：\s]+", "", t)
    t = re.sub(r"[（(]\s*：\s*", "（", t)
    t = re.sub(r"[，、；]\s*([。！？])", r"\1", t)
    t = re.sub(r"^[：:]\s*", "", t)
    # 6) 存疑标记：中文词后的半角 ? 是转写存疑标记（术语已校正，读者不需要看到）
    t = re.sub(r"(?<=[\u4e00-\u9fff])\?", "", t)
    t = re.sub(r"\?(?=[\u4e00-\u9fff])", "", t)
    t = re.sub(r"\?{2,}", "", t)
    # 7) 角色档案里的来源前缀
    t = re.sub(r"^(?:角色卡设定|角色卡原件|转写)\s*[：:]\s*", "", t)
    # 「PC」→「众人」：必须避开 NPC / PC们 这类；先护住 NPC，再替换独立的 PC
    t = re.sub(r"NPC", "\x00", t)
    t = re.sub(r"(?<![A-Za-z])PC(?!s)(?![A-Za-z])", "众人", t)
    t = t.replace("\x00", "NPC")
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def clean_events(items: list) -> list:
    """角色档案里的"出场与事件"同样去噪（保留"段N"作为出处线索时改成·）。"""
    out = []
    for x in items or []:
        s = str(x)
        s = re.sub(r"^(段\s*\d+)\s*[：:]\s*", r"\1 · ", s)
        s = clean_text(s)
        if s:
            out.append(s)
    return out


def _sentences(text: str) -> list[str]:
    """把一小节正文切成句子（按空行分段，段内按句末标点断）。"""
    out: list[str] = []
    for para in (text or "").split("\n"):
        para = para.strip()
        if not para:
            continue
        for s in re.split(r"(?<=[。！？；])", para):
            if s:
                out.append(s)
    return out


def split_pages(text: str, limit: int = 210) -> list[str]:
    """把一小节的正文拆成"绘本页"。

    按 **句数均分** 而不是"贪婪填满"——贪婪会在末尾留一个两三行的小尾巴页，
    读起来像半空的书页。均分后每页字数接近，页数也更少。

    例：9 句 → 3 页各 3 句；10 句 → 4/3/3 句。
    """
    text = (text or "").strip()
    if not text:
        return [""]
    sents = _sentences(text)
    if not sents:
        return [text]
    total = sum(len(s) for s in sents)
    parts = max(1, -(-total // limit))          # 向上取整 = 需要几页
    if parts == 1:
        return [text]
    per = max(1, -(-len(sents) // parts))       # 向上取整 = 每页最少几句
    chunks: list[str] = []
    for i in range(0, len(sents), per):
        chunks.append("".join(sents[i:i + per]))
    return chunks if chunks else [text]


def build_pages(story: dict) -> list[dict]:
    """一页一段。每小节的**首页**挂 CG 与原声（后续页只有字）。"""
    pages: list[dict] = []
    for seg in story["segments"]:
        for s in seg["sections"]:
            chunks = split_pages(s.get("body", ""))
            for i, chunk in enumerate(chunks):
                pages.append({
                    "key": s["key"], "part": i, "parts": len(chunks),
                    "seg": seg["tag"], "seg_label": seg["label"],
                    "time": s.get("time", ""), "title": s["title"] if i == 0 else "",
                    "body": chunk,
                    "show_cg": i == 0,        # CG / 原声只挂在该小节的首页
                    "show_audio": i == 0,
                })
    for i, p in enumerate(pages):
        p["index"] = i
    return pages


def build_roster(ws: Workspace) -> dict:
    chars = json.loads(ws.data_file("characters").read_text(encoding="utf-8"))["characters"]
    rels = json.loads(ws.data_file("relations").read_text(encoding="utf-8"))["relations"]
    mine = [c for c in chars if GROUP in (c.get("groups") or [])]
    ids = {c["id"] for c in mine}
    rel_by: dict[str, list] = {i: [] for i in ids}
    for r in rels:
        if r.get("from") in ids:
            rel_by[r["from"]].append({"dir": "out", "other": r.get("to"), "type": r.get("type"),
                                      "strength": r.get("strength"), "event": r.get("event")})
        if r.get("to") in ids:
            rel_by[r["to"]].append({"dir": "in", "other": r.get("from"), "type": r.get("type"),
                                    "strength": r.get("strength"), "event": r.get("event")})
    name_of = {c["id"]: c.get("name") for c in mine}
    out = []
    for c in mine:
        tags = c.get("tags") or []
        ev = [i for e in (c.get("events") or []) for i in (e.get("items") or [])]
        ev = clean_events(ev)
        out.append({
            "id": c["id"], "name": c.get("name"), "aliases": c.get("aliases") or [],
            "identity": clean_text(c.get("identity") or ""), "tags": tags,
            "faction": FACTION_OF.get(tags[0] if tags else "", "其他"),
            "is_pc": "PC" in tags,
            "played_by": c.get("played_by") or "",
            "note": clean_text(c.get("note") or ""),
            "events": ev,
            "avatar": c.get("avatar") or "",
            "relations": [
                {**r, "other_name": name_of.get(r["other"], r["other"])}
                for r in rel_by.get(c["id"], [])
            ],
        })
    out.sort(key=lambda c: (not c["is_pc"], c["id"]))
    return {"characters": out, "count": len(out),
            "pc_count": sum(1 for c in out if c["is_pc"])}


def fmt_size(n: int) -> str:
    return f"{n / 1024:.0f} KB"


def copy_images(ws: Workspace, roster: dict) -> dict:
    """按角色的 avatar 字段复制（这样跨团角色如「结刻/杰克」的图也能带上）。"""
    from PIL import Image

    dst = SITE / "assets" / "avatars"
    dst.mkdir(parents=True, exist_ok=True)
    total_in = total_out = 0
    count = missing = 0
    seen: set[str] = set()
    for c in roster["characters"]:
        av = (c.get("avatar") or "").strip()
        if not av:
            missing += 1
            continue
        src = ws.root / av.replace("\\", "/")
        if not src.is_file():
            # 兜底：按团名前缀在 数据/头像 里找同名
            cand = ws.data / "头像" / Path(av).name
            if cand.is_file():
                src = cand
            else:
                print(f"  !! 缺图 {c['name']}: {av}")
                missing += 1
                continue
        if src.stem in seen:
            continue
        seen.add(src.stem)
        out = dst / (src.stem + ".jpg")
        try:
            im = Image.open(src).convert("RGB")
            w, h = im.size
            scale = 1000 / max(w, h)
            if scale < 1:
                im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
            im.save(out, "JPEG", quality=85, optimize=True)
            total_in += src.stat().st_size
            total_out += out.stat().st_size
            count += 1
        except Exception as e:  # noqa: BLE001
            print(f"  !! {src.name}: {type(e).__name__}: {e}")
    print(f"  头像 {count} 张: {total_in/1e6:.1f} MB -> {total_out/1e6:.1f} MB"
          + (f"（{missing} 个角色暂无图）" if missing else ""))
    # 清孤儿：换过立绘后，旧图（如 <角色>__image1.jpg）会留在目录里，
    # 前端只按 characters.json 的 avatar 取图，孤儿纯属占体积还会一起发布。
    for p in sorted(dst.glob("*.jpg")):
        if p.stem not in seen:
            p.unlink()
            print(f"  清理孤儿头像 {p.name}")
    return {"count": count, "bytes": total_out, "missing": missing}


def copy_relations(ws: Workspace) -> bool:
    src = ws.output / f"{GROUP}_关系图.html"
    if not src.is_file():
        return False
    html = src.read_text(encoding="utf-8")
    html = html.replace("../数据/头像/", "assets/avatars/")
    html = html.replace("../数据\\头像\\", "assets/avatars/")
    html = html.replace(".png", ".jpg").replace(".jpeg", ".jpg")
    (SITE / "relations.html").write_text(html, encoding="utf-8")
    return True


def sync_kv() -> bool:
    """首页主视觉：novelai/archive/18-trpg-sjt-kv/kv-a.png -> site/assets/kv.jpg（裁掉底部水印）。"""
    src = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '18-trpg-sjt-kv' / 'kv-a.png')
    if not src.is_file():
        return False
    from PIL import Image

    dst = SITE / "assets" / "kv.jpg"
    dst.parent.mkdir(parents=True, exist_ok=True)
    im = Image.open(src).convert("RGB")
    w, h = im.size
    im = im.crop((0, 0, w, int(h * 0.955)))          # 去掉画师串自带的角标
    scale = 900 / im.size[0]
    if scale < 1:
        im = im.resize((900, int(im.size[1] * scale)), Image.LANCZOS)
    im.save(dst, "JPEG", quality=88, optimize=True)
    print(f"  主视觉 assets/kv.jpg ({dst.stat().st_size//1024} KB)")
    return True


CG_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '17-trpg-sjt-cg')
PC_CG_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '22-trpg-sjt-cg-pc')   # 按 PC 外貌重画的一批（优先）
AVATAR_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '20-trpg-sjt-bachongying')
PL_DIR = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '21-trpg-sjt-pl')   # PL 立绘重做批次
CAND_DIR = ROOT / ".trpg" / "pickpage" / "cg-cand"     # 挑图页素材（不发布，故不在 site/ 内）
PICK_SITE = ROOT / ".trpg" / "pickpage"                 # 挑图页 + 缩略图都放这
BGM_SRC = ROOT / "素材" / "bgm"

# BGM 文件名的情绪前缀 → 站点 mood key（英文/中文都认；不写前缀的 mp3 归 calm）
MOOD_PREFIX = {
    "title": "title", "封面": "title", "标题": "title", "main": "title",
    "epic": "epic", "史诗": "epic", "战斗": "epic", "battle": "epic",
    "dark": "dark", "幽暗": "dark", "恐怖": "dark", "压迫": "dark",
    "calm": "calm", "宁静": "calm", "日常": "calm", "旅途": "calm",
    "sad": "sad", "悲怆": "sad", "悲伤": "sad", "离别": "sad",
    "final": "final", "终章": "final", "终局": "final", "结局": "final",
}


# ---------------------------------------------------------------- 立绘挑选登记
# 角色名 -> (候选图目录, 文件名前缀)。挑图页导出的 key 就是角色名（或「<角色名>立绘」）。
AVATAR_DIRS: dict[str, tuple[Path, str]] = {
    "八重樱": (AVATAR_DIR, "bachongying"),
    "飒飒米": (PL_DIR, "sasami"),
    "流星亚什": (PL_DIR, "liuxingyashi"),
    "妮娜·可可": (PL_DIR, "ninakeke"),
    "莉亚·岩心": (PL_DIR, "liya"),
}
# 挑图页 / 主人手写可能出现的别名 → 角色名
AVATAR_ALIAS: dict[str, str] = {"八重樱立绘": "八重樱"}
for _n in list(AVATAR_DIRS):
    AVATAR_ALIAS[_n + "立绘"] = _n


def load_picks() -> dict:
    """主人挑好的候选：{"段1_003": "c", "飒飒米": "a", ...}
    （`_picks.json` 由挑图页导出，放到 CG_DIR 下即可）。"""
    f = CG_DIR / "_picks.json"
    if not f.is_file():
        return {}
    try:
        raw = json.loads(f.read_text(encoding="utf-8"))
    except Exception as e:  # noqa: BLE001
        print(f"  !! _picks.json 读不动：{type(e).__name__}: {e}")
        return {}
    out = {}
    for k, v in (raw or {}).items():
        if isinstance(v, dict):
            v = v.get("pick") or v.get("tag") or ""
        v = str(v).strip().lstrip("_")
        k = AVATAR_ALIAS.get(str(k), str(k))       # 「飒飒米立绘」→「飒飒米」
        if v in ("a", "b", "c"):
            out[k] = v
    return out


def sync_avatar_pick() -> list[str]:
    """按 _picks.json 把选定的立绘候选落到 数据\\头像\\圣剑英雄谭_<角色名>.jpg。

    返回已落地的角色名列表（供 register_avatar 写回 characters.json）。
    """
    picks = load_picks()
    from PIL import Image

    ws = Path(os.environ.get("TRPG_WS", "workspace"))
    dst_dir = ws / "数据" / "头像"
    dst_dir.mkdir(parents=True, exist_ok=True)
    done: list[str] = []
    for name, (src_dir, prefix) in AVATAR_DIRS.items():
        tag = picks.get(name)
        if not tag:
            continue
        src = src_dir / f"{prefix}_{tag}.png"
        if not src.is_file():
            print(f"  !! {name} 立绘候选缺失：{src.name}")
            continue
        dst = dst_dir / f"圣剑英雄谭_{name}.jpg"
        im = Image.open(src).convert("RGB")
        w, h = im.size
        scale = 1000 / max(w, h)
        if scale < 1:
            im = im.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        im.save(dst, "JPEG", quality=90, optimize=True)
        print(f"  立绘 {name} 候选_{tag} -> {dst.name} ({dst.stat().st_size//1024} KB)")
        done.append(name)
    return done


def register_avatar(ws: Workspace, names: list[str]) -> int:
    """把 characters.json 里这些角色的 avatar 指向刚落地的图（已指向则跳过）。"""
    if not names:
        return 0
    f = ws.data_file("characters")
    doc = json.loads(f.read_text(encoding="utf-8"))
    n = 0
    for c in doc.get("characters", []):
        cname = c.get("name") or ""
        hit = next((x for x in names if x == cname or (x in cname)), None)
        if not hit:
            continue
        rel = f"数据\\头像\\圣剑英雄谭_{hit}.jpg"
        if c.get("avatar") != rel and (ws.root / rel).is_file():
            c["avatar"] = rel
            n += 1
    if n:
        import shutil as _sh
        import time as _t
        bak = f.with_name(f"{f.name}.bak_avatar_{_t.strftime('%Y%m%d_%H%M%S')}")
        _sh.copyfile(f, bak)
        f.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  characters.json: {n} 个角色补/换 avatar（备份 {bak.name}）")
    return n


def _cg_batches() -> list[tuple[str, Path]]:
    """CG 候选批次，**靠后的优先级更高**。

    2026-10-04 主人定稿：**只用 PC 版**（`22-trpg-sjt-cg-pc`，按 PC 外貌重画）。
    旧批 `17-trpg-sjt-cg`（泛化角色）已停用，不再进站点、也不再进挑图页；
    目录与文件保留在磁盘上（没删），真要回退把下面这行改回
    `[("old", CG_DIR), ("pc", PC_CG_DIR)]` 即可。
    """
    return [("pc", PC_CG_DIR)]


def sync_cg() -> int:
    """NAI 候选图 → 站点 assets/cg/<key>.jpg。

    选择优先级：_picks.json 指定的候选（高优先级批次 > 低）> 最高批次里的 <key>_a.png。
    `_picks.json` 支持两种写法：
        "段1_003": "c"           → 两个批次里找 _c，PC 批优先
        "段1_003": "pc:c"        → 强制用 PC 批的 _c
    """
    dst = SITE / "assets" / "cg"
    batches = [(n, d) for n, d in _cg_batches() if d.is_dir()]
    if not batches:
        return 0
    from PIL import Image

    picks = load_picks()
    dst.mkdir(parents=True, exist_ok=True)

    # 收集：key -> {batch: {tag: path}}
    avail: dict[str, dict[str, dict[str, Path]]] = {}
    for bname, bdir in batches:
        for p in bdir.glob("*_[abc].png"):
            if len(p.stem) < 2 or p.stem[-2] != "_":
                continue
            key, tag = p.stem[:-2], p.stem[-1]
            avail.setdefault(key, {}).setdefault(bname, {})[tag] = p

    order = [b for b, _ in batches]          # 低 → 高
    n = 0
    picked = []
    for key in sorted(avail):
        spec = str(picks.get(key, "") or "")
        want_batch = None
        if ":" in spec:                       # "pc:c"
            want_batch, spec = spec.split(":", 1)
        tag = spec.strip().lstrip("_") or "a"
        src = None
        if want_batch:                        # 指定批次
            src = avail[key].get(want_batch, {}).get(tag)
        else:                                 # 未指定 → 从高到低找
            for b in reversed(order):
                if tag in avail[key].get(b, {}):
                    src = avail[key][b][tag]
                    break
        if src is None:                       # 该 tag 没有 → 回退 _a（仍是高批次优先）
            for b in reversed(order):
                if "a" in avail[key].get(b, {}):
                    src = avail[key][b]["a"]
                    tag = "a"
                    break
        if src is None:
            continue
        out = dst / f"{key}.jpg"
        try:
            Image.open(src).convert("RGB").save(out, "JPEG", quality=88, optimize=True)
            n += 1
            if key in picks:
                picked.append(f"{key}→{src.parent.name[:2]}:{tag}")
        except Exception as e:  # noqa: BLE001
            print(f"  !! CG {src.name}: {type(e).__name__}: {e}")
    # 清理换了批次/换图后的残留（只会是同名覆盖，这里只报数）
    print(f"  CG {n} 张 -> assets/cg/  （批次：{'、'.join(b for b, _ in batches)}）"
          + (f"｜已按挑选：{', '.join(picked[:5])}" + ("…" if len(picked) > 5 else "") if picked else ""))
    return n


def to_mp3(src: Path, dst: Path, bitrate: int = 128000, max_sec: int = 300) -> bool:
    """任意常见音频 → mp3（PyAV，不依赖系统 ffmpeg）；超长自动截断到 max_sec。"""
    import av

    try:
        inp = av.open(str(src))
        out = av.open(str(dst), mode="w", format="mp3")
        stream = out.add_stream("mp3", rate=44100, layout="stereo")
        stream.bit_rate = bitrate
        tb = 1 / 44100
        n = 0
        for frame in inp.decode(audio=0):
            if frame.time is not None and frame.time > max_sec:
                break
            for pkt in stream.encode(frame):
                out.mux(pkt)
            n += 1
        for pkt in stream.encode():
            out.mux(pkt)
        out.close()
        inp.close()
        return n > 0
    except Exception as e:  # noqa: BLE001
        print(f"  !! BGM 转码失败 {src.name}: {type(e).__name__}: {e}")
        return False


def sync_bgm() -> dict:
    """扫描 素材/bgm/ → 转码 & 归位到 site/assets/bgm/，返回前端用的 tracks 表。"""
    dst = SITE / "assets" / "bgm"
    tracks: dict[str, str] = {}
    if not BGM_SRC.is_dir():
        return {"tracks": tracks, "count": 0}

    exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg", ".aac", ".opus"}
    files = [p for p in sorted(BGM_SRC.iterdir())
             if p.is_file() and p.suffix.lower() in exts]
    if not files:
        if dst.is_dir():
            for p in dst.glob("*.mp3"):
                tracks.setdefault(_mood_of(p.name), "assets/bgm/" + p.name)
        return {"tracks": tracks, "count": 0}

    dst.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in files:
        mood = _mood_of(p.name)
        out = dst / (mood + ".mp3")
        if p.suffix.lower() == ".mp3" and p.stat().st_size < 12 * 1024 * 1024:
            shutil.copyfile(p, out)          # 已经够小的 mp3 直接搬，省一遍转码
        elif not to_mp3(p, out):
            continue
        tracks[mood] = "assets/bgm/" + out.name
        n += 1
        print(f"  BGM {p.name}  ->  {mood}.mp3")
    if "default" not in tracks:
        for k in ("calm", "title", "epic", "dark", "sad", "final"):
            if k in tracks:
                tracks["default"] = tracks[k]
                break
    print(f"  BGM {n} 首 -> assets/bgm/  曲目表 {sorted(tracks)}")
    return {"tracks": tracks, "count": n}


def _mood_of(name: str) -> str:
    """从文件名判情绪。容忍前导序号/下划线/横线，如「01-史诗」、「_epic_xxx」、
    「主题曲 title」；认不出就归 calm。"""
    low = name.lower()
    if "." in low:
        low = low.rsplit(".", 1)[0]
    # 去掉前导的序号与分隔符：01- / 3_ / _ / - / 空格
    low = re.sub(r"^[\s\d._\-–—]+", "", low)
    for k, v in MOOD_PREFIX.items():
        if low.startswith(k):
            return v
    # 前缀不在开头（「主题曲 title」这类）时，退化为"包含即命中"
    for k, v in MOOD_PREFIX.items():
        if k in low:
            return v
    return "calm"


def build_pickpage() -> bool:
    """生成 site/asset-pick.html：三选一挑图页（CG 场景 + 八重樱立绘）。

    候选图同时压成 site/cg-cand/，这样挑图页在 http 与 file:// 下都能看图。
    """
    from PIL import Image

    groups = []

    # ① PC 版场景 CG（按 PC 外貌设定重画：画面里真的是那五个人）——放在最前面，主人一眼看到
    if PC_CG_DIR.is_dir():
        keys = sorted({p.stem[:-2] for p in PC_CG_DIR.glob("*_[abc].png")})
        items = []
        for k in keys:
            for t in ("a", "b", "c"):
                src = PC_CG_DIR / f"{k}_{t}.png"
                if not src.is_file():
                    continue
                out = CAND_DIR / f"cgpc_{k}_{t}.jpg"
                if not out.is_file() or out.stat().st_mtime < src.stat().st_mtime:
                    try:
                        Image.open(src).convert("RGB").resize((760, 520), Image.LANCZOS).save(
                            out, "JPEG", quality=80, optimize=True)
                    except Exception as e:  # noqa: BLE001
                        print(f"  !! PC版候选图 {src.name}: {type(e).__name__}: {e}")
                        continue
                items.append({"key": k, "tag": t, "src": out.name})
        if items:
            groups.append({"id": "cgpc",
                           "title": f"★ PC 版场景 CG（{len(keys)} 个场景 × 3 张）— 按 PC 外貌重画，优先看这组",
                           "items": items})

    # ② 旧批场景 CG（泛化角色）已按主人要求停用，不再进挑图页
    #    如需回退：把 `_cg_batches()` 改回两批，并把下面这段恢复。
    if False and CG_DIR.is_dir():
        keys = sorted({p.stem[:-2] for p in CG_DIR.glob("*_[abc].png")})
        items = []
        for k in keys:
            for t in ("a", "b", "c"):
                src = CG_DIR / f"{k}_{t}.png"
                if not src.is_file():
                    continue
                out = CAND_DIR / f"cg_{k}_{t}.jpg"
                if not out.is_file() or out.stat().st_mtime < src.stat().st_mtime:
                    try:
                        Image.open(src).convert("RGB").resize((760, 520), Image.LANCZOS).save(
                            out, "JPEG", quality=80, optimize=True)
                    except Exception as e:  # noqa: BLE001
                        print(f"  !! 候选图 {src.name}: {type(e).__name__}: {e}")
                        continue
                items.append({"key": k, "tag": t, "src": out.name})
        if items:
            groups.append({"id": "cg", "title": "旧批场景 CG（泛化角色，可作对照）", "items": items})

    # ③ 立绘（八重樱 + 重做的 4 名 PL）：每个角色一行三张
    av_items = []
    for name, (src_dir, prefix) in AVATAR_DIRS.items():
        if not src_dir.is_dir():
            continue
        for t in ("a", "b", "c"):
            src = src_dir / f"{prefix}_{t}.png"
            if not src.is_file():
                continue
            out = CAND_DIR / f"av_{prefix}_{t}.jpg"
            if not out.is_file() or out.stat().st_mtime < src.stat().st_mtime:
                try:
                    Image.open(src).convert("RGB").resize((480, 700), Image.LANCZOS).save(
                        out, "JPEG", quality=82, optimize=True)
                except Exception as e:  # noqa: BLE001
                    print(f"  !! 立绘 {src.name}: {type(e).__name__}: {e}")
                    continue
            av_items.append({"key": name, "tag": t, "src": out.name, "portrait": True})
    if av_items:
        names = sorted({i["key"] for i in av_items})
        groups.append({"id": "avatar",
                       "title": f"立绘三选一（{len(names)} 名圣剑使 × 3 张）", "items": av_items})

    if not groups:
        return False
    CAND_DIR.mkdir(parents=True, exist_ok=True)
    html = (PICKPAGE_TMPL
            .replace("__DATA__", json.dumps({"groups": groups}, ensure_ascii=False))
            .replace("__PICKED__", json.dumps(load_picks(), ensure_ascii=False)))
    # 挑图页与缩略图放在 site/ 之外：它们是工作流工具，不该随站点发布到公网
    out = PICK_SITE / "asset-pick.html"
    out.write_text(html, encoding="utf-8")
    total = sum(len(g["items"]) for g in groups)
    print(f"  asset-pick.html  ({len(groups)} 组 · {total} 张候选)  -> {out}")
    print(f"     打开方式: 起服务时把 {PICK_SITE} 也挂上，或直接双击该文件（图用相对路径）")
    return True


PICKPAGE_TMPL = r"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>素材三选一 · 圣剑英雄谭</title>
<style>
:root{--ink:#07080b;--ink2:#12151c;--rule:#232833;--gold:#c9a961;--paper:#e8e9ec;--dim:#878c98}
*{box-sizing:border-box}
body{margin:0;background:var(--ink);color:var(--paper);
 font:14.5px/1.8 "Noto Sans SC","PingFang SC","Microsoft YaHei",system-ui,sans-serif}
header{position:sticky;top:0;z-index:20;display:flex;align-items:center;gap:18px;padding:14px 24px;
 background:rgba(7,8,11,.96);border-bottom:1px solid var(--rule);backdrop-filter:blur(10px)}
header h1{margin:0;font-size:16px;letter-spacing:.1em}
header .sp{margin-left:auto;font-size:12.5px;color:var(--dim)}
header button{padding:9px 16px;background:transparent;border:1px solid var(--gold);color:var(--gold);
 cursor:pointer;font-size:13px;letter-spacing:.1em}
header button:hover{background:var(--gold);color:var(--ink)}
main{max-width:1500px;margin:0 auto;padding:26px 24px 120px}
.group{margin:38px 0 0;border-top:1px solid var(--rule);padding-top:18px}
.group>h2{margin:0 0 14px;font-size:15px;letter-spacing:.14em;color:var(--gold);
 font-weight:500;display:flex;align-items:center;gap:12px}
.group>h2 s{display:block;flex:1;height:1px;background:var(--rule);text-decoration:none}
.scene{margin:0 0 30px;padding-top:12px;border-top:1px dashed rgba(35,40,51,.8)}
.scene h3{margin:0 0 4px;font-size:14px;letter-spacing:.06em;color:var(--paper);font-weight:500}
.scene .hint{font-size:11.5px;color:var(--dim);margin-bottom:10px}
.row{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
figure{margin:0;border:1px solid var(--rule);cursor:pointer;position:relative;overflow:hidden;background:#0c0e13}
figure img{width:100%;display:block;aspect-ratio:1216/832;object-fit:cover;object-position:top center}
figure.portrait img{aspect-ratio:480/700}
figure figcaption{padding:8px 10px;font:11px/1 monospace;letter-spacing:.16em;color:var(--dim);
 display:flex;gap:10px;align-items:center}
figure .dot{width:9px;height:9px;border:1px solid var(--rule);display:inline-block;flex:0 0 auto}
figure:hover{border-color:#49515f}
figure.on{border-color:var(--gold);box-shadow:0 0 0 1px var(--gold)}
figure.on .dot{background:var(--gold);border-color:var(--gold)}
figure.on figcaption{color:var(--gold)}
@media(max-width:900px){.row{grid-template-columns:1fr}}
.tip{position:fixed;left:0;right:0;bottom:0;padding:14px 24px;background:rgba(7,8,11,.97);
 border-top:1px solid var(--rule);font-size:12.5px;color:var(--dim);display:flex;gap:16px;flex-wrap:wrap}
.tip b{color:var(--gold);font-weight:500}
</style></head><body>
<header>
  <h1>素材三选一</h1>
  <span class="sp" id="cnt"></span>
  <button id="exp">导出 _picks.json</button>
</header>
<main id="app"></main>
<div class="tip">
  点图选中 → 右上角「导出 _picks.json」→ 放进
  <b><NAI库>\archive\17-trpg-sjt-cg\</b> → 重跑 <b>tools\build_site.py</b> 即同步进站点。
  <span id="stat"></span>
</div>
<script>
var DATA = __DATA__;
var PICKED = __PICKED__;
var app = document.getElementById('app');
var TOTAL = 0;
DATA.groups.forEach(function(g){ TOTAL += g.items.length; });
function esc(s){return String(s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]})}
function groupHtml(g){
  /* 按 key 归拢成"每个场景一行三张" */
  var byKey = {}, order = [];
  g.items.forEach(function(it){
    if (!byKey[it.key]) { byKey[it.key] = []; order.push(it.key); }
    byKey[it.key].push(it);
  });
  var body = order.map(function(k){
    var list = byKey[k];
    var cur = PICKED[k] || '';
    var row = list.map(function(it){
      var on = (cur === it.tag) ? ' on' : '';
      var cls = 'figure' + on + (it.portrait ? ' portrait' : '');
      return '<figure class="'+cls.trim()+'" data-k="'+esc(k)+'" data-t="'+it.tag+'">'
        + '<img loading="lazy" src="cg-cand/'+encodeURIComponent(it.src)+'" alt="">'
        + '<figcaption><span class="dot"></span>'+esc(k)+' _'+it.tag+'</figcaption></figure>';
    }).join('');
    var def = (g.id === 'avatar') ? '未选（暂用 _a）' : '未选（暂用 _a）';
    return '<section class="scene"><h3>'+esc(k)+'</h3>'
      + '<div class="hint">'+list.length+' 张候选 · 当前：'+(cur||def)+'</div>'
      + '<div class="row">'+row+'</div></section>';
  }).join('');
  return '<section class="group"><h2>'+esc(g.title)+'<s></s></h2>'+body+'</section>';
}
function draw(){
  app.innerHTML = DATA.groups.map(groupHtml).join('');
  var n = Object.keys(PICKED).length;
  document.getElementById('cnt').textContent = n + ' / ' + TOTAL + ' 已挑';
  document.getElementById('stat').textContent = n ? '（已挑 ' + n + ' 个）' : '';
}
app.addEventListener('click', function(e){
  var f = e.target.closest('figure'); if(!f) return;
  var k = f.dataset.k, t = f.dataset.t;
  if (PICKED[k] === t) delete PICKED[k]; else PICKED[k] = t;
  draw();
});
document.getElementById('exp').addEventListener('click', function(){
  var blob = new Blob([JSON.stringify(PICKED, null, 1)], {type:'application/json'});
  var a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = '_picks.json';
  document.body.appendChild(a); a.click(); a.remove();
});
draw();
</script></body></html>
"""


def scan_assets() -> dict:
    """已生成的 CG / 原声 / BGM 清单（前端据此决定哪一页显示图与播放器）。"""
    cg_dir, au_dir = SITE / "assets" / "cg", SITE / "assets" / "audio"
    cg = sorted(p.stem for p in cg_dir.glob("*.jpg")) if cg_dir.is_dir() else []
    au = sorted(p.stem for p in au_dir.glob("*.mp3")) if au_dir.is_dir() else []
    return {"cg": cg, "audio": au}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    _cfg, ws = load_env()
    (SITE / "data").mkdir(parents=True, exist_ok=True)

    # 立绘挑选要落在 build_roster / copy_images 之前，否则本次构建读不到新图
    picked = sync_avatar_pick()
    register_avatar(ws, picked)

    story = build_story(ws)
    roster = build_roster(ws)
    rels = json.loads(ws.data_file("relations").read_text(encoding="utf-8"))["relations"]
    ids = {c["id"] for c in roster["characters"]}
    mine_rels = [r for r in rels if r.get("from") in ids or r.get("to") in ids]

    meta = {
        "group": GROUP,
        "title": "圣剑英雄谭",
        "subtitle": "六位圣剑使 · 十一把圣剑 · 一个需要被修正的世界",
        "intro": INTRO,
        "stats": {
            "audio_hours": 6.28,
            "transcript_segments": 13662,
            "chronicle_words": 30724,
            "sections": sum(len(s["sections"]) for s in story["segments"]),
            "characters": roster["count"],
            "pc": roster["pc_count"],
            "relations": len(mine_rels),
            "avatars": 0,
            "cg": 0,
        },
        "known_gaps": [
            "血系作战归妮娜·可可（往）；莉亚·岩心只有土系",
            "四骑士均无本名，以代号称呼",
            "「结刻」＝杰克（终局）",
            "「乌龙茶」是桌边梗（宽现实中是调酒师）",
        ],
    }

    for name, doc in (("story", story), ("roster", roster),
                      ("relations", {"relations": mine_rels})):
        (SITE / "data" / f"{name}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"  data/{name}.json  ({len(json.dumps(doc, ensure_ascii=False))} 字符)")

    img = copy_images(ws, roster)
    meta["stats"]["avatars"] = img["count"]
    (SITE / "data" / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")

    # 内联数据包: 双击 file:// 打开时 fetch 会被 CORS 拦, 所以数据直接写进 JS
    pages = build_pages(story)
    sync_cg()
    sync_kv()
    bgm = sync_bgm()
    build_pickpage()
    meta["stats"]["pages"] = len(pages)
    meta["assets"] = scan_assets()
    meta["assets"]["bgm"] = bgm
    meta["stats"]["cg"] = len(meta["assets"]["cg"])
    meta["stats"]["clips"] = len(meta["assets"]["audio"])
    meta["stats"]["bgm"] = bgm.get("count", 0)
    (SITE / "data" / "meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")
    (SITE / "data" / "pages.json").write_text(
        json.dumps({"pages": pages}, ensure_ascii=False, indent=1), encoding="utf-8")
    bundle = {"meta": meta, "story": story, "pages": pages, "roster": roster,
              "relations": {"relations": mine_rels}}
    (SITE / "data" / "bundle.js").write_text(
        "window.SITE_DATA = " + json.dumps(bundle, ensure_ascii=False) + ";\n", encoding="utf-8")
    print(f"  data/pages.json  绘本 {len(pages)} 页")
    print(f"  data/bundle.js  ({(SITE / 'data' / 'bundle.js').stat().st_size/1024:.0f} KB)")

    ok = copy_relations(ws)
    print(f"  relations.html: {'已生成' if ok else '缺失（先跑 visualize --group）'}")
    print(f"\nOK 站点数据 -> {SITE}")
    print(f"   三幕 / {len(story['segments'])} 段 / {meta['stats']['sections']} 小节 / "
          f"{roster['count']} 角色（PC {roster['pc_count']}）/ {len(mine_rels)} 关系边")
    return 0


if __name__ == "__main__":
    sys.exit(main())
