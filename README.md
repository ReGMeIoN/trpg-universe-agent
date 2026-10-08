# TRPG-Universe Agent 🐳

> 把一场场跑团录音 / 聊天导出，酿成一册**可检索、可浏览、可发布**的人物关系档案。
>
> **中文** · [English](README.en.md)

---

## 这是什么

一个**本地优先**的跑团资料整理工具链。输入是几小时到几十小时的录音和聊天记录，
输出是结构化的角色 / 关系数据库，以及能直接给人看的关系网站、编年史和绘本。

三件事它做得比较认真：

1. **长音频转写**——6 小时以上的录音在 16 GB 内存的机器上也能跑完，不怕中断。
2. **关系数据的一致性**——LLM 提炼容易"同一个人新建三次"，靠 canon 注入 + 补丁契约压住。
3. **数据安全**——生产库默认拒写、写前必备份、未确认的内容一律不落盘。

> 适合：KP / GM / 跑团团长、想给自己的团做档案站的人、想研究 LLM 长文本结构化的人。

---

## 特性

| 能力 | 说明 |
|---|---|
| 九步主链 | `ingest → transcribe → segment → extract → review → store → visualize → export → housekeep`，每步可单独重跑，产物即状态 |
| 窗口化转写 | 30 分钟一个窗口流式解码，避免长音频整段 STFT 的 OOM；**字节级断点续跑** |
| 质量自检 | 过滤 `initial_prompt` 泄漏与复读幻觉，报告保留率与抽样 |
| 补丁驱动入库 | LLM 产出补丁 JSON，`store` 负责校验 → 归一 → 去重 → 工作副本 → 报告 → 备份回填 |
| 待确认闭环 | `confirmed:false` 一律降级进「待确认」，人工裁决后写回补丁与称呼表 |
| canon 注入 | 铁律 + 称呼归一表 + 已入库名单打包进每次提炼，压制重复节点 |
| 可视化 | 团关系图（SVG）、PL 画像墙、宇宙总览、单人关系网、剧情编年史 |
| 本地 Web 面板 | Vue3 进度看板 + 待确认裁决 + 产物预览 |
| 自托管编辑站 | FastAPI 薄壳 + 版本历史 + 共享口令 + 限流，可部署到自己的服务器 |
| 回归测试 | 96 项断言：幂等 / 断点 / 生产库闸门 / pid 复用保护 / 多录音不覆盖 |

---

## 架构

### 九步主链

```
① ingest  → ② transcribe → ③ segment → ④ extract → ⑤ review
                                          ↓
        ⑨ housekeep ← ⑧ export ← ⑦ visualize ← ⑥ store (chronicle 在旁边)
```

| 步 | 命令 | 产出 | 要点 |
|---|---|---|---|
| ① ingest | `python -m trpg_agent ingest` | `manifest.json` | 素材丢进 `<工作区>/素材/<团名>/` |
| ② transcribe | `python -m trpg_agent transcribe --group "X"` | `素材/<团>_转写.txt` | **最耗时**；断点续跑 = 同配置重跑 |
| ③ segment | `python -m trpg_agent segment --group "X"` | `.trpg/segments/<团>_段N.txt` | 一场 = 一段 |
| ④ extract | `python tools/extract_all.py` | `.trpg/patches/<团>_patch.json` | LLM 只抽**角色骨架**；关系另补 |
| ⑤ review | `python -m trpg_agent review --group "X"` | `产出/<团>_待确认.json` | 人工裁决 |
| ⑥ store | `python -m trpg_agent store --apply --allow-production` | 回填生产库 | 影子库预演 → 生产库；**只能加不能删** |
| ⑦ visualize | `python -m trpg_agent visualize --group "X"` | 关系图 HTML + 关系网 md | 立绘登记后需重出 |
| ⑧ export | `python -m trpg_agent export` | `产出/astrbot知识库导入/` | RAG 友好的 KB 包 |
| ⑨ housekeep | `python -m trpg_agent housekeep` | `产出/收尾清单.md` | 数据量 / 状态 / 待确认汇总 |

### 三层，别混

| 层 | 产物 | 读者 | 纪律 |
|---|---|---|---|
| **数据层** | `<工作区>/数据/characters.json` `relations.json` | 工具与查证 | 写前备份 · `confirmed:false` 不落盘 · 生产库闸门 |
| **文本层** | `<工作区>/产出/<团>_剧情编年史.md` | 内部查证 | 带时间戳与存疑标记，可以脏 |
| **成品层** | `<工作区>/产出/` 站点与图 | 给人看 | **必须清洗**：删时间戳、元说明、编者注 |

