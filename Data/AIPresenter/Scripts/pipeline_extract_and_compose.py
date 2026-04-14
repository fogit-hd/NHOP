"""
Build composed narration from slide sources.

Priority:
1) slides.csv + slide images (legacy behavior)
2) .pptx file in Data/AIPresenter/Input (or configured path)

Writes:
- Data/AIPresenter/Temp/extracted_slides_raw.txt
- Data/AIPresenter/Input/gpt_slide_content.txt

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


def resolve_pptx_path(root: str, cfg: dict) -> str:
    configured = (
        (cfg.get("presentation_pptx_path") or "").strip()
        or (cfg.get("pptx_input_path") or "").strip()
        or (cfg.get("slide_pptx_path") or "").strip()
    )
    if configured:
        candidate = configured if os.path.isabs(configured) else os.path.join(root, configured)
        candidate = os.path.normpath(candidate)
        if os.path.isfile(candidate):
            return candidate
        return ""

    input_dir = os.path.join(root, "Data", "AIPresenter", "Input")
    if not os.path.isdir(input_dir):
        return ""

    for name in sorted(os.listdir(input_dir)):
        low = name.lower()
        if low.endswith(".pptx") and not low.startswith("~$"):
            candidate = os.path.normpath(os.path.join(input_dir, name))
            if os.path.isfile(candidate):
                return candidate
    return ""


def extract_shape_text(shape) -> str:
    parts: list[str] = []

    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        for para in shape.text_frame.paragraphs:
            line = (para.text or "").strip()
            if line:
                parts.append(line)

    if getattr(shape, "has_table", False) and shape.has_table:
        for row in shape.table.rows:
            row_cells: list[str] = []
            for cell in row.cells:
                cell_text = " ".join((cell.text or "").split())
                if cell_text:
                    row_cells.append(cell_text)
            if row_cells:
                parts.append(" | ".join(row_cells))

    return "\n".join(parts).strip()


def load_slides_from_pptx(pptx_path: str) -> list[tuple[int, str, str]]:
    try:
        from pptx import Presentation
    except Exception as e:
        raise RuntimeError(
            "python-pptx is required for PPTX mode. Install dependencies and retry."
        ) from e

    presentation = Presentation(pptx_path)
    rows: list[tuple[int, str, str]] = []
    for idx, slide in enumerate(presentation.slides, start=1):
        title = ""
        try:
            if slide.shapes.title is not None:
                title = (slide.shapes.title.text or "").strip()
        except Exception:
            title = ""
        if not title:
            title = f"Slide {idx}"

        text_chunks: list[str] = []
        for shape in slide.shapes:
            chunk = extract_shape_text(shape)
            if chunk:
                text_chunks.append(chunk)

        notes_text = ""
        try:
            if slide.has_notes_slide and slide.notes_slide is not None:
                frame = slide.notes_slide.notes_text_frame
                if frame is not None:
                    notes_text = (frame.text or "").strip()
        except Exception:
            notes_text = ""

        body_parts: list[str] = []
        if text_chunks:
            body_parts.append("Slide text:\n" + "\n".join(text_chunks))
        if notes_text:
            body_parts.append("Presenter notes:\n" + notes_text)
        if not body_parts:
            body_parts.append("[No extractable text found on this slide.]")

        rows.append((idx, title, "\n\n".join(body_parts).strip()))
    return rows


def load_rows_from_csv(root: str, csv_path: str) -> list[tuple[int, str, str]]:
    rows: list[tuple[int, str, str]] = []
    if not os.path.isfile(csv_path):
        return rows

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
    return rows


def build_raw_from_images(
    api_key: str,
    vision_model: str,
    rows: list[tuple[int, str, str]],
    raw_out: str,
) -> str:
    raw_text_parts: list[str] = []
    with open(raw_out, "w", encoding="utf-8") as raw_fp:
        for idx, title, abs_img in rows:
            label = f"{idx} - {title}"
            if not os.path.isfile(abs_img):
                block = f"=== SLIDE {idx} ({title}) ===\n[Image file not found: {abs_img}]\n"
                raw_fp.write(block)
                raw_fp.flush()
                raw_text_parts.append(block)
                print(f"WARN missing image: {abs_img}", file=sys.stderr)
                continue
            extracted = vision_extract(api_key, vision_model, abs_img, label)
            block = f"=== SLIDE {idx} ({title}) ===\n{extracted}\n"
            raw_fp.write(block)
            raw_fp.flush()
            raw_text_parts.append(block)
    return "".join(raw_text_parts)


def build_raw_from_pptx(rows: list[tuple[int, str, str]], raw_out: str) -> str:
    raw_text_parts: list[str] = []
    with open(raw_out, "w", encoding="utf-8") as raw_fp:
        for idx, title, extracted in rows:
            block = f"=== SLIDE {idx} ({title}) ===\n{extracted}\n"
            raw_fp.write(block)
            raw_fp.flush()
            raw_text_parts.append(block)
    return "".join(raw_text_parts)


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

    if not os.path.isfile(master_prompt_path):
        print("presentation_master_prompt.txt not found", file=sys.stderr)
        sys.exit(1)

    with open(master_prompt_path, encoding="utf-8") as f:
        master_prompt = f.read().strip()

    configured_pptx_setting = (
        (cfg.get("presentation_pptx_path") or "").strip()
        or (cfg.get("pptx_input_path") or "").strip()
        or (cfg.get("slide_pptx_path") or "").strip()
    )
    prefer_pptx = bool(configured_pptx_setting)

    csv_rows = load_rows_from_csv(root, csv_path)
    pptx_path = resolve_pptx_path(root, cfg)
    if prefer_pptx and not pptx_path:
        print(
            "Configured PPTX path not found. Check presentation_pptx_path/pptx_input_path/slide_pptx_path.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_text = ""
    source_mode = ""
    if prefer_pptx and pptx_path:
        try:
            pptx_rows = load_slides_from_pptx(pptx_path)
        except Exception as e:
            print(f"PPTX parse failed: {e}", file=sys.stderr)
            sys.exit(2)
        raw_text = build_raw_from_pptx(pptx_rows, raw_out)
        source_mode = f"pptx:{os.path.basename(pptx_path)}"
    elif csv_rows:
        try:
            raw_text = build_raw_from_images(api_key, vision_model, csv_rows, raw_out)
            source_mode = "csv-images"
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, OSError) as e:
            print(f"Vision extraction failed: {e}", file=sys.stderr)
            sys.exit(2)
    elif pptx_path:
        try:
            pptx_rows = load_slides_from_pptx(pptx_path)
        except Exception as e:
            print(f"PPTX parse failed: {e}", file=sys.stderr)
            sys.exit(2)
        raw_text = build_raw_from_pptx(pptx_rows, raw_out)
        source_mode = f"pptx:{os.path.basename(pptx_path)}"
    else:
        print(
            "No slide source found. Provide slides.csv or a .pptx in Data/AIPresenter/Input "
            "(or set presentation_pptx_path in ai_settings.json).",
            file=sys.stderr,
        )
        sys.exit(1)

    if not raw_text.strip():
        print("No slide content extracted from source.", file=sys.stderr)
        sys.exit(2)

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

    print(f"OK source={source_mode} raw={raw_out} gpt={gpt_out} slide_blocks={len(slides_parsed)}")
    sys.exit(0)


if __name__ == "__main__":
    main()
