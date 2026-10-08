# -*- coding: utf-8 -*-
"""Probe the configured extract LLM route (cloud) with the project's own client.

Usage:
    .venv\\Scripts\\python.exe tools\\_llm_probe.py [route]
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent.adapters import make_llm_client  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    route = sys.argv[1] if len(sys.argv) > 1 else "extract"
    cfg = load_config(ROOT / "config.yaml")
    prov = cfg.llm.provider_for(route)
    print(f"route={route} type={prov.type} model={prov.model} base={prov.base_url}")
    print(f"api_key_env={prov.api_key_env} key_set={bool(prov.api_key)}")
    client = make_llm_client(prov)
    print("probe:", client.probe())
    try:
        res = client.chat([{"role": "user", "content": "只回复两个字：收到"}], max_tokens=512)
    except Exception as e:  # noqa: BLE001
        print(f"chat FAILED: {type(e).__name__}: {e}")
        return 1
    print(f"chat OK: {res.text!r} prompt={res.prompt_tokens} completion={res.completion_tokens} "
          f"reasoning={res.reasoning_tokens} elapsed={res.elapsed_s:.1f}s truncated={res.truncated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
