"""
Play response WAV and block until playback ends (no overlapping MessageBox in UiPath).

1) ffplay.exe next to ffmpeg.exe: ffplay -nodisp -autoexit (preferred).
2) Else Windows winsound on PCM 16-bit WAV.
3) Else if ffmpeg.exe is available: transcode to PCM WAV then winsound.
4) Else: sleep for estimated duration (last resort).

Paths like Data\\...\\ffmpeg.exe are resolved from the project root (same folder as Data/),
so playback still works when the Python process cwd is not the project folder.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
import tempfile
import time
import wave
from pathlib import Path

from ffplay_locate import ffplay_hint_stderr, resolve_ffplay

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent


def _subprocess_kwargs_windows() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    return kwargs


def _resolve_under_project(p: str) -> Path:
    raw = Path(p.strip())
    if raw.is_file():
        return raw.resolve()
    if raw.is_absolute():
        out = raw.resolve()
        return out if out.is_file() else out
    return (PROJECT_ROOT / raw).resolve()


def _resolve_ffmpeg_exe(ffmpeg_arg: str) -> Path | None:
    if not ffmpeg_arg.strip():
        return None
    p = _resolve_under_project(ffmpeg_arg)
    return p if p.is_file() else None


def _wav_duration_seconds(wav: Path) -> float:
    with wave.open(str(wav), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def _duration_via_ffmpeg_stderr(ffmpeg_exe: Path, media: Path) -> float | None:
    kwargs = _subprocess_kwargs_windows()
    r = subprocess.run(
        [str(ffmpeg_exe), "-hide_banner", "-i", str(media), "-f", "null", "-"],
        capture_output=True,
        timeout=120,
        check=False,
        **kwargs,
    )
    text = (r.stderr or b"").decode("utf-8", errors="replace")
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)", text)
    if not m:
        return None
    h, s_sec, frac = int(m.group(1)), int(m.group(2)), float(m.group(3))
    return h * 3600 + s_sec * 60 + frac


def _transcode_to_pcm_wav(ffmpeg_exe: Path, src: Path) -> Path | None:
    tmp_dir = PROJECT_ROOT / "Data" / "AIPresenter" / "Temp"
    tmp_dir.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".wav", dir=str(tmp_dir))
    os.close(fd)
    out = Path(tmp)
    kwargs = _subprocess_kwargs_windows()
    r = subprocess.run(
        [
            str(ffmpeg_exe),
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(src),
            "-acodec",
            "pcm_s16le",
            "-ar",
            "44100",
            "-ac",
            "1",
            str(out),
        ],
        cwd=str(src.parent),
        timeout=600,
        check=False,
        **kwargs,
    )
    if r.returncode == 0 and out.is_file() and out.stat().st_size > 0:
        return out
    try:
        out.unlink(missing_ok=True)
    except OSError:
        pass
    return None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--wav", required=True)
    p.add_argument(
        "--ffmpeg",
        default="",
        help="Path to ffmpeg.exe (relative to project root or absolute); ffplay.exe beside it",
    )
    args = p.parse_args()

    wav = _resolve_under_project(args.wav)
    if not wav.is_file():
        sys.exit(0)

    ffmpeg_exe = _resolve_ffmpeg_exe(args.ffmpeg)

    ffplay = resolve_ffplay(args.ffmpeg, PROJECT_ROOT)
    if not ffplay and args.ffmpeg.strip():
        print(ffplay_hint_stderr(), file=sys.stderr)

    if ffplay:
        kwargs = _subprocess_kwargs_windows()
        r = subprocess.run(
            [
                str(ffplay),
                "-hide_banner",
                "-loglevel",
                "quiet",
                "-nodisp",
                "-autoexit",
                str(wav),
            ],
            cwd=str(wav.parent),
            timeout=3600,
            check=False,
            **kwargs,
        )
        sys.exit(r.returncode if r.returncode is not None else 0)

    played = False
    if sys.platform == "win32":
        try:
            import winsound

            winsound.PlaySound(str(wav), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
            played = True
        except Exception:
            played = False

        if not played and ffmpeg_exe:
            pcm = _transcode_to_pcm_wav(ffmpeg_exe, wav)
            if pcm is not None:
                try:
                    import winsound

                    winsound.PlaySound(str(pcm), winsound.SND_FILENAME | winsound.SND_NODEFAULT)
                    played = True
                except Exception:
                    played = False
                try:
                    pcm.unlink(missing_ok=True)
                except OSError:
                    pass

        if played:
            sys.exit(0)

    d: float | None = None
    try:
        d = _wav_duration_seconds(wav)
    except Exception:
        d = None
    if d is None and ffmpeg_exe:
        d = _duration_via_ffmpeg_stderr(ffmpeg_exe, wav)
    if d is None or d <= 0:
        d = 5.0
    time.sleep(min(d + 0.75, 600.0))
    sys.exit(0)


if __name__ == "__main__":
    main()
