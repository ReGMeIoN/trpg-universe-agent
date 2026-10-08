# -*- coding: utf-8 -*-
"""转写质量自检: 提示词泄漏 / 复读幻觉 / 空段 / 抽样。

教训(2026-09 实盘): 带 initial_prompt 时, whisper 会在音乐/噪声段每 30 秒把提示词
原样吐出来(该文件前 13 分钟泄漏 27 行/13.5%)。这类行是纯幻觉, 必须过滤, 但必须
计数并报告 —— 不能静默丢。
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Any

_PUNCT = re.compile(r"[\s，。！？、；：,.!?;:~～…—\-（）()【】\[\]「」『』\"'“”‘’]+")


def normalize(text: str) -> str:
    return _PUNCT.sub("", text or "")


@dataclass
class QualityFilter:
    initial_prompt: str = ""
    filter_leak: bool = True
    filter_repeats: bool = True
    similarity_threshold: float = 0.8
    # 统计
    leaks: list[tuple[float, str]] = field(default_factory=list)
    repeats: list[tuple[float, str]] = field(default_factory=list)
    kept: int = 0
    heads: list[str] = field(default_factory=list)
    _last: str = ""

    def _is_leak(self, text: str) -> bool:
        if not self.filter_leak or not self.initial_prompt:
            return False
        n_text = normalize(text)
        n_prompt = normalize(self.initial_prompt)
        if not n_text or len(n_text) < 4:
            return False
        if n_text in n_prompt:
            return True
        # 提示词被切碎后逐句吐出("主持人与玩家的角色扮演发言。")
        best = 0.0
        for piece in re.split(r"[，。！？；,;.!?]", self.initial_prompt):
            p = normalize(piece)
            if len(p) >= 5 and (p in n_text or n_text in p):
                return True
            if len(p) >= 5:
                best = max(best, SequenceMatcher(None, n_text, p).ratio())
        return best >= self.similarity_threshold

    def accept(self, start: float, text: str) -> bool:
        """返回 True 表示该段应写入。"""
        if self._is_leak(text):
            self.leaks.append((start, text))
            return False
        if self.filter_repeats and text and text == self._last:
            self.repeats.append((start, text))
            return False
        self._last = text
        self.kept += 1
        if len(self.heads) < 5:
            self.heads.append(f"[{start:07.2f}] {text}")
        return True

    @property
    def dropped(self) -> int:
        return len(self.leaks) + len(self.repeats)

    def summary(self) -> dict[str, Any]:
        total = self.kept + self.dropped
        return {
            "kept": self.kept,
            "dropped": self.dropped,
            "prompt_leak": len(self.leaks),
            "repeat": len(self.repeats),
            "kept_ratio": round(self.kept / total, 4) if total else 0.0,
            "first_kept": self.heads,
            "leak_samples": [t for _, t in self.leaks[:3]],
        }

    def render(self) -> list[str]:
        s = self.summary()
        lines = [
            f"质量自检: 保留 {s['kept']} 段 / 丢弃 {s['dropped']} 段 "
            f"(提示词泄漏 {s['prompt_leak']} · 复读 {s['repeat']})",
        ]
        if s["kept"]:
            lines.append(f"  保留率 {s['kept_ratio']*100:.1f}%")
        if s["prompt_leak"]:
            lines.append(f"  ⚠ 检测到 initial_prompt 泄漏, 例: {s['leak_samples'][:2]}")
            lines.append("  (症状: 音乐/噪声段每 30 秒重复提示词; 可设 asr.initial_prompt 为空从源头消除)")
        for h in s["first_kept"]:
            lines.append(f"  抽样: {h}")
        return lines
