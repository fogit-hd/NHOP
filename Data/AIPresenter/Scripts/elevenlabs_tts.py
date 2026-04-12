"""
ElevenLabs text-to-speech (stdlib urllib). Reads text/key/voice/output path from temp files when args omitted.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


# Strip lone UTF-16 surrogates (same intent as PowerShell script)
_SUR = re.compile(
    "[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]"
)


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace").strip()


def clean_tts_text(text: str) -> str:
    if not text:
        return ""
    return _SUR.sub("", text).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--voice-id", default="")
    parser.add_argument("--output-audio", default="")
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent
    temp_dir = script_dir.parent / "Temp"
    history_root = temp_dir / "History"
    history_root.mkdir(parents=True, exist_ok=True)
    cfg_path = script_dir.parent / "Config" / "api_runtime.json"

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    run_dir = history_root / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output_result = Path(args.output_path) if args.output_path else temp_dir / "tts_result.txt"
    output_result.parent.mkdir(parents=True, exist_ok=True)

    text = args.text or read_text(temp_dir / "tts_text.txt")
    api_key = args.api_key or read_text(temp_dir / "tts_key.txt")
    voice_id = args.voice_id or read_text(temp_dir / "tts_voice.txt")
    output_audio = args.output_audio or read_text(temp_dir / "tts_output_audio_path.txt")

    try:
        text = clean_tts_text(text)
        (run_dir / "tts_text.txt").write_text(text, encoding="utf-8")
        (run_dir / "tts_voice.txt").write_text(voice_id, encoding="utf-8")

        if not text:
            raise ValueError("TTS text is empty.")
        if not api_key:
            raise ValueError("ElevenLabs key is missing.")
        if not voice_id:
            raise ValueError("ElevenLabs voice id is missing.")

        if not output_audio:
            output_audio = str(script_dir.parent / "Output" / "response.wav")
        out_audio_path = Path(output_audio)
        if not out_audio_path.is_absolute():
            out_audio_path = project_root / output_audio
        out_audio_path.parent.mkdir(parents=True, exist_ok=True)

        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        template = cfg["elevenlabs"]["endpoint_template"]
        endpoint = template.replace("{voice_id}", voice_id)
        model_id = cfg["elevenlabs"]["model_id"]
        accept_type = cfg["elevenlabs"]["accept"]

        payload = json.dumps({"text": text, "model_id": model_id}, ensure_ascii=False).encode("utf-8")
        req = Request(endpoint, data=payload, method="POST")
        req.add_header("xi-api-key", api_key)
        req.add_header("accept", accept_type)
        req.add_header("Content-Type", "application/json; charset=utf-8")

        with urlopen(req, timeout=120) as resp:
            audio_bytes = resp.read()

        out_audio_path.write_bytes(audio_bytes)

        ok_text = f"TTS_OK: {out_audio_path}"
        hr = run_dir / "tts_result.txt"
        for p in (output_result, hr):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(ok_text, encoding="utf-8")

        ext = out_audio_path.suffix or ".wav"
        shutil.copyfile(out_audio_path, run_dir / f"tts_output{ext}")
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        err_text = f"TTS_ERROR: {err.code} {err.reason} | {detail}"
        hr = run_dir / "tts_result.txt"
        for p in (output_result, hr):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(err_text, encoding="utf-8")
    except URLError as err:
        err_text = f"TTS_ERROR: Network error: {err.reason}"
        hr = run_dir / "tts_result.txt"
        for p in (output_result, hr):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(err_text, encoding="utf-8")
    except Exception as err:
        err_text = f"TTS_ERROR: {err}"
        hr = run_dir / "tts_result.txt"
        for p in (output_result, hr):
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(err_text, encoding="utf-8")


if __name__ == "__main__":
    main()
