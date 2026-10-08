# -*- coding: utf-8 -*-
"""程序化校验生成的关系图 HTML(不依赖人眼看图)。"""
import json
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

base = Path(sys.argv[1] if len(sys.argv) > 1 else ".tmp/demo_ws/产出")
bad = 0
files = sorted(base.glob("*_关系图.html"))
for f in files:
    t = f.read_text(encoding="utf-8")
    nodes = len(re.findall(r'<div class="node"', t))
    lines = len(re.findall(r"<line ", t))
    m = re.search(r"const DETAILS = (.*?);\n", t, re.S)
    details_ok = False
    if m:
        try:
            details_ok = isinstance(json.loads(m.group(1).replace("<\\/", "</")), dict)
        except Exception as e:  # noqa: BLE001
            details_ok = f"parse-fail:{e}"
    # 只把残留 `{{` 当作模板转义 bug: str.format() 必然把 {{ 渲染成 {
    # (`}}` 不能作为判据 —— DETAILS JSON 里天然会出现 }} )
    esc_left = "{{" in t
    braces = (t.count("{"), t.count("}"))
    ok = nodes > 0 and details_ok is True and not esc_left and braces[0] == braces[1]
    print(f"{'OK  ' if ok else 'FAIL'} {f.name}: 节点={nodes} 边={lines} DETAILS={details_ok} "
          f"花括号={braces[0]}/{braces[1]} 残留转义={esc_left}")
    if not ok:
        bad += 1

print("---")
print(f"{len(files)} 个关系图, " + ("全部通过" if bad == 0 else f"{bad} 个有问题"))
sys.exit(1 if bad else 0)
