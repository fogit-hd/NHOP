import argparse
import json
import mimetypes
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_multipart_form(fields, file_field_name, file_path: Path):
    boundary = f"----UiPathWhisperBoundary{datetime.now().strftime('%Y%m%d%H%M%S%f')}"
    line_break = b"\r\n"
    body = bytearray()

    for key, value in fields.items():
        body.extend(f"--{boundary}".encode("utf-8"))
        body.extend(line_break)
        body.extend(f'Content-Disposition: form-data; name="{key}"'.encode("utf-8"))
        body.extend(line_break)
        body.extend(line_break)
        body.extend(str(value).encode("utf-8"))
        body.extend(line_break)

    mime_type = mimetypes.guess_type(str(file_path))[0] or "audio/wav"
    file_bytes = file_path.read_bytes()
    body.extend(f"--{boundary}".encode("utf-8"))
    body.extend(line_break)
    body.extend(
        f'Content-Disposition: form-data; name="{file_field_name}"; filename="{file_path.name}"'.encode("utf-8")
    )
    body.extend(line_break)
    body.extend(f"Content-Type: {mime_type}".encode("utf-8"))
    body.extend(line_break)
    body.extend(line_break)
    body.extend(file_bytes)
    body.extend(line_break)
    body.extend(f"--{boundary}--".encode("utf-8"))
    body.extend(line_break)
    return boundary, bytes(body)


def write_all_outputs(text: str, output_path: Path, latest_result_path: Path, run_result_path: Path):
    for target in [output_path, latest_result_path, run_result_path]:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio-path", default="")
    parser.add_argument("--api-key", default="")
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    project_root = script_dir.parent.parent.parent
    temp_dir = script_dir.parent / "Temp"
    history_root = temp_dir / "History"
    history_root.mkdir(parents=True, exist_ok=True)

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    latest_result_path = temp_dir / "whisper_result.txt"
    output_path = Path(args.output_path) if args.output_path else latest_result_path
    run_dir = history_root / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_path = args.audio_path or read_text(temp_dir / "whisper_audio_path.txt")
    api_key = args.api_key or read_text(temp_dir / "whisper_key.txt")

    try:
        audio_file = Path(audio_path)
        if not audio_file.is_absolute():
            audio_file = project_root / audio_file
        if not audio_file.exists():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        if not api_key:
            raise ValueError("OpenAI API key missing in whisper_key.txt")

        cfg_path = script_dir.parent / "Config" / "api_runtime.json"
        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        endpoint = cfg["openai"]["whisper"]["endpoint"]
        model = cfg["openai"]["whisper"]["model"]

        (run_dir / "whisper_audio_path.txt").write_text(str(audio_file), encoding="utf-8")
        ext = audio_file.suffix if audio_file.suffix else ".wav"
        shutil.copyfile(audio_file, run_dir / f"whisper_input{ext}")

        boundary, payload = build_multipart_form({"model": model}, "file", audio_file)
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        }
        req = Request(endpoint, data=payload, headers=headers, method="POST")
        with urlopen(req, timeout=120) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")

        try:
            obj = json.loads(raw_body)
            text = str(obj.get("text", "")).strip() or raw_body
        except Exception:
            text = raw_body

        write_all_outputs(text, output_path, latest_result_path, run_dir / "whisper_result.txt")
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        msg = f"WHISPER_ERROR: Whisper API error: {err.code} - {detail}"
        write_all_outputs(msg, output_path, latest_result_path, run_dir / "whisper_result.txt")
    except URLError as err:
        msg = f"WHISPER_ERROR: Network error: {err.reason}"
        write_all_outputs(msg, output_path, latest_result_path, run_dir / "whisper_result.txt")
    except Exception as err:
        msg = f"WHISPER_ERROR: {err}"
        write_all_outputs(msg, output_path, latest_result_path, run_dir / "whisper_result.txt")


if __name__ == "__main__":
    main()
