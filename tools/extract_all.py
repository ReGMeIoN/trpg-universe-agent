# -*- coding: utf-8 -*-
"""批量提炼: 对所有已有段索引的团依次跑 extract。

只写 <work>/extracts、<work>/patches、<work>/reports —— **不碰 数据/**。
已存在的段提炼默认跳过(skip_if_exists), 便于中断续跑。

用法:
    .venv\\Scripts\\python.exe tools\\extract_all.py --dry-run          # 只列清单与预估
    .venv\\Scripts\\python.exe tools\\extract_all.py --exclude 无敌巨鲨大战奈亚拉托提普
    .venv\\Scripts\\python.exe tools\\extract_all.py --only 魔法少女五 魔法少女2
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent import log  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.extract import run_extract  # noqa: E402
from trpg_agent.segment import load_index  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

# 粗略估算: 生产段平均约 25k 输入 token(60~140KB), 输出含思考约 15k
EST_IN_TOK = 25000
EST_OUT_TOK = 15000
PRICE_IN_PER_M = 1.5   # DeepSeek 低谷 缓存未命中(元/M); 仅作量级参考
PRICE_OUT_PER_M = 8.0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default=None, help="工作区根(覆盖 config)")
    ap.add_argument("--config", default=None)
    ap.add_argument("--only", nargs="*", default=None, help="只跑这些团")
    ap.add_argument("--exclude", nargs="*", default=[], help="跳过这些团")
    ap.add_argument("--force", action="store_true", help="已有提炼也重跑")
    ap.add_argument("--dry-run", action="store_true", help="只列清单与预估, 不调用 LLM")
    ap.add_argument("--include-unclassified", action="store_true",
                    help="连 '<团>·未归类' 这种非团分组也提炼(默认跳过)")
    args = ap.parse_args()

    cfg = load_config(args.config, args.ws)
    ws = Workspace.from_config(cfg)
    idx_dir = ws.work / "segments_index"
    if not idx_dir.is_dir():
        print("!! 没有段索引, 先跑: trpg-agent segment")
        return 2

    groups: list[tuple[str, int, int]] = []
    for p in sorted(idx_dir.glob("*.json")):
        idx = json.loads(p.read_text(encoding="utf-8"))
        n = len(idx.get("segments") or [])
        if not n:
            continue
        groups.append((p.stem, n, int(idx.get("total_lines") or 0)))

    if args.only:
        groups = [g for g in groups if g[0] in set(args.only)]
    groups = [g for g in groups if g[0] not in set(args.exclude)]
    if not args.include_unclassified:
        skipped_unclassified = [g[0] for g in groups if g[0].endswith("·未归类")]
        groups = [g for g in groups if not g[0].endswith("·未归类")]
        for s in skipped_unclassified:
            log.warn(f"跳过非团分组: {s}（区间外消息的暂存桶, 不构成团; 要提炼加 --include-unclassified）")

    total_seg = sum(g[1] for g in groups)
    est_in = total_seg * EST_IN_TOK
    est_out = total_seg * EST_OUT_TOK
    est_cost = est_in / 1e6 * PRICE_IN_PER_M + est_out / 1e6 * PRICE_OUT_PER_M

    log.step(f"批量提炼 · {len(groups)} 团 / {total_seg} 段")
    for name, n, lines in groups:
        log.info(f"  {name:<30} {n:>2} 段 / {lines:>7} 行")
    log.info(
        f"预估: 输入 ~{est_in/1e6:.2f}M tok · 输出 ~{est_out/1e6:.2f}M tok "
        f"· 约 ¥{est_cost:.1f}(量级参考, 推理模型输出占比高)"
    )
    if args.dry_run:
        log.info("--dry-run: 不执行")
        return 0

    results: list[dict] = []
    t0 = time.time()
    for i, (name, n, _lines) in enumerate(groups, 1):
        log.step(f"[{i}/{len(groups)}] {name} · {n} 段")
        t = time.time()
        try:
            r = run_extract(ws, cfg, name, force=args.force)
            r["elapsed_s"] = round(time.time() - t, 1)
            results.append(r)
        except Exception as e:  # noqa: BLE001
            log.err(f"[{name}] 失败: {type(e).__name__}: {e}")
            results.append({"group": name, "error": f"{type(e).__name__}: {e}",
                            "elapsed_s": round(time.time() - t, 1)})

    ok = [r for r in results if "error" not in r]
    total_s = round(time.time() - t0, 1)
    lines = ["# 批量提炼汇总", "", f"- 时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
             f"- 团数: {len(results)} (成功 {len(ok)} / 失败 {len(results) - len(ok)})",
             f"- 总耗时: {total_s/60:.1f} 分钟", "",
             "| 团 | 段 | 新增角色 | 更新 | 关系 | 待确认 | 耗时 s |", "|---|---|---|---|---|---|---|"]
    for r in results:
        c = r.get("counts") or {}
        lines.append(
            f"| {r['group']} | {len(r.get('results') or [])} | {c.get('characters', '-')} "
            f"| {c.get('character_updates', '-')} | {c.get('relations', '-')} "
            f"| {c.get('pending', '-')} | {r.get('elapsed_s', '-')} |"
        )
    errs = [r for r in results if "error" in r]
    if errs:
        lines += ["", "## 失败", ""]
        for r in errs:
            lines.append(f"- {r['group']}: {r['error']}")
    out = ws.reports / f"批量提炼_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    log.ok(f"批量汇总: {ws.rel(out)}")
    log.info(f"成功 {len(ok)}/{len(results)} · 总耗时 {total_s/60:.1f} 分钟")
    log.info("下一步: 逐个团看 reports/<团>_入库报告.md, 确认后 store --group <团> --apply --allow-production")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
