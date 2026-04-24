"""Check whether ffmpeg/ffprobe can execute on this machine.

Usage:
  py Data\\AIPresenter\\Scripts\\ffmpeg_preflight_check.py --root "%CD%"
  py Data\\AIPresenter\\Scripts\\ffmpeg_preflight_check.py --root "%CD%" --ffmpeg "Data\\AIPresenter\\Tools\\ffmpeg.exe"
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent


def _safe_print(message: str, *, is_error: bool = False) -> None:
    stream = sys.stderr if is_error else sys.stdout
    text = message + "\n"
    try:
        stream.write(text)
        stream.flush()
        return
    except UnicodeEncodeError:
        pass
    encoding = getattr(stream, "encoding", None) or "utf-8"
    payload = text.encode(encoding, errors="backslashreplace")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        try:
            buffer.write(payload)
            buffer.flush()
        except Exception:
            pass


def _subprocess_kwargs_windows() -> dict:
    kwargs: dict = {}
    if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
        si = subprocess.STARTUPINFO()
        si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        si.wShowWindow = 0
        kwargs["startupinfo"] = si
    return kwargs


def _decode_bytes(payload: bytes | None) -> str:
    return (payload or b"").decode("utf-8", errors="replace")


def _resolve_under_root(root: Path, value: str) -> Path:
    raw = Path((value or "").strip())
    if raw.is_absolute():
        return raw.resolve()
    return (root / raw).resolve()


def _load_ffmpeg_from_settings(root: Path) -> str:
    cfg = root / "Data" / "AIPresenter" / "Config" / "ai_settings.json"
    if not cfg.is_file():
        return ""
    try:
        with open(cfg, encoding="utf-8-sig") as f:
            data = json.load(f)
        return str(data.get("ffmpeg_path") or "").strip()
    except Exception:
        return ""


def _resolve_ffmpeg_exe(root: Path, ffmpeg_arg: str) -> Path | None:
    if ffmpeg_arg.strip():
        p = _resolve_under_root(root, ffmpeg_arg)
        if p.is_file():
            return p

    cfg_value = _load_ffmpeg_from_settings(root)
    if cfg_value:
        p = _resolve_under_root(root, cfg_value)
        if p.is_file():
            return p

    bundled = root / "Data" / "AIPresenter" / "Tools" / "ffmpeg.exe"
    if bundled.is_file():
        return bundled.resolve()

    for name in ("ffmpeg.exe", "ffmpeg"):
        found = shutil.which(name)
        if found:
            p = Path(found)
            if p.is_file():
                return p.resolve()
    return None


def _zone_identifier_exists(path: Path) -> bool:
    if sys.platform != "win32":
        return False
    try:
        with open(str(path) + ":Zone.Identifier", "r", encoding="utf-8", errors="replace"):
            return True
    except OSError:
        return False


def _run_command(cmd: list[str], timeout: int = 45) -> tuple[int, str, str, str]:
    kwargs = _subprocess_kwargs_windows()
    try:
        r = subprocess.run(
            cmd,
            capture_output=True,
            timeout=timeout,
            check=False,
            **kwargs,
        )
        return int(r.returncode), _decode_bytes(r.stdout), _decode_bytes(r.stderr), ""
    except OSError as e:
        return -1, "", "", f"{type(e).__name__}: {e!r}"
    except subprocess.TimeoutExpired as e:
        return -2, _decode_bytes(e.stdout), _decode_bytes(e.stderr), "TimeoutExpired"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=str(PROJECT_ROOT))
    p.add_argument("--ffmpeg", default="")
    args = p.parse_args()

    root = Path(args.root).resolve()
    temp_dir = root / "Data" / "AIPresenter" / "Temp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    report = temp_dir / "ffmpeg_preflight_report.txt"
    lines: list[str] = []

    ffmpeg_exe = _resolve_ffmpeg_exe(root, args.ffmpeg)
    if not ffmpeg_exe:
        msg = "FAIL ffmpeg.exe not found (checked args, ai_settings.json, Tools, PATH)."
        lines.append(msg)
        report.write_text("\n".join(lines) + "\n", encoding="utf-8")
        _safe_print(msg, is_error=True)
        _safe_print(f"Report: {report}")
        sys.exit(1)

    lines.append(f"ffmpeg_path={ffmpeg_exe}")
    lines.append(f"ffmpeg_zone_identifier={_zone_identifier_exists(ffmpeg_exe)}")

    ffprobe = ffmpeg_exe.parent / "ffprobe.exe"
    lines.append(f"ffprobe_path={ffprobe if ffprobe.is_file() else '(missing)'}")
    if ffprobe.is_file():
        lines.append(f"ffprobe_zone_identifier={_zone_identifier_exists(ffprobe)}")

    rc, out, err, launch_err = _run_command([str(ffmpeg_exe), "-hide_banner", "-version"], timeout=30)
    lines.append(f"ffmpeg_version_rc={rc}")
    if launch_err:
        lines.append(f"ffmpeg_version_launch_error={launch_err}")
    if out.strip():
        lines.append("=== ffmpeg -version stdout ===")
        lines.append(out.strip())
    if err.strip():
        lines.append("=== ffmpeg -version stderr ===")
        lines.append(err.strip())

    if ffprobe.is_file():
        rc_probe, out_probe, err_probe, launch_err_probe = _run_command(
            [str(ffprobe), "-hide_banner", "-version"],
            timeout=30,
        )
        lines.append(f"ffprobe_version_rc={rc_probe}")
        if launch_err_probe:
            lines.append(f"ffprobe_version_launch_error={launch_err_probe}")
        if out_probe.strip():
            lines.append("=== ffprobe -version stdout ===")
            lines.append(out_probe.strip())
        if err_probe.strip():
            lines.append("=== ffprobe -version stderr ===")
            lines.append(err_probe.strip())

    test_out = temp_dir / "ffmpeg_preflight_test.mp4"
    test_cmd = [
        str(ffmpeg_exe),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "lavfi",
        "-i",
        "color=c=black:s=640x360:d=1",
        "-f",
        "lavfi",
        "-i",
        "anullsrc=r=44100:cl=stereo",
        "-shortest",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "30",
        "-c:a",
        "aac",
        str(test_out),
    ]
    rc_mux, out_mux, err_mux, launch_err_mux = _run_command(test_cmd, timeout=60)
    lines.append(f"ffmpeg_mux_test_rc={rc_mux}")
    if launch_err_mux:
        lines.append(f"ffmpeg_mux_test_launch_error={launch_err_mux}")
    if out_mux.strip():
        lines.append("=== ffmpeg mux test stdout ===")
        lines.append(out_mux.strip())
    if err_mux.strip():
        lines.append("=== ffmpeg mux test stderr ===")
        lines.append(err_mux.strip())
    lines.append(f"ffmpeg_mux_test_output_exists={test_out.is_file()}")
    if test_out.is_file():
        lines.append(f"ffmpeg_mux_test_output_size={test_out.stat().st_size}")

    report.write_text("\n".join(lines) + "\n", encoding="utf-8")
    _safe_print(f"Report: {report}")

    ok = rc == 0 and rc_mux == 0 and test_out.is_file() and test_out.stat().st_size > 100
    if ok:
        _safe_print("OK ffmpeg preflight passed.")
        sys.exit(0)

    _safe_print("FAIL ffmpeg preflight failed. Open report for details.", is_error=True)
    sys.exit(1)


if __name__ == "__main__":
    main()
