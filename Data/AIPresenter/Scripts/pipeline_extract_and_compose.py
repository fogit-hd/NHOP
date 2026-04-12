"""
Read slides.csv → for each image, OpenAI Vision → append to ONE file
(Data/AIPresenter/Temp/extracted_slides_raw.txt; flushed after each slide).
Then GPT (presentation_master_prompt.txt) → ONE composed file
(Data/AIPresenter/Input/gpt_slide_content.txt). No per-slide narration files.

Run from project folder:
  py Data\\AIPresenter\\Scripts\\pipeline_extract_and_compose.py --root "%CD%"
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import re
import sys
import urllib.error
import urllib.request


def load_json(path: str) -> dict:
    with open(path, encoding="utf-8-sig") as f:
        return json.load(f)


def http_post_json(url: str, headers: dict, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=300) as resp:
        return json.loads(resp.read().decode("utf-8"))


def vision_extract(api_key: str, model: str, image_path: str, slide_label: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png" if ext == ".png" else "image/jpeg"
    user_text = (
        f"Slide: {slide_label}\n"
        "Extract all legible text from the image in a sensible reading order. "
        "Briefly describe charts, diagrams, and illustrations (skip per-cell table OCR if unreadable). "
        "Output in clear English."
    )
    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_text},
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:{mime};base64,{b64}"},
                    },
                ],
            }
        ],
        "max_tokens": 4096,
        "temperature": 0.2,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    out = http_post_json("https://api.openai.com/v1/chat/completions", headers, payload)
    return out["choices"][0]["message"]["content"].strip()


def chat_completion(api_key: str, model: str, system: str, user: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "temperature": 0.4,
        "max_tokens": 8192,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    out = http_post_json("https://api.openai.com/v1/chat/completions", headers, payload)
    return out["choices"][0]["message"]["content"].strip()


def parse_slides_blocks(gpt_text: str) -> list[tuple[int, str, str]]:
    """Return [(index, title, body), ...] from === SLIDE | ... === blocks."""
    pattern = re.compile(
        r"===\s*SLIDE\s*\|\s*(\d+)\s*\|\s*([^=]+?)\s*===\s*(.*?)(?=\n===\s*SLIDE|\Z)",
        re.DOTALL | re.IGNORECASE,
    )
    found = []
    for m in pattern.finditer(gpt_text):
        idx = int(m.group(1))
        title = m.group(2).strip()
        body = m.group(3).strip()
        found.append((idx, title, body))
    return sorted(found, key=lambda x: x[0])


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=os.getcwd())
    args = p.parse_args()
    root = os.path.normpath(args.root)

    settings_path = os.path.join(root, "Data", "AIPresenter", "Config", "ai_settings.json")
    csv_path = os.path.join(root, "Data", "AIPresenter", "Input", "slides.csv")
    master_prompt_path = os.path.join(root, "Data", "AIPresenter", "Input", "presentation_master_prompt.txt")
    raw_out = os.path.join(root, "Data", "AIPresenter", "Temp", "extracted_slides_raw.txt")
    gpt_out = os.path.join(root, "Data", "AIPresenter", "Input", "gpt_slide_content.txt")
    os.makedirs(os.path.dirname(raw_out), exist_ok=True)
    os.makedirs(os.path.dirname(gpt_out), exist_ok=True)
    if not os.path.isfile(gpt_out):
        open(gpt_out, "w", encoding="utf-8").close()

    cfg = load_json(settings_path)
    api_key = (cfg.get("openai_api_key") or "").strip()
    vision_model = (cfg.get("openai_vision_model") or "gpt-4o").strip()
    chat_model = (cfg.get("openai_model") or "gpt-4o").strip()

    if not api_key or api_key.startswith("YOUR_"):
        print("Missing valid openai_api_key in ai_settings.json", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(csv_path):
        print("slides.csv not found", file=sys.stderr)
        sys.exit(1)

    if not os.path.isfile(master_prompt_path):
        print("presentation_master_prompt.txt not found", file=sys.stderr)
        sys.exit(1)

    with open(master_prompt_path, encoding="utf-8") as f:
        master_prompt = f.read().strip()

    rows: list[tuple[int, str, str]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if not row:
                continue
            idx_s = (row.get("slide_index") or "").strip()
            title = (row.get("slide_title") or "").strip()
            rel = (row.get("slide_path") or "").strip().strip('"')
            if not idx_s or not rel:
                continue
            idx = int(idx_s)
            abs_img = rel if os.path.isabs(rel) else os.path.normpath(os.path.join(root, rel))
            rows.append((idx, title, abs_img))

    rows.sort(key=lambda x: x[0])
    raw_text_parts: list[str] = []
    with open(raw_out, "w", encoding="utf-8") as raw_fp:
        for idx, title, abs_img in rows:
            label = f"{idx} — {title}"
            if not os.path.isfile(abs_img):
                block = f"=== SLIDE {idx} ({title}) ===\n[Image file not found: {abs_img}]\n"
                raw_fp.write(block)
                raw_fp.flush()
                raw_text_parts.append(block)
                print(f"WARN missing image: {abs_img}", file=sys.stderr)
                continue
            try:
                extracted = vision_extract(api_key, vision_model, abs_img, label)
            except (urllib.error.HTTPError, urllib.error.URLError, KeyError, OSError) as e:
                print(f"Vision failed slide {idx}: {e}", file=sys.stderr)
                sys.exit(2)
            block = f"=== SLIDE {idx} ({title}) ===\n{extracted}\n"
            raw_fp.write(block)
            raw_fp.flush()
            raw_text_parts.append(block)

    raw_text = "".join(raw_text_parts)

    user_block = (
        "RAW DATA (slide order):\n\n"
        + raw_text
        + "\n\nFollow the === SLIDE | index | title === block format as instructed."
    )

    try:
        composed = chat_completion(api_key, chat_model, master_prompt, user_block)
    except (urllib.error.HTTPError, urllib.error.URLError, KeyError) as e:
        print(f"GPT compose failed: {e}", file=sys.stderr)
        sys.exit(3)

    with open(gpt_out, "w", encoding="utf-8") as f:
        f.write(composed)

    slides_parsed = parse_slides_blocks(composed)
    if not slides_parsed:
        print(
            "GPT did not return === SLIDE | ... === blocks — UiPath will not find per-slide narration; "
            "check presentation_master_prompt.txt and model output.",
            file=sys.stderr,
        )

    print(f"OK raw={raw_out} gpt={gpt_out} slide_blocks={len(slides_parsed)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
