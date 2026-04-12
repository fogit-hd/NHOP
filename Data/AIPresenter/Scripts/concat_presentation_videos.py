"""Concatenate slide segment MP4s (same codec) into one presentation_full.mp4."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

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


def _resolve_ffmpeg_exe(ffmpeg_arg: str) -> Path | None:
    if not ffmpeg_arg.strip():
        return None
    raw = Path(ffmpeg_arg.strip())
    p = raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()
    return p if p.is_file() else None


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--manifest", required=True, help="segments_manifest.txt (one absolute .mp4 path per line)")
    p.add_argument("--out", required=True, help="Output e.g. Data/AIPresenter/Output/presentation_full.mp4")
    p.add_argument("--ffmpeg", default="", help="Path to ffmpeg.exe")
    args = p.parse_args()

    ffmpeg_exe = _resolve_ffmpeg_exe(args.ffmpeg)
    if not ffmpeg_exe:
        print("ffmpeg.exe not found.", file=sys.stderr)
        sys.exit(1)

    man = Path(args.manifest.strip())
    if not man.is_absolute():
        man = (PROJECT_ROOT / man).resolve()
    if not man.is_file():
        print(f"Manifest not found: {man}", file=sys.stderr)
        sys.exit(2)

    lines = [ln.strip() for ln in man.read_text(encoding="utf-8").splitlines() if ln.strip()]
    paths: list[Path] = []
    for ln in lines:
        fp = Path(ln)
        if not fp.is_file():
            print(f"Skip missing segment: {fp}", file=sys.stderr)
            continue
        paths.append(fp.resolve())
    if not paths:
        print("No valid segment files in manifest; skip concat.", file=sys.stderr)
        sys.exit(0)

    out = Path(args.out.strip())
    if not out.is_absolute():
        out = (PROJECT_ROOT / out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    # ffmpeg concat demuxer: file 'C:/path/file.mp4' per line
    concat_lines = "".join(f"file '{p.as_posix()}'\n" for p in paths)
    tmp_dir = out.parent
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix="_concat.txt",
        delete=False,
        dir=str(tmp_dir),
    ) as tf:
        tf.write(concat_lines)
        list_path = Path(tf.name)

    kwargs = _subprocess_kwargs_windows()
    cmd = [
        str(ffmpeg_exe),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(list_path),
        "-c",
        "copy",
        str(out),
    ]
    try:
        r = subprocess.run(cmd, cwd=str(out.parent), timeout=7200, check=False, **kwargs)
    finally:
        try:
            list_path.unlink(missing_ok=True)
        except OSError:
            pass

    if r.returncode != 0 or not out.is_file() or out.stat().st_size < 100:
        print("Concat failed.", file=sys.stderr)
        sys.exit(3)
    print(f"OK full_presentation={out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
