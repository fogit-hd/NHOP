"""
Stop ffmpeg started by start_ffmpeg_record.py: soft (taskkill without /F, then Ctrl+C attach), then force.
Reads PID from --pid-file. Stdlib only (ctypes on Windows).
"""
from __future__ import annotations

import argparse
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes


def _taskkill_soft(pid: int, timeout: float = 12.0) -> None:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "taskkill.exe")
    if not os.path.isfile(exe):
        return
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    try:
        subprocess.run([exe, "/PID", str(pid)], timeout=timeout, check=False, **kwargs)
    except (subprocess.TimeoutExpired, OSError):
        pass


def _process_exists_win(pid: int) -> bool:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    SYNCHRONIZE = 0x00100000
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    handle = kernel32.OpenProcess(SYNCHRONIZE | PROCESS_QUERY_LIMITED_INFORMATION, False, wintypes.DWORD(pid))
    if not handle:
        return False
    try:
        kernel32.CloseHandle(handle)
        return True
    except OSError:
        return False


def _ctrl_c_attach(pid: int) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    FreeConsole = kernel32.FreeConsole
    FreeConsole.argtypes = ()
    FreeConsole.restype = wintypes.BOOL
    AttachConsole = kernel32.AttachConsole
    AttachConsole.argtypes = (wintypes.DWORD,)
    AttachConsole.restype = wintypes.BOOL
    SetConsoleCtrlHandler = kernel32.SetConsoleCtrlHandler
    SetConsoleCtrlHandler.argtypes = (wintypes.LPVOID, wintypes.BOOL)
    SetConsoleCtrlHandler.restype = wintypes.BOOL
    GenerateConsoleCtrlEvent = kernel32.GenerateConsoleCtrlEvent
    GenerateConsoleCtrlEvent.argtypes = (wintypes.DWORD, wintypes.DWORD)
    GenerateConsoleCtrlEvent.restype = wintypes.BOOL

    try:
        FreeConsole()
    except OSError:
        pass
    if not AttachConsole(wintypes.DWORD(pid)):
        return
    try:
        SetConsoleCtrlHandler(None, True)
        GenerateConsoleCtrlEvent(0, 0)
        time.sleep(2.0)
    finally:
        try:
            FreeConsole()
        except OSError:
            pass


def _wait_wav_ready(path: str, min_bytes: int = 320, timeout: float = 25.0) -> None:
    """After ffmpeg exits, NTFS may still flush; wait until size is stable and >= min_bytes."""
    deadline = time.time() + timeout
    last = -1
    same = 0
    while time.time() < deadline:
        try:
            if os.path.isfile(path):
                sz = os.path.getsize(path)
                if sz >= min_bytes and sz == last:
                    same += 1
                    if same >= 2:
                        return
                else:
                    same = 0
                last = sz
        except OSError:
            pass
        time.sleep(0.25)


def _taskkill_force(pid: int) -> None:
    root = os.environ.get("SystemRoot", r"C:\Windows")
    exe = os.path.join(root, "System32", "taskkill.exe")
    kwargs = {}
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    try:
        subprocess.run([exe, "/PID", str(pid), "/F", "/T"], timeout=15.0, check=False, **kwargs)
    except (subprocess.TimeoutExpired, OSError):
        pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--pid-file", required=True)
    p.add_argument(
        "--expect-wav",
        default="",
        help="Optional: WAV path to poll until flushed (same size twice) after stop.",
    )
    args = p.parse_args()

    if not os.path.isfile(args.pid_file):
        return
    raw = open(args.pid_file, encoding="utf-8", errors="replace").read().strip()
    if not raw:
        return
    try:
        pid = int(raw)
    except ValueError:
        return

    if sys.platform != "win32":
        try:
            os.kill(pid, 15)
        except OSError:
            pass
        return

    _taskkill_soft(pid)
    time.sleep(1.5)

    if not _process_exists_win(pid):
        return

    _ctrl_c_attach(pid)
    time.sleep(0.5)

    deadline = time.time() + 8.0
    while time.time() < deadline and _process_exists_win(pid):
        time.sleep(0.15)

    if _process_exists_win(pid):
        _taskkill_force(pid)

    if args.expect_wav.strip():
        _wait_wav_ready(os.path.normpath(args.expect_wav.strip()))


if __name__ == "__main__":
    main()
