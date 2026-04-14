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


SUPPORTED_HANDBOOK_SUFFIXES = {".txt", ".md", ".csv", ".json"}


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


def resolve_handbook_files(project_root: Path, cfg: dict, override_path: str) -> list[Path]:
    paths_cfg = cfg.get("paths") or {}
    configured = (
        override_path.strip()
        or str(paths_cfg.get("handbook_file") or "").strip()
        or str(paths_cfg.get("handbook_path") or "").strip()
    )

    if configured:
        candidate = Path(configured)
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if candidate.is_file():
            return [candidate]
        if candidate.is_dir():
            file_candidates = sorted(
                [
                    p
                    for p in candidate.rglob("*")
                    if p.is_file() and p.suffix.lower() in SUPPORTED_HANDBOOK_SUFFIXES
                ]
            )
            if file_candidates:
                return file_candidates
        return []

    default_txt = project_root / "Data" / "AIPresenter" / "FPT-handbook.txt"
    if default_txt.exists() and default_txt.is_file():
        return [default_txt]

    default_dir = project_root / "Data" / "AIPresenter" / "FPT-handbook"
    if default_dir.exists() and default_dir.is_dir():
        file_candidates = sorted(
            [
                p
                for p in default_dir.rglob("*")
                if p.is_file() and p.suffix.lower() in SUPPORTED_HANDBOOK_SUFFIXES
            ]
        )
        if file_candidates:
            return file_candidates
    return []


def load_handbook_content(project_root: Path, cfg: dict, override_path: str) -> tuple[list[Path], str]:
    handbook_files = resolve_handbook_files(project_root, cfg, override_path)
    if not handbook_files:
        return [], ""

    content_blocks: list[str] = []
    for handbook_path in handbook_files:
        try:
            content = handbook_path.read_text(encoding="utf-8", errors="replace").strip()
        except OSError:
            continue
        if not content:
            continue
        content_blocks.append(f"[FILE: {handbook_path.name}]\n{content}")

    if not content_blocks:
        return handbook_files, ""

    max_chars_cfg = (
        cfg.get("openai", {})
        .get("gpt", {})
        .get("handbook_max_chars", 120000)
    )
    try:
        max_chars = max(2000, int(max_chars_cfg))
    except (TypeError, ValueError):
        max_chars = 120000

    combined = "\n\n".join(content_blocks)
    if len(combined) > max_chars:
        combined = (
            combined[:max_chars]
            + "\n\n[Handbook content truncated due to size limit for this run.]"
        )
    return handbook_files, combined


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-path", default="")
    parser.add_argument(
        "--handbook-file",
        default="",
        help="Optional handbook file or folder path (folder mode loads all supported files)",
    )
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
            else "You are an AI interactive presenter. Your name is NEO."
        )

        handbook_files, handbook_content = load_handbook_content(project_root, cfg, args.handbook_file)
        (run_dir / "gpt_handbook_source.txt").write_text(
            "\n".join(str(p) for p in handbook_files) if handbook_files else "[no handbook found]",
            encoding="utf-8",
        )
        if handbook_content:
            (run_dir / "gpt_handbook_used.txt").write_text(handbook_content, encoding="utf-8")

        if handbook_content:
            system_prompt = (
                f"{system_prompt}\n\n"
                "Your name is NEO.\n"
                "You MUST strictly follow the rules and information in the provided handbook to answer user questions.\n"
                "Treat uploaded handbook files as the primary policy source for compliance-related answers.\n"
                "The user is an employee in an internal process, so your answers must be professional and align with the company's policies.\n"
                "Emphasize important points like dates, deadlines, and penalties mentioned in the slides or the handbook.\n\n"
                "HANDBOOK CONTENT:\n"
                "-------------------\n"
                f"{handbook_content}\n"
                "-------------------\n"
            )
        else:
            system_prompt = (
                f"{system_prompt}\n\n"
                "Your name is NEO.\n"
                "No handbook file was loaded for this run. Answer using slide content and available context only.\n"
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
            f"{time_context}\n\n"
            f"Slide content:\n{slide_text}\n\n"
            f"User question:\n{question_text}\n\n"
            "Please provide a clear, informative, and trustworthy answer based on the slide content and the company handbook. "
            "If the information is not in the slides or handbook, state that clearly."
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
