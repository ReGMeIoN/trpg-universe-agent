# -*- coding: utf-8 -*-
"""数据层：JSON 权威数据 + SQLite 版本历史。

设计取舍（为什么不是"全塞进数据库表"）：
  · **权威数据是 JSON 文件** —— 人可读、可 git、可手工改，也能被既有的
    `trpg_agent` 工具链（store / build_net_site / _pull_suggestions）直接读；
    角色字段还在演进，JSON 比表结构灵活得多。
  · **SQLite 只干一件事：版本历史** —— 每次保存一份 gzip 压缩的全量快照。
    236 角色 ≈ 200KB JSON，gzip 后约 40–60KB，存上千版也就几十 MB，
    换来的是「谁在什么时候改了什么」+「一键回滚」。
  · **写入一律原子**（临时文件 + os.replace）—— 写一半断电不会毁数据。

并发：单进程 uvicorn + 一把进程内锁即可（这个规模不需要更复杂的东西）。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS revisions (
  rev      INTEGER PRIMARY KEY AUTOINCREMENT,
  ts       TEXT    NOT NULL,
  editor   TEXT,
  note     TEXT,
  kind     TEXT,          -- char_update / char_create / char_delete / rel_update / ... / rollback
  target   TEXT,          -- 受影响的 id（便于按角色查历史）
  summary  TEXT,          -- 人类可读的一行摘要
  digest   TEXT,          -- 快照内容的 sha256（相同内容不重复存）
  snapshot BLOB           -- gzip(JSON) 全量快照
);
CREATE INDEX IF NOT EXISTS idx_rev_ts     ON revisions(ts DESC);
CREATE INDEX IF NOT EXISTS idx_rev_target ON revisions(target, ts DESC);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class Store:
    def __init__(self, data_dir: Path, db_path: Path, keep_revisions: int = 2000):
        self.dir = Path(data_dir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.chars_path = self.dir / "characters.json"
        self.rels_path = self.dir / "relations.json"
        self.layout_path = self.dir / "layout.json"
        self.ann_path = self.dir / "announce.json"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.keep = keep_revisions
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()

    # ── 读 ────────────────────────────────────────────────────
    def load(self) -> dict:
        with self._lock:
            chars = json.loads(self.chars_path.read_text(encoding="utf-8")) if self.chars_path.is_file() else {}
            rels = json.loads(self.rels_path.read_text(encoding="utf-8")) if self.rels_path.is_file() else {}
            return {
                "characters": chars.get("characters", []) if isinstance(chars, dict) else chars,
                "relations": rels.get("relations", []) if isinstance(rels, dict) else rels,
            }

    def _raw_docs(self) -> tuple[dict, dict]:
        """保留原始文档结构（characters.json 顶层可能还有别的键）。"""
        c = json.loads(self.chars_path.read_text(encoding="utf-8")) if self.chars_path.is_file() else {"characters": []}
        r = json.loads(self.rels_path.read_text(encoding="utf-8")) if self.rels_path.is_file() else {"relations": []}
        if isinstance(c, list):
            c = {"characters": c}
        if isinstance(r, list):
            r = {"relations": r}
        c.setdefault("characters", [])
        r.setdefault("relations", [])
        return c, r

    # ── 写（原子 + 版本）─────────────────────────────────────
    @staticmethod
    def _atomic_write(path: Path, doc) -> None:
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    def save(self, mutate, *, editor: str = "", note: str = "", kind: str = "edit",
             target: str = "", summary: str = "") -> int:
        """mutate(cdoc, rdoc) 就地修改两份文档；返回新版本号。

        全程持锁 → 改 → 落盘 → 存快照，中途任何异常都不会留下半截数据。

        ⚠️ `kind` / `summary` 支持**函数**：`mutate` 里才知道"这次到底是新建还是修改"，
        而 Python 会先把实参算完再调用 `save`（所以直接传 `ctx["kind"]` 拿到的永远是旧值
        —— 这就是「新建的角色在版本历史里被记成 char_update」的根因）。
        传 lambda 进来，快照时才求值，就对了。
        """
        with self._lock:
            cdoc, rdoc = self._raw_docs()
            before = self._digest(cdoc, rdoc)
            mutate(cdoc, rdoc)
            after = self._digest(cdoc, rdoc)
            if before == after:
                return -1                       # 无变化，不产生版本
            self._atomic_write(self.chars_path, cdoc)
            self._atomic_write(self.rels_path, rdoc)
            k = kind() if callable(kind) else kind
            sm = summary() if callable(summary) else summary
            return self._snapshot(cdoc, rdoc, editor, note, k, target, sm)

    def _digest(self, cdoc, rdoc) -> str:
        h = hashlib.sha256()
        h.update(json.dumps(cdoc, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        h.update(json.dumps(rdoc, ensure_ascii=False, sort_keys=True).encode("utf-8"))
        return h.hexdigest()

    def _snapshot(self, cdoc, rdoc, editor, note, kind, target, summary) -> int:
        blob = gzip.compress(json.dumps({"characters": cdoc, "relations": rdoc},
                                        ensure_ascii=False).encode("utf-8"), 6)
        cur = self._conn.execute(
            """INSERT INTO revisions (ts, editor, note, kind, target, summary, digest, snapshot)
               VALUES (?,?,?,?,?,?,?,?)""",
            (now_iso(), editor or "", note or "", kind, target or "", summary or "",
             self._digest(cdoc, rdoc), blob))
        self._conn.commit()
        rev = int(cur.lastrowid)
        # 只保留最近 N 版（更老的删掉，磁盘不会无限涨）
        self._conn.execute(
            "DELETE FROM revisions WHERE rev <= (SELECT MAX(rev) FROM revisions) - ?", (self.keep,))
        self._conn.commit()
        return rev

    # ── 版本历史 ──────────────────────────────────────────────
    def history(self, limit: int = 100, target: str | None = None) -> list[dict]:
        with self._lock:
            if target:
                rows = self._conn.execute(
                    """SELECT rev, ts, editor, note, kind, target, summary FROM revisions
                        WHERE target=? ORDER BY rev DESC LIMIT ?""", (target, limit)).fetchall()
            else:
                rows = self._conn.execute(
                    """SELECT rev, ts, editor, note, kind, target, summary FROM revisions
                        ORDER BY rev DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(r) for r in rows]

    def get_rev(self, rev: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM revisions WHERE rev=?", (rev,)).fetchone()
            if not row:
                return None
            snap = json.loads(gzip.decompress(row["snapshot"]).decode("utf-8"))
            return {"rev": row["rev"], "ts": row["ts"], "editor": row["editor"],
                    "note": row["note"], "kind": row["kind"], "target": row["target"],
                    "summary": row["summary"], "data": snap}

    def rollback(self, rev: int, editor: str = "", note: str = "") -> int:
        """把数据回滚到某个版本（回滚本身也记一条版本，history 不会断）。"""
        snap = self.get_rev(rev)
        if not snap:
            raise KeyError(f"版本 {rev} 不存在")
        d = snap["data"]

        def mutate(cdoc, rdoc):
            cdoc["characters"] = d.get("characters", {}).get("characters", [])
            rdoc["relations"] = d.get("relations", {}).get("relations", [])
        return self.save(mutate, editor=editor, note=note or f"回滚到 #{rev}",
                         kind="rollback", target="", summary=f"rollback -> #{rev}")

    def backup(self, tag: str = "") -> Path:
        """把当前数据文件复制一份到 _bak_<时间戳>/（给危险操作留后路）。"""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S") + (f"_{tag}" if tag else "")
        d = self.dir / f"_bak_{stamp}"
        d.mkdir(parents=True, exist_ok=True)
        for f in (self.chars_path, self.rels_path):
            if f.is_file():
                shutil.copy2(f, d / f.name)
        return d

    # ── 布局账本（可选文件；不存在时 API 返回空模板）─────────
    EMPTY_LAYOUT = {"version": 1, "updated": "", "next_slot": 0,
                    "entity_pos": {}, "slot_of": {}, "manual": {}}

    def load_layout(self) -> dict:
        """读 `layout.json`。**注意**：不存在时**不要**在这里创建文件——
        只有真正发生人工微调才落盘（否则挂载只读目录会炸）。"""
        with self._lock:
            if not self.layout_path.is_file():
                return json.loads(json.dumps(self.EMPTY_LAYOUT, ensure_ascii=False))
            try:
                doc = json.loads(self.layout_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return json.loads(json.dumps(self.EMPTY_LAYOUT, ensure_ascii=False))
            for k, v in self.EMPTY_LAYOUT.items():
                doc.setdefault(k, json.loads(json.dumps(v, ensure_ascii=False)))
            return doc

    def save_layout(self, mutate, *, editor: str = "", note: str = "") -> int:
        """就地把 layout.json 改掉（原子写）。布局**不进版本库**——
        它是可再生的呈现层数据，回滚角色数据不该跟着回滚排版。"""
        with self._lock:
            doc = self.load_layout()
            before = json.dumps(doc, ensure_ascii=False, sort_keys=True)
            mutate(doc)
            after = json.dumps(doc, ensure_ascii=False, sort_keys=True)
            if before == after:
                return 0
            doc["updated"] = now_iso()
            tmp = self.layout_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.layout_path)
            return 1

    def entity_slots(self, ids: list[str], *, name_of=None) -> dict[str, int]:
        """给一个实体的成员分**稳定槽位**（只增不改）。

        规则（写给以后的自己）：
          · 先占据「已经是这个实体槽位的 id」——**已定下的槽位永不动**；
          · 再按 `(名字, id)` 排序把没槽位的人接在后面；
          · 结果按槽位号写回 `slot_of`；`next_slot` 推到最大号 +1。
        `(名字, id)` 而不是「数据文件顺序」：任何人、任何时候算出的顺序都一样。
        """
        doc = self.load_layout()
        slot_of = doc["slot_of"]
        used = {slot_of[i] for i in ids if i in slot_of}
        free = [i for i in ids if i not in slot_of]
        nxt = max([doc.get("next_slot", 0)] + [s + 1 for s in used]) if (used or free) else doc.get("next_slot", 0)

        def sort_key(i):
            nm = (name_of(i) if name_of else "") or ""
            return (nm, i)

        changed = False
        for i in sorted(free, key=sort_key):
            while nxt in used:
                nxt += 1
            slot_of[i] = nxt
            used.add(nxt)
            nxt += 1
            changed = True
        if changed:
            doc["next_slot"] = max(doc.get("next_slot", 0), nxt)
            self.save_layout(lambda d: d.update(slot_of=slot_of, next_slot=doc["next_slot"]))
        return {i: slot_of[i] for i in ids if i in slot_of}

    # ── 公告（公开可发；`announce.json`，不进版本库）────────
    EMPTY_ANN = {"version": 1, "updated": "", "next_id": 1, "items": []}

    def load_announcements(self) -> dict:
        with self._lock:
            if not self.ann_path.is_file():
                return json.loads(json.dumps(self.EMPTY_ANN, ensure_ascii=False))
            try:
                doc = json.loads(self.ann_path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                return json.loads(json.dumps(self.EMPTY_ANN, ensure_ascii=False))
            for k, v in self.EMPTY_ANN.items():
                doc.setdefault(k, json.loads(json.dumps(v, ensure_ascii=False)))
            return doc

    def save_announcements(self, mutate, *, editor: str = "") -> int:
        """改公告文件。返回 items 数量变化（正=新增、负=删除）。"""
        with self._lock:
            doc = self.load_announcements()
            before = len(doc.get("items", []))
            mutate(doc)
            doc["updated"] = now_iso()
            tmp = self.ann_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
            os.replace(tmp, self.ann_path)
            return len(doc.get("items", [])) - before

    def stats(self) -> dict:
        d = self.load()
        with self._lock:
            n_rev = self._conn.execute("SELECT COUNT(*) c FROM revisions").fetchone()["c"]
            last = self._conn.execute(
                "SELECT ts, editor, summary FROM revisions ORDER BY rev DESC LIMIT 1").fetchone()
        return {
            "characters": len(d["characters"]),
            "relations": len(d["relations"]),
            "revisions": n_rev,
            "last_edit": dict(last) if last else None,
            "files": {
                "characters": self.chars_path.exists(),
                "relations": self.rels_path.exists(),
            },
        }
