# -*- coding: utf-8 -*-
"""分格漫画页生成（参考日式 リプレイ本版式）。

设计要点（抄日式 replay，不抄美漫）：
    · **演出层**：格子 + 对话框/旁白框 —— 读起来像轻小说/漫画；
    · **桌边层**：每节末尾一个「桌边原声」框，贴**原始录音转写**（带错字与插科打诨）
      + 播放器。这正是 replay 的味道：既看演出，也看桌面上真实发生了什么；
    · 对话框**不画在图里**（AI 画中文必崩），用 HTML/CSS 叠加 → 可改、可搜、可选中；
    · 纸张质感、双线格框、竖排书脊字、页码 —— 做出「印刷物」的暗示。

产出：site/comic.html（读取 archive/23-trpg-comic 的底图，转成站点 jpg）

用法:
    .venv\\Scripts\\python.exe tools\\build_comic.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SITE = ROOT / "site"
COMIC_SRC = Path(os.environ.get("TRPG_NAI", "novelai") / 'archive' / '23-trpg-comic')
COMIC_DST = SITE / "assets" / "comic"

# ---------------------------------------------------------------- 分镜数据
# 台词与旁白**严格取自** 产出\圣剑英雄谭_剧情编年史.md 该节正文（未编造）
EPISODES = [
    {
        "id": "段1_008",
        "seg": "段1", "no": "第八节", "time": "45:30",
        "title": "雷剑归属与威尔娜入门",
        "lead": "篝火边上，宽把雷剑递了出去——交给一个还不会「呼吸」的小跟班。",
        "panels": [
            {"img": "段1_008_p1", "h": "wide",
             "nar": "少女将雷剑交出。众人辨别剑型：雷剑是长剑，有人使大剑。",
             "who": "宽（八重樱）", "line": "最终决定由某人带着雷剑，并让少女跟随学习。",
             "note": "少女被称作「威尔娜」或「威尔特」「威尔拉」，笨拙地跟着剑盒。"},
            {"img": "段1_008_p2", "h": "wide",
             "nar": "有人让她去找宽训练。宽说：「先学会我的这个大地址的剑术吧。」"
                    "实际上宽只教她「调整呼吸」。",
             "who": "宽（八重樱）", "line": "「第一课先学会呼吸吧。」",
             "note": "威尔娜疑惑呼吸也要学，宽便展示给她看，结果被吐槽「把他吸二手一眼」。"},
            {"img": "段1_008_p3", "h": "wide",
             "nar": "众人决定把雷剑交给她试试，说「你就是雷剑的使用者」。"
                    "雷剑与她的烟产生共鸣，烟围绕剑身，最终共鸣成功。",
             "who": "威尔娜", "line": "「雷剑行啦，三千雷洞，大男一生，皮地在旁边，胭脂呼吸。」",
             "note": "飒飒米在旁边演奏起来，BGM 响起；剑光电闪，闪电连锁电了一大片。"},
        ],
        "table_talk": [
            ("09:45", "少女将雷剑交出"),
            ("45:30", "宽：第一课先学会呼吸吧"),
            ("48:12", "威尔娜：可我只是一个小跟班啊"),
            ("48:40", "宽：对，快去吧 —— 只有在实战中才能获得成长"),
        ],
        "audio": "段1_008",
        "next": "古人攻城与雷剑共鸣",
    },
]

PAGE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<meta name="theme-color" content="#0a0906">
<title>{title} · 圣剑英雄谭 分格漫画</title>
<link rel="stylesheet" href="style.css">
<style>
/* ===== 分格漫画页（日式 replay 版式） ===== */
body.comic{{background:#0a0906}}
.comic-wrap{{max-width:1020px;margin:0 auto;padding:96px 24px 90px}}
/* 书脊：左侧竖排英文 */
.spine{{position:fixed;left:18px;top:50%;transform:translateY(-50%);writing-mode:vertical-rl;
 font:10px/1 var(--mono);letter-spacing:.5em;color:rgba(201,169,97,.4);user-select:none}}
@media(max-width:1180px){{.spine{{display:none}}}}

/* 「书页」：纸色底 + 深墨字 —— 底图是白纸底的漫画，贴在深色页上会飘，所以正文区改成纸张 */
.sheet{{background:#efe9dc;color:#221e18;border:1px solid #3a332a;
 box-shadow:0 30px 90px rgba(0,0,0,.7);padding:44px 46px 40px;position:relative}}
.sheet::after{{content:"";position:absolute;inset:0;pointer-events:none;opacity:.42;
 background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='p'><feTurbulence type='fractalNoise' baseFrequency='.9' numOctaves='2'/></filter><rect width='140' height='140' filter='url(%23p)' opacity='.4'/></svg>")}}
@media(max-width:700px){{.sheet{{padding:24px 18px 22px}}}}

.ep-head{{border-bottom:2px solid #221e18;padding-bottom:16px;margin-bottom:6px}}
.ep-head .kick{{display:flex;align-items:center;gap:12px;margin-bottom:13px}}
.ep-head .kick s{{display:block;width:38px;height:1px;background:#8a7440}}
.ep-head .kick span{{font:10px/1 var(--mono);letter-spacing:.34em;color:#8a7440}}
.ep-head h1{{margin:0;font-size:clamp(24px,3.2vw,37px);font-weight:700;letter-spacing:.02em;line-height:1.25;color:#161310}}
.ep-head .meta{{margin-top:9px;font:10.5px/1 var(--mono);letter-spacing:.2em;color:#6d6455}}
.ep-lead{{margin:18px 0 30px;padding-left:13px;border-left:2px solid #8a7440;
 color:#4a4237;font-size:14.5px;line-height:1.95}}

/* 格子：漫画底图本来就是白纸底，只加一圈墨框 + 轻微投影，别再加内白框 */
.panel{{position:relative;margin:0 0 26px;background:#fff;border:2px solid #191512;
 box-shadow:0 10px 26px rgba(0,0,0,.28)}}
.panel img{{width:100%;display:block}}
.panel .pno{{position:absolute;right:8px;top:8px;z-index:3;font:10px/1 var(--mono);
 letter-spacing:.14em;color:#f4f1e8;background:rgba(20,18,14,.66);border:1px solid rgba(244,241,232,.3);
 padding:4px 7px}}

/* 旁白框：贴格子上沿的横条（避开人物脸，尽量压在上方留白处） */
.panel .nar{{position:absolute;left:12px;top:12px;z-index:3;max-width:58%;
 background:rgba(18,16,13,.86);color:#f2eee2;border-left:3px solid #c9a961;
 padding:9px 13px;font-size:13px;line-height:1.8;letter-spacing:.02em}}
/* 对话框：白底圆角 + 尾巴 */
.say{{position:absolute;z-index:3;max-width:44%;background:#fbfaf6;color:#141110;
 border:2px solid #141110;border-radius:13px;padding:11px 14px;font-size:14px;line-height:1.7;
 box-shadow:0 5px 0 rgba(20,17,16,.15)}}
.say .who{{display:block;font-size:10.5px;letter-spacing:.16em;color:#8a7440;margin-bottom:4px}}
.say::after{{content:"";position:absolute;bottom:-11px;width:0;height:0;
 border:10px solid transparent;border-top-color:#fbfaf6;border-bottom:0}}
.say::before{{content:"";position:absolute;bottom:-14px;width:0;height:0;
 border:12px solid transparent;border-top-color:#141110;border-bottom:0}}
.say.br{{right:14px;bottom:14px}}
.say.br::after{{right:24px}} .say.br::before{{right:22px}}
.say.bl{{left:14px;bottom:14px}}
.say.bl::after{{left:24px}} .say.bl::before{{left:22px}}
@media(max-width:700px){{
 .panel .nar{{left:7px;top:7px;max-width:86%;font-size:12px;padding:8px 10px}}
 .say{{max-width:68%;font-size:12.5px;padding:9px 11px}}
}}
/* 格注：格子下方的编者小字 */
.gnote{{margin:-18px 0 28px;padding:10px 14px 0;font-size:12px;color:#5f574a;
 border-left:1px solid #c9bfa8;line-height:1.9}}
.gnote b{{color:#8a7440;font-weight:400;font:10px/1 var(--mono);letter-spacing:.2em;margin-right:8px}}

/* 桌边原声框：本页的「replay 味」所在（在纸面上做成"框起来的批注"） */
.table-talk{{margin:40px 0 0;border:1px solid #c9bfa8;background:rgba(255,255,255,.5)}}
.table-talk .hd{{display:flex;align-items:center;gap:12px;padding:13px 17px;border-bottom:1px solid #c9bfa8}}
.table-talk .hd h3{{margin:0;font-size:13.5px;font-weight:600;letter-spacing:.1em;color:#161310}}
.table-talk .hd .en{{font:9px/1 var(--mono);letter-spacing:.28em;color:#8a7440}}
.table-talk .hd .sp{{margin-left:auto;font-size:11.5px;color:#6d6455}}
.table-talk .body{{padding:15px 17px}}
.table-talk .row{{display:grid;grid-template-columns:74px 1fr;gap:9px 14px;font-size:13px;line-height:1.85}}
.table-talk .t{{font:11px/1.9 var(--mono);color:#8a7440;letter-spacing:.08em}}
.table-talk .q{{color:#3d372e}}
.table-talk .src{{padding:0 17px 15px;font-size:11.5px;color:#6d6455;line-height:1.9}}
.table-talk audio{{width:100%;height:34px;margin-top:11px}}
.ep-foot{{margin-top:30px;display:flex;gap:14px;align-items:center;flex-wrap:wrap;
 border-top:1px solid #c9bfa8;padding-top:16px;font-size:12.5px;color:#6d6455}}
.ep-foot .nx{{margin-left:auto;color:#8a7440}}
</style>
</head>
<body class="comic">
<div class="spine">REPLAY · SWORD HEROES</div>
<div class="comic-wrap">
<div class="sheet">
{body}
</div>
</div>
<script src="data/bundle.js"></script>
</body>
</html>
"""


