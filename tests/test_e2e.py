# -*- coding: utf-8 -*-
"""端到端测试: 脱敏示例团跑完整固定工作流。

覆盖: ingest -> segment -> store(工作副本) -> store(--apply) -> visualize -> export -> housekeep
      + 关系图 HTML 结构校验
(transcribe/extract 需要音频与 LLM, 已在各自模块单独验证过, 这里不纳入以免测试依赖外部服务)

用法(项目根目录):
    .venv\\Scripts\\python.exe tests\\test_e2e.py
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.export.kb_pack import run_export  # noqa: E402
from trpg_agent.housekeep import run_housekeep  # noqa: E402
from trpg_agent.ingest import scan  # noqa: E402
from trpg_agent.ingest import qq as qq_mod  # noqa: E402
from trpg_agent.segment import segment_one  # noqa: E402
from trpg_agent.store import run_store  # noqa: E402
from trpg_agent.visualize import run_visualize  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

SRC = ROOT / "examples" / "mini-group"
TMP = ROOT / ".tmp" / "e2e_ws"
FAIL: list[str] = []
N = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global N
    N += 1
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  {detail}"))
    if not cond:
        FAIL.append(name)


def check_html(path: Path) -> None:
    t = path.read_text(encoding="utf-8")
    nodes = len(re.findall(r'<div class="node"', t))
    details = re.search(r"const DETAILS = (.*?);\n", t, re.S)
    ok_json = False
    if details:
        try:
            ok_json = isinstance(json.loads(details.group(1).replace("<\\/", "</")), dict)
        except json.JSONDecodeError:
            ok_json = False
    check(f"HTML 结构 {path.name}（节点 {nodes}）",
          nodes > 0 and ok_json and "{{" not in t and t.count("{") == t.count("}"),
          f"nodes={nodes} json={ok_json}")


def main() -> int:
    print(f"== 端到端测试 ==\n源: {SRC}\n目标: {TMP}\n")
    shutil.rmtree(TMP, ignore_errors=True)
    TMP.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, TMP)

    fix = json.loads((TMP / "数据" / "characters.json").read_text(encoding="utf-8"))
    if len(fix["characters"]) != 1:
        print("!! 示例夹具不是初始态, 先跑 tools\\reset_example.py")
        return 2

    cfg = load_config(ROOT / "config.yaml", str(TMP))
    ws = Workspace.from_config(cfg)
    ws.ensure_dirs()

    # 工作补丁从受保护夹具复制(extract 会覆盖 .trpg/patches 下的工作副本)
    fix_patch = TMP / "fixtures" / "星海列车_patch.json"
    work_patch = TMP / ".trpg" / "patches" / "星海列车_patch.json"
    work_patch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fix_patch, work_patch)

    print("[1] ingest")
    m = scan(ws, cfg)
    check("素材 2 个 / 2 团", m["counts"]["total"] == 2 and len(m["groups"]) == 2, str(m["groups"]))
    entry = next(f for f in m["files"] if f["type"] == "qq_export")
    info = qq_mod.convert_qq_export(ws, ws.root / entry["path"])
    textlog = qq_mod.write_textlog(ws, "星海列车外传", info["text"])
    check("QQ 导出转文本 22 行", info["lines"] == 22, str(info["lines"]))

    print("[2] segment")
    a = segment_one(ws, cfg, "星海列车", [ws.root / "素材/星海列车/星海列车_录音转写.txt"],
                    strategy="time_window")
    b = segment_one(ws, cfg, "星海列车外传", [textlog], strategy="date")
    check("转写线 3 段", len(a["segments"]) == 3, str(len(a["segments"])))
    check("QQ 线 1 段", len(b["segments"]) == 1, str(len(b["segments"])))

    print("[3] store (工作副本)")
    patch = TMP / ".trpg" / "patches" / "星海列车_patch.json"
    r = run_store(ws, cfg, patch_path=patch, apply=False)
    plan = r["plan"]
    check("计划 角色4/更新1/关系3/待确认5",
          len(plan["new_characters"]) == 4 and len(plan["updated_characters"]) == 1
          and len(plan["new_relations"]) == 3 and len(plan["pending"]) == 5,
          json.dumps({k: len(plan[k]) for k in ("new_characters", "updated_characters",
                                                "new_relations", "pending")}, ensure_ascii=False))
    check("称呼归一 3 处", len(plan["normalized"]) == 3, str(plan["normalized"]))
    check("工作副本校验通过", r["validation_ok"] is True)

    print("[4] store --apply")
    r2 = run_store(ws, cfg, patch_path=patch, apply=True)
    chars = json.loads(ws.data_file("characters").read_text(encoding="utf-8"))["characters"]
    rels = json.loads(ws.data_file("relations").read_text(encoding="utf-8"))["relations"]
    check("回填后 5 角色 / 3 关系", len(chars) == 5 and len(rels) == 3, f"{len(chars)}/{len(rels)}")
    check("备份已生成", len(r2["backups"]) == 4, str(len(r2["backups"])))
    heiyi = next(c for c in chars if c["id"] == "cross_heiyi")
    check("跨团角色 groups 追加", "星海列车" in heiyi["groups"], str(heiyi["groups"]))
    tieya = next(c for c in chars if c["id"] == "xh_tieya")
    check("归一: 老鸭 -> 老鸦", tieya["played_by"] == "老鸦", tieya["played_by"])
    check("未确认角色未入库", all(c["id"] != "xh_shenmi" for c in chars))

    print("[5] visualize")
    v = run_visualize(ws, cfg, group="星海列车")
    check("关系图生成", len(v["net"]) == 1 and v["net"][0]["nodes"] == 5,
          json.dumps(v["net"], ensure_ascii=False))
    check("PL 画像墙生成", bool(v.get("pl_wall")))
    if v["net"]:
        check_html(ws.root / v["net"][0]["path"])
    rel_md = ws.output / "星海列车_关系网.md"
    check("关系网 md 生成", rel_md.is_file() and "临海" in rel_md.read_text(encoding="utf-8"))

    print("[6] export")
    e = run_export(ws, cfg)
    check("KB 包生成", len(e["written"]) >= 4, str(e["written"]))
    kb = ws.output / cfg.export.out_dir
    check("KB 含总览/杰克/PL/团文档",
          all((kb / n).is_file() for n in ("00_跑团宇宙总览.md", "00b_杰克档案.md",
                                           "00c_PL档案.md", "星海列车.md")),
          str(sorted(p.name for p in kb.glob("*.md"))))

    print("[7] housekeep")
    h = run_housekeep(ws, cfg)
    check("收尾清单生成", Path(ws.root / h["path"]).is_file())
    check("数据量与回填一致", h["counts"]["characters"] == 5 and h["counts"]["relations"] == 3,
          json.dumps(h["counts"], ensure_ascii=False))

    print(f"\n== 结果: {N - len(FAIL)}/{N} 通过 ==")
    if FAIL:
        print("失败项:")
        for f in FAIL:
            print("  -", f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
