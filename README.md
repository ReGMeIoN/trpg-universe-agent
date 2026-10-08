# TRPG-Universe Agent 🐳

> **文档入口**：仓库结构与工作流主线见 `docs/工作流程总结.md`；各环节踩坑与实现细节见 `docs/` 下的交付说明。

把每一场跑团，酿成一册可检索的宇宙档案。

固定工作流（状态机，每步可单独重跑、产物即状态）：

```
ingest → transcribe → segment → extract → review → store → visualize → export → housekeep
```

## 现状（v0.1）

| 步骤 | 状态 |
|---|---|
| `ingest` 素材接入（扫描/分类/hash 去重/manifest/QQ 导出转文本/按日期拆团） | ✅ |
| `transcribe` 转写（窗口化流式解码 + VAD 分批 + 逐行落盘 + 字节级断点 + 质量自检 + 后台任务） | ✅ |
| `segment` 切段（等时间窗 / 按日期 / 按行切） | ✅ |
| `extract` 提炼（canon 注入 + 分段扇出 + 汇总成补丁 JSON） | ✅ |
| `review` 待确认闭环（收集 → 裁决文件 → 写回补丁/称呼表） | ✅ |
| `store` 入库（补丁 → schema 校验 → 工作副本 → 报告 → 备份回填） | ✅ |
| `canon` 铁律/称呼表/名单固化与注入 | ✅ |
| `visualize` 可视化（团关系图 SVG / PL 画像墙 / 杰克档案 / 宇宙总览） | ✅ |
| `export` KB 包导出 | ✅ |
| `housekeep` 收尾清单 | ✅ |
| `run` 一键跑固定工作流 | ✅ |
| `web` 本地 Web 面板（进度看板 / 待确认裁决 / 产物预览） | ✅ 切片 5 |
| `llm check` LLM 后端探活 | ✅ |
| `jobs` / `status` | ✅ |

> 交付说明：`docs/切片1-交付说明.md`（ingest/segment/store）、`docs/切片3-4-交付说明.md`（canon/extract/review/可视化/导出）、
> `docs/切片5-Web面板.md`（Web 面板）、`docs/Ollama-CUDA-修复指南.md`（本机 LLM 后端修复）。

## Web 面板（v0.3）

```powershell
$py = ".\.venv\Scripts\python.exe"
$env:TRPG_LLM_KEY = [Environment]::GetEnvironmentVariable('TRPG_LLM_KEY','User')
& $py -m trpg_agent web --background     # http://127.0.0.1:8765
```

三块功能：**进度看板**（任务/百分比/实时日志/中断）、**待确认裁决**（逐条确认入库/驳回/改字段/并入称呼表，
写回补丁与称呼表）、**产物预览**（关系图内嵌、报告 Markdown 渲染）。
默认只绑 127.0.0.1、路径越界拦截、生产库回填需双确认、绝不下发密钥。详见 `docs/切片5-Web面板.md`。


### 三层数据流（为什么这么设计）

```
素材 ──ingest──> manifest + 归一纯文本
      ──transcribe──> 素材/<团>_转写.txt        (逐行追加, 字节级断点)
      ──segment──> .trpg/segments/<团>_段N_*.txt (等时间窗, 索引落盘)
      ──extract──> .trpg/extracts/<团>_段N_提炼.md   (canon 注入, 分段扇出)
                 + .trpg/patches/<团>_patch.json     (汇总: 唯一入库契约)
      ──review──> .trpg/review/<团>_待确认.json      (人裁决, 写回补丁+称呼表)
      ──store──> .trpg/staging/*.json -> 数据/*.json (备份 + 复验)
```

**canon 是跨段/跨团一致性的命门**：每次提炼都注入
`canon_rules.md`(铁律 1-12) + `naming.json`(称呼归一表) + `roster.json`(已入库 137 角色的 id/别名，
本团相关与跨团常驻给详情、其余只给名字去重)。示例团 753 字 / 生产库按需裁剪。

### 转写为何是"窗口化"的

`faster-whisper` 会对传入音频**一次性做 STFT**：7.3 小时音频在 16GB 机器上要 ~7.6GiB 数组，直接 OOM
（这是 `transcribe_s05.py` 的教训）。本工具改为：

```
顺序流式解码（PyAV） → 每 30 分钟一个窗口（约 115MB 内存）
  → 窗口内 VAD 找语音块 → 贪心合并成批（语音 ≤13min，跨度 ≤30min）
  → 逐批 transcribe → 时间戳平移回全文件时间轴
```

- 输出**逐行追加并 flush**；断点记 `音频指纹 + 参数指纹 + 窗口/批 + 输出字节偏移`。
  参数或算法版本变了会自动从头（不会拿旧断点续错）；**续跑先截断到批起点**，
  所以半途崩溃不会产生重复行。
- **质量自检**：过滤 `initial_prompt` 泄漏（音乐/噪声段每 30 秒复读提示词）与复读幻觉，
  并在结尾报告保留率与抽样。

## 快速开始

