# -*- coding: utf-8 -*-
"""转写引擎适配层。

当前实现: faster_whisper(本地, 窗口化流式解码 + VAD 分批 + 时间戳平移)。
扩展方式: 实现 iter_events() 生成器并登记到 ASR_ENGINES。
"""
from __future__ import annotations

from typing import Any, Iterator

from trpg_agent.adapters import asr_faster_whisper
from trpg_agent.adapters.llm_base import ChatResult, LLMError
from trpg_agent.adapters.llm_ollama import OllamaClient
from trpg_agent.adapters.llm_openai import OpenAIClient
from trpg_agent.config import AsrCfg, LLMProviderCfg

ASR_ENGINES: dict[str, Any] = {
    "faster_whisper": asr_faster_whisper,
}


def get_asr_engine(name: str):
    if name not in ASR_ENGINES:
        raise KeyError(f"未知转写引擎 {name!r} (可用: {list(ASR_ENGINES)})")
    return ASR_ENGINES[name]


def probe_audio(engine: str, path) -> dict[str, Any]:
    return get_asr_engine(engine).probe_audio(path)


def iter_events(engine: str, path, cfg: AsrCfg, **kwargs) -> Iterator[dict[str, Any]]:
    return get_asr_engine(engine).iter_events(path, cfg, **kwargs)


def make_llm_client(cfg: LLMProviderCfg):
    """按 provider 类型造客户端; 对外接口一致(chat(messages, json_schema=...))。"""
    if cfg.type == "ollama":
        return OllamaClient(cfg)
    if cfg.type == "openai":
        return OpenAIClient(cfg)
    raise KeyError(f"未知 LLM provider 类型: {cfg.type!r}")


__all__ = [
    "ASR_ENGINES", "ChatResult", "LLMError", "OllamaClient", "OpenAIClient",
    "get_asr_engine", "iter_events", "make_llm_client", "probe_audio",
]
