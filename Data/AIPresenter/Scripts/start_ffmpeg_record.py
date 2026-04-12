"""
Start ffmpeg with no visible console (Windows). Writes child PID to a text file.

IMPORTANT: Do not use shlex.split() on the full arg line — on Windows it incorrectly
splits dshow device names like audio="Headset (Buds2 ...)" at parentheses inside
the quotes, which breaks ffmpeg and yields missing/empty WAV files.

We parse the project-specific layout: -y -f dshow -i audio="<device>" -loglevel ...
Stdlib only.
"""
from __future__ import annotations

import argparse
import os
import re
import shlex
import subprocess
import sys

# Our UiPath-built line (see AIInteractivePresenter Assign_FfmpegArgLine)
_ARG_PATTERN = re.compile(
    r"^-y\s+-f\s+dshow\s+-i\s+audio=\"(?P<dev>.+?)\"\s+"
    r"-loglevel\s+error\s+-ac\s+1\s+-ar\s+16000\s+-c:a\s+pcm_s16le\s+\"(?P<wav>.+)\"\s*$",
    re.DOTALL,
)


def _argv_from_argline(exe: str, argline: str) -> list[str]:
    argline = argline.strip()
    m = _ARG_PATTERN.match(argline)
    if m:
        dev = m.group("dev")
        wav = m.group("wav")
        # One argv for dshow: audio=<device> — list form avoids shell quoting bugs with "(" in name
        return [
            exe,
            "-y",
            "-f",
            "dshow",
            "-i",
            f"audio={dev}",
            "-loglevel",
            "error",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            wav,
        ]
    # Fallback for custom arg lines (may still break on exotic dshow names)
    return [exe] + shlex.split(argline, posix=False)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--exe-file", required=True, help="Text file: full path to ffmpeg.exe (one line)")
    p.add_argument("--arg-file", required=True, help="Text file: full ffmpeg argument string (one line)")
    p.add_argument("--pid-file", required=True, help="Output: write child PID as ASCII text")
    p.add_argument("--working-directory", required=True, help="Process working directory")
    args = p.parse_args()

    with open(args.exe_file, encoding="utf-8", errors="replace") as f:
        exe = f.read().strip()
    with open(args.arg_file, encoding="utf-8", errors="replace") as f:
        argline = f.read().strip()

    if not exe or not os.path.isfile(exe):
        print(f"ffmpeg not found: {exe!r}", file=sys.stderr)
        sys.exit(1)

    os.chdir(args.working_directory)

    try:
        argv = _argv_from_argline(exe, argline)
    except ValueError as e:
        print(f"Bad arg line: {e}", file=sys.stderr)
        sys.exit(1)

    kwargs: dict = {
        "cwd": args.working_directory,
    }
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0  # SW_HIDE
        kwargs["startupinfo"] = si

    proc = subprocess.Popen(argv, **kwargs)
    with open(args.pid_file, "w", encoding="ascii", newline="") as out:
        out.write(str(proc.pid))


if __name__ == "__main__":
    main()
