# -*- coding: utf-8 -*-
"""expract 编排: 分段提炼(扇出) -> 汇总成补丁 -> (可选)直接交给 store。

产物:
    <work>/extracts/<团>_段N_提炼.md      每段结构化草稿(可人读/可手改)
    <work>/extracts/<团>_汇总.md          汇总调用的人读版(模型原始输出)
    <work>/patches/<团>_patch.json        store 直接消费的补丁
    <work>/state/extract_<团>.json        断点/统计
"""
from __future__ import annotations

import json
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.adapters import make_llm_client
from trpg_agent.adapters.llm_base import LLMError
from trpg_agent.adapters.llm_ollama import parse_json_reply
from trpg_agent.canon import render_canon_block
from trpg_agent.config import Config
from trpg_agent.extract.prompt import patch_json_schema, render_consolidate_prompt, render_segment_prompt
from trpg_agent.segment import load_index
from trpg_agent.state import sha256_text
from trpg_agent.workspace import Workspace

LEAK_JUNK = re.compile(r"^(未能|无法|抱歉|作为|注意)[^\n]{0,40}$")


def extract_dir(ws: Workspace) -> Path:
    return ws.work / "extracts"


def segment_extract_path(ws: Workspace, group: str, n: int) -> Path:
    return extract_dir(ws) / f"{group}_段{n}_提炼.md"


def _segment_text(ws: Workspace, seg: dict[str, Any]) -> str:
    p = ws.root / seg["file"]
    if not p.is_file():
        raise FileNotFoundError(f"段文件不存在, 请先跑 segment: {p}")
    return p.read_text(encoding="utf-8", errors="replace")


def lint_patch(patch: dict[str, Any]) -> list[str]:
    """补丁体检: 挡住弱模型常见的退化输出。

    实测(qwen2.5:7b)常见问题:
      - 同一角色重复多条(同 id)
      - 自环关系(from == to)
      - character_updates 指向本次新增的 id(应该是 characters)
      - 关系端点不存在
    """
    warns: list[str] = []

    # 1) characters 去重(合并 aliases / events)
    seen: dict[str, dict[str, Any]] = {}
    deduped: list[dict[str, Any]] = []
    for c in patch.get("characters") or []:
        if not isinstance(c, dict):
            continue
        cid = c.get("id")
        if cid and cid in seen:
            keep = seen[cid]
            aliases = list(keep.get("aliases") or [])
            aliases += [a for a in (c.get("aliases") or []) if a not in aliases]
            keep["aliases"] = aliases
            if not keep.get("note") and c.get("note"):
                keep["note"] = c["note"]
            if not keep.get("played_by") and c.get("played_by"):
                keep["played_by"] = c["played_by"]
            for ev in c.get("events") or []:
                keep.setdefault("events", []).append(ev)
            warns.append(f"characters 里 {cid} 重复出现, 已合并")
            continue
        if cid:
            seen[cid] = c
        deduped.append(c)
    if len(deduped) != len(patch.get("characters") or []):
        patch["characters"] = deduped

    new_ids = set(seen)

    # 2) 自环关系剔除
    rels = []
    for r in patch.get("relations") or []:
        if not isinstance(r, dict):
            continue
        if r.get("from") and r.get("from") == r.get("to"):
            warns.append(f"剔除自环关系: {r.get('from')} -- {r.get('type')} (自己指向自己)")
            continue
        rels.append(r)
    if len(rels) != len(patch.get("relations") or []):
        patch["relations"] = rels

    # 3) updates 指向本次新增 id -> 提醒(store 会跳过)
    for u in patch.get("character_updates") or []:
        if isinstance(u, dict) and u.get("id") in new_ids:
            warns.append(
                f"character_updates 指向本次新增的 {u.get('id')}(应放在 characters 里); store 会跳过它"
            )

    # 4) 关系端点必须在 characters 或 roster 里(这里只能查补丁内部)
    known = new_ids
    for r in patch.get("relations") or []:
        for side in ("from", "to"):
            v = r.get(side)
            if v and v not in known and not str(v).startswith("cross_"):
                # 可能是既有角色 id, 交给 store 的 references 校验
                pass
    return warns


