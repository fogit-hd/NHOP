"""
OpenAI Chat Completions for AI presenter (stdlib urllib). Reads slide/question/key from temp files.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def repair_mojibake_utf8(text: str) -> str:
    if not text or not text.strip():
        return text
    if "à¸" in text or "Ã" in text:
        try:
            return text.encode("latin-1").decode("utf-8")
        except (UnicodeDecodeError, UnicodeEncodeError):
            pass
    return text


def write_outputs(
    text: str,
    output_path: Path,
    latest_path: Path,
    run_result: Path,
) -> None:
    for p in (output_path, latest_path, run_result):
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-path", default="")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    app_root = script_dir.parent
    project_root = script_dir.parent.parent.parent
    temp_dir = app_root / "Temp"
    history_root = temp_dir / "History"
    history_root.mkdir(parents=True, exist_ok=True)
    cfg_path = app_root / "Config" / "api_runtime.json"

    run_stamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    latest_result_path = temp_dir / "gpt_result.txt"
    output_path = Path(args.output_path) if args.output_path else latest_result_path
    run_dir = history_root / run_stamp
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    slide_path = temp_dir / "gpt_slide.txt"
    question_path = temp_dir / "gpt_question.txt"
    key_path = temp_dir / "gpt_key.txt"

    slide = read_text(slide_path)
    question = read_text(question_path)
    api_key = read_text(key_path).strip()

    try:
        if not api_key:
            raise ValueError("OpenAI API key missing in gpt_key.txt")

        (run_dir / "gpt_slide.txt").write_text(slide, encoding="utf-8")
        (run_dir / "gpt_question.txt").write_text(question, encoding="utf-8")

        cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
        endpoint = cfg["openai"]["gpt"]["endpoint"]
        model = cfg["openai"]["gpt"]["model"]
        temperature = float(cfg["openai"]["gpt"].get("temperature", 0.4))

        prompt_rel = cfg["paths"]["system_prompt"]
        prompt_path = Path(prompt_rel) if Path(prompt_rel).is_absolute() else project_root / prompt_rel
        system_prompt = (
            prompt_path.read_text(encoding="utf-8", errors="replace").strip()
            if prompt_path.exists()
            else "You are an AI interactive presenter."
        )
        system_prompt_text = system_prompt + "\nAlways respond in English only."

        slide_text = repair_mojibake_utf8(slide)
        if not slide_text.strip():
            slide_text = "[No slide content provided]"
        question_text = repair_mojibake_utf8(question)
        if not question_text.strip():
            question_text = "Please provide a concise helpful answer."

        local_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        time_context = f"Current local datetime (system): {local_now}"
        user_content = (
            f"{time_context}\n\nSlide content:\n{slide_text}\n\nUser question:\n{question_text}\n\n"
            "Please answer primarily based on the slide content above. If the slide does not contain "
            "the needed information, say that briefly, then provide the best helpful answer."
        )

        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt_text},
                {"role": "user", "content": user_content},
            ],
            "temperature": temperature,
        }
        payload_json = json.dumps(payload, ensure_ascii=False)
        (run_dir / "gpt_payload.json").write_text(payload_json, encoding="utf-8")

        data = payload_json.encode("utf-8")
        req = Request(endpoint, data=data, method="POST")
        req.add_header("Authorization", f"Bearer {api_key}")
        req.add_header("Content-Type", "application/json; charset=utf-8")

        with urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", errors="replace")

        obj = json.loads(raw)
        choices = obj.get("choices") or []
        if not choices:
            answer = "[Empty GPT response]"
        else:
            msg = choices[0].get("message") or {}
            answer = (msg.get("content") or "").strip()
            if not answer:
                answer = "[Empty GPT response]"

        run_result = run_dir / "gpt_result.txt"
        write_outputs(answer, output_path, latest_result_path, run_result)
    except HTTPError as err:
        detail = err.read().decode("utf-8", errors="replace")
        err_text = f"GPT_ERROR: {err.code} {err.reason} | {detail}"
        run_result = run_dir / "gpt_result.txt"
        write_outputs(err_text, output_path, latest_result_path, run_result)
    except URLError as err:
        err_text = f"GPT_ERROR: Network error: {err.reason}"
        run_result = run_dir / "gpt_result.txt"
        write_outputs(err_text, output_path, latest_result_path, run_result)
    except Exception as err:
        err_text = f"GPT_ERROR: {err}"
        run_result = run_dir / "gpt_result.txt"
        write_outputs(err_text, output_path, latest_result_path, run_result)


if __name__ == "__main__":
    main()
