# -*- coding: utf-8 -*-
"""疑问片段核对工作流：把"转写存疑"的录音片段剪出来，生成可逐条播放+填答的 HTML 页。

为什么需要它（2026-10-03 主人提出）：
  核对环节只贴转写原文没用 —— 转写本身就是 ASR 错字（「地牙?」「劳昌?」「士兮」），
  光看文字谁也认不出来；把对应**音频片段**剪出来一听就明白。
  这条工作流对任何团/任何存疑清单都通用。

用法:
    .venv\\Scripts\\python.exe tools\\_clip_quiz.py --group 圣剑英雄谭
    .venv\\Scripts\\python.exe tools\\_clip_quiz.py --group 圣剑英雄谭 --quiz my_quiz.json
    # 外部 JSON: [{"id":"Q01","topic":"...","kws":["威尔娜","维尼拉"],"hint":"..."}]

产物:
    <产出>/quiz/<团>/Q01_威尔娜.mp3 ...      （音频片段）
    <产出>/<团>_疑问核对.html                （带播放器 + 答题框 + 导出按钮）
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

TS_RE = re.compile(r"^\[\s*([\d.]+)\s*->\s*([\d.]+)\s*\]\s?(.*)$")
PAD_BEFORE = 6.0
PAD_AFTER = 4.0

# 圣剑英雄谭：需要"听"的存疑条目（来自 .trpg/reports/圣剑英雄谭_待确认.md）
QUIZ_SJT = [
    {"id": "Q01", "topic": "威尔娜的名字到底怎么写？",
     "kws": ["威尔娜", "维尼拉", "肥腾威尔拉", "威尔特", "威尔拉"],
     "hint": "转写里并存几种写法，请确认标准写法（是她本人的自称/他人称呼哪一处为准）"},
    {"id": "Q02", "topic": "「黄泳多」是不是「煌炎国」？",
     "kws": ["黄泳多"], "hint": "段1 提及圣女所属国；是国名听错吗？"},
    {"id": "Q03", "topic": "「死鬼」是不是「尸鬼」？",
     "kws": ["死鬼"], "hint": "四骑士带来的东西；正式叫法是什么？"},
    {"id": "Q04", "topic": "「吉祖哥」「沙沙」「杀杀」「雪人沙铃」分别指谁？",
     "kws": ["吉祖哥", "雪人沙铃", "沙沙", "杀杀"], "hint": "段2 多人名混用，请分别指认"},
    {"id": "Q05", "topic": "灾星「诺亚/压实」是流星亚什本人吗？",
     "kws": ["诺亚", "压实"], "hint": "难民口述的灾星，特征与流星亚什吻合；请确认名字与是否同一人"},
    {"id": "Q07", "topic": "「艳术/焰术/炎术」哪个对？",
     "kws": ["艳术", "焰术", "炎术"], "hint": "矮人国地下的共生种族名；另：当年毁灭该族的 PC 是谁"},
    {"id": "Q08", "topic": "矮人大师的名字怎么写？",
     "kws": ["80铁饭", "铁饭", "马斯特"], "hint": "持火焰圣剑的矮人大师"},
    {"id": "Q09", "topic": "三重猎虫的三个名字",
     "kws": ["亚尼姆斯", "格洛斯达", "福提士"], "hint": "超越之光/黑夜之志/尖盾——名字与归属"},
    {"id": "Q10", "topic": "「无龙茶」与传奇调酒师「宽」",
     "kws": ["无龙茶"], "hint": "是世界内传说/NPC 名，还是桌边玩梗？与跨团「宽」有关吗"},
    {"id": "Q11", "topic": "「企鹅人」是种族名还是玩梗？",
     "kws": ["企鹅"], "hint": "雪山土著"},
    {"id": "Q12", "topic": "「哈基米」是冰晶圣兽的正式名吗？",
     "kws": ["哈基米"], "hint": "雪山圣兽"},
    {"id": "Q13", "topic": "「蓝丰炸药」是雪山巨像的名字吗？",
     "kws": ["蓝丰"], "hint": "冰封巨像/可驾驶机甲"},
    {"id": "Q14", "topic": "瘟疫骑士的红石「写者之实/血者之实」？",
     "kws": ["写者之实", "血者之实", "写者"], "hint": "炼金术师用的红色石头，名称与作用"},
    {"id": "Q15", "topic": "瘟疫骑士的正式名是「腐败的人」吗？",
     "kws": ["腐败的人", "腐败"], "hint": "另：村庄死亡人数「几千人」的准确数字"},
    {"id": "Q16", "topic": "段6 的「士兮」「高文」「敌者」「贤将」",
     "kws": ["士兮", "高文", "敌者", "贤将"], "hint": "这些是专有名词吗？正确写法？"},
    {"id": "Q17", "topic": "女巫「色蛮/瑟蛮」、同伴「西修/希秀」",
     "kws": ["色蛮", "瑟蛮", "西修", "希秀"], "hint": "段3 过去/未来试炼里的两个名字"},
    {"id": "Q18", "topic": "「背火箭的矮人」「六把圣剑」伏笔",
     "kws": ["背火箭", "六个圣剑", "六把圣剑"], "hint": "段4 回收的早期伏笔，含义是什么"},
    {"id": "Q19", "topic": "（已确认，留作复核）「地牙?」「劳昌?」",
     "kws": ["地牙", "劳昌"], "hint": "上一轮已确认都指莉亚·岩心；听一下是否还有别的意思"},
    {"id": "Q20", "topic": "（已裁决，留作复核）「天津诗情诗」",
     "kws": ["天津诗情诗"], "hint": "已定为玩梗写法；对应的「均衡/世界意志」设定成立"},
]


def parse_ts(lines: list[str]) -> list[tuple[float, float, str]]:
    out = []
    for ln in lines:
        m = TS_RE.match(ln.strip())
        if m:
            out.append((float(m.group(1)), float(m.group(2)), m.group(3)))
    return out


def find_kw(rows: list[tuple[float, float, str]], kw: str) -> list[tuple[float, float, str]]:
    return [r for r in rows if kw in r[2]]


def clip(src: Path, start: float, end: float, dst: Path) -> bool:
    import av

    s = max(0.0, start - PAD_BEFORE)
    e = end + PAD_AFTER
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        with av.open(str(src)) as inp:
            st = inp.streams.audio[0]
            inp.seek(int(s * 1_000_000), backward=True)
            out = av.open(str(dst), mode="w", format="mp3")
            ost = out.add_stream("mp3", rate=st.rate, layout=st.layout.name)
            for frame in inp.decode(st):
                t = frame.time
                if t is None:
                    continue
                if t > e:
                    break
                if t + frame.samples / st.rate < s:
                    continue
                for pkt in ost.encode(frame):
                    out.mux(pkt)
            for pkt in ost.encode(None):
                out.mux(pkt)
            out.close()
        return dst.is_file() and dst.stat().st_size > 1000
    except Exception as e:  # noqa: BLE001
        print(f"    !! 剪片失败 {dst.name}: {type(e).__name__}: {e}")
        return False


def mmss(sec: float) -> str:
    return f"{int(sec) // 60}:{int(sec) % 60:02d}"


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser(description="疑问片段核对工作流")
    ap.add_argument("--group", default="圣剑英雄谭")
    ap.add_argument("--audio", help="音频路径（默认取该团素材里的 audio）")
    ap.add_argument("--transcript", help="转写稿路径")
    ap.add_argument("--quiz", help="外部疑问清单 JSON")
    ap.add_argument("--tag", default="", help="输出后缀与片段子目录（如 第2轮），便于多轮并存")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    ws = Workspace.from_config(cfg)
    group = args.group

    quiz = QUIZ_SJT
    if args.quiz:
        quiz = json.loads(Path(args.quiz).read_text(encoding="utf-8"))

    audio = Path(args.audio) if args.audio else None
    if audio is None:
        cand = list(ws.material.glob(f"{group}*.mp3")) + list(ws.material.glob(f"{group}*.m4a"))
        if not cand:
            print(f"找不到 {group} 的音频")
            return 1
        audio = cand[0]
    transcript = Path(args.transcript) if args.transcript else None
    if transcript is None:
        cand = list(ws.material.glob(f"{group}*转写*.txt"))
        if not cand:
            print(f"找不到 {group} 的转写稿")
            return 1
        transcript = cand[0]

    print(f"音频: {audio.name}  转写: {transcript.name}")
    rows = parse_ts(transcript.read_text(encoding="utf-8", errors="replace").splitlines())
    print(f"转写行(带时间戳): {len(rows)}")

    tag = args.tag.strip()
    sub = f"{group}_{tag}" if tag else group
    out_dir = ws.output / "quiz" / sub
    items = []
    for q in quiz:
        clips = []
        # 条目可以直接给时间点（关键词在转写里找不到时用）: {"id","topic","at":[start,end],"label"}
        if q.get("at"):
            start, end = float(q["at"][0]), float(q["at"][1])
            label = q.get("label") or "clip"
            name = f"{q['id']}_{label}_{int(start)}s.mp3"
            dst = out_dir / name
            ok = clip(audio, start, end, dst) if not dst.is_file() else True
            clips.append({"kw": label, "miss": False, "ok": ok, "t": start,
                          "text": "(手工指定时间点的片段，转写里没有可匹配的关键词)",
                          "file": f"quiz/{sub}/{name}", "hits": 1})
            print(f"  {q['id']} {label} @{mmss(start)} 手工指定 {'OK' if ok else 'FAIL'}")
            items.append({**q, "clips": clips})
            continue
        for kw in q["kws"]:
            hits = find_kw(rows, kw)
            if not hits:
                clips.append({"kw": kw, "miss": True})
                continue
            start, end, text = hits[0]
            # 文件名要带关键词与时间戳: 同一疑问的多个关键词常常落在不同时间点,
            # 只按 id 命名会互相覆盖(实测踩过)。
            safe = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]", "", kw) or "kw"
            name = f"{q['id']}_{safe}_{int(start)}s.mp3"
            dst = out_dir / name
            ok = clip(audio, start, end, dst) if not dst.is_file() else True
            clips.append({"kw": kw, "miss": False, "ok": ok, "t": start, "text": text,
                          "file": f"quiz/{sub}/{name}", "hits": len(hits)})
            print(f"  {q['id']} {kw:<8} @{mmss(start)} hits={len(hits)} {'OK' if ok else 'FAIL'}")
        items.append({**q, "clips": clips})

    html = render_html(group + (f" · {tag}" if tag else ""), items, audio.name)
    page = ws.output / f"{group}_疑问核对{('_' + tag) if tag else ''}.html"
    page.write_text(html, encoding="utf-8")
    print(f"\nOK 核对页: {page}")
    print(f"   音频片段目录: {out_dir}")
    miss = sum(1 for it in items for c in it["clips"] if c.get("miss"))
    print(f"   条目 {len(items)} · 片段 {sum(len(it['clips']) for it in items)} · 未命中关键词 {miss}")
    return 0


def render_html(group: str, items: list[dict], audio_name: str) -> str:
    head = f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<title>{group} · 疑问核对</title>
<style>
 body{{font-family:-apple-system,"Segoe UI","Microsoft YaHei",sans-serif;background:#f6f4ef;color:#2b2b2b;
      max-width:900px;margin:0 auto;padding:24px 18px 80px;line-height:1.6}}
 h1{{font-size:22px;margin:0 0 6px}} .sub{{color:#777;font-size:13px;margin-bottom:20px}}
 .q{{background:#fff;border:1px solid #e3ded2;border-radius:10px;padding:14px 16px;margin:0 0 16px;
     box-shadow:0 1px 3px rgba(0,0,0,.04)}}
 .q h2{{font-size:16px;margin:0 0 8px}} .q h2 span{{color:#b0895b;font-weight:600;margin-right:6px}}
 .clip{{margin:8px 0;padding:8px 10px;background:#faf8f3;border-radius:8px}}
 .clip .kw{{font-weight:600;color:#5a6b4f}} .clip .ts{{color:#999;font-size:12px;margin-left:6px}}
 .clip .txt{{font-size:13px;color:#444;margin:4px 0 6px;word-break:break-all}}
 audio{{width:100%;max-width:420px;height:34px}}
 .miss{{color:#b06a6a;font-size:13px}}
 .hint{{font-size:13px;color:#8a7f6a;margin:8px 0 6px}}
 textarea{{width:100%;min-height:52px;border:1px solid #ddd6c8;border-radius:8px;padding:8px;
          font-family:inherit;font-size:14px;background:#fffdf8}}
 #bar{{position:fixed;bottom:0;left:0;right:0;background:#fffdf8;border-top:1px solid #e3ded2;
       padding:10px 18px;display:flex;gap:12px;align-items:center;box-shadow:0 -2px 8px rgba(0,0,0,.05)}}
 button{{background:#5a6b4f;color:#fff;border:0;border-radius:8px;padding:8px 16px;font-size:14px;cursor:pointer}}
 button.ghost{{background:#e8e3d7;color:#4a4a4a}}
 #out{{display:none;white-space:pre-wrap;background:#fff;border:1px solid #e3ded2;border-radius:8px;
       padding:12px;margin-top:14px;font-size:13px}}
</style></head><body>
<h1>{group} · 疑问核对（听录音逐条确认）</h1>
<div class="sub">源音频：{audio_name} ｜ 每条疑问下面是自动剪出的录音片段（关键词命中处，前后各留几秒）。<br>
听不清可以重复播放；填完点右下「导出答案」把结果复制回来给我。</div>
"""
    body = []
    for it in items:
        body.append('<div class="q">')
        body.append(f'<h2><span>{it["id"]}</span>{it["topic"]}</h2>')
        if it.get("hint"):
            body.append(f'<div class="hint">💡 {it["hint"]}</div>')
        for c in it["clips"]:
            if c.get("miss"):
                body.append(f'<div class="clip"><span class="kw">{c["kw"]}</span> '
                            f'<span class="miss">（转写里没找到这个词，需人工定位）</span></div>')
                continue
            body.append('<div class="clip">')
            body.append(f'<div><span class="kw">{c["kw"]}</span>'
                        f'<span class="ts">@{mmss(c["t"])} · 命中 {c["hits"]} 处（下面播放第一处）</span></div>')
            body.append(f'<div class="txt">{c["text"]}</div>')
            body.append(f'<audio controls preload="none" src="{c["file"]}"></audio>')
            body.append('</div>')
        body.append(f'<textarea data-q="{it["id"]}" placeholder="听后的结论（{it["topic"]}）"></textarea>')
        body.append('</div>')
    tail = """
<div id="bar">
  <button onclick="exportAll()">导出答案</button>
  <button class="ghost" onclick="document.getElementById('out').style.display='none'">收起</button>
  <span style="font-size:13px;color:#999">填完把下面这段复制给我就行</span>
</div>
<pre id="out"></pre>
<script>
function exportAll(){
  var out=[];
  document.querySelectorAll('textarea[data-q]').forEach(function(t){
    var v=(t.value||'').trim();
    if(v) out.push(t.dataset.q+'：'+v);
  });
  var pre=document.getElementById('out');
  pre.textContent = out.length? out.join('\\n') : '（还没填任何答案）';
  pre.style.display='block';
  pre.scrollIntoView({behavior:'smooth'});
  if(navigator.clipboard && out.length) navigator.clipboard.writeText(out.join('\\n')).catch(function(){});
}
</script>
</body></html>
"""
    return head + "\n".join(body) + tail


if __name__ == "__main__":
    sys.exit(main())
