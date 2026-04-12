"""Open a file with the Windows default application (no console). Stdlib only."""
from __future__ import annotations

import argparse
import os
import sys


def _unblock_mark_of_web_win32(path: str) -> None:
    """Remove Mark of the Web (Zone.Identifier ADS) so Explorer does not prompt."""
    if sys.platform != "win32":
        return
    zone = path + ":Zone.Identifier"
    try:
        os.remove(zone)
    except OSError:
        pass


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--path", required=True, help="File to open (e.g. slide .mp4)")
    args = p.parse_args()
    path = os.path.normpath(args.path.strip())
    if not path or not os.path.isfile(path):
        print(f"File not found: {path!r}", file=sys.stderr)
        sys.exit(1)
    _unblock_mark_of_web_win32(path)
    os.startfile(path)
    sys.exit(0)


if __name__ == "__main__":
    main()
