"""Mux one slide image + narration WAV into a short H.264/AAC MP4 (one segment for later concat)."""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
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


def _safe_print(message: str, *, is_error: bool = False) -> None:
    stream = sys.stderr if is_error else sys.stdout
    text = message + "\n"
    try:
        stream.write(text)
        stream.flush()
    except UnicodeEncodeError:
        encoding = getattr(stream, "encoding", None) or "utf-8"
        payload = text.encode(encoding, errors="backslashreplace")
        buffer = getattr(stream, "buffer", None)
        if buffer is not None:
            try:
                buffer.write(payload)
                buffer.flush()
            except Exception:
                pass


def _decode_bytes(payload: bytes | None) -> str:
    return (payload or b"").decode("utf-8", errors="replace")


def _write_err_log(err_log: Path, content: str) -> None:
    try:
        err_log.write_text(content, encoding="utf-8")
    except OSError:
        pass


def _unblock_mark_of_web(path: Path) -> None:
    if sys.platform != "win32":
        return
    try:
        os.remove(str(path) + ":Zone.Identifier")
    except OSError:
        pass


def _valid_output(path: Path) -> bool:
    return path.is_file() and path.stat().st_size >= 100


def _resolve_ffmpeg_exe(ffmpeg_arg: str) -> Path | None:
    raw_value = ffmpeg_arg.strip()
    if raw_value:
        raw = Path(raw_value)
        p = raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()
        if p.is_file():
            return p

    bundled = PROJECT_ROOT / "Data" / "AIPresenter" / "Tools" / "ffmpeg.exe"
    if bundled.is_file():
        return bundled.resolve()

    for name in ("ffmpeg.exe", "ffmpeg"):
        found = shutil.which(name)
        if found:
            p = Path(found)
            if p.is_file():
                return p.resolve()

    return None


def _resolve_media(p: str) -> Path:
    raw = Path(p.strip())
    if raw.is_file():
        return raw.resolve()
    if raw.is_absolute():
        return raw.resolve()
    return (PROJECT_ROOT / raw).resolve()


def _ffprobe_path(ffmpeg_exe: Path) -> Path | None:
    cand = ffmpeg_exe.parent / "ffprobe.exe"
    return cand if cand.is_file() else None


