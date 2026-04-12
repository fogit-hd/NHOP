"""Measure WAV duration in seconds.

Supports:
- positional: wav_duration_seconds.py <wav_path>
- flags: wav_duration_seconds.py --wav <wav_path> [--out <result_file>]
"""
from __future__ import annotations

import argparse
import re
import os
import subprocess
import sys
import time
import wave


def _subprocess_kwargs_windows() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    return kwargs


def _duration_via_ffmpeg(path: str, ffmpeg: str) -> str:
    exe = ffmpeg.strip()
    if not exe:
        return "0"
    if not os.path.isabs(exe):
        exe = os.path.normpath(exe)
    if not os.path.isfile(exe):
        return "0"
    kwargs = _subprocess_kwargs_windows()
    try:
        r = subprocess.run(
            [exe, "-hide_banner", "-i", path, "-f", "null", "-"],
            capture_output=True,
            timeout=30,
            check=False,
            **kwargs,
        )
        text = (r.stderr or b"").decode("utf-8", errors="replace")
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
        if not m:
            return "0"
        h = int(m.group(1))
        mnt = int(m.group(2))
        sec = float(m.group(3))
        return f"{h * 3600 + mnt * 60 + sec:.6f}"
    except Exception:
        return "0"


def _duration_text(path: str, ffmpeg: str = "") -> str:
    if not path or not os.path.isfile(path):
        return "0"
    # TTS writers can return before file metadata fully settles; retry briefly.
    for _ in range(5):
        try:
            with wave.open(path, "rb") as w:
                frames = w.getnframes()
                rate = float(w.getframerate() or 1)
                if frames > 0 and rate > 0:
                    return f"{frames / rate:.6f}"
        except Exception:
            pass
        fallback = _duration_via_ffmpeg(path, ffmpeg)
        if fallback != "0":
            return fallback
        time.sleep(0.2)
    return "0"


def main() -> None:
    p = argparse.ArgumentParser(add_help=False)
    p.add_argument("positional_wav", nargs="?")
    p.add_argument("--wav", dest="wav", default="")
    p.add_argument("--out", dest="out", default="")
    p.add_argument("--ffmpeg", dest="ffmpeg", default="")
    args, _ = p.parse_known_args()

    wav = (args.wav or args.positional_wav or "").strip()
    value = _duration_text(wav, args.ffmpeg)

    if args.out.strip():
        out = os.path.normpath(args.out.strip())
        folder = os.path.dirname(out)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(out, "w", encoding="ascii", newline="") as f:
            f.write(value)

    print(value)


if __name__ == "__main__":
    main()
