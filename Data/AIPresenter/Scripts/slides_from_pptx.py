"""Build Temp/slides_iterate.tsv for UiPath from available slide sources.

Priority:
1) Configured .pptx path in Data/AIPresenter/Config/ai_settings.json
2) Ordered .pptx list in Data/AIPresenter/Input/pptx_run_order.xlsx
    or Data/AIPresenter/Input/pptx_run_order_template.csv
3) First .pptx in Data/AIPresenter/Input/pptx_file_here
4) Data/AIPresenter/Input/slides.csv (legacy fallback)

TSV columns (tab-separated): index, title, absolute_path, relative_path
Rows are sorted by slide_index ascending.
"""
from __future__ import annotations

import argparse
import csv
import importlib
import json
import os
import shutil
import sys
from typing import Any

RUN_ORDER_DEFAULT = os.path.join("Data", "AIPresenter", "Input", "pptx_run_order.xlsx")
RUN_ORDER_TEMPLATE_CSV_DEFAULT = os.path.join(
    "Data", "AIPresenter", "Input", "pptx_run_order_template.csv"
)
PPTX_SOURCE_ERROR_FILE = os.path.join(
    "Data", "AIPresenter", "Temp", "pptx_source_resolution_error.txt"
)


def clear_pptx_export_root(root: str) -> str:
    out_dir = os.path.join(root, "Data", "AIPresenter", "Temp", "pptx_slides")
    os.makedirs(out_dir, exist_ok=True)

    for name in os.listdir(out_dir):
        target = os.path.join(out_dir, name)
        try:
            if os.path.isdir(target):
                shutil.rmtree(target)
            else:
                os.remove(target)
        except OSError as e:
            print(f"WARN Could not remove old export item: {target} ({e})", file=sys.stderr)
    return out_dir


def sanitize_name(name: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in name)
    cleaned = cleaned.strip("_")
    return cleaned or "presentation"


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


def list_pptx_files(folder: str) -> list[str]:
    files: list[str] = []
    if not os.path.isdir(folder):
        return files
    for name in sorted(os.listdir(folder)):
        low = name.lower()
        if low.endswith(".pptx") and not low.startswith("~$"):
            candidate = os.path.normpath(os.path.join(folder, name))
            if os.path.isfile(candidate):
                files.append(candidate)
    return files


def format_path_for_message(root: str, path: str) -> str:
    try:
        rel = os.path.relpath(path, root)
        return rel.replace("\\", "/")
    except ValueError:
        return path.replace("\\", "/")


def build_run_order_mismatch_message(
    root: str,
    queue_path: str,
    unresolved_entries: list[str],
    folder_pptx_files: list[str],
) -> str:
    unresolved_unique: list[str] = []
    seen: set[str] = set()
    for raw in unresolved_entries:
        key = raw.strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        unresolved_unique.append(raw.strip())

    lines: list[str] = [
        "PPTX source mismatch: run-order file and PPTX folder are not aligned.",
        f"Run-order file: {format_path_for_message(root, queue_path)}",
        "",
        "Entries listed in run-order but not found on disk:",
    ]

    if unresolved_unique:
        for raw in unresolved_unique[:30]:
            lines.append(f"- {raw}")
        if len(unresolved_unique) > 30:
            lines.append(f"- ... and {len(unresolved_unique) - 30} more")
    else:
        lines.append("- (none)")

    lines.extend(["", "PPTX files currently found in Data/AIPresenter/Input/pptx_file_here:"])
    if folder_pptx_files:
        for path in folder_pptx_files[:30]:
            lines.append(f"- {format_path_for_message(root, path)}")
        if len(folder_pptx_files) > 30:
            lines.append(f"- ... and {len(folder_pptx_files) - 30} more")
    else:
        lines.append("- (none)")

    lines.extend(
        [
            "",
            "Fix:",
            "- Update pptx_run_order_template.csv (or pptx_run_order.xlsx).",
            "- Ensure each pptx_path exactly matches an existing .pptx file name/path.",
        ]
    )
    return "\n".join(lines)