```powershell
$py = ".\.venv\Scripts\python.exe"

# 0) canon 固化（铁律 + 称呼表 + 已入库名单）
& $py -m trpg_agent canon build
& $py -m trpg_agent canon show --group 魔法少女五      # 预览注入块

# 1) 示例团端到端（脱敏虚构团「星海列车」）
& $py -m trpg_agent ingest  --ws examples/mini-group
& $py -m trpg_agent segment --ws examples/mini-group
& $py -m trpg_agent store   --ws examples/mini-group --patch "examples/mini-group/.trpg/patches/星海列车_patch.json"

# 2) 生产库（非破坏性: 只写 .trpg/ 与转写稿）
& $py -m trpg_agent ingest
& $py -m trpg_agent segment

# 3) 转写：先冒烟，再后台全量（可断点续跑）
& $py -m trpg_agent transcribe --group 圣剑英雄谭 --smoke 120
& $py -m trpg_agent transcribe --group 圣剑英雄谭 --background
& $py -m trpg_agent jobs list
& $py -m trpg_agent jobs logs <job-id> --tail 30
& $py -m trpg_agent jobs kill <job-id>

# 4) 提炼 -> 裁决 -> 入库
& $py -m trpg_agent extract --group 魔法少女五 --base-url http://127.0.0.1:11438
& $py -m trpg_agent review  --group 魔法少女五          # 生成裁决文件
& $py -m trpg_agent review  --group 魔法少女五 --apply  # 固化裁决
& $py -m trpg_agent store   --group 魔法少女五          # 先看工作副本
& $py -m trpg_agent store   --group 魔法少女五 --apply --allow-production
```

> LLM 后端：本机 Ollama 的 CUDA 路径对**对话模型**会崩，修复方式见
> `docs/Ollama-CUDA-修复指南.md`（结论：serve 进程带 `OLLAMA_FLASH_ATTENTION=0`）。
> 上面的 `--base-url` 就是为"另起一个专用实例"准备的。

## 自测

```powershell
# 回归自测(32 项断言: 幂等/切段/归一/未确认降级/备份/生产库闸门/误删防护)
.\.venv\Scripts\python.exe tests\test_slice1.py

# 示例被 apply 过后, 重置回初始态再跑
.\.venv\Scripts\python.exe tools\reset_example.py
```

## 目录约定

一个 **Workspace** = 一个宇宙库：

```
<root>/素材/     原始素材（输入）
<root>/数据/     characters | relations | players | pl_profiles .json（契约资产）
<root>/产出/     可视化 / KB 包（人读产物）
<root>/.trpg/    运行态：state/ jobs/ logs/ patches/ staging/ reports/ canon/ normalized/
```

切库只改 `config.yaml` 的 `workspace.root`，或用 `--ws` 临时覆盖。

## 关键设计

- **补丁驱动入库**：不再为每个团手写 `add_<团>.py`。`extract` 产出补丁 JSON
  （`.trpg/patches/<团>_patch.json`），`store` 负责校验 → 归一 → 去重 → 工作副本 →
  报告 → 备份回填。契约见 `trpg_agent/store/merger.py` 顶部注释。
- **只写明确项**：补丁里 `confirmed: false` 的条目一律降级进「待确认」，不写盘。
- **写前必备份**：`<name>.bak_store_<时间戳>`，默认保留 10 份。
- **生产库闸门**：`store --apply` 对生产库默认拒绝，需 `--allow-production` 或
  `config.workspace.allow_production_write: true`。
- **schema 策略**：必填最小集 + 可选字段宽松放行（未知字段原样保留），
  不会把既有 `in_graph` / `played_by_alt` / `待确认` 等字段判非法。

## 本机沙箱注意事项（.boot）

> 本节是**作者本机**的沙箱 workaround，`.boot/` 未随仓库发布，其他人可跳过。

DSH 文件沙箱下 `os.mkdir(path, 0o700)` 建出的目录后续**写入与删除都会被拒**（`PermissionError`），
而 `tempfile.mkdtemp()` 固定用 0o700，导致 `ensurepip` / `pip` 全部失败。
`.boot/sitecustomize.py` 通过 `PYTHONPATH` 注入，把临时目录改为 0o777。仅装依赖时需要：

```powershell
New-Item -ItemType Directory -Force -Path .tmp | Out-Null
$env:TEMP = (Resolve-Path .tmp).Path; $env:TMP = $env:TEMP
$env:PYTHONPATH = (Resolve-Path .boot).Path
.\.venv\Scripts\python.exe -m pip install --no-cache-dir -r requirements.txt
```

> 副作用提醒：踩坑过程中用 0o700 建出来的空目录（`.tmp` 下若干）在本机**删不掉**（连 `rd /s /q`
> 都是 Access denied）。它们为空且被 `.gitignore` 忽略，不影响功能。新的临时目录一律用 0o777。

## 许可 / License

**代码与文档**：[MIT](LICENSE) © 2026 ReGMeIoN

⚠️ 仓库**不含**跑团录音、聊天导出、玩家角色卡正文与配图、NovelAI 生成图 ——
这些内容的版权归各玩家与画师所有，**不在本仓库授权范围内**。
详见 [NOTICE](NOTICE)。
