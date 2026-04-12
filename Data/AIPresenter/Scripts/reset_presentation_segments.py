"""Clear segment folder and manifest before a new presentation run."""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default="", help="Project root (UiPath Environment.CurrentDirectory)")
    args = p.parse_args()
    root = Path(args.root.strip() or Path.cwd()).resolve()
    seg_dir = root / "Data" / "AIPresenter" / "Temp" / "segments"
    manifest = root / "Data" / "AIPresenter" / "Temp" / "segments_manifest.txt"
    try:
        if seg_dir.is_dir():
            shutil.rmtree(seg_dir)
        seg_dir.mkdir(parents=True, exist_ok=True)
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text("", encoding="utf-8")
    except OSError as e:
        print(f"reset_presentation_segments: {e}", file=sys.stderr)
        sys.exit(1)
    print(f"OK cleared segments -> {seg_dir}")
    sys.exit(0)


if __name__ == "__main__":
    main()
