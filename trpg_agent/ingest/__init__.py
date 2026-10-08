# -*- coding: utf-8 -*-
"""素材接入: 扫描 -> 分类 -> 去重(hash) -> manifest.json。

幂等: 同一文件 sha256 不变则标 unchanged, 不重复处理。
"""
from __future__ import annotations

import fnmatch
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.state import sha256_file
from trpg_agent.workspace import Workspace

MANIFEST_VERSION = 1

# 转写稿行: [00012.34 -> 00018.90] 文本
TS_LINE_RE = re.compile(r"^\[\s*(\d+(?:\.\d+)?)\s*->\s*(\d+(?:\.\d+)?)\s*\]\s?(.*)$")
# QQ 纯文本行: [07-30 21:05] 名字: 内容
QQ_LINE_RE = re.compile(r"^\[\d{2}-\d{2}\s+\d{2}:\d{2}\]\s*")

TYPE_AUDIO = "audio"
TYPE_QQ_EXPORT = "qq_export"
TYPE_QQ_TEXT = "qq_text"
TYPE_TRANSCRIPT = "transcript"
TYPE_DOCX = "docx_card"
TYPE_DOC_LEGACY = "doc_legacy"   # .doc/.xls/.ppt (OLE 二进制, 需专门提取器)
TYPE_IMAGE = "image"
TYPE_RAW_TEXT = "raw_text"
TYPE_UNSUPPORTED = "unsupported"

SEGMENT_INPUT_TYPES = {TYPE_TRANSCRIPT, TYPE_QQ_TEXT, TYPE_RAW_TEXT}


def _matches_any(rel_posix: str, name: str, globs: list[str]) -> bool:
    for pat in globs:
        if fnmatch.fnmatch(rel_posix, pat) or fnmatch.fnmatch(name, pat):
            return True
        # 支持 "dir/**" 形式匹配目录下任意层级
        if pat.endswith("/**") and (rel_posix.startswith(pat[:-3] + "/")):
            return True
    return False


def _split_loose_name(stem: str) -> str:
    """从文件名推团名: 取第一个 '_' 前的片段; 去掉编号前缀与尾部括号/副本标记。"""
    head = stem.split("_")[0].strip()
    head = re.sub(r"^[0-9]{1,2}[\.\-、]?", "", head).strip()
    head = re.sub(r"\s*[(（\[【][^)）\]】]*[)）\]】]\s*$", "", head).strip()
    return head or stem


def guess_group(ws: Workspace, cfg: Config, path: Path) -> tuple[str, str]:
    """返回 (团名, 依据)。优先级: group_rules > 命中已知团名 > group_aliases > 目录名/文件名前缀。"""
    rel = path.relative_to(ws.material)
    rel_posix = rel.as_posix()
    stem = path.stem

    for rule in cfg.ingest.group_rules:
        pat = str(rule.get("glob") or rule.get("match") or "")
        grp = str(rule.get("group") or "")
        if pat and grp and (fnmatch.fnmatch(path.name, pat) or fnmatch.fnmatch(rel_posix, pat)):
            return grp, f"group_rules:{pat}"

    parts = rel.parts
    if len(parts) >= 2:
        raw, src = parts[0], f"dir:{parts[0]}"
    else:
        raw, src = _split_loose_name(stem), "filename-prefix"

    known = cfg.ingest.known_groups
    if raw in known:
        return raw, src
    probe = f"{raw} {stem}"
    hits = [g for g in known if g and g in probe]
    if hits:
        best = max(hits, key=len)
        return best, f"substring:{best}"
    if raw in cfg.ingest.group_aliases:
        return cfg.ingest.group_aliases[raw], f"alias:{raw}"
    return raw, src