def clear_pptx_source_error(root: str) -> None:
    path = os.path.join(root, PPTX_SOURCE_ERROR_FILE)
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def write_pptx_source_error(root: str, message: str) -> None:
    path = os.path.join(root, PPTX_SOURCE_ERROR_FILE)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write((message or "").strip() + "\n")


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

    for candidate in candidates:
        normalized = os.path.normpath(candidate)
        base_name = os.path.basename(normalized).lower()
        if base_name.startswith("~$") or not base_name.endswith(".pptx"):
            continue
        if os.path.isfile(normalized):
            return normalized
    return ""


def read_pptx_run_order(root: str, input_dir: str, queue_path: str) -> tuple[list[str], int, list[str]]:
    if not os.path.isfile(queue_path):
        return [], 0, []

    try:
        from openpyxl import load_workbook
    except Exception:
        print(
            "WARN pptx_run_order.xlsx found but openpyxl is missing. "
            "Install dependencies to use ordered multi-PPTX mode.",
            file=sys.stderr,
        )
        return [], 0, []

    try:
        workbook = load_workbook(queue_path, data_only=True, read_only=True)
        sheet = workbook.active
    except Exception as e:
        print(f"WARN Could not read PPTX run-order file: {queue_path} ({e})", file=sys.stderr)
        return [], 0, []

    header_row = None
    for values in sheet.iter_rows(min_row=1, max_row=1, values_only=True):
        header_row = list(values)
        break

    if not header_row:
        return [], 0, []

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
        return [], 0, []

    items: list[tuple[int, str]] = []
    unresolved_paths: list[str] = []
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
            unresolved_paths.append(raw_path)
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

    return ordered_paths, rows_with_path, unresolved_paths


