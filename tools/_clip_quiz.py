# -*- coding: utf-8 -*-
"""疑问片段核对工作流：把"转写存疑"的录音片段剪出来，生成可逐条播放+填答的 HTML 页。

为什么需要它（2026-10-03 主人提出）：
  核对环节只贴转写原文没用 —— 转写本身就是 ASR 错字（「地牙?」「劳昌?」「士兮」），
  光看文字谁也认不出来；把对应**音频片段**剪出来一听就明白。
  这条工作流对任何团/任何存疑清单都通用。

用法:
    .venv\\Scripts\\python.exe tools\\_clip_quiz.py --group <团名>
    .venv\\Scripts\\python.exe tools\\_clip_quiz.py --group <团名> --quiz my_quiz.json
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

# <团名>：需要"听"的存疑条目（来自 .trpg/reports/<团名>_待确认.md）
DEFAULT_QUIZ = [
    {"id": "Q01", "topic": "某个专有名词的标准写法是什么？",
     "kws": ["候选写法1", "候选写法2"],
     "hint": "转写里并存几种写法，听一下哪一处为准"},
    {"id": "Q02", "topic": "某个称呼指的是谁？",
     "kws": ["称呼A", "称呼B"], "hint": "多人混用时请分别指认"},
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
    ap.add_argument("--group", required=True)
    ap.add_argument("--audio", help="音频路径（默认取该团素材里的 audio）")
    ap.add_argument("--transcript", help="转写稿路径")
    ap.add_argument("--quiz", help="外部疑问清单 JSON")
    ap.add_argument("--tag", default="", help="输出后缀与片段子目录（如 第2轮），便于多轮并存")
    ap.add_argument("--config", default=str(ROOT / "config.yaml"))
    args = ap.parse_args()

    cfg = load_config(args.config)
    ws = Workspace.from_config(cfg)
    group = args.group

    quiz = DEFAULT_QUIZ
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
