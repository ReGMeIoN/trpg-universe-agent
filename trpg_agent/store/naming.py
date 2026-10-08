# -*- coding: utf-8 -*-
"""PL 称呼规范加载与归一 (铁律 10/11)。

来源: <work>/canon/naming.json
格式(两种都支持):
    {"canonical": [{"name": "菌羊", "aliases": ["军阳", "君羊", "俊阳"]}]}
    {"菌羊": ["军阳", "君羊"]}
归一结果会记录成映射表, 供入库报告审计(重大合并必须可审)。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class Naming:
    alias_to_canonical: dict[str, str] = field(default_factory=dict)
    canonical_names: set[str] = field(default_factory=set)

    @classmethod
    def empty(cls) -> "Naming":
        return cls()

    @classmethod
    def from_dict(cls, doc: Any) -> "Naming":
        n = cls()
        if not isinstance(doc, dict):
            return n
        entries = doc.get("canonical")
        if isinstance(entries, list):
            for e in entries:
                if not isinstance(e, dict):
                    continue
                name = str(e.get("name") or "").strip()
                if not name:
                    continue
                n.canonical_names.add(name)
                n.alias_to_canonical[name] = name
                for a in e.get("aliases") or []:
                    a = str(a).strip()
                    if a:
                        n.alias_to_canonical[a] = name
        else:
            for k, v in doc.items():
                if k.startswith("_"):
                    continue
                name = str(k).strip()
                n.canonical_names.add(name)
                n.alias_to_canonical[name] = name
                if isinstance(v, list):
                    for a in v:
                        a = str(a).strip()
                        if a:
                            n.alias_to_canonical[a] = name
        return n

    def normalize(self, value: str | None) -> tuple[str | None, bool]:
        """返回 (规范名, 是否发生归一)。未登记的保持原样。"""
        if value is None:
            return None, False
        s = str(value).strip()
        if not s:
            return value, False
        if s in self.alias_to_canonical:
            canon = self.alias_to_canonical[s]
            return canon, canon != s
        # 子串匹配: "菌羊（凤樱姬玩家）" 命中 "菌羊" / "凤樱姬玩家"
        for alias, canon in self.alias_to_canonical.items():
            if len(alias) >= 2 and alias in s:
                return canon, canon != s
        return s, False


def load_naming(rel_path: Path) -> Naming:
    if not rel_path.is_file():
        return Naming.empty()
    try:
        return Naming.from_dict(json.loads(rel_path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError):
        return Naming.empty()
