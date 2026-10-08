# -*- coding: utf-8 -*-
"""把 Cloudflare D1 的提案箱数据导出成一份本地 SQLite 文件（迁移/备份用）。

D1 就是 SQLite，所以**不需要任何格式转换**：`wrangler d1 export` 出来的就是
标准 SQL（建表 + INSERT），直接喂 `sqlite3.executescript()` 即可。

用法:
    python tools\\_export_d1.py                        # 导出到 server\\wiki.db
    python tools\\_export_d1.py --out D:\\bak\\wiki.db   # 指定目标
    python tools\\_export_d1.py --from-sql dump.sql     # 用已导出的 SQL（不再调 wrangler）
    python tools\\_export_d1.py --db <D1库名> --keep-sql
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = os.environ.get("TRPG_D1_DB", "")
DEFAULT_OUT = ROOT / "server" / "wiki.db"


def run_wrangler_export(db_name: str, out_sql: Path) -> None:
    cmd = ["npx", "--yes", "wrangler@latest", "d1", "export", db_name,
           "--remote", "--output", str(out_sql)]
    print("执行:", " ".join(cmd))
    p = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", shell=(sys.platform == "win32"))
    tail = (p.stdout or "")[-800:]
    if p.returncode != 0:
        raise RuntimeError(f"wrangler 导出失败（exit {p.returncode}）\n{tail}\n{(p.stderr or '')[-800:]}")
    if not out_sql.is_file():
        raise RuntimeError(f"wrangler 没生成文件：{out_sql}\n{tail}")


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError, ValueError):
        pass
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB, help="D1 数据库名")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="目标 SQLite 文件")
    ap.add_argument("--from-sql", default=None, help="改用已有的导出 SQL")
    ap.add_argument("--keep-sql", action="store_true", help="保留中间 SQL 文件")
    args = ap.parse_args()

    out = Path(args.out)
    if out.exists():
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        bak = out.with_suffix(f".bak_{stamp}.db")
        shutil.copy2(out, bak)
        print(f"已备份原文件 → {bak.name}")

    tmpdir = Path(tempfile.mkdtemp(prefix="d1export_"))
    try:
        if args.from_sql:
            sql_path = Path(args.from_sql)
            if not sql_path.is_file():
                print(f"!! 找不到 {sql_path}")
                return 1
        else:
            sql_path = tmpdir / f"{args.db}.sql"
            run_wrangler_export(args.db, sql_path)

        sql = sql_path.read_text(encoding="utf-8", errors="replace")
        print(f"SQL 文件: {sql_path.name}（{len(sql) / 1024:.1f} KB）")

        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        con = sqlite3.connect(str(out))
        try:
            con.executescript(sql)
            con.commit()
        finally:
            con.close()

        # ── 复验 ────────────────────────────────────────────
        con = sqlite3.connect(str(out))
        con.row_factory = sqlite3.Row
        try:
            tables = [r["name"] for r in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            print(f"\n表: {', '.join(tables) or '(空)'}")
            if "suggestions" in tables:
                tot = con.execute("SELECT COUNT(*) c FROM suggestions").fetchone()["c"]
                print(f"建议总数: {tot}")
                for r in con.execute("SELECT status, COUNT(*) n FROM suggestions GROUP BY status"):
                    print(f"  {r['status']:<9} {r['n']}")
            dangling = 0
        finally:
            con.close()

        print(f"\nOK 已写出: {out}（{out.stat().st_size / 1024:.1f} KB）")
        print("提示: 搬到服务器后直接放在 WIKI_DB 指向的位置即可，表结构一致。")
        if args.keep_sql and not args.from_sql:
            keep = ROOT / "server" / f"{args.db}_dump.sql"
            shutil.copy2(sql_path, keep)
            print(f"中间 SQL 已保留: {keep}")
        return 0
    finally:
        if not args.keep_sql:
            shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