def panel_html(p: dict, idx: int) -> str:
    pos = "br" if idx % 2 == 1 else "bl"
    return f"""
<div class="panel">
  <img src="assets/comic/{p['img']}.jpg" alt="{p['nar'][:20]}">
  <div class="pno">PANEL {idx:02d}</div>
  <div class="nar">{p['nar']}</div>
  <div class="say {pos}"><span class="who">{p['who']}</span>{p['line']}</div>
</div>
<div class="gnote"><b>注</b>{p['note']}</div>"""


def ep_html(ep: dict) -> str:
    panels = "".join(panel_html(p, i + 1) for i, p in enumerate(ep["panels"]))
    talk = "".join(f'<div class="t">{t}</div><div class="q">{q}</div>'
                   for t, q in ep["table_talk"])
    return f"""
<div class="ep-head">
  <div class="kick"><s></s><span>REPLAY · {ep['seg']}</span></div>
  <h1>{ep['title']}</h1>
  <div class="meta">{ep['seg']}　{ep['no']}　·　{ep['time']}　·　{len(ep['panels'])} 格</div>
</div>
<p class="ep-lead">{ep['lead']}</p>
{panels}
<div class="table-talk">
  <div class="hd"><h3>桌边原声</h3><span class="en">AT THE TABLE</span>
    <span class="sp">这一段在桌面上实际说了什么</span></div>
  <div class="body">
    <div class="row">{talk}</div>
    <audio id="pa" controls preload="none" src="assets/audio/{ep['audio']}.mp3"></audio>
  </div>
  <div class="src">以上为 6.28 小时录音的原始转写片段（保留 ASR 的错字与口语），
  与左侧「演出」分层对照 —— 这正是日式 replay 的做法：既给你成品，也给你桌面。</div>
</div>
<div class="ep-foot">
  <span>圣剑英雄谭 · 分格漫画 · 试样</span>
  <span class="nx">下一节：{ep['next']} →</span>
</div>"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    from PIL import Image

    if not COMIC_SRC.is_dir():
        print(f"!! 找不到分镜底图目录：{COMIC_SRC}")
        return 1
    COMIC_DST.mkdir(parents=True, exist_ok=True)
    n = 0
    for ep in EPISODES:
        for p in ep["panels"]:
            src = COMIC_SRC / f"{p['img']}.png"
            if not src.is_file():
                print(f"  !! 缺底图 {src.name}")
                continue
            out = COMIC_DST / f"{p['img']}.jpg"
            if not out.is_file() or out.stat().st_mtime < src.stat().st_mtime:
                Image.open(src).convert("RGB").save(out, "JPEG", quality=90, optimize=True)
            n += 1
    body = "".join(ep_html(ep) for ep in EPISODES)
    html = PAGE.format(title=EPISODES[0]["title"], body=body)
    (SITE / "comic.html").write_text(html, encoding="utf-8")
    print(f"  comic.html  ({len(EPISODES)} 节 · {n} 格底图)")
    print(f"  打开：http://127.0.0.1:8899/site/comic.html")
    return 0


if __name__ == "__main__":
    sys.exit(main())