def _duration_seconds_ffprobe(ffprobe_exe: Path, media: Path) -> float | None:
    try:
        r = subprocess.run(
            [
                str(ffprobe_exe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(media),
            ],
            capture_output=True,
            timeout=120,
            check=False,
            **_subprocess_kwargs_windows(),
        )
        if r.returncode != 0:
            return None
        line = (r.stdout or b"").decode("utf-8", errors="replace").strip().splitlines()
        if not line:
            return None
        return float(line[0].strip())
    except (ValueError, OSError):
        return None


def _duration_seconds_wave_pcm(audio: Path) -> float | None:
    try:
        import wave

        with wave.open(str(audio), "rb") as w:
            return w.getnframes() / float(w.getframerate())
    except Exception:
        return None


def _ensure_ffmpeg_runnable(ffmpeg_exe: Path, err_log: Path) -> bool:
    kwargs = _subprocess_kwargs_windows()
    _unblock_mark_of_web(ffmpeg_exe)
    ffprobe = ffmpeg_exe.parent / "ffprobe.exe"
    if ffprobe.is_file():
        _unblock_mark_of_web(ffprobe)

    try:
        r = subprocess.run(
            [str(ffmpeg_exe), "-hide_banner", "-version"],
            capture_output=True,
            timeout=30,
            check=False,
            **kwargs,
        )
    except OSError as e:
        _write_err_log(
            err_log,
            (
                "ffmpeg preflight execution failed.\n"
                f"ffmpeg_path={ffmpeg_exe}\n"
                f"os_error={e!r}\n"
                "Possible causes: AppLocker/Defender policy block, missing execute permission, or invalid binary."
            ),
        )
        _safe_print(
            f"ffmpeg.exe was found but could not execute (possible policy/security block). See {err_log}",
            is_error=True,
        )
        return False

    stdout_text = _decode_bytes(r.stdout)
    stderr_text = _decode_bytes(r.stderr)
    if r.returncode != 0:
        _write_err_log(
            err_log,
            (
                "ffmpeg preflight returned non-zero.\n"
                f"ffmpeg_path={ffmpeg_exe}\n"
                f"returncode={r.returncode}\n"
                "=== stdout ===\n"
                f"{stdout_text}\n\n"
                "=== stderr ===\n"
                f"{stderr_text}"
            ),
        )
        _safe_print(
            f"ffmpeg.exe failed preflight check (-version, rc={r.returncode}). See {err_log}",
            is_error=True,
        )
        return False

    return True


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--image", required=True)
    p.add_argument("--audio", required=True)
    p.add_argument("--out", required=True, help="Output .mp4 path")
    p.add_argument("--ffmpeg", default="", help="Path to ffmpeg.exe (relative to project or absolute)")
    p.add_argument(
        "--append-manifest",
        default="",
        help="If set, append absolute path of output .mp4 to this file (one line)",
    )
    args = p.parse_args()

    ffmpeg_exe = _resolve_ffmpeg_exe(args.ffmpeg)
    if not ffmpeg_exe:
        _safe_print(
            "ffmpeg.exe not found (checked --ffmpeg value, Data/AIPresenter/Tools, and PATH).",
            is_error=True,
        )
        sys.exit(1)

    image = _resolve_media(args.image)
    audio = _resolve_media(args.audio)
    out = _resolve_media(args.out)
    if not image.is_file():
        _safe_print(f"Image not found: {image}", is_error=True)
        sys.exit(2)
    if not audio.is_file():
        _safe_print(f"Audio not found: {audio}", is_error=True)
        sys.exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)
    err_log = out.parent / (out.stem + "_ffmpeg_mux_stderr.txt")

    if not _ensure_ffmpeg_runnable(ffmpeg_exe, err_log):
        sys.exit(1)

    # Drive output length from narration audio. Using only -shortest with -loop 1 still image
    # can truncate audio on some FFmpeg builds (video track seen as shorter than WAV).
    ffprobe = _ffprobe_path(ffmpeg_exe)
    dur: float | None = None
    if ffprobe:
        dur = _duration_seconds_ffprobe(ffprobe, audio)
    if dur is None or dur <= 0:
        dur = _duration_seconds_wave_pcm(audio)
    if dur is None or dur <= 0:
        _safe_print(
            "Could not read audio duration (ffprobe/wave); mux may be wrong. Install ffprobe next to ffmpeg.",
            is_error=True,
        )
        dur = None
    else:
        # Small pad so AAC/encoder tail and TTS fade do not clip the last words
        dur = dur + 2.0

    vf = (
        "scale=1920:1080:force_original_aspect_ratio=decrease,"
        "pad=1920:1080:(ow-iw)/2:(oh-ih)/2,format=yuv420p"
    )
    head = [
        str(ffmpeg_exe),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-loop",
        "1",
        "-framerate",
        "1",
        "-i",
        str(image),
        "-i",
        str(audio),
        "-vf",
        vf,
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
    ]
    h264_v = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"]
    mpeg4_v = ["-c:v", "mpeg4", "-q:v", "5"]
    tail = [
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-ac",
        "2",
    ]
    if dur is not None:
        tail.extend(["-t", f"{dur:.6f}"])
    else:
        tail.append("-shortest")
    tail.extend(["-movflags", "+faststart", str(out)])
    kwargs = _subprocess_kwargs_windows()
    def run_mux(video_codec_args: list[str]) -> tuple[subprocess.CompletedProcess | None, str]:
        cmd = head + video_codec_args + tail
        try:
            return (
                subprocess.run(
                    cmd,
                    cwd=str(out.parent),
                    timeout=3600,
                    check=False,
                    capture_output=True,
                    **kwargs,
                ),
                "",
            )
        except OSError as e:
            return None, f"{type(e).__name__}: {e!r}"

    r, exec_err1 = run_mux(h264_v)
    first_failed = bool(exec_err1) or (r is None) or (r.returncode != 0) or (not _valid_output(out))
    if first_failed:
        r2, exec_err2 = run_mux(mpeg4_v)
        stderr_text = _decode_bytes(r.stderr if r is not None else None)
        stderr2 = _decode_bytes(r2.stderr if r2 is not None else None)

        details: list[str] = []
        if exec_err1:
            details.append(f"=== libx264 launch error ===\n{exec_err1}")
        if r is not None:
            details.append(f"=== libx264 returncode ===\n{r.returncode}")
            details.append(f"=== libx264 stderr ===\n{stderr_text}")
        if exec_err2:
            details.append(f"=== mpeg4 launch error ===\n{exec_err2}")
        if r2 is not None:
            details.append(f"=== mpeg4 returncode ===\n{r2.returncode}")
            details.append(f"=== mpeg4 stderr ===\n{stderr2}")
        _write_err_log(err_log, "\n\n".join(details).strip())

        second_failed = bool(exec_err2) or (r2 is None) or (r2.returncode != 0) or (not _valid_output(out))
        if second_failed:
            first_lines = stderr_text[:800] if stderr_text else (exec_err1 or exec_err2 or "No ffmpeg stderr.")
            _safe_print(
                f"ffmpeg mux failed (see {err_log}). First error lines:\n{first_lines}",
                is_error=True,
            )
            sys.exit(3)

    if args.append_manifest.strip():
        man = Path(args.append_manifest.strip())
        if not man.is_absolute():
            man = (PROJECT_ROOT / man).resolve()
        man.parent.mkdir(parents=True, exist_ok=True)
        line = str(out.resolve()).replace("\\", "/") + "\n"
        with open(man, "a", encoding="utf-8") as f:
            f.write(line)
    _safe_print(f"OK segment={out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
