"""Mux one slide image + narration WAV into a short H.264/AAC MP4 (one segment for later concat)."""
from __future__ import annotations

import argparse
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


def _resolve_ffmpeg_exe(ffmpeg_arg: str) -> Path | None:
    if not ffmpeg_arg.strip():
        return None
    raw = Path(ffmpeg_arg.strip())
    p = raw if raw.is_absolute() else (PROJECT_ROOT / raw).resolve()
    return p if p.is_file() else None


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
        print("ffmpeg.exe not found (check --ffmpeg / ai_settings.json).", file=sys.stderr)
        sys.exit(1)

    image = _resolve_media(args.image)
    audio = _resolve_media(args.audio)
    out = _resolve_media(args.out)
    if not image.is_file():
        print(f"Image not found: {image}", file=sys.stderr)
        sys.exit(2)
    if not audio.is_file():
        print(f"Audio not found: {audio}", file=sys.stderr)
        sys.exit(2)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Drive output length from narration audio. Using only -shortest with -loop 1 still image
    # can truncate audio on some FFmpeg builds (video track seen as shorter than WAV).
    ffprobe = _ffprobe_path(ffmpeg_exe)
    dur: float | None = None
    if ffprobe:
        dur = _duration_seconds_ffprobe(ffprobe, audio)
    if dur is None or dur <= 0:
        dur = _duration_seconds_wave_pcm(audio)
    if dur is None or dur <= 0:
        print(
            "Could not read audio duration (ffprobe/wave); mux may be wrong. Install ffprobe next to ffmpeg.",
            file=sys.stderr,
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
    err_log = out.parent / (out.stem + "_ffmpeg_mux_stderr.txt")

    def run_mux(video_codec_args: list[str]) -> subprocess.CompletedProcess:
        cmd = head + video_codec_args + tail
        return subprocess.run(
            cmd,
            cwd=str(out.parent),
            timeout=3600,
            check=False,
            capture_output=True,
            **kwargs,
        )

    r = run_mux(h264_v)
    if r.returncode != 0 or not out.is_file() or out.stat().st_size < 100:
        r2 = run_mux(mpeg4_v)
        stderr_text = (r.stderr or b"").decode("utf-8", errors="replace")
        stderr2 = (r2.stderr or b"").decode("utf-8", errors="replace")
        try:
            err_log.write_text(
                "=== libx264 attempt ===\n" + stderr_text + "\n\n=== mpeg4 fallback ===\n" + stderr2,
                encoding="utf-8",
            )
        except OSError:
            pass
        if r2.returncode != 0 or not out.is_file() or out.stat().st_size < 100:
            print(
                f"ffmpeg mux failed (see {err_log}). First error lines:\n{stderr_text[:800]}",
                file=sys.stderr,
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
    print(f"OK segment={out}")
    sys.exit(0)


if __name__ == "__main__":
    main()