def _call_with_retry(client, messages: list[dict[str, str]], *, json_schema=None, retries: int = 2, **kwargs: Any) -> Any:
    last: Exception | None = None
    for attempt in range(retries + 1):
        try:
            return client.chat(messages, json_schema=json_schema, **kwargs)
        except LLMError as e:
            last = e
            if attempt < retries:
                log.warn(f"LLM 调用失败(第 {attempt + 1} 次), 重试: {e}")
    raise last  # type: ignore[misc]


def run_extract(
    ws: Workspace,
    cfg: Config,
    group: str,
    *,
    force: bool = False,
    only_segment: int | None = None,
    segments_only: bool = False,
    consolidate_only: bool = False,
    id_prefix: str | None = None,
) -> dict[str, Any]:
    ws.ensure_dirs()
    extract_dir(ws).mkdir(parents=True, exist_ok=True)
    idx = load_index(ws, group)
    if not idx:
        raise FileNotFoundError(f"找不到段索引, 请先跑 segment --group {group}")

    segments: list[dict[str, Any]] = idx.get("segments", [])
    if only_segment is not None:
        segments = [s for s in segments if int(s.get("n", 0)) == only_segment]
    if not segments:
        raise ValueError(f"没有可提炼的段(团 {group})")

    provider = cfg.llm.provider_for(cfg.extract.model_route)
    client = make_llm_client(provider)
    canon_block = render_canon_block(ws, group, roster_scope=cfg.extract.roster_scope)
    log.info(
        f"提炼 [{group}] {len(segments)} 段 · 后端={provider.type}/{provider.model} · "
        f"并发={cfg.extract.concurrency} · canon 注入 {len(canon_block)} 字"
    )

    # ---------------- 阶段 1: 分段提炼 ----------------
    results: list[dict[str, Any]] = []
    if not consolidate_only:
        todo = []
        for seg in segments:
            out = segment_extract_path(ws, group, int(seg["n"]))
            if out.is_file() and not force and cfg.extract.skip_if_exists:
                log.info(f"段{seg['n']} 已有提炼, 跳过: {ws.rel(out)}")
                results.append({"n": seg["n"], "path": ws.rel(out), "skipped": True})
                continue
            todo.append((seg, out))

        def work(item: tuple[dict[str, Any], Path]) -> dict[str, Any]:
            seg, out = item
            text = _segment_text(ws, seg)
            if len(text) > cfg.extract.max_segment_chars:
                raise ValueError(
                    f"段{seg['n']} 文本 {len(text)} 字超过 extract.max_segment_chars="
                    f"{cfg.extract.max_segment_chars}; 请调小 segment.window_s 重新切段"
                )
            prompt = render_segment_prompt(cfg, ws, group, seg, text, canon_block)
            res = _call_with_retry(
                client, [{"role": "user", "content": prompt}], retries=cfg.extract.retry
            )
            if res.truncated:
                raise ValueError(
                    f"段{seg['n']} 输出被 max_tokens 截断(finish_reason=length, "
                    f"reasoning={res.reasoning_tokens} tok); 请调大该 provider 的 max_tokens"
                )
            body = res.text.strip()
            if not body or LEAK_JUNK.match(body):
                raise ValueError(f"段{seg['n']} 返回内容异常: {body[:80]!r}")
            out.write_text(body + "\n", encoding="utf-8")
            return {
                "n": seg["n"], "path": ws.rel(out), "skipped": False,
                "chars": len(body), "prompt_tokens": res.prompt_tokens,
                "completion_tokens": res.completion_tokens,
                "reasoning_tokens": res.reasoning_tokens,
                "elapsed_s": round(res.elapsed_s, 1),
                "tok_per_s": res.tok_per_s,
            }

        if cfg.extract.concurrency > 1 and len(todo) > 1:
            with ThreadPoolExecutor(max_workers=cfg.extract.concurrency) as pool:
                futures = {pool.submit(work, it): it for it in todo}
                for fut in as_completed(futures):
                    seg = futures[fut][0]
                    try:
                        r = fut.result()
                        results.append(r)
                        log.ok(
                            f"段{seg['n']} 提炼完成: {r['chars']} 字 "
                            f"({r['completion_tokens']} tok / {r['elapsed_s']}s / {r['tok_per_s']} tok/s)"
                        )
                    except Exception as e:  # noqa: BLE001
                        log.err(f"段{seg['n']} 提炼失败: {type(e).__name__}: {e}")
        else:
            for it in todo:
                seg = it[0]
                try:
                    r = work(it)
                    results.append(r)
                    log.ok(
                        f"段{seg['n']} 提炼完成: {r['chars']} 字 "
                        f"(输出 {r['completion_tokens']} tok 含思考 {r.get('reasoning_tokens', 0)} / "
                        f"{r['elapsed_s']}s / {r['tok_per_s']} tok/s)"
                    )
                except Exception as e:  # noqa: BLE001
                    log.err(f"段{seg['n']} 提炼失败: {type(e).__name__}: {e}")

    if segments_only:
        return {"group": group, "phase": "segments", "results": results}

    # ---------------- 阶段 2: 汇总成补丁 ----------------
    pairs: list[tuple[str, str]] = []
    for seg in segments:
        p = segment_extract_path(ws, group, int(seg["n"]))
        if p.is_file():
            pairs.append((f"段{seg['n']}（{seg.get('label', '')}）", p.read_text(encoding="utf-8")))
    if not pairs:
        raise ValueError("没有任何段提炼产物, 无法汇总")

    prefix = id_prefix or cfg.store.id_prefix_map.get(group) or "new"
    prompt = render_consolidate_prompt(cfg, group, prefix, pairs, canon_block)
    log.info(f"汇总 {len(pairs)} 段提炼 -> 补丁 (前缀 {prefix}_) ...")
    res = _call_with_retry(
        client,
        [{"role": "user", "content": prompt}],
        json_schema=patch_json_schema(),
        retries=cfg.extract.retry,
        max_tokens=cfg.extract.consolidation_max_output_tokens,
    )
    raw_path = extract_dir(ws) / f"{group}_汇总.md"
    raw_path.write_text(res.text + "\n", encoding="utf-8")
    if res.truncated:
        raise LLMError(
            f"汇总输出被截断(finish_reason=length, reasoning={res.reasoning_tokens} tok)。"
            f"请调大 extract.consolidation_max_output_tokens 或 llm.providers.*.max_tokens; "
            f"原始输出: {ws.rel(raw_path)}"
        )

    try:
        patch = parse_json_reply(res.text)
    except LLMError as e:
        raise LLMError(
            f"汇总输出不是合法 JSON: {e}\n原始输出已存: {ws.rel(raw_path)}"
        ) from e
    if not isinstance(patch, dict):
        raise LLMError(f"汇总输出不是 JSON 对象, 原始输出: {ws.rel(raw_path)}")

    patch.setdefault("group", group)
    patch.setdefault("id_prefix", prefix)
    lint_warnings = lint_patch(patch)
    for w in lint_warnings:
        log.warn(f"补丁体检: {w}")
    patch["_meta"] = {
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "generator": f"{provider.type}/{provider.model}",
        "source_segments": [s.get("file") for s in segments],
        "extract_hashes": {str(n): sha256_text(t) for n, t in pairs},
        "lint_warnings": lint_warnings,
    }
    patch_path = ws.patches / f"{group}_patch.json"
    patch_path.parent.mkdir(parents=True, exist_ok=True)
    patch_path.write_text(json.dumps(patch, ensure_ascii=False, indent=2), encoding="utf-8")
    log.ok(
        f"补丁已生成: {ws.rel(patch_path)} "
        f"(角色 {len(patch.get('characters') or [])} · 更新 {len(patch.get('character_updates') or [])} · "
        f"关系 {len(patch.get('relations') or [])} · 待确认 {len(patch.get('pending') or [])})"
    )

    state = {
        "group": group,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "segments": len(segments),
        "patch": ws.rel(patch_path),
        "summary_raw": ws.rel(raw_path),
        "usage": {
            "prompt_tokens": res.prompt_tokens,
            "completion_tokens": res.completion_tokens,
            "elapsed_s": round(res.elapsed_s, 1),
            "tok_per_s": res.tok_per_s,
        },
        "results": results,
    }
    sp = ws.state / f"extract_{''.join(ch if ch.isalnum() else '_' for ch in group)[:50]}.json"
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "group": group,
        "phase": "full",
        "results": results,
        "patch": ws.rel(patch_path),
        "summary_raw": ws.rel(raw_path),
        "usage": state["usage"],
        "counts": {
            "characters": len(patch.get("characters") or []),
            "character_updates": len(patch.get("character_updates") or []),
            "relations": len(patch.get("relations") or []),
            "pending": len(patch.get("pending") or []),
        },
    }
