# -*- coding: utf-8 -*-
"""Verify the append_note idempotency guard on the shadow workspace (real store, twice).

Scenario copied from today's incident: a patch carries `append_note` text that ALREADY exists in
the target node's note; running `store --apply` again used to append it a second time.
This injects exactly that, stores twice on the shadow, and asserts the sentence count stays 1.

usage: python tools/_verify_note_idempotent.py
"""
from __future__ import annotations

import os
import json
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WS = Path(os.environ.get("TRPG_WS", "workspace"))
SHADOW = WS / ".trpg" / "shadow_ws"
GROUP = "\u9634\u9633\u5dee\u4e8b\u5f55 \u8d85\u81ea\u7136\u602a\u8c08"
SENT = "\u8fd9\u4e9b\u7ebf\u7d22\u7b97\u6770\u514b\u672c\u4eba\u51fa\u573a"      # 已在杰克 note 里的一句
PY = str(ROOT / ".venv" / "Scripts" / "python.exe")


def jack_note(shadow: Path) -> str:
    d = json.loads((shadow / "\u6570\u636e" / "characters.json").read_text(encoding="utf-8"))
    c = next(x for x in d["characters"] if x.get("id") == "cross_jieke")
    return c.get("note") or ""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    print("1) 重建影子库 ...")
    subprocess.run([PY, str(ROOT / "tools" / "_shadow_sync.py"), "--apply"],
                   check=True, capture_output=True)
    before = jack_note(SHADOW)
    print(f"   杰克 note 长度 {len(before)} · 该句出现 {before.count(SENT)} 次")

    # 注入「已在 note 里」的 append_note（= 今天的事故场景）
    p = SHADOW / ".trpg" / "patches" / f"{GROUP}_patch.json"
    doc = json.loads(p.read_text(encoding="utf-8"))
    u = next(x for x in (doc.get("character_updates") or []) if x.get("id") == "cross_jieke")
    u["append_note"] = SENT
    u["confirmed"] = True
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"2) 已注入重复 append_note（{SENT}）")

    for n in (1, 2):
        r = subprocess.run([PY, "-m", "trpg_agent", "store", "--apply", "--ws", str(SHADOW),
                            "--group", GROUP], cwd=str(ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        out = (r.stdout or "") + (r.stderr or "")
        line = next((x.strip() for x in out.splitlines() if "更新角色" in x or "跳过" in x), "")
        after = jack_note(SHADOW)
        print(f"   第 {n} 次 store: {line} | note 长度 {len(after)} · 该句 {after.count(SENT)} 次")

    final = jack_note(SHADOW)
    ok = final.count(SENT) == before.count(SENT)
    print(f"\n结果: {'OK 幂等（重复入库不再追加）' if ok else 'FAIL 仍然重复追加'}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
