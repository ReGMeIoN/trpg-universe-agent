# 切片 5 · 本地 Web 面板（v0.3）

> 2026-09-13 · 后端 FastAPI（薄壳）+ 前端 Vue 3 + Vite · 首批三块：**进度看板 / 待确认裁决 / 产物预览**

## 一、为什么这样分层

```
浏览器 (Vue 3 SPA, localhost:8765)
   │  /api/*  (JSON)
   ▼
FastAPI 薄壳  ← 不新增业务逻辑, 只做三件事: 读产物、启任务、存裁决
   │
   ├── jobs     (.trpg/jobs/*.json + logs/*.log)   → 进度与实时日志
   ├── review   (review.collect / apply_decisions) → 待确认闭环
   ├── canon    (naming.json)                      → 称呼归一
   ├── 数据/产出 (characters/relations/产物 HTML/MD) → 只读展示
   └── subprocess: python -m trpg_agent <step> ...  → 脱离式后台任务
```

**为什么不用 Streamlit**：面板要在页面上长期挂着看进度、点裁决，且要能复用已有的
job 记录与步骤 state；薄壳式 FastAPI 让"UI 崩了不影响数据管线"，也便于以后换前端框架。

## 二、三块功能

| 页面 | 做什么 |
|---|---|
| **概览** | 数据量卡片 / 九步状态 / 素材与团统计 / **数据卫生提醒**（如 `groups` 里的脏值）/ 团清单（角色·段·提炼·补丁·报告·待确认）+ 每行快捷按钮（提炼·入库副本·出图）+ 启动任务表单 |
| **任务与进度** | 任务列表（状态/百分比/pid/启动时间）每 2 秒刷新、选中任务看日志尾部（可调行数）、一键中断（断点已保存，可续跑） |
| **待确认裁决** | 选团 → 逐条待确认项 → `确认入库 / 驳回 / 改字段 / 并入称呼表 / 撤销` → **保存裁决** 或 **保存并应用**（写回补丁与称呼表，不写数据目录） |
| **产物预览** | 产出目录文件清单（可按名过滤）→ HTML 关系图直接内嵌 iframe、Markdown 渲染为可读文档 |

## 三、API

```
GET  /api/workspace            工作区信息(是否生产库/是否可写)
GET  /api/status               数据量 + 九步状态 + manifest + LLM 路由 + 数据卫生
GET  /api/groups               团清单(角色/段/提炼/补丁/报告/待确认)
GET  /api/jobs                 任务列表(含进度百分比)
GET  /api/jobs/{id}/log        日志(tail 可调)
POST /api/jobs/{id}/kill       中断(整进程树)
POST /api/jobs                 启动任务 {step, group?, force?, smoke?, apply?, allow_production?, all_groups?}
GET  /api/review/{group}       待确认项 + 已有裁决
POST /api/review/{group}       保存裁决
POST /api/review/{group}/apply 应用裁决(写回补丁+称呼表)
GET  /api/patches/{group}      补丁 JSON
GET  /api/reports/{group}      入库报告 / 待确认 / 批量汇总
GET  /api/segments/{group}     段索引
GET  /api/extract/{group}/{n}  某段提炼稿
GET  /api/products             产物清单
GET  /api/product?path=        取单个产物(路径必须落在工作区内)
```

FastAPI 自带交互式文档：`http://127.0.0.1:8765/docs`

## 四、安全设计

| 措施 | 说明 |
|---|---|
| **只绑 127.0.0.1** | 默认本机；绑到其他地址会告警（团数据只在自己机器上） |
| **路径校验** | 所有文件读取都 resolve 后校验落在工作区内，越界返回 400（已测 `../../../windows/win.ini`） |
| **只读模式** | `--read-only` 下所有写操作（启任务/存裁决/中断）直接 403 |
| **回填双确认** | 前端勾了「回填数据」且目标在生产库时必须同时勾「允许写生产库」；后端仍受 CLI 的生产库闸门约束 |
| **不下发密钥** | `/api/status` 只回 `has_key: true/false` 与变量名，绝不返回 key 值 |
| **不破坏人工资产** | 杰克档案/编年史等人工文档由 `visualize` 生成时走「建议文件」分支，不被面板覆盖 |

## 五、启动方式

```powershell
cd <仓库>
$env:TRPG_LLM_KEY = [Environment]::GetEnvironmentVariable('TRPG_LLM_KEY','User')

# 前台(关掉终端即停)
.\.venv\Scripts\python.exe -m trpg_agent web

# 脱离式常驻(与终端/DSH 会话无关, 推荐)
.\.venv\Scripts\python.exe -m trpg_agent web --background
#   停止: python -m trpg_agent jobs kill <web-job-id>
#   日志: python -m trpg_agent jobs logs <web-job-id> --tail 30

# 只读模式(给别人看/自己乱点时保命)
.\.venv\Scripts\python.exe -m trpg_agent web --read-only

# 前端开发模式(热更新): 先起后端, 再 npm run dev (5173, 已配 /api 代理)
cd web; npm run dev
```

改前端后要重新构建：`cd web; npm run build`（产物 `web/dist`，由后端托管）。

## 六、验证证据

```
tools\check_web_frontend.py  → 9/9   首页/JS/CSS/docs/openapi/api/404 兜底
tools\check_web_api.py       → 13/13 全部读端点 + 路径越界防护(400)
tools\check_web_write.py     → 8/8   启动任务→完成→日志→裁决保存→应用
                                       并在磁盘上核对: 补丁 confirmed False→True、
                                       称呼表并入新变体(老鸦 ← 老鸭二代)
tests\test_slice1.py         → 32/32
tests\test_e2e.py            → 20/20
```

## 七、这一轮修掉的坑

| 问题 | 说明 |
|---|---|
| **`--background --job-id` 全步骤乱传** | 这两个选项只有 transcribe/extract 有，其他步骤会直接报错。现在按步骤能力传，其余步骤的完成状态改由**步骤 state 文件**判定（`jobs.refresh_status` 增强） |
| 静态资源 404 | 后端原先只返回 index.html，没挂 `/assets/*`；已 `StaticFiles` 挂载 + 通配兜底（且不吃掉 `/docs` 与 `/api/*`） |
| 内联 Python 中文被 PS 当命令 | 工作区老坑；所有带中文的校验都写成 `tools/*.py` 再跑 |

## 八、下一步（v0.4 候选）

1. **打包**：PyInstaller 出 `trpg-agent.exe`，或 pywebview 包成真桌面窗口（前端代码不用改）。
2. **进度走 SSE**：现在是 2 秒轮询，够用；SSE 可省带宽并做到逐行实时。
3. **配置中心页面**：在面板里改 `config.yaml`（模型路由/并发/阈值）与填 key。
4. **多工作区切换**：目前一个面板一个工作区（`--ws`）；可加下拉切换。
5. **宇宙数据浏览器**：角色/关系/PL 的搜索与关系图交互（要新做检索层，不只是文件预览）。