def read_pptx_run_order_csv(root: str, input_dir: str, queue_path: str) -> tuple[list[str], int, list[str]]:
    if not os.path.isfile(queue_path):
        return [], 0, []

    try:
        with open(queue_path, newline="", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            if not reader.fieldnames:
                return [], 0, []

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
                return [], 0, []

            items: list[tuple[int, str]] = []
            unresolved_paths: list[str] = []
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
                    unresolved_paths.append(raw_path)
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

        return ordered_paths, rows_with_path, unresolved_paths
    except Exception as e:
        print(f"WARN Could not read PPTX run-order CSV: {queue_path} ({e})", file=sys.stderr)
        return [], 0, []


def resolve_pptx_paths(root: str, cfg: dict) -> list[str]:
    input_dir = os.path.join(root, "Data", "AIPresenter", "Input")

    configured = (
        (cfg.get("presentation_pptx_path") or "").strip()
        or (cfg.get("pptx_input_path") or "").strip()
        or (cfg.get("slide_pptx_path") or "").strip()
    )
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
    queue_path_with_rows = ""
    unresolved_queue_entries: list[str] = []
    for queue_path in queue_candidates:
        ext = os.path.splitext(queue_path)[1].lower()
        if ext == ".csv":
            queue_paths, queue_rows, unresolved = read_pptx_run_order_csv(root, input_dir, queue_path)
        else:
            queue_paths, queue_rows, unresolved = read_pptx_run_order(root, input_dir, queue_path)

        if queue_paths:
            return queue_paths
        if queue_rows > 0 and not queue_path_with_rows:
            queue_path_with_rows = queue_path
        queue_rows_detected = max(queue_rows_detected, queue_rows)
        unresolved_queue_entries.extend(unresolved)

    if queue_rows_detected > 0:
        preferred_dir = os.path.join(input_dir, "pptx_file_here")
        preferred_files = list_pptx_files(preferred_dir)

        if unresolved_queue_entries:
            queue_path_for_message = queue_path_with_rows or queue_candidates[0]
            raise RuntimeError(
                build_run_order_mismatch_message(
                    root,
                    queue_path_for_message,
                    unresolved_queue_entries,
                    preferred_files,
                )
            )

        print(
            "WARN PPTX run-order file exists but no valid entries were resolved. "
            "Falling back to folder auto-detection.",
            file=sys.stderr,
        )

    preferred_dir = os.path.join(input_dir, "pptx_file_here")
    preferred_candidate = find_first_pptx(preferred_dir)
    if preferred_candidate:
        return [preferred_candidate]

    return []


def load_rows_from_csv(root: str, csv_path: str) -> list[tuple[int, str, str, str]]:
    rows: list[tuple[int, str, str, str]] = []
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
            abs_path = rel if os.path.isabs(rel) else os.path.normpath(os.path.join(root, rel))
            rows.append((idx, title, abs_path, rel))

    rows.sort(key=lambda x: x[0])
    return rows


def export_pptx_slides_to_images(root: str, pptx_path: str, slide_count: int, deck_order: int) -> list[str]:
    out_root = os.path.join(root, "Data", "AIPresenter", "Temp", "pptx_slides")
    deck_name = sanitize_name(os.path.splitext(os.path.basename(pptx_path))[0])
    out_dir = os.path.join(out_root, f"deck_{deck_order:03d}_{deck_name}")
    os.makedirs(out_dir, exist_ok=True)

    try:
        cc = importlib.import_module("comtypes.client")
    except Exception:
        print(
            "WARN Could not import comtypes.client for PowerPoint image export.",
            file=sys.stderr,
        )
        return []

    app = None
    pres = None
    exported: list[str] = [""] * max(0, slide_count)
    try:
        app = cc.CreateObject("PowerPoint.Application")
        app.Visible = 1

        # Open(FileName, ReadOnly, Untitled, WithWindow)
        pres = app.Presentations.Open(pptx_path, False, False, False)
        total = int(pres.Slides.Count)
        for idx in range(1, total + 1):
            out_png = os.path.join(out_dir, f"slide_{idx:03d}.png")
            slide = pres.Slides.Item(idx)
            # Export to 1920x1080 PNG for consistent ffmpeg behavior.
            slide.Export(out_png, "PNG", 1920, 1080)
            if os.path.isfile(out_png):
                exported[idx - 1] = os.path.normpath(out_png)
    except Exception as e:
        print(
            f"WARN PPTX slide image export failed via PowerPoint COM: {e}",
            file=sys.stderr,
        )
    finally:
        try:
            if pres is not None:
                pres.Close()
        except Exception:
            pass
        try:
            if app is not None:
                app.Quit()
        except Exception:
            pass

    return exported


def load_rows_from_single_pptx(
    root: str,
    pptx_path: str,
    start_index: int,
    deck_order: int,
) -> list[tuple[int, str, str, str]]:
    try:
        Presentation = importlib.import_module("pptx").Presentation
    except Exception:
        print("PPTX detected but python-pptx is missing. Install dependencies.", file=sys.stderr)
        return []

    presentation = Presentation(pptx_path)
    slide_count = len(presentation.slides)
    exported_abs_paths = export_pptx_slides_to_images(root, pptx_path, slide_count, deck_order)

    rows: list[tuple[int, str, str, str]] = []
    base_name = os.path.basename(pptx_path)
    for local_idx, slide in enumerate(presentation.slides, start=1):
        global_idx = start_index + (local_idx - 1)
        title = ""
        try:
            if slide.shapes.title is not None:
                title = (slide.shapes.title.text or "").strip()
        except Exception:
            title = ""
        if not title:
            title = f"Slide {local_idx}"

        abs_path = ""
        rel_path = f"{base_name}#slide={local_idx}"
        if local_idx - 1 < len(exported_abs_paths):
            candidate = exported_abs_paths[local_idx - 1]
            if candidate and os.path.isfile(candidate):
                abs_path = candidate
                rel_path = os.path.relpath(candidate, root)
        rows.append((global_idx, title, abs_path, rel_path))

    if not any(r[2] for r in rows):
        print(
            "WARN PPTX text was parsed, but slide images were not exported. "
            "Audio/Q&A will still work; image display may be skipped.",
            file=sys.stderr,
        )
    return rows


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument(
        "--root",
        default=os.getcwd(),
        help="Project root (UiPath Environment.CurrentDirectory)",
    )
    p.add_argument(
        "--csv",
        default=os.path.join("Data", "AIPresenter", "Input", "slides.csv"),
        help="Path to slides.csv (relative to --root if not absolute)",
    )
    args = p.parse_args()
    root = os.path.normpath(args.root)

    input_dir = os.path.join(root, "Data", "AIPresenter", "Input")
    temp_dir = os.path.join(root, "Data", "AIPresenter", "Temp")
    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(temp_dir, exist_ok=True)
    clear_pptx_export_root(root)

    slides_txt = os.path.join(input_dir, "slides.txt")
    gpt_slide_content = os.path.join(input_dir, "gpt_slide_content.txt")
    gpt_slide_sidecar = os.path.join(temp_dir, "gpt_slide.txt")
    for path in (slides_txt, gpt_slide_content, gpt_slide_sidecar):
        if not os.path.isfile(path):
            open(path, "w", encoding="utf-8").close()

    csv_path = args.csv
    if not os.path.isabs(csv_path):
        csv_path = os.path.normpath(os.path.join(root, csv_path))

    out_tsv = os.path.join(temp_dir, "slides_iterate.tsv")

    cfg_path = os.path.join(root, "Data", "AIPresenter", "Config", "ai_settings.json")
    cfg: dict = {}
    configured_pptx_setting = ""
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
            configured_pptx_setting = (
                (cfg.get("presentation_pptx_path") or "").strip()
                or (cfg.get("pptx_input_path") or "").strip()
                or (cfg.get("slide_pptx_path") or "").strip()
            )
        except Exception:
            cfg = {}
            configured_pptx_setting = ""

    clear_pptx_source_error(root)
    try:
        pptx_paths = resolve_pptx_paths(root, cfg)
    except RuntimeError as e:
        detail = str(e).strip()
        write_pptx_source_error(root, detail)
        print(detail, file=sys.stderr)
        sys.exit(1)

    if configured_pptx_setting and not pptx_paths:
        print(
            "Configured PPTX path not found or unreadable. Check presentation_pptx_path/pptx_input_path/slide_pptx_path.",
            file=sys.stderr,
        )
        sys.exit(1)

    rows: list[tuple[int, str, str, str]] = []
    source_mode = "none"

    if pptx_paths:
        next_index = 1
        for deck_order, pptx_path in enumerate(pptx_paths, start=1):
            deck_rows = load_rows_from_single_pptx(root, pptx_path, next_index, deck_order)
            rows.extend(deck_rows)
            next_index += len(deck_rows)

        source_mode = "pptx" if len(pptx_paths) == 1 else f"pptx-batch:{len(pptx_paths)}"
        print(
            "INFO pptx order: " + ", ".join(os.path.basename(path) for path in pptx_paths),
            file=sys.stderr,
        )
    else:
        rows = load_rows_from_csv(root, csv_path)
        if rows:
            source_mode = "slides.csv"

    with open(out_tsv, "w", encoding="utf-8") as out:
        for idx, title, abs_path, rel in rows:
            out.write(f"{idx}\t{title}\t{abs_path}\t{rel}\n")

    if source_mode == "none":
        print(
            "No PPTX or slides.csv source found. Ensure at least one .pptx is available "
            "(Data/AIPresenter/Input/pptx_file_here or configured path).",
            file=sys.stderr,
        )
        sys.exit(1)

    if source_mode.startswith("pptx") and not rows:
        print(
            "PPTX source was detected but no slides were extracted. "
            "Check PPTX readability and required dependencies (python-pptx/comtypes/PowerPoint).",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"OK source={source_mode} {len(rows)} slide(s) -> {out_tsv}")
    sys.exit(0)


if __name__ == "__main__":
    main()
