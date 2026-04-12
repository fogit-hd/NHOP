"""Print whether ffplay.exe can be found (same rules as play_response_audio / play_video_blocking).

Run from project folder:
  py Data\\AIPresenter\\Scripts\\check_ffplay.py
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

from ffplay_locate import ffplay_hint_stderr, resolve_ffplay


def main() -> None:
    os.chdir(PROJECT_ROOT)
    ffmpeg_arg = ""
    settings = PROJECT_ROOT / "Data" / "AIPresenter" / "Config" / "ai_settings.json"
    if settings.is_file():
        try:
            cfg = json.loads(settings.read_text(encoding="utf-8-sig"))
            ffmpeg_arg = (cfg.get("ffmpeg_path") or "").strip()
        except (OSError, json.JSONDecodeError):
            pass

    ff = resolve_ffplay(ffmpeg_arg, PROJECT_ROOT)
    if ff and ff.is_file():
        print(f"OK: ffplay found -> {ff}")
        sys.exit(0)
    print("NOT FOUND: ffplay.exe was not resolved.")
    print(ffplay_hint_stderr())
    sys.exit(1)


if __name__ == "__main__":
    main()
