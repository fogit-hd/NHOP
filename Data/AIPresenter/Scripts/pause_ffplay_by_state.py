"""Pause/resume ffplay playback based on a shared state file.

State file values:
- running : ensure playback is resumed
- paused  : suspend playback process
- stop    : resume (if needed) then exit monitor

This script is intended to run in background via pythonw.
"""
from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
PROCESS_SUSPEND_RESUME = 0x0800
STILL_ACTIVE = 259
STATUS_SUCCESS = 0


def _resolve_under_project(path_value: str) -> Path:
    raw = Path(path_value.strip())
    if raw.is_absolute():
        return raw.resolve()
    return (PROJECT_ROOT / raw).resolve()


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return default


def _read_pid(path: Path) -> int | None:
    txt = _read_text(path, "").strip()
    if not txt:
        return None
    try:
        pid = int(txt)
        return pid if pid > 0 else None
    except ValueError:
        return None


def _process_alive_windows(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        exit_code = wintypes.DWORD(0)
        if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0:
            return False
        return int(exit_code.value) == STILL_ACTIVE
    finally:
        kernel32.CloseHandle(handle)


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        return _process_alive_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _suspend_process_windows(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        status = int(ntdll.NtSuspendProcess(handle))
        return status == STATUS_SUCCESS
    finally:
        kernel32.CloseHandle(handle)


def _resume_process_windows(pid: int) -> bool:
    kernel32 = ctypes.windll.kernel32
    ntdll = ctypes.windll.ntdll
    handle = kernel32.OpenProcess(PROCESS_SUSPEND_RESUME | PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
    if not handle:
        return False
    try:
        status = int(ntdll.NtResumeProcess(handle))
        return status == STATUS_SUCCESS
    finally:
        kernel32.CloseHandle(handle)


def _suspend_process(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    return _suspend_process_windows(pid)


def _resume_process(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    return _resume_process_windows(pid)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", required=True, help="Path to presentation_control_state.txt")
    p.add_argument("--ffplay-pid-file", required=True, help="Path to last_ffplay_pid.txt")
    p.add_argument("--owner-pid", type=int, default=0, help="Optional owner process PID")
    p.add_argument("--poll-ms", type=int, default=150, help="Polling interval in milliseconds")
    args = p.parse_args()

    state_file = _resolve_under_project(args.state_file)
    ffplay_pid_file = _resolve_under_project(args.ffplay_pid_file)
    owner_pid = int(args.owner_pid or 0)
    poll_seconds = max(0.05, float(args.poll_ms) / 1000.0)

    suspended_pids: set[int] = set()

    def resume_if_needed(pid: int) -> None:
        if pid <= 0:
            return
        if _process_alive(pid):
            _resume_process(pid)

    def suspend_if_needed(pid: int) -> None:
        if pid <= 0:
            return
        if pid in suspended_pids:
            return
        if _process_alive(pid) and _suspend_process(pid):
            suspended_pids.add(pid)

    def cleanup_suspended() -> None:
        dead = [pid for pid in suspended_pids if not _process_alive(pid)]
        for pid in dead:
            suspended_pids.discard(pid)

    try:
        while True:
            if owner_pid > 0 and not _process_alive(owner_pid):
                break

            state = _read_text(state_file, "running").strip().lower() or "running"
            if state == "stop":
                break

            cleanup_suspended()

            target_pid = _read_pid(ffplay_pid_file)
            if target_pid is not None and not _process_alive(target_pid):
                target_pid = None

            if state == "paused":
                if target_pid is not None:
                    suspend_if_needed(target_pid)
            else:
                for pid in list(suspended_pids):
                    resume_if_needed(pid)
                    suspended_pids.discard(pid)

            time.sleep(poll_seconds)
    finally:
        for pid in list(suspended_pids):
            resume_if_needed(pid)
            suspended_pids.discard(pid)

    sys.exit(0)


if __name__ == "__main__":
    main()
