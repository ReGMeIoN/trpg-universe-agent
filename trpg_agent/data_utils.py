# -*- coding: utf-8 -*-
"""数据读取的小工具与卫生守卫。

`groups` 字段按铁律只应放**团名(群名)**。实盘数据里存在把标签写进 groups 的情况
(如 `groups: ["恋爱与命运的不思议冒险？！", "跨团"]`), 若不守卫, 会凭空多出一个叫
「跨团」的团, 污染关系图/KB 包/统计。
"""
from __future__ import annotations

from typing import Any, Iterable

#: 这些词是标签/状态, 不是团名
RESERVED_GROUP_VALUES = {"跨团", "跨团常驻", "跨团主持人", "待确认", "KP", "PC", "NPC", ""}


def is_real_group(value: Any) -> bool:
    return bool(value) and str(value).strip() not in RESERVED_GROUP_VALUES


def char_groups(char: dict[str, Any]) -> list[str]:
    """返回该角色真正的团名列表(滤掉标签类脏值)。"""
    return [str(g) for g in (char.get("groups") or []) if is_real_group(g)]


def collect_groups(chars: Iterable[dict[str, Any]]) -> list[str]:
    groups: set[str] = set()
    for c in chars:
        groups.update(char_groups(c))
    return sorted(groups)


def find_dirty_group_values(chars: Iterable[dict[str, Any]]) -> dict[str, list[str]]:
    """找出被写进 groups 的标签类脏值 -> {脏值: [角色id...]}"""
    dirty: dict[str, list[str]] = {}
    for c in chars:
        for g in c.get("groups") or []:
            if not is_real_group(g):
                dirty.setdefault(str(g), []).append(str(c.get("id")))
    return dirty
