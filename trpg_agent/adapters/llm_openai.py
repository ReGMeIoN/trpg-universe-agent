# -*- coding: utf-8 -*-
"""OpenAI 兼容端点适配器(DeepSeek / Moonshot / OpenAI / OpenRouter / 本地 vLLM…)。

密钥只从环境变量读(cfg.api_key_env), 不落配置文件。
结构化输出用 response_format=json_schema; 不支持的端点会自动降级为提示词约束 + 容错解析。
"""
from __future__ import annotations

import time
from typing import Any

import requests

from trpg_agent.adapters.llm_base import ChatResult, LLMError
from trpg_agent.config import LLMProviderCfg


class OpenAIClient:
    def __init__(self, cfg: LLMProviderCfg, *, strict_json: bool = True):
        self.cfg = cfg
        self.base = cfg.base_url.rstrip("/")
        self.strict_json = strict_json
        self.json_mode = cfg.json_mode
        self._json_supported = self.json_mode != "none"

    def _headers(self) -> dict[str, str]:
        h = {"Content-Type": "application/json"}
        key = self.cfg.api_key
        if key:
            h["Authorization"] = f"Bearer {key}"
        return h

    def _response_format(self, json_schema: dict[str, Any] | None) -> dict[str, Any] | None:
        if not json_schema or not self._json_supported:
            return None
        if self.json_mode == "json_object":
            return {"type": "json_object"}
        return {
            "type": "json_schema",
            "json_schema": {"name": "result", "schema": json_schema, "strict": False},
        }

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
            "temperature": self.cfg.temperature if temperature is None else temperature,
            "max_tokens": self.cfg.max_tokens if max_tokens is None else max_tokens,
        }
        rf = self._response_format(json_schema)
        if rf is not None:
            payload["response_format"] = rf

        t0 = time.time()
        try:
            r = requests.post(
                f"{self.base}/chat/completions", json=payload, headers=self._headers(),
                timeout=self.cfg.timeout_s,
            )
        except requests.RequestException as e:
            raise LLMError(f"LLM 请求失败: {e}") from e
        if r.status_code >= 400 and "response_format" in payload:
            # 端点不支持所选结构化输出模式 -> 降级重试一次(实测 DeepSeek 不支持 json_schema)
            self._json_supported = False
            payload.pop("response_format", None)
            r = requests.post(
                f"{self.base}/chat/completions", json=payload, headers=self._headers(),
                timeout=self.cfg.timeout_s,
            )
        if r.status_code >= 400:
            raise LLMError(f"LLM HTTP {r.status_code}: {r.text[:300]}")
        data = r.json()
        elapsed = time.time() - t0
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        usage = data.get("usage") or {}
        details = usage.get("completion_tokens_details") or {}
        finish = choice.get("finish_reason")
        content = (msg.get("content") or "").strip()
        truncated = finish == "length"
        if not content and truncated:
            raise LLMError(
                "模型输出被 max_tokens 截断且 content 为空"
                f"(finish_reason=length, reasoning_tokens={details.get('reasoning_tokens')}); "
                "推理型模型请调大 max_tokens(见 llm.providers.<name>.max_tokens)"
            )
        return ChatResult(
            text=content,
            model=data.get("model", self.cfg.model),
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            elapsed_s=elapsed,
            raw={"finish_reason": finish},
            truncated=truncated,
            reasoning_tokens=int(details.get("reasoning_tokens") or 0),
        )

    def probe(self) -> dict[str, Any]:
        if self.cfg.api_key_env and not self.cfg.api_key:
            return {"ok": False, "error": f"环境变量 {self.cfg.api_key_env} 未设置"}
        try:
            r = requests.get(f"{self.base}/models", headers=self._headers(), timeout=15)
            return {"ok": r.status_code < 400, "status": r.status_code}
        except requests.RequestException as e:
            return {"ok": False, "error": str(e)}
