"""Play a video with ffplay -autoexit and optional blocking. Writes ffplay PID to a file."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from ffplay_locate import ffplay_hint_stderr, resolve_ffplay

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent


def _resolve_under_project(p: str) -> Path:
    raw = Path(p.strip())
    if raw.is_file():
        return raw.resolve()
    if raw.is_absolute():
        return raw.resolve()
    return (PROJECT_ROOT / raw).resolve()


def _resolve_ffmpeg_exe(ffmpeg_arg: str) -> Path | None:
    if not ffmpeg_arg.strip():
        return None
    p = _resolve_under_project(ffmpeg_arg)
    return p if p.is_file() else None


def _subprocess_kwargs_windows() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    return kwargs


def _ffplay_launch_kwargs_windows() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32":
        # Detach ffplay from console host (Windows Terminal/conhost) but keep its SDL video window.
        detached = getattr(subprocess, "DETACHED_PROCESS", 0x00000008)
        kwargs["creationflags"] = detached
    return kwargs


def _unblock_motw(path: str) -> None:
    if sys.platform != "win32":
        return
    try:
        os.remove(path + ":Zone.Identifier")
    except OSError:
        pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--path", required=True, help="Video file (e.g. .mp4)")
    p.add_argument("--ffmpeg", default="", help="Path to ffmpeg.exe; ffplay.exe is beside it")
    p.add_argument("--pid-file", default="", help="Path to write the ffplay process ID")
    p.add_argument("--wait", action="store_true", help="Wait until playback ends")
    p.add_argument("--no-autoexit", action="store_true", help="Keep ffplay window open after media end")
    args = p.parse_args()
    video = _resolve_under_project(args.path.strip())
    if not video.is_file():
        print(f"Video not found: {video}", file=sys.stderr)
        sys.exit(1)
    _unblock_motw(str(video))

    ffmpeg_exe = _resolve_ffmpeg_exe(args.ffmpeg)
    ffplay = resolve_ffplay(args.ffmpeg, PROJECT_ROOT)
    if not ffplay and args.ffmpeg.strip():
        print(ffplay_hint_stderr(), file=sys.stderr)
    if ffplay:
        # Do not force CREATE_NO_WINDOW for ffplay itself; it can suppress or destabilize the video window.
        kwargs_ffplay = _ffplay_launch_kwargs_windows()
        cmd = [str(ffplay), "-hide_banner", "-loglevel", "quiet"]
        if not args.no_autoexit:
            cmd.append("-autoexit")
        cmd.append(str(video))
        proc = subprocess.Popen(
            cmd,
            cwd=str(video.parent),
            **kwargs_ffplay,
        )
        if args.pid_file:
            pid_path = _resolve_under_project(args.pid_file)
            pid_path.parent.mkdir(parents=True, exist_ok=True)
            pid_path.write_text(str(proc.pid), encoding="utf-8")
        if args.wait:
            rc = proc.wait(timeout=86400)
            sys.exit(rc if rc is not None else 0)
        sys.exit(0)

    # Fallback without ffplay: use shell-open directly to avoid spawning terminal windows.
    if sys.platform == "win32":
        os.startfile(str(video))
        if args.wait:
            # No reliable process handle from startfile; keep a conservative grace delay.
            time.sleep(1.0)
        sys.exit(0)

    os.startfile(str(video))
    sys.exit(0)


if __name__ == "__main__":
    main()
