# -*- coding: utf-8 -*-
"""切片 1 回归自测: 在 .tmp/selftest_ws 里复制一份示例团, 跑完整 ingest->segment->store。

用法(项目根目录):
    .venv\\Scripts\\python.exe tests\\test_slice1.py

不依赖 pytest / 不依赖 tempfile(本机沙箱下 tempfile 不可用), 全部走显式路径。
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.ingest import load_manifest, scan  # noqa: E402
from trpg_agent.ingest import qq as qq_mod  # noqa: E402
from trpg_agent.segment import load_index, segment_one  # noqa: E402
from trpg_agent.store import run_store  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

SRC_WS = ROOT / "examples" / "mini-group"
TMP_WS = ROOT / ".tmp" / "selftest_ws"
PATCH = TMP_WS / ".trpg" / "patches" / "星海列车_patch.json"

FAILURES: list[str] = []
CHECKS = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    print(f"== 切片 1 回归自测 ==\n源: {SRC_WS}\n目标: {TMP_WS}\n")
    shutil.rmtree(TMP_WS, ignore_errors=True)
    TMP_WS.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC_WS, TMP_WS)

    # 夹具必须处于初始态, 否则 store 的"新增"会变成"重复"
    _fx_chars = json.loads((TMP_WS / "数据" / "characters.json").read_text(encoding="utf-8"))
    _fx_rels = json.loads((TMP_WS / "数据" / "relations.json").read_text(encoding="utf-8"))
    if len(_fx_chars["characters"]) != 1 or _fx_rels["relations"]:
        print("!! 示例夹具不是初始态(已被 apply 过)。先跑: "
              ".venv\\Scripts\\python.exe tools\\reset_example.py\n")
        return 2

    cfg = load_config(ROOT / "config.yaml", str(TMP_WS))
    ws = Workspace.from_config(cfg)
    ws.ensure_dirs()

    # 工作补丁从受保护夹具复制(extract 会覆盖 .trpg/patches 下的工作副本)
    fix_patch = TMP_WS / "fixtures" / "星海列车_patch.json"
    work_patch = TMP_WS / ".trpg" / "patches" / "星海列车_patch.json"
    work_patch.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(fix_patch, work_patch)

    # ---------- 1. ingest ----------
    print("[1] ingest")
    manifest = scan(ws, cfg)
    check("manifest 记录 2 个素材", manifest["counts"]["total"] == 2, str(manifest["counts"]))
    check("识别出 2 个团", sorted(manifest["groups"]) == ["星海列车", "星海列车外传"], str(manifest["groups"]))
    types = manifest["by_type"]
    check("类型识别 transcript/qq_export",
          types.get("transcript") == 1 and types.get("qq_export") == 1, str(types))

    qq_entry = next(f for f in manifest["files"] if f["type"] == "qq_export")
    info = qq_mod.convert_qq_export(ws, ws.root / qq_entry["path"])
    textlog = qq_mod.write_textlog(ws, "星海列车外传", info["text"])
    check("QQ 导出转纯文本 22 行", textlog.is_file() and info["lines"] == 22, f"lines={info['lines']}")
    check("QQ 日期范围正确", info["d0"] == "2026-01-17" and info["d1"] == "2026-01-18",
          f"{info['d0']}~{info['d1']}")

    manifest2 = scan(ws, cfg)
    check("二次扫描全部 unchanged(幂等)", manifest2["counts"]["unchanged"] == 2, str(manifest2["counts"]))

    # ---------- 2. segment ----------
    print("[2] segment")
    res_a = segment_one(ws, cfg, "星海列车", [ws.root / "素材/星海列车/星海列车_录音转写.txt"],
                        strategy="time_window")
    check("转写线切成 3 段(63 分钟窗)", len(res_a["segments"]) == 3, f"{len(res_a['segments'])} 段")
    check("转写线无未解析行", res_a["unparsed"] == 0, str(res_a["unparsed"]))
    check("段标签带单位", res_a["segments"][0]["label"] == "0h00m-0h04m", res_a["segments"][0]["label"])

    res_b = segment_one(ws, cfg, "星海列车外传", [textlog], strategy="date")
    check("QQ 线默认把两天合并为 1 段", len(res_b["segments"]) == 1, f"{len(res_b['segments'])} 段")

    # 生产库存在人工命名的历史段文件, 清理时绝不能误删
    foreign = ws.segments / "星海列车_段9_人工命名.txt"
    foreign.write_text("人工内容, 不属于本工具产出", encoding="utf-8")

    res_b2 = segment_one(ws, cfg, "星海列车外传", [textlog], strategy="date", date_merge_lines=0)
    check("QQ 线 --date-merge-lines 0 -> 2 段", len(res_b2["segments"]) == 2, f"{len(res_b2['segments'])} 段")
    check("孤儿段被清理(只按索引)", not list(ws.segments.glob("星海列车外传_段*_01-17~01-18.txt")))
    check("人工段文件未被误删", foreign.is_file(), str(foreign))

    # 复原默认切段, 供 store 段落引用
    segment_one(ws, cfg, "星海列车外传", [textlog], strategy="date")
    idx = load_index(ws, "星海列车")
    check("段索引落盘", idx is not None and idx["count"] == 3, str(idx and idx.get("count")))

    # ---------- 3. store(工作副本) ----------
    print("[3] store (工作副本)")
    before = {k: sha(ws.data_file(k)) for k in ("characters", "relations", "players", "pl_profiles")}
    r = run_store(ws, cfg, patch_path=PATCH, apply=False)
    plan = r["plan"]
    check("计划: 新增角色 4", len(plan["new_characters"]) == 4, str(plan["new_characters"]))
    check("计划: 更新角色 1", plan["updated_characters"] == ["xh_heiyi"], str(plan["updated_characters"]))
    check("计划: 新增关系 3", len(plan["new_relations"]) == 3, str(plan["new_relations"]))
    check("计划: 待确认 5(含 2 条未确认降级)", len(plan["pending"]) == 5, str(len(plan["pending"])))
    check("计划: 称呼归一 3", len(plan["normalized"]) == 3, str(plan["normalized"]))
    check("id 前缀走 config 登记表", plan["id_prefix_source"] == "config.store.id_prefix_map", plan["id_prefix_source"])
    check("工作副本校验通过", r["validation_ok"] is True)
    after = {k: sha(ws.data_file(k)) for k in before}
    check("工作副本模式不动数据目录", before == after)

    staged = json.loads((ws.staging / "characters.json").read_text(encoding="utf-8"))
    check("未确认角色未进工作副本", all(c["id"] != "xh_shenmi" for c in staged["characters"]))
    tieya = next(c for c in staged["characters"] if c["id"] == "xh_tieya")
    check("称呼归一: 老鸭 -> 老鸦", tieya["played_by"] == "老鸦", tieya["played_by"])
    heiyi = next(c for c in staged["characters"] if c["id"] == "xh_heiyi")
    check("角色 groups 追加", "星海列车" in heiyi["groups"], str(heiyi["groups"]))

    # ---------- 4. store --apply ----------
    print("[4] store --apply (示例库非生产库, 允许回填)")
    r2 = run_store(ws, cfg, patch_path=PATCH, apply=True)
    check("回填成功", r2["applied"] is True)
    check("生成 4 份备份", len(r2["backups"]) == 4, str(len(r2["backups"])))
    final = json.loads(ws.data_file("characters").read_text(encoding="utf-8"))
    check("回填后 5 个角色", len(final["characters"]) == 5, str(len(final["characters"])))
    check("_meta.updated 已更新", final["_meta"]["updated"] != "2026-01-01", final["_meta"]["updated"])
    rels = json.loads(ws.data_file("relations").read_text(encoding="utf-8"))
    check("回填后 3 条关系", len(rels["relations"]) == 3, str(len(rels["relations"])))

    # ---------- 4b. 纯更新也要回填 ----------
    # 2026-10-03 修复: 旧版用 counts_after == counts_before 判"净变更"(只比条目数量),
    # 于是"更新角色 1(追加 note/events)"这种纯更新永远被"跳过回填"。
    print("[4b] 纯更新回填")
    first_id = final["characters"][0]["id"]
    upd_patch = TMP_WS / ".trpg" / "patches" / "纯更新_patch.json"
    upd_patch.write_text(json.dumps({
        "group": "星海列车",
        "characters": [],
        "relations": [],
        "character_updates": [{
            "id": first_id,
            "append_note": "回归测试标记：纯更新也要回填",
            "set_name": "改名测试角色",
            "confirmed": True,
        }],
    }, ensure_ascii=False), encoding="utf-8")
    run_store(ws, cfg, patch_path=upd_patch, apply=True)
    after = json.loads(ws.data_file("characters").read_text(encoding="utf-8"))
    hit = next((c for c in after["characters"] if c["id"] == first_id), {})
    check("纯更新已写盘", "回归测试标记" in (hit.get("note") or ""), (hit.get("note") or "")[:60])
    check("纯更新不改变条目数", len(after["characters"]) == len(final["characters"]))
    check("set_name 改名生效", hit.get("name") == "改名测试角色", str(hit.get("name")))

    # ---------- 5. 生产库闸门 ----------
    print("[5] 生产库安全闸")
    prod_cfg = load_config(ROOT / "config.yaml")
    prod_ws = Workspace.from_config(prod_cfg)
    check("默认工作区被标记为生产库", prod_ws.is_production is True)
    blocked = False
    try:
        prod_ws.guard_write("selftest")
    except Exception as e:  # ProductionWriteBlocked
        blocked = "拒绝写入生产库" in str(e)
    check("未授权写生产库被拒绝", blocked)

    print(f"\n== 结果: {CHECKS - len(FAILURES)}/{CHECKS} 通过 ==")
    if FAILURES:
        print("失败项:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
