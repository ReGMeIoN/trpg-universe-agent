# -*- coding: utf-8 -*-
"""jobs 模块回归自测: 后台任务状态判定(存活探测 / 误判纠正 / 终止 / state 兜底)。

用法(项目根目录):
    .venv\\Scripts\\python.exe tests\\test_jobs.py

背景(2026-10-03 实盘踩坑): 旧版用 `tasklist` + 管道捕获探测 pid, 受限/沙箱环境下
子进程管道会失败 -> "转写明明在跑却被标成 failed"。文档据此会诱导人去重开任务,
而重开会截断产物/毁坏断点。本测试把新判据锁死:
  1) 进程活着 = running(即使记录里写着 failed, 也要纠正回来)
  2) 日志 mtime 新鲜 = 仍在推进(包装器进程与真实孙进程分离时的兜底)
  3) 进程真没了 -> 才按步骤 state 定 finished/failed/unknown
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from trpg_agent import jobs as jobs_mod  # noqa: E402
from trpg_agent.config import load_config  # noqa: E402
from trpg_agent.workspace import Workspace  # noqa: E402

TMP_WS = ROOT / ".tmp" / "jobs_test_ws"
FAILURES: list[str] = []
CHECKS = 0
OLD_TS = time.time() - 3600  # 一小时前: 足够"不新鲜"


def check(name: str, cond: bool, detail: str = "") -> None:
    global CHECKS
    CHECKS += 1
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(f"{name} {detail}")


def record(ws: Workspace, job_id: str, **kw) -> jobs_mod.JobRecord:
    """落一条 job 记录(未给的字段用默认), 再重新加载以模拟真实读取路径。"""
    rec = jobs_mod.JobRecord(
        id=job_id, kind=kw.pop("kind", "selftest"), argv=[], workspace=str(ws.root), **kw
    )
    jobs_mod.save_job(ws, rec)
    return jobs_mod.load_job(ws, job_id)


def main() -> int:
    print(f"== jobs 回归自测 ==\n目标: {TMP_WS}\n")
    shutil.rmtree(TMP_WS, ignore_errors=True)
    TMP_WS.mkdir(parents=True, exist_ok=True)
    cfg = load_config(ROOT / "config.yaml", ws_override=TMP_WS)
    cfg.workspace.production_root = ""  # 测试库不是生产库
    ws = Workspace.from_config(cfg)
    ws.ensure_dirs()

    # ---------- 1. 存活探测 ----------
    print("[1] 进程存活探测(不依赖 tasklist / 管道)")
    check("自己(当前进程)算活着", jobs_mod.pid_alive(os.getpid()))
    check("pid=0 视为不活", not jobs_mod.pid_alive(0))
    check("pid=None 视为不活", not jobs_mod.pid_alive(None))
    gone = subprocess.Popen(
        [sys.executable, "-c", "pass"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )
    gone.wait(timeout=30)
    time.sleep(0.3)
    check("已退出进程算不活", not jobs_mod.pid_alive(gone.pid), f"pid={gone.pid}")

    # ---------- 2. 日志新鲜度兜底 ----------
    print("[2] 日志新鲜度兜底(包装器退出但孙进程仍在写)")
    fresh_log = ws.logs / "fresh.log"
    fresh_log.write_text("还在转写\n", encoding="utf-8")
    rec_fresh = jobs_mod.JobRecord(
        id="fresh", kind="selftest", argv=[], pid=gone.pid, status="running",
        log=str(fresh_log), workspace=str(ws.root),
    )
    check("刚写过的日志算在跑", jobs_mod._log_recent(rec_fresh))
    os.utime(fresh_log, (OLD_TS, OLD_TS))
    check("一小时没动的日志不算在跑", not jobs_mod._log_recent(rec_fresh))
    check("空日志文件不算在跑", not jobs_mod._log_recent(
        jobs_mod.JobRecord(id="e", kind="selftest", argv=[], log=str(ws.logs / "nope.log"))
    ))

    # ---------- 3. 误判纠正(核心) ----------
    print("[3] failed 误判纠正: 进程活着就必须是 running")
    stale_log = ws.logs / "stale.log"
    stale_log.write_text("(日志也停了)\n", encoding="utf-8")
    os.utime(stale_log, (OLD_TS, OLD_TS))  # 只留"进程活着"这一条证据
    record(ws, "misjudged", pid=os.getpid(), status="failed",
           finished="2026-01-01 00:00:00", log=str(stale_log))
    got = jobs_mod.refresh_status(ws, jobs_mod.load_job(ws, "misjudged"))
    check("failed -> running", got.status == "running", got.status)
    check("纠正后清掉 finished 时间", got.finished is None, str(got.finished))
    on_disk = json.loads((ws.jobs / "misjudged.json").read_text(encoding="utf-8"))
    check("纠正结果已落盘", on_disk["status"] == "running", on_disk["status"])

    # ---------- 4. 真没了才按 state 定状态 ----------
    print("[4] 进程确实结束: 按步骤 state 判定")
    (ws.state / "selftest.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
    record(ws, "reallydone", pid=gone.pid, status="running", log=str(stale_log))
    got = jobs_mod.refresh_status(ws, jobs_mod.load_job(ws, "reallydone"))
    check("state=done -> finished", got.status == "finished", got.status)
    check("补上 finished 时间", bool(got.finished))

    (ws.state / "selftest.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    record(ws, "reallyfailed", pid=gone.pid, status="running", log=str(stale_log))
    got = jobs_mod.refresh_status(ws, jobs_mod.load_job(ws, "reallyfailed"))
    check("state=failed -> failed", got.status == "failed", got.status)

    (ws.state / "selftest.json").unlink()
    record(ws, "noclue", pid=gone.pid, status="running", log=str(stale_log))
    got = jobs_mod.refresh_status(ws, jobs_mod.load_job(ws, "noclue"))
    check("无 state 兜底 unknown", got.status == "unknown", got.status)

    # ---------- 5. 每团 state 优先于全局 state ----------
    print("[5] 每团 state(kind_<主体>.json)优先")
    (ws.state / "selftest.json").write_text(json.dumps({"status": "failed"}), encoding="utf-8")
    (ws.state / "selftest_团A.json").write_text(json.dumps({"status": "done"}), encoding="utf-8")
    record(ws, "pergroup", pid=gone.pid, status="running", log=str(stale_log), extra={"group": "团A"})
    got = jobs_mod.refresh_status(ws, jobs_mod.load_job(ws, "pergroup"))
    check("团自己的 state=done 胜出", got.status == "finished", got.status)

    # ---------- 6. 真启动 / 真终止 ----------
    print("[6] 后台启动 -> 状态可见 -> 终止")
    argv = [sys.executable, "-c", "import time;print('boot-ok',flush=True);time.sleep(120)"]
    rec_run = jobs_mod.start_background(ws, "selftest", argv, extra={"group": "g"}, pass_job_id=False)
    try:
        check("启动即 running", rec_run.status == "running", rec_run.status)
        time.sleep(2.5)
        check("子进程存活", jobs_mod.pid_alive(rec_run.pid), f"pid={rec_run.pid}")
        check("日志已落盘", "boot-ok" in jobs_mod.read_log(ws, rec_run.id))
        listed = {r.id: r for r in jobs_mod.list_jobs(ws)}
        check("list_jobs 显示 running", listed[rec_run.id].status == "running",
              listed[rec_run.id].status)
        check("kill_job 成功", jobs_mod.kill_job(ws, rec_run.id))
        time.sleep(0.8)
        check("终止后进程消失", not jobs_mod.pid_alive(rec_run.pid))
        check("状态标记 killed", jobs_mod.load_job(ws, rec_run.id).status == "killed",
              jobs_mod.load_job(ws, rec_run.id).status)
    finally:
        if jobs_mod.pid_alive(rec_run.pid):
            subprocess.run(["taskkill", "/PID", str(rec_run.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    # ---------- 7. 不误杀已结束的任务 ----------
    print("[7] 对已结束的任务 kill 不报成功")
    record(ws, "gone-job", pid=gone.pid, status="running", log=str(stale_log))
    check("kill 已结束任务返回 False", jobs_mod.kill_job(ws, "gone-job") is False)

    # ---------- 8. pid 复用保护 ----------
    print("[8] pid 复用保护: 目标不是 python 就拒绝终止")
    other = subprocess.Popen(
        ["ping", "-n", "30", "127.0.0.1"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
    )
    try:
        time.sleep(1.0)
        record(ws, "pid-reuse", pid=other.pid, status="running", log=str(stale_log))
        check("拒绝终止非 python 进程", jobs_mod.kill_job(ws, "pid-reuse") is False)
        check("被保护进程仍然活着", jobs_mod.pid_alive(other.pid))
    finally:
        other.kill()
        other.wait(timeout=15)

    print(f"\n== 结果: {CHECKS - len(FAILURES)}/{CHECKS} 通过 ==")
    if FAILURES:
        print("失败项:")
        for f in FAILURES:
            print("  -", f)
        return 1
    print("全部通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
