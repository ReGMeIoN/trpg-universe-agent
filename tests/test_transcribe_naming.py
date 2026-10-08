# -*- coding: utf-8 -*-
"""转写产物命名回归: 一个团多个录音时不能互相覆盖。

背景（2026-10-05 实测坑）: 一个团带两份录音（如「魔法少女育成计划 6」的上下场）时,
`out_path_for()` 只按团名生成 `<团>_转写.txt`, 第二份录音会把第一份**整份覆盖**,
而且两份还共用同一个断点文件 -> 续跑直接把前一份的进度判废。

修法: 多录音团给每份录音加 part_tag（= 音频名），转写稿与断点文件都带这个 tag。

用法(项目根目录):
    .venv\\Scripts\\python.exe tests\\test_transcribe_naming.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import ASR_ENGINES  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.transcribe import (  # noqa: E402
    _safe_tag,
    out_path_for,
    run_transcribe,
    state_path_for,
)
from trpg_agent.workspace import Workspace  # noqa: E402

FAILURES: list[str] = []
CHECKS = 0

TMP_WS = ROOT / ".tmp" / "naming_ws"


class FakeEngine:
    """假转写引擎: 不碰音频/模型, 只回一段带时间戳的假文本(内容是音频文件名)。"""

    name = "fake_asr_test"

    @staticmethod
    def probe_audio(path) -> dict:
        return {"path": str(path), "codec": "fake", "sample_rate": 16000,
                "channels": 1, "duration_s": 12.0}

    @staticmethod
    def iter_events(path, cfg, resume=None, smoke_seconds=0):
        tag = Path(path).stem
        yield {"kind": "model_loaded", "seconds": 0.0, "model": "fake"}
        yield {"kind": "window", "window": 0, "base_s": 0, "speech_chunks": 1, "batches": 1,
               "speech_s": 12.0}
        yield {"kind": "batch_start", "window": 0, "batch": 0, "batch_count": 1}
        yield {"kind": "chunk", "start": 0.0, "end": 3.0, "text": f"这是 {tag} 的第一句话"}
        yield {"kind": "chunk", "start": 3.0, "end": 6.0, "text": f"{tag} 说的第二句完全不同的话"}
        yield {"kind": "batch", "window": 0, "batch": 0, "batch_count": 1, "audio_at": 12.0,
               "skipped": False}
        yield {"kind": "window_done", "window": 0, "batches": 1, "skipped": False}
        yield {"kind": "done", "segments": 2, "windows": 1, "audio_s": 12.0, "speech_s": 12.0,
               "elapsed_s": 0.1, "truncated": False, "decode_error": None}


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def main() -> int:
    print("== 转写命名回归自测 ==")
    cfg = load_config(ROOT / "config.yaml")
    ws = Workspace.from_config(cfg)
    group = "测试团 双录音"
    up, down = "上半场 2026", "下半场/2026"  # 下半场故意带非法文件名字符

    p_plain = out_path_for(ws, cfg, group)
    p_up = out_path_for(ws, cfg, group, part_tag=up)
    p_down = out_path_for(ws, cfg, group, part_tag=down)

    check("单录音团仍用 <团>_转写.txt", p_plain.name == f"{group}{cfg.asr.out_suffix}.txt", p_plain.name)
    check("多录音两份产物不同名", p_up != p_down, f"{p_up.name} vs {p_down.name}")
    check("多录音产物带音频标签", "上半场" in p_up.name and "下半场" in p_down.name,
          f"{p_up.name} / {p_down.name}")
    check("标签里的路径分隔符被清洗", "/" not in p_down.name and "\\" not in p_down.name,
          p_down.name)
    check("单录音产物不与分片产物相撞", p_plain != p_up, f"{p_plain.name} vs {p_up.name}")
    check("产物都落在 素材 目录", p_up.parent == ws.material == p_plain.parent,
          f"{p_up.parent} / {p_plain.parent}")

    s_plain = state_path_for(ws, group)
    s_up = state_path_for(ws, group, part_tag=up)
    s_down = state_path_for(ws, group, part_tag=down)
    check("断点文件按分片隔离", len({s_plain, s_up, s_down}) == 3,
          f"{s_plain.name} / {s_up.name} / {s_down.name}")
    check("断点文件名无非法字符", all("/" not in p.name and "\\" not in p.name for p in (s_up, s_down)))

    check("_safe_tag 清洗非法字符", _safe_tag('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j",
          _safe_tag('a/b\\c:d*e?f"g<h>i|j'))
    long_tag = _safe_tag("x" * 200)
    check("_safe_tag 截断到 40 字符", len(long_tag) == 40, str(len(long_tag)))
    check("_safe_tag 空输入有兜底", _safe_tag("   ") == "part", _safe_tag("   "))

    # ---- 端到端(假引擎): 一个团两份录音, 两份产物都要在, 且互不覆盖 ----
    import shutil

    shutil.rmtree(TMP_WS, ignore_errors=True)
    (TMP_WS / "素材").mkdir(parents=True, exist_ok=True)
    cfg2 = load_config(ROOT / "config.yaml", str(TMP_WS))
    cfg2.asr.engine = FakeEngine.name
    ws2 = Workspace.from_config(cfg2)
    ws2.ensure_dirs()
    ASR_ENGINES[FakeEngine.name] = FakeEngine

    a1 = ws2.material / "上半场录音.m4a"
    a2 = ws2.material / "下半场录音.m4a"
    a1.write_bytes(b"fake")
    a2.write_bytes(b"fake")
    g = "双录音团"

    r1 = run_transcribe(ws2, cfg2, a1, group=g, part_tag=a1.stem)
    r2 = run_transcribe(ws2, cfg2, a2, group=g, part_tag=a2.stem)
    p1, p2 = ws2.root / r1["out"], ws2.root / r2["out"]
    check("两段录音都产出了各自的稿子", p1.is_file() and p2.is_file(), f"{p1.name} / {p2.name}")
    check("两份稿子内容不同(没有互相覆盖)",
          p1.read_text(encoding="utf-8") != p2.read_text(encoding="utf-8"))
    check("稿子内容确实来自各自的音频",
          "上半场录音" in p1.read_text(encoding="utf-8")
          and "下半场录音" in p2.read_text(encoding="utf-8"))
    check("两份断点文件各自独立",
          (ws2.state / state_path_for(ws2, g, a1.stem).name).is_file()
          and (ws2.state / state_path_for(ws2, g, a2.stem).name).is_file())
    check("合并时间轴能接上两份稿子",
          "上半场录音" in p1.read_text(encoding="utf-8")
          and len(p1.read_text(encoding="utf-8").splitlines()) == 2)

    print(f"\n== 结果: {CHECKS - len(FAILURES)}/{CHECKS} 通过 ==")
    if FAILURES:
        print("失败项:")
        for f in FAILURES:
            print("  - " + f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