> ⚠️ 最常见的错误：把编年史直接端给读者。**编年史是证据，成品是作品。**

---

## 安装

需要 **Python ≥ 3.11**。

```bash
git clone https://github.com/ReGMeIoN/trpg-universe-agent.git
cd trpg-universe-agent

python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

只想跑通示例、不做转写的话，`faster-whisper` 可以不装：

```bash
pip install typer pydantic PyYAML rich jsonschema requests python-docx
```

---

## 快速开始

仓库自带一个**完全虚构的脱敏示例团** `examples/mini-group`（「星海列车」），
**不依赖音频、不依赖 LLM**，可以直接端到端跑通：

```bash
# 0) canon 固化（铁律 + 称呼表 + 已入库名单）
python -m trpg_agent canon build
python -m trpg_agent canon show --group 星海列车

# 1) 示例团全链路
python -m trpg_agent ingest  --ws examples/mini-group
python -m trpg_agent segment --ws examples/mini-group
python -m trpg_agent store   --ws examples/mini-group \
  --patch "examples/mini-group/.trpg/patches/星海列车_patch.json"
python -m trpg_agent visualize --ws examples/mini-group --group 星海列车
python -m trpg_agent export    --ws examples/mini-group

# 跑过了想重置
python tools/reset_example.py
```

跑自己的团：

```bash
# 1) 素材就位
mkdir -p workspace/素材/我的团
cp 我的团-第1场.m4a workspace/素材/我的团/

# 2) 转写（先冒烟 120 秒，再后台全量）
python -m trpg_agent transcribe --group 我的团 --smoke 120
python -m trpg_agent transcribe --group 我的团 --background
python -m trpg_agent jobs list
python -m trpg_agent jobs logs <job-id> --tail 30

# 3) 切段 → 提炼 → 裁决 → 入库
python -m trpg_agent segment --group 我的团
python -m trpg_agent extract --group 我的团 --base-url http://127.0.0.1:11434
python -m trpg_agent review  --group 我的团            # 生成裁决文件
python -m trpg_agent review  --group 我的团 --apply    # 固化裁决
python -m trpg_agent store   --group 我的团            # 先看工作副本
python -m trpg_agent store   --group 我的团 --apply --allow-production

# 4) 出成品
python -m trpg_agent visualize --group 我的团
python -m trpg_agent export
python -m trpg_agent housekeep
```

### 本地 Web 面板

```bash
# 密钥只从环境变量读，不写进配置
export TRPG_LLM_KEY=sk-xxxx        # Windows: $env:TRPG_LLM_KEY = "sk-xxxx"
python -m trpg_agent web --background     # http://127.0.0.1:8765
```

三块功能：**进度看板**（任务 / 百分比 / 实时日志 / 中断）、**待确认裁决**（逐条确认入库 / 驳回 / 改字段）、
**产物预览**（关系图内嵌、报告 Markdown 渲染）。默认只绑 `127.0.0.1`。

---

## 配置

复制示例配置后按需修改：

```bash
cp config.example.yaml config.yaml
```

- **切库只改一行**：`workspace.root`
- **密钥只从环境变量读**（`api_key_env`），不写进配置文件
- 生产库闸门：`workspace.allow_production_write`，默认 `false`

### `tools/` 脚本的环境变量

`tools/` 下的脚本**不含任何绝对路径**，通过环境变量定位外部目录：

| 变量 | 用途 | 默认 |
|---|---|---|
| `TRPG_WS` | 工作区根目录 | `./workspace` |
| `TRPG_NAI` | NovelAI 出图归档目录 | `./novelai` |
| `TRPG_DATA` | 其它外部数据根 | 视脚本而定 |
| `TRPG_USER_HOME` | 用户目录（个别脚本用） | 空 |
| `TRPG_LIVE_BASE` | 线上站点地址（联调脚本用） | `http://127.0.0.1:8080/` |
| `TRPG_LLM_KEY` | LLM API 密钥 | 必填（走云端时） |

---

## 工作区目录约定

一个 **Workspace** = 一个宇宙库：

