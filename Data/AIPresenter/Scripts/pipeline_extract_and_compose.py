"""
Build composed narration from slide sources.

Priority:
1) Configured .pptx path in Data/AIPresenter/Config/ai_settings.json
2) Ordered .pptx list in Data/AIPresenter/Input/pptx_run_order.xlsx
    or Data/AIPresenter/Input/pptx_run_order_template.csv
3) First .pptx in Data/AIPresenter/Input/pptx_file_here
4) First .pptx in Data/AIPresenter/Input
5) slides.csv + slide images (legacy fallback)

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
from typing import Any

RUN_ORDER_DEFAULT = os.path.join("Data", "AIPresenter", "Input", "pptx_run_order.xlsx")
RUN_ORDER_TEMPLATE_CSV_DEFAULT = os.path.join(
    "Data", "AIPresenter", "Input", "pptx_run_order_template.csv"
)


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


def find_first_pptx(folder: str) -> str:
    if not os.path.isdir(folder):
        return ""
    for name in sorted(os.listdir(folder)):
        low = name.lower()
        if low.endswith(".pptx") and not low.startswith("~$"):
            candidate = os.path.normpath(os.path.join(folder, name))
            if os.path.isfile(candidate):
                return candidate
    return ""


def parse_enabled(value: Any) -> bool:
    if value is None:
        return True
    text = str(value).strip().lower()
    if text == "":
        return True
    return text not in {"0", "false", "no", "n", "off", "disabled"}


def resolve_pptx_candidate(root: str, input_dir: str, raw_path: str) -> str:
    value = (raw_path or "").strip().strip('"')
    if not value:
        return ""

    candidates: list[str] = []
    if os.path.isabs(value):
        candidates.append(value)
    else:
        candidates.append(os.path.join(root, value))
        candidates.append(os.path.join(input_dir, "pptx_file_here", value))
        candidates.append(os.path.join(input_dir, value))

    for candidate in candidates:
        normalized = os.path.normpath(candidate)
        base_name = os.path.basename(normalized).lower()
        if base_name.startswith("~$") or not base_name.endswith(".pptx"):
            continue
        if os.path.isfile(normalized):
            return normalized
    return ""


def read_pptx_run_order(root: str, input_dir: str, queue_path: str) -> tuple[list[str], int]:
    if not os.path.isfile(queue_path):
        return [], 0

    try:
        from openpyxl import load_workbook
    except Exception:
        print(
            "WARN pptx_run_order.xlsx found but openpyxl is missing. "
            "Install dependencies to use ordered multi-PPTX mode.",
            file=sys.stderr,
        )
        return [], 0

    try:
        workbook = load_workbook(queue_path, data_only=True, read_only=True)
        sheet = workbook.active
    except Exception as e:
        print(f"WARN Could not read PPTX run-order file: {queue_path} ({e})", file=sys.stderr)
        return [], 0

    header_row = None
    for values in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
        header_row = list(values)
        break

    if not header_row:
        return [], 0

    def norm_header(value: Any) -> str:
        return str(value or "").strip().lower().replace(" ", "_")

    headers = [norm_header(v) for v in header_row]
    path_aliases = {"pptx_path", "file_path", "path", "pptx", "file", "filename", "pptx_file"}
    order_aliases = {"run_order", "order", "stt", "index", "priority"}
    enabled_aliases = {"enabled", "is_enabled", "active", "use"}

    path_idx = next((i for i, h in enumerate(headers) if h in path_aliases), -1)
    order_idx = next((i for i, h in enumerate(headers) if h in order_aliases), -1)
    enabled_idx = next((i for i, h in enumerate(headers) if h in enabled_aliases), -1)

    if path_idx < 0:
        print(
            "WARN pptx_run_order.xlsx does not contain a path column. "
            "Expected one of: pptx_path, file_path, path, pptx.",
            file=sys.stderr,
        )
        return [], 0

    items: list[tuple[int, str]] = []
    rows_with_path = 0
    for row in sheet.iter_rows(min_row=2, values_only=True):
        values = list(row)

        raw_path = ""
        if path_idx < len(values) and values[path_idx] is not None:
            raw_path = str(values[path_idx]).strip()
        if not raw_path:
            continue

        rows_with_path += 1

        enabled = True
        if enabled_idx >= 0 and enabled_idx < len(values):
            enabled = parse_enabled(values[enabled_idx])
        if not enabled:
            continue

        order_value = rows_with_path
        if order_idx >= 0 and order_idx < len(values) and values[order_idx] not in (None, ""):
            try:
                order_value = int(float(str(values[order_idx]).strip()))
            except ValueError:
                order_value = rows_with_path

        resolved = resolve_pptx_candidate(root, input_dir, raw_path)
        if not resolved:
            print(f"WARN queue path not found: {raw_path}", file=sys.stderr)
            continue

        items.append((order_value, resolved))

    items.sort(key=lambda it: (it[0], it[1].lower()))
    ordered_paths: list[str] = []
    seen: set[str] = set()
    for _, path in items:
        key = path.lower()
        if key in seen:
            continue
        seen.add(key)
        ordered_paths.append(path)

    return ordered_paths, rows_with_path


def read_pptx_run_order_csv(root: str, input_dir: str, queue_path: str) -> tuple[list[str], int]:
    if not os.path.isfile(queue_path):
        return [], 0

    try:
        with open(queue_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], 0

            def norm_header(value: Any) -> str:
                return str(value or "").strip().lower().replace(" ", "_")

            path_aliases = {"pptx_path", "file_path", "path", "pptx", "file", "filename", "pptx_file"}
            order_aliases = {"run_order", "order", "stt", "index", "priority"}
            enabled_aliases = {"enabled", "is_enabled", "active", "use"}

            header_pairs = [(name, norm_header(name)) for name in reader.fieldnames]
            path_key = next((name for name, h in header_pairs if h in path_aliases), None)
            order_key = next((name for name, h in header_pairs if h in order_aliases), None)
            enabled_key = next((name for name, h in header_pairs if h in enabled_aliases), None)

            if not path_key:
                print(
                    "WARN pptx run-order CSV does not contain a path column. "
                    "Expected one of: pptx_path, file_path, path, pptx.",
                    file=sys.stderr,
                )
                return [], 0

            items: list[tuple[int, str]] = []
            rows_with_path = 0
            for row in reader:
                raw_path = str((row.get(path_key) if row else "") or "").strip()
                if not raw_path:
                    continue

                rows_with_path += 1

                enabled = True
                if enabled_key:
                    enabled = parse_enabled(row.get(enabled_key) if row else None)
                if not enabled:
                    continue

                order_value = rows_with_path
                if order_key:
                    order_raw = (row.get(order_key) if row else None)
                    if order_raw not in (None, ""):
                        try:
                            order_value = int(float(str(order_raw).strip()))
                        except ValueError:
                            order_value = rows_with_path

                resolved = resolve_pptx_candidate(root, input_dir, raw_path)
                if not resolved:
                    print(f"WARN queue path not found: {raw_path}", file=sys.stderr)
                    continue

                items.append((order_value, resolved))

        items.sort(key=lambda it: (it[0], it[1].lower()))
        ordered_paths: list[str] = []
        seen: set[str] = set()
        for _, path in items:
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            ordered_paths.append(path)

        return ordered_paths, rows_with_path
    except Exception as e:
        print(f"WARN Could not read PPTX run-order CSV: {queue_path} ({e})", file=sys.stderr)
        return [], 0


def resolve_pptx_paths(root: str, cfg: dict) -> list[str]:
    configured = (
        (cfg.get("presentation_pptx_path") or "").strip()
        or (cfg.get("pptx_input_path") or "").strip()
        or (cfg.get("slide_pptx_path") or "").strip()
    )
    input_dir = os.path.join(root, "Data", "AIPresenter", "Input")

    if configured:
        candidate = resolve_pptx_candidate(root, input_dir, configured)
        return [candidate] if candidate else []

    queue_setting = (cfg.get("pptx_run_order_file") or "").strip()
    queue_candidates: list[str] = []
    if queue_setting:
        queue_candidates.append(
            os.path.normpath(queue_setting)
            if os.path.isabs(queue_setting)
            else os.path.normpath(os.path.join(root, queue_setting))
        )
    else:
        queue_candidates.append(os.path.join(root, RUN_ORDER_DEFAULT))
        queue_candidates.append(os.path.join(root, RUN_ORDER_TEMPLATE_CSV_DEFAULT))

    queue_rows_detected = 0
    for queue_path in queue_candidates:
        ext = os.path.splitext(queue_path)[1].lower()
        if ext == ".csv":
            queue_paths, queue_rows = read_pptx_run_order_csv(root, input_dir, queue_path)
        else:
            queue_paths, queue_rows = read_pptx_run_order(root, input_dir, queue_path)

        if queue_paths:
            return queue_paths
        queue_rows_detected = max(queue_rows_detected, queue_rows)

    if queue_rows_detected > 0:
        print(
            "WARN PPTX run-order file exists but no valid entries were resolved. "
            "Falling back to folder auto-detection.",
            file=sys.stderr,
        )

    preferred_dir = os.path.join(input_dir, "pptx_file_here")
    preferred_candidate = find_first_pptx(preferred_dir)
    if preferred_candidate:
        return [preferred_candidate]

    fallback_candidate = find_first_pptx(input_dir)
    if fallback_candidate:
        return [fallback_candidate]

    return []


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


def load_slides_from_pptx(pptx_path: str, start_index: int = 1) -> list[tuple[int, str, str]]:
    try:
        from pptx import Presentation
    except Exception as e:
        raise RuntimeError(
            "python-pptx is required for PPTX mode. Install dependencies and retry."
        ) from e

    presentation = Presentation(pptx_path)
    rows: list[tuple[int, str, str]] = []
    for local_idx, slide in enumerate(presentation.slides, start=1):
        idx = start_index + (local_idx - 1)
        title = ""
        try:
            if slide.shapes.title is not None:
                title = (slide.shapes.title.text or "").strip()
        except Exception:
            title = ""
        if not title:
            title = f"Slide {local_idx}"

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
    csv_rows = load_rows_from_csv(root, csv_path)
    pptx_paths = resolve_pptx_paths(root, cfg)
    if configured_pptx_setting and not pptx_paths:
        print(
            "Configured PPTX path not found. Check presentation_pptx_path/pptx_input_path/slide_pptx_path.",
            file=sys.stderr,
        )
        sys.exit(1)

    raw_text = ""
    source_mode = ""
    if pptx_paths:
        try:
            all_pptx_rows: list[tuple[int, str, str]] = []
            next_index = 1
            for pptx_path in pptx_paths:
                deck_rows = load_slides_from_pptx(pptx_path, start_index=next_index)
                all_pptx_rows.extend(deck_rows)
                next_index += len(deck_rows)
        except Exception as e:
            print(f"PPTX parse failed: {e}", file=sys.stderr)
            sys.exit(2)

        raw_text = build_raw_from_pptx(all_pptx_rows, raw_out)
        source_mode = f"pptx:{len(pptx_paths)} file(s)"
        print(
            "INFO pptx order: " + ", ".join(os.path.basename(path) for path in pptx_paths),
            file=sys.stderr,
        )
    elif csv_rows:
        try:
            raw_text = build_raw_from_images(api_key, vision_model, csv_rows, raw_out)
            source_mode = "csv-images"
        except (urllib.error.HTTPError, urllib.error.URLError, KeyError, OSError) as e:
            print(f"Vision extraction failed: {e}", file=sys.stderr)
            sys.exit(2)
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
