"""Build Temp/slides_iterate.tsv for UiPath from available slide sources.

Priority:
1) Data/AIPresenter/Input/slides.csv
2) .pptx in Data/AIPresenter/Input (or configured path)

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


def clear_pptx_export_dir(root: str) -> str:
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


def resolve_pptx_path(root: str) -> str:
    cfg_path = os.path.join(root, "Data", "AIPresenter", "Config", "ai_settings.json")
    if os.path.isfile(cfg_path):
        try:
            with open(cfg_path, encoding="utf-8-sig") as f:
                cfg = json.load(f)
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
        except Exception:
            pass

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


def load_rows_from_pptx(root: str) -> list[tuple[int, str, str, str]]:
    pptx_path = resolve_pptx_path(root)
    if not pptx_path:
        return []

    try:
        Presentation = importlib.import_module("pptx").Presentation
    except Exception:
        print("PPTX detected but python-pptx is missing. Install dependencies.", file=sys.stderr)
        return []

    presentation = Presentation(pptx_path)
    slide_count = len(presentation.slides)
    exported_abs_paths = export_pptx_slides_to_images(root, pptx_path, slide_count)

    rows: list[tuple[int, str, str, str]] = []
    base_name = os.path.basename(pptx_path)
    for idx, slide in enumerate(presentation.slides, start=1):
        title = ""
        try:
            if slide.shapes.title is not None:
                title = (slide.shapes.title.text or "").strip()
        except Exception:
            title = ""
        if not title:
            title = f"Slide {idx}"

        abs_path = ""
        rel_path = f"{base_name}#slide={idx}"
        if idx - 1 < len(exported_abs_paths):
            candidate = exported_abs_paths[idx - 1]
            if candidate and os.path.isfile(candidate):
                abs_path = candidate
                rel_path = os.path.relpath(candidate, root)
        rows.append((idx, title, abs_path, rel_path))

    if not any(r[2] for r in rows):
        print(
            "WARN PPTX text was parsed, but slide images were not exported. "
            "Audio/Q&A will still work; image display may be skipped.",
            file=sys.stderr,
        )
    return rows


def export_pptx_slides_to_images(root: str, pptx_path: str, slide_count: int) -> list[str]:
    out_dir = clear_pptx_export_dir(root)

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
    clear_pptx_export_dir(root)

    slides_txt = os.path.join(input_dir, "slides.txt")
    gpt_slide_content = os.path.join(input_dir, "gpt_slide_content.txt")
    gpt_slide_sidecar = os.path.join(temp_dir, "gpt_slide.txt")
    for path in (slides_txt, gpt_slide_content, gpt_slide_sidecar):
        if not os.path.isfile(path):
            open(path, "w", encoding="utf-8").close()

    csv_path = args.csv
    if not os.path.isabs(csv_path):
        csv_path = os.path.normpath(os.path.join(root, csv_path))

    out_dir = temp_dir
    out_tsv = os.path.join(out_dir, "slides_iterate.tsv")

    rows = load_rows_from_csv(root, csv_path)
    source_mode = "slides.csv"

    cfg_path = os.path.join(root, "Data", "AIPresenter", "Config", "ai_settings.json")
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
            configured_pptx_setting = ""

    pptx_rows = load_rows_from_pptx(root)
    if configured_pptx_setting and not pptx_rows:
        print(
            "Configured PPTX path not found or unreadable. Check presentation_pptx_path/pptx_input_path/slide_pptx_path.",
            file=sys.stderr,
        )
        sys.exit(1)

    if configured_pptx_setting and pptx_rows:
        rows = pptx_rows
        source_mode = "pptx"
    elif not rows and pptx_rows:
        rows = pptx_rows
        source_mode = "pptx"
    elif not rows:
        source_mode = "none"

    with open(out_tsv, "w", encoding="utf-8") as out:
        for idx, title, abs_path, rel in rows:
            out.write(f"{idx}\t{title}\t{abs_path}\t{rel}\n")

    if source_mode == "none":
        print("No slides.csv or PPTX source found; wrote empty slides_iterate.tsv", file=sys.stderr)
    print(f"OK source={source_mode} {len(rows)} slide(s) -> {out_tsv}")
    sys.exit(0)


if __name__ == "__main__":
    main()