def classify(path: Path, cfg: Config, text_head: str | None) -> str:
    ext = path.suffix.lower()
    if ext in cfg.ingest.audio_exts:
        return TYPE_AUDIO
    if ext in cfg.ingest.image_exts:
        return TYPE_IMAGE
    if ext in cfg.ingest.legacy_doc_exts:
        return TYPE_DOC_LEGACY
    if ext in cfg.ingest.doc_exts:
        return TYPE_DOCX
    if ext in cfg.ingest.json_exts:
        # 注意: 这里只有截断的头部, 不能 json.loads(必然失败), 只做特征嗅探
        return TYPE_QQ_EXPORT if _looks_like_qq_export(text_head) else TYPE_UNSUPPORTED
    if ext in cfg.ingest.text_exts:
        head = (text_head or "")
        lines = [ln for ln in head.splitlines() if ln.strip()][:40]
        if not lines:
            return TYPE_RAW_TEXT
        ts = sum(1 for ln in lines if TS_LINE_RE.match(ln.strip()))
        qq = sum(1 for ln in lines if QQ_LINE_RE.match(ln.strip()))
        if ts >= max(1, len(lines) // 2):
            return TYPE_TRANSCRIPT
        if qq >= max(1, len(lines) // 2):
            return TYPE_QQ_TEXT
        return TYPE_RAW_TEXT
    return TYPE_UNSUPPORTED


def _looks_like_qq_export(head: str | None) -> bool:
    """qq-chat-exporter 导出的特征: 顶层 messages 数组 + chatInfo。"""
    if not head:
        return False
    return '"messages"' in head and ('"type"' in head or '"sender"' in head or '"chatInfo"' in head)


def _read_head(path: Path, limit: int = 8192) -> str | None:
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read(limit)
    except OSError:
        return None


def scan(ws: Workspace, cfg: Config, only_group: str | None = None, rebuild: bool = False) -> dict[str, Any]:
    ws.ensure_dirs()
    manifest_path = ws.work / "manifest.json"
    old: dict[str, Any] = {}
    if manifest_path.is_file() and not rebuild:
        try:
            old = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            old = {}
    old_by_path = {e["path"]: e for e in old.get("files", [])}

    files: list[dict[str, Any]] = []
    skipped: list[tuple[str, str]] = []
    for path in sorted(ws.material.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(ws.root)
        rel_posix = rel.as_posix()
        rel_in_mat = path.relative_to(ws.material).as_posix()
        if _matches_any(rel_in_mat, path.name, cfg.ingest.exclude_globs):
            skipped.append((rel_posix, "excluded"))
            continue

        group, group_src = guess_group(ws, cfg, path)
        if only_group and group != only_group:
            skipped.append((rel_posix, f"group-filter({group})"))
            continue

        digest = sha256_file(path)
        prev = old_by_path.get(rel_posix)
        if prev is None:
            status = "new"
        elif prev.get("sha256") != digest:
            status = "changed"
        else:
            status = "unchanged"

        # 只有指纹变化时才需要重新嗅探内容类型
        if prev and status == "unchanged" and prev.get("type"):
            ftype = prev["type"]
        else:
            head = _read_head(path)
            ftype = classify(path, cfg, head)

        entry = {
            "path": rel_posix,
            "group": group,
            "group_source": group_src,
            "type": ftype,
            "size": path.stat().st_size,
            "sha256": digest,
            "mtime": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
            "status": status,
            "superseded": _matches_any(rel_in_mat, path.name, cfg.ingest.supersede_globs)
            if cfg.ingest.supersede_globs
            else False,
            "first_seen": (prev or {}).get("first_seen") or datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        files.append(entry)

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "generated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "workspace": str(ws.root),
        "counts": {
            "total": len(files),
            "new": sum(1 for f in files if f["status"] == "new"),
            "changed": sum(1 for f in files if f["status"] == "changed"),
            "unchanged": sum(1 for f in files if f["status"] == "unchanged"),
        },
        "by_type": {t: sum(1 for f in files if f["type"] == t) for t in sorted({f["type"] for f in files})},
        "groups": sorted({f["group"] for f in files}),
        "files": files,
        "skipped": [{"path": p, "reason": r} for p, r in skipped],
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def load_manifest(ws: Workspace) -> dict[str, Any] | None:
    p = ws.work / "manifest.json"
    if not p.is_file():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def group_files(manifest: dict[str, Any], group: str | None = None) -> list[dict[str, Any]]:
    files = manifest.get("files", [])
    if group:
        files = [f for f in files if f["group"] == group]
    return files


def render_summary(manifest: dict[str, Any], per_group: bool = True) -> None:
    c = manifest["counts"]
    log.info(
        f"素材 {c['total']} 个 (新增 {c['new']} / 变化 {c['changed']} / 未变 {c['unchanged']})"
        f" | 跳过 {len(manifest['skipped'])}"
    )
    log.info("类型分布: " + ", ".join(f"{k}={v}" for k, v in manifest["by_type"].items()))
    if not per_group:
        return
    superseded = set(manifest.get("superseded_groups") or [])
    buckets: dict[str, dict[str, int]] = {}
    for f in manifest["files"]:
        buckets.setdefault(f["group"], {})[f["type"]] = buckets.setdefault(f["group"], {}).get(f["type"], 0) + 1
    if not buckets:
        log.info("团: (无)")
        return
    log.info(f"团分布 ({len(buckets)} 个, 按文件数降序):")
    for g, types in sorted(buckets.items(), key=lambda kv: -sum(kv[1].values())):
        detail = " ".join(f"{t}={n}" for t, n in sorted(types.items(), key=lambda kv: -kv[1]))
        flag = "  [已停用:其导出已拆分为多团]" if g in superseded else ""
        log.info(f"  {g:<28} {sum(types.values()):>4} 个  {detail}{flag}")
