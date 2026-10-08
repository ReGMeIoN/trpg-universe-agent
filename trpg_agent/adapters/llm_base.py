# -*- coding: utf-8 -*-
"""LLM 适配层基类与通用类型。

两种后端:
    openai  —— 任意 OpenAI 兼容端点(DeepSeek/Moonshot/OpenRouter/本地 vLLM…)
    ollama  —— 本地 Ollama(原生 /api/chat, 支持 format 传 JSON Schema)
对外接口一致: chat(messages, json_schema=None) -> ChatResult
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol


class LLMError(RuntimeError):
    pass


@dataclass
class ChatResult:
    text: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    elapsed_s: float = 0.0
    raw: dict[str, Any] = field(default_factory=dict)
    #: 输出被 max_tokens 截断(finish_reason == "length") —— 对这种结果不能静默接受
    truncated: bool = False
    #: 推理型模型的思考 token(计入 completion_tokens, 不占 content)
    reasoning_tokens: int = 0

    @property
    def tok_per_s(self) -> float:
        if not self.elapsed_s or not self.completion_tokens:
            return 0.0
        return round(self.completion_tokens / self.elapsed_s, 2)

    @property
    def answer_tokens(self) -> int:
        return max(0, self.completion_tokens - self.reasoning_tokens)


class LLMClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult: ...


@dataclass
class Timer:
    _t0: float = 0.0

    def __enter__(self) -> "Timer":
        self._t0 = time.time()
        return self

    def __exit__(self, *exc: object) -> None:
        self.elapsed = time.time() - self._t0

    @property
    def elapsed(self) -> float:
        return getattr(self, "_elapsed", 0.0)

    @elapsed.setter
    def elapsed(self, v: float) -> None:
        self._elapsed = v
