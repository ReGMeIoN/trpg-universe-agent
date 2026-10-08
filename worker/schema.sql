-- 跑团宇宙 · 提案箱（wiki 化）表结构
-- 设计口径：**访客改的东西一律先落 pending，绝不直接改生产库**。
--   1) 访客/朋友在站点上提交「修改 / 新增 / 删除」建议  → 本表 pending
--   2) 管理员（主人）在站点审核页点「通过」            → 本表 approved
--   3) 站点前端把 approved 的条目当**覆盖层**实时套上去  → 立刻可见（不改真数据）
--   4) 主人本地跑 `tools\_pull_suggestions.py` 拉回生产库 → 走既有的备份+复验流程入库
-- 这样既有 wiki 的即时感，又守住「生产库改动必须人工过审」的铁律。

CREATE TABLE IF NOT EXISTS suggestions (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  kind        TEXT    NOT NULL,          -- char_update|char_create|char_delete|rel_update|rel_create|rel_delete
  target_id   TEXT,                      -- 角色 id；关系类为 'from|to|type'
  payload     TEXT    NOT NULL,          -- JSON，字段已按白名单裁剪
  reason      TEXT,                      -- 提交者的理由/出处
  author      TEXT,                      -- 可选署名（匿名留空）
  status      TEXT    NOT NULL DEFAULT 'pending',   -- pending|approved|rejected
  created_at  TEXT    NOT NULL,
  reviewed_at TEXT,
  review_note TEXT,
  ip_hash     TEXT                       -- 只存哈希（限流用），不存明文 IP
);

CREATE INDEX IF NOT EXISTS idx_sugg_status ON suggestions(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_sugg_target ON suggestions(target_id);
CREATE INDEX IF NOT EXISTS idx_sugg_ip     ON suggestions(ip_hash, created_at DESC);
