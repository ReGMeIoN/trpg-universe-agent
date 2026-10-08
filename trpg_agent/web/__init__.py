# -*- coding: utf-8 -*-
"""本地 Web 面板: `trpg-agent web`。

用法:
    trpg-agent web                     # http://127.0.0.1:8765
    trpg-agent web --port 9000
    trpg-agent web --read-only         # 禁用一切写操作(只看不动)
    trpg-agent web --reload            # 开发时热重载后端

前端(web/)构建产物由本服务托管; 未构建时首页会给出提示。
开发模式请单独跑 `npm run dev`(Vite 5173, 已配代理)。
"""
from __future__ import annotations

from trpg_agent import log
from trpg_agent.config import Config
from trpg_agent.web.app import DIST_DIR, create_app
from trpg_agent.workspace import Workspace


def serve(cfg: Config, ws: Workspace, host: str = "127.0.0.1", port: int = 8765,
          read_only: bool = False, reload: bool = False) -> None:
    import uvicorn

    app = create_app(cfg, ws, allow_write=not read_only)
    if host not in ("127.0.0.1", "localhost", "::1"):
        log.warn(f"绑定到 {host} 会让同网段其他机器访问到你的团数据; 默认只绑 127.0.0.1")
    log.step(f"web · http://{host}:{port}")
    log.info(f"工作区: {ws.root}")
    log.info(f"前端产物: {'已构建 ' + str(DIST_DIR) if (DIST_DIR / 'index.html').is_file() else '未构建(仅 API 可用, 见 /docs)'}")
    if read_only:
        log.warn("只读模式: 启动任务/保存裁决/中断任务 均被禁用")
    uvicorn.run(app, host=host, port=port, log_level="warning", reload=reload)
