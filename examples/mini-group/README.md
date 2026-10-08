# 示例团 · 星海列车（脱敏 / 纯虚构）

用途：`trpg-agent` 端到端演示与回归测试。**不含任何真实素材、真人昵称或聊天记录。**

## 结构

```
mini-group/
├─ 素材/
│  ├─ 星海列车/星海列车_录音转写.txt        线下录音线(已转写文本, 带 [起 -> 止] 时间戳)
│  └─ 星海列车外传/星海列车外传_聊天导出.json  线上 QQ 线(qq-chat-exporter 导出格式)
├─ 数据/                                    characters/relations/players/pl_profiles
└─ .trpg/
   ├─ canon/naming.json                     PL 称呼规范(演示音近/别称归一)
   └─ patches/星海列车_patch.json            extract 的产出契约(演示 store 入库)
```

## 跑一遍

```powershell
$py = ".\.venv\Scripts\python.exe"
& $py -m trpg_agent ingest  --ws examples/mini-group
& $py -m trpg_agent segment --ws examples/mini-group
& $py -m trpg_agent store   --ws examples/mini-group --patch "examples/mini-group/.trpg/patches/星海列车_patch.json"
& $py -m trpg_agent store   --ws examples/mini-group --patch "examples/mini-group/.trpg/patches/星海列车_patch.json" --apply
& $py -m trpg_agent status  --ws examples/mini-group
```

## 预期结果（切片 1 验收）

| 步骤 | 预期 |
|---|---|
| ingest | manifest 记录 2 个文件 / 2 个团；QQ 导出转出 `.trpg/normalized/星海列车外传_聊天记录纯文本.txt`（22 条消息） |
| segment | 星海列车（转写）按 63 分钟窗切成 **3 段**；星海列车外传（QQ）按日期切成 **1 段**（两天合并，≤3600 行）；`--date-merge-lines 0` 可切成 2 段 |
| store（不回填） | 新增角色 4 / 更新 1 / 新关系 3 / 称呼归一 3 / 待确认 5；只写 `.trpg/staging/` |
| store --apply | 备份 4 个数据文件为 `*.bak_store_<时间戳>`，回填后复验通过；`xh_heiyi.groups` 追加「星海列车」 |

## 这个示例特意覆盖的边界

- **未确认降级**：`xh_shenmi`（神秘乘客）与一条「黑衣客—白露」关系标了 `confirmed: false`，
  不会写盘，只进待确认清单。
- **称呼归一**：`阿蓝（临海的玩家）` → `阿蓝`、`老鸭` → `老鸦`（走 `canon/naming.json`）。
- **同角色跨组更新**：`xh_heiyi` 只追加 `groups` / `note` / `events` / `tags`，不动其它字段。
- **场外闲聊不入库**：转写里那句「点外卖」的闲聊进了待确认清单，而不是数据。