```
<root>/素材/     原始素材（录音、聊天导出、角色卡）——⚠️ 通常含隐私，不要公开
<root>/数据/     characters.json · relations.json · players.json · pl_profiles.json
<root>/产出/     可视化 / KB 包 / 编年史（人读产物）
<root>/.trpg/    运行态：state/ jobs/ logs/ patches/ staging/ reports/ canon/ normalized/
```

切库只改 `config.yaml` 的 `workspace.root`，或用 `--ws` 临时覆盖。

---

## 关键设计

### 补丁驱动入库

不再为每个团手写 `add_<团>.py`。`extract` 产出补丁 JSON，
`store` 负责校验 → 归一 → 去重 → 工作副本 → 报告 → 备份回填。契约见 `trpg_agent/store/merger.py` 顶部注释。

### 只写明确项

补丁里 `confirmed: false` 的条目一律降级进「待确认」，**不写盘**。宁可多记待确认，也不要自信地写错。

### 写前必备份 · 生产库闸门

- `<name>.bak_store_<时间戳>`，默认保留 10 份
- `store --apply` 对生产库**默认拒绝**，需 `--allow-production` 或 `config.workspace.allow_production_write: true`
- 影子库预演：把工作区复制到 `<工作区>/.trpg/shadow_ws` 再 `store --ws "<shadow>"`，**生产库零风险看成品**

### 转写为什么是"窗口化"的

`faster-whisper` 会对传入音频**一次性做 STFT**：7.3 小时音频在 16 GB 机器上要 ~7.6 GiB 数组，直接 OOM。本工具改为：

```
顺序流式解码（PyAV） → 每 30 分钟一个窗口（约 115 MB 内存）
  → 窗口内 VAD 找语音块 → 贪心合并成批（语音 ≤13min，跨度 ≤30min）
  → 逐批 transcribe → 时间戳平移回全文件时间轴
```

- 输出**逐行追加并 flush**；断点记 `音频指纹 + 参数指纹 + 窗口/批 + 输出字节偏移`
- 参数或算法版本变了会**自动从头**（不会拿旧断点续错）；续跑先截断到批起点，所以半途崩溃不会产生重复行
- ⚠️ 断点指纹包含 `config.yaml` 的 `asr.*`——**换团前先把当前团跑完再改**

### 关系数据容易抽漏

`extract` 抽关系的口径**天然偏小**（通常只落"师徒/配对"那类）。补充手段：

```bash
python tools/_extract_relations.py --group "X"     # 抽
python tools/_merge_relations.py   --group "X" --write
python tools/_relation_vocab.py                    # 自由写法 → 标准类型
python tools/_relation_stats.py                    # 体检：边/节点 < 0.8，或孤立角色过多 → 抽漏了
```

> ⚠️ 改 `type` 必须同时改补丁——去重键包含 type。

---

## 自测

回归测试是**脚本式**的（不依赖 pytest，因为部分环境 `tempfile` 不可用）：

```bash
python tests/test_slice1.py             # 35 项：幂等 / 切段 / 归一 / 未确认降级 / 备份 / 闸门 / 误删防护
python tests/test_e2e.py                # 20 项：示例团端到端 + 关系图 HTML 结构
python tests/test_jobs.py               # 25 项：后台任务判活 / pid 复用保护 / kill 语义
python tests/test_transcribe_naming.py  # 16 项：多录音团产物不互相覆盖
```

共 **96 项断言**，每项都能独立运行。

---

## 仓库结构

```
trpg_agent/      主包（ingest / transcribe / segment / extract / review / store /
                 visualize / export / housekeep / canon）
tools/           60+ 个通用脚本（关系补齐 / 立绘登记 / 站点构建 / 自检）
tests/           96 项回归断言
examples/        脱敏示例团 mini-group（不依赖音频与 LLM）
web/             Vue3 本地面板前端
server/          FastAPI 薄壳：自托管编辑站 + 编辑 API
worker/          Cloudflare Workers + D1 的在线百科
```

---

## 许可 / License

**代码与文档**：[MIT](LICENSE) © 2026 ReGMeIoN

⚠️ 本仓库**不含**跑团录音、聊天导出、玩家角色卡正文与配图、AI 生成图 ——
这些内容的版权归各玩家与画师所有，**不在本仓库授权范围内**。详见 [NOTICE](NOTICE)。

`examples/mini-group/` 是**完全虚构的脱敏示例团**，人名、剧情、数据均为演示用途编造。
