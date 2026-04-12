"""Write the friendly name of the default Windows capture device (for FFmpeg dshow).

This overwrites the output file each time it runs. The path is only a runtime cache,
not a hand-edited config — set microphone_name to default in ai_settings.json for portability.

Requires: py -m pip install pycaw
"""
import sys
from pathlib import Path


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: resolve_default_microphone.py <output_txt_path>", file=sys.stderr)
        sys.exit(2)
    out = Path(sys.argv[1])
    try:
        from pycaw.pycaw import AudioUtilities
    except ImportError:
        print("Missing dependency. Run: py -m pip install pycaw", file=sys.stderr)
        sys.exit(1)
    mic = AudioUtilities.GetMicrophone()
    dev = AudioUtilities.CreateDevice(mic)
    if dev is None or not dev.FriendlyName:
        print("Could not resolve default microphone.", file=sys.stderr)
        sys.exit(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(dev.FriendlyName.strip(), encoding="utf-8")


if __name__ == "__main__":
    main()
