# -*- coding: utf-8 -*-
"""长任务: detached 子进程 + job 记录 + 日志 + 可中断可恢复。

设计:
- `jobs.run_background(...)` 以脱离式进程启动同一个 CLI(带 --job-id), 输出重定向到日志文件
  (刻意不用管道, 避免沙箱下 named pipe 限制), 立即返回 job id。
- job 记录落在 <work>/jobs/<id>.json, 进程存活状态按 pid 实时探测。
- 恢复: 真正的断点信息在各步骤自己的 state 文件里(如 transcribe_*.json),
  重跑同一条命令即可续跑。
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from trpg_agent.log import info, ok, warn
from trpg_agent.workspace import Workspace

# Windows 进程创建标志
DETACHED_PROCESS = 0x00000008
CREATE_NEW_PROCESS_GROUP = 0x00000200
CREATE_NO_WINDOW = 0x08000000
CREATE_BREAKAWAY_FROM_JOB = 0x01000000


def new_job_id(kind: str) -> str:
    return f"{kind}-{datetime.now().strftime('%Y%m%d-%H%M%S')}-{os.getpid() % 1000:03d}"


@dataclass
class JobRecord:
    id: str
    kind: str
    argv: list[str]
    pid: int | None = None
    status: str = "pending"  # pending|running|finished|failed|unknown|killed
    started: str = ""
    finished: str | None = None
    log: str = ""
    workspace: str = ""
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "argv": self.argv, "pid": self.pid,
            "status": self.status, "started": self.started, "finished": self.finished,
            "log": self.log, "workspace": self.workspace, "extra": self.extra,
        }


def job_path(ws: Workspace, job_id: str) -> Path:
    return ws.jobs / f"{job_id}.json"


def save_job(ws: Workspace, rec: JobRecord) -> Path:
    ws.jobs.mkdir(parents=True, exist_ok=True)
    p = job_path(ws, rec.id)
    p.write_text(json.dumps(rec.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def load_job(ws: Workspace, job_id: str) -> JobRecord | None:
    p = job_path(ws, job_id)
    if not p.is_file():
        return None
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return JobRecord(**d)


def list_jobs(ws: Workspace, refresh: bool = True) -> list[JobRecord]:
    if not ws.jobs.is_dir():
        return []
    recs: list[JobRecord] = []
    for p in sorted(ws.jobs.glob("*.json"), reverse=True):
        try:
            recs.append(JobRecord(**json.loads(p.read_text(encoding="utf-8"))))
        except (json.JSONDecodeError, OSError, TypeError):
            continue
    if refresh:
        for r in recs:
            refresh_status(ws, r)
    return recs


# --- 进程存活探测 -------------------------------------------------------------
# 刻意不用 `tasklist` + 管道捕获: 受限/沙箱环境下子进程管道会失败(EPERM),
# 于是"进程明明活着却判成 failed"。实测踩过: 转写在跑却被标 failed, 差点被重开
# 而毁掉断点(重开会从头解码甚至重复行)。Windows 走 kernel32, 零子进程零管道。
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
STILL_ACTIVE = 259


def _pid_alive_win(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes

    try:
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return False
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = k32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        code = wintypes.DWORD()
        if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
            return False
        return code.value == STILL_ACTIVE
    finally:
        k32.CloseHandle(handle)


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    if os.name == "nt":
        return _pid_alive_win(int(pid))
    try:  # POSIX: signal 0 只做权限/存在性检查, 不会杀进程
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


def _log_recent(rec: JobRecord, within_s: int = 180) -> bool:
    """日志文件最近还在被写入 = 任务仍在推进(兜底判据)。

    venv 的 python.exe 是包装器: 真正干活的是孙进程, 万一包装器先退出,
    光看 pid 会误判。日志 mtime 是零副作用的第二证据。
    """
    if not rec.log:
        return False
    try:
        p = Path(rec.log)
        if not p.is_file() or p.stat().st_size == 0:
            return False
        age = datetime.now().timestamp() - p.stat().st_mtime
        return age <= within_s
    except OSError:
        return False


def refresh_status(ws: Workspace, rec: JobRecord) -> JobRecord:
    """按"进程活着 / 日志还在动 / 步骤 state"三级判据定状态。

    顺序很重要: 只要还有活着的证据, 就把误标的 failed/unknown 纠正回 running
    (旧版本在这里会把在跑的任务写成 failed, 危险)。
    """
    alive = pid_alive(rec.pid)
    if not alive:
        alive = _log_recent(rec)
        if alive:
            warn(f"任务 {rec.id}: pid {rec.pid} 不在, 但日志仍在更新 -> 视为运行中")
    if alive:
        if rec.status != "running":
            info(f"任务 {rec.id}: 进程仍在运行, 状态 {rec.status} -> running(纠正)")
            rec.status = "running"
            rec.finished = None
            save_job(ws, rec)
        return rec
    if rec.status in ("running", "pending"):
        status = "unknown"
        # 步骤 state 优先按 "kind_<主体>.json" 找(transcribe/extract 每团一份), 再退回 kind.json
        candidates: list[Path] = []
        subject = rec.extra.get("group") or rec.extra.get("file")
        if subject:
            candidates.append(ws.state / f"{rec.kind}_{subject}.json")
        candidates.append(ws.state / f"{rec.kind}.json")
        for st in candidates:
            if not st.is_file():
                continue
            try:
                doc = json.loads(st.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            s = doc.get("status")
            if s == "done":
                status = "finished"
            elif s == "failed":
                status = "failed"
            break  # 第一个存在的 state 说了算(每团的优先于全局), 别被后面的覆盖
        rec.status = status
        rec.finished = rec.finished or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_job(ws, rec)
    return rec


def mark_finished(ws: Workspace, job_id: str, status: str = "finished") -> None:
    rec = load_job(ws, job_id)
    if rec:
        rec.status = status
        rec.finished = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        save_job(ws, rec)


def start_background(
    ws: Workspace, kind: str, argv: list[str], extra: dict[str, Any] | None = None,
    pass_job_id: bool = True,
) -> JobRecord:
    """以脱离式进程启动, 日志重定向到文件(不走管道)。

    pass_job_id: 目标命令是否支持 `--job-id`(只有 transcribe/extract 支持)。
    不支持时子进程不会回写 job 状态, 由 refresh_status 依据步骤 state 判定。
    """
    job_id = new_job_id(kind)
    ws.jobs.mkdir(parents=True, exist_ok=True)
    ws.logs.mkdir(parents=True, exist_ok=True)
    log_path = ws.logs / f"{job_id}.log"
    full_argv = list(argv) + (["--job-id", job_id] if pass_job_id else [])

    flags = DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW
    # 日志重定向到文件时 Python 会块缓冲(约 8KB), 会让 jobs logs 严重滞后 -> 强制无缓冲
    child_env = os.environ.copy()
    child_env["PYTHONUNBUFFERED"] = "1"
    child_env["PYTHONIOENCODING"] = "utf-8"
    # 先尝试从父作业对象脱离(否则父进程退出时可能连带被杀)
    for attempt_flags in (flags | CREATE_BREAKAWAY_FROM_JOB, flags):
        try:
            with open(log_path, "w", encoding="utf-8") as logf:
                proc = subprocess.Popen(
                    full_argv,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    stdin=subprocess.DEVNULL,
                    creationflags=attempt_flags,
                    cwd=str(Path(__file__).resolve().parent.parent),
                    env=child_env,
                    close_fds=True,
                )
            rec = JobRecord(
                id=job_id, kind=kind, argv=full_argv, pid=proc.pid, status="running",
                started=datetime.now().strftime("%Y-%m-%d %H:%M:%S"), log=str(log_path),
                workspace=str(ws.root), extra=extra or {},
            )
            save_job(ws, rec)
            return rec
        except OSError as e:
            last = e
            continue
    raise OSError(f"无法启动后台任务: {last}")


def read_log(ws: Workspace, job_id: str, tail: int = 40) -> str:
    p = ws.logs / f"{job_id}.log"
    if not p.is_file():
        return ""
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(lines[-tail:]) if tail else "\n".join(lines)


PROCESS_TERMINATE = 0x0001
TH32CS_SNAPPROCESS = 0x00000002


def _snapshot_procs() -> tuple[dict[int, list[int]], dict[int, str]]:
    """一次性进程快照 -> (pid->子进程列表, pid->exe 名)。零子进程零管道。"""
    import ctypes
    from ctypes import wintypes

    class PROCESSENTRY32(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),  # ULONG_PTR
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_char * 260),
        ]

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.Process32First.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    k32.Process32Next.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESSENTRY32)]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    snap = k32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    children: dict[int, list[int]] = {}
    exes: dict[int, str] = {}
    if not snap or snap == (1 << (8 * ctypes.sizeof(ctypes.c_void_p))) - 1:
        return children, exes
    try:
        entry = PROCESSENTRY32()
        entry.dwSize = ctypes.sizeof(PROCESSENTRY32)
        if not k32.Process32First(snap, ctypes.byref(entry)):
            return children, exes
        while True:
            pid = int(entry.th32ProcessID)
            children.setdefault(int(entry.th32ParentProcessID), []).append(pid)
            exes[pid] = entry.szExeFile.decode("mbcs", "replace")
            if not k32.Process32Next(snap, ctypes.byref(entry)):
                break
    finally:
        k32.CloseHandle(snap)
    return children, exes


def _terminate_tree(
    pid: int, children: dict[int, list[int]] | None = None
) -> list[int]:
    """终止 pid 及其全部后代, 返回被杀掉的 pid 列表。

    为什么需要它: taskkill 在受限/沙箱环境下会直接 "ERROR: Access denied"(rc=1),
    实测本机就是如此。而 taskkill /T 的意图必须保住 —— venv 的 python.exe 是**包装器**,
    只杀包装器会留下真正干活的孙进程(继续吃内存/占断点)。
    """
    import ctypes
    from ctypes import wintypes

    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    k32.CloseHandle.argtypes = [wintypes.HANDLE]

    if children is None:
        children, _ = _snapshot_procs()
    order: list[int] = []
    stack = [int(pid)]
    seen: set[int] = set()
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        order.append(cur)
        stack.extend(children.get(cur, []))

    killed: list[int] = []
    for target in reversed(order):  # 后序: 先杀后代, 免得包装器先死留下孤儿
        handle = k32.OpenProcess(PROCESS_TERMINATE, False, target)
        if not handle:
            continue
        try:
            if k32.TerminateProcess(handle, 1):
                killed.append(target)
        finally:
            k32.CloseHandle(handle)
    return killed


def kill_job(ws: Workspace, job_id: str) -> bool:
    rec = load_job(ws, job_id)
    if not rec or not rec.pid:
        warn(f"任务 {job_id} 无可用 pid")
        return False
    if not pid_alive(rec.pid):
        warn(f"任务 {job_id} 的进程 {rec.pid} 已不在运行")
        mark_finished(ws, job_id, "unknown")
        return False
    if os.name == "nt":
        children, exes = _snapshot_procs()
        exe = exes.get(int(rec.pid), "")
        # pid 复用保护: 任务早结束后 pid 可能被别的程序占用, 别误杀无辜
        if exe and "python" not in exe.lower():
            warn(f"任务 {job_id} 的 pid {rec.pid} 现在是 {exe!r}(不是 python), "
                 f"疑似 pid 复用, 拒绝终止")
            return False
        try:
            # 不捕获输出(受限环境下管道捕获会失败); 正常环境这条路最省事
            rc = subprocess.run(
                ["taskkill", "/PID", str(rec.pid), "/T", "/F"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=30,
            ).returncode
        except (OSError, subprocess.SubprocessError) as e:
            rc = -1
            warn(f"taskkill 调用失败: {e}")
        if pid_alive(rec.pid):
            killed = _terminate_tree(rec.pid, children=children)
            if killed:
                info(f"taskkill 未生效(rc={rc}), 已用 kernel32 终止 "
                     f"{len(killed)} 个进程(含后代)")
    else:
        import signal

        try:
            os.kill(int(rec.pid), signal.SIGTERM)
        except OSError as e:
            warn(f"kill 失败: {e}")
    if pid_alive(rec.pid):
        warn(f"任务 {job_id} 的进程 {rec.pid} 仍存活, 未标记状态")
        return False
    mark_finished(ws, job_id, "killed")
    ok(f"已终止任务 {job_id} (pid {rec.pid})")
    return True


def current_python() -> str:
    return sys.executable
