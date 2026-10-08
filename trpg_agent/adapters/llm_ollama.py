# -*- coding: utf-8 -*-
"""Ollama 原生 /api/chat 适配器(支持 format 传 JSON Schema, 结构化输出比兼容层稳)。"""
from __future__ import annotations

import json
import time
from typing import Any

import requests

from trpg_agent.adapters.llm_base import ChatResult, LLMError
from trpg_agent.config import LLMProviderCfg


class OllamaClient:
    def __init__(self, cfg: LLMProviderCfg):
        self.cfg = cfg
        self.base = cfg.base_url.rstrip("/")

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        json_schema: dict[str, Any] | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> ChatResult:
        payload: dict[str, Any] = {
            "model": self.cfg.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.cfg.temperature if temperature is None else temperature,
                "num_predict": self.cfg.max_tokens if max_tokens is None else max_tokens,
                "num_ctx": self.cfg.num_ctx,
            },
        }
        if json_schema is not None:
            payload["format"] = json_schema

        t0 = time.time()
        try:
            r = requests.post(f"{self.base}/api/chat", json=payload, timeout=self.cfg.timeout_s)
        except requests.RequestException as e:
            raise LLMError(f"Ollama 请求失败: {e}") from e
        if r.status_code >= 400:
            detail = ""
            try:
                detail = r.json().get("error", "")
            except (ValueError, AttributeError):
                detail = r.text[:300]
            raise LLMError(f"Ollama HTTP {r.status_code}: {detail}")
        data = r.json()
        elapsed = time.time() - t0
        msg = data.get("message") or {}
        return ChatResult(
            text=(msg.get("content") or "").strip(),
            model=data.get("model", self.cfg.model),
            prompt_tokens=int(data.get("prompt_eval_count") or 0),
            completion_tokens=int(data.get("eval_count") or 0),
            elapsed_s=elapsed,
            raw={"done_reason": data.get("done_reason")},
        )

    def probe(self) -> dict[str, Any]:
        """连通性 + 模型是否已就绪。"""
        try:
            r = requests.get(f"{self.base}/api/tags", timeout=10)
            r.raise_for_status()
            names = [m.get("name") for m in r.json().get("models", [])]
            return {"ok": True, "models": names, "has_model": self.cfg.model in names}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}


def parse_json_reply(text: str) -> Any:
    """容错解析模型返回的 JSON(可能带 ```json 围栏或前后解释文字)。"""
    s = text.strip()
    if s.startswith("```"):
        s = s.split("```")[1] if "```" in s[3:] else s[3:]
        if s.lstrip().lower().startswith("json"):
            s = s.lstrip()[4:]
    s = s.strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for opener, closer in (("{", "}"), ("[", "]")):
        i, j = s.find(opener), s.rfind(closer)
        if i >= 0 and j > i:
            try:
                return json.loads(s[i : j + 1])
            except json.JSONDecodeError:
                continue
    raise LLMError(f"无法从模型输出中解析 JSON: {text[:200]!r}")
