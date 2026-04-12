"""Read Data/AIPresenter/Input/slides.csv and write Temp/slides_iterate.tsv for UiPath.

CSV columns: slide_index, slide_title, slide_path
slide_path must be relative to the project root (where UiPath sets CurrentDirectory), e.g.:
  Data\\AIPresenter\\Input\\photos\\slide_01.jpg

Output TSV columns (tab-separated): index, title, absolute_path, relative_path
Rows are sorted by slide_index ascending.
"""
from __future__ import annotations

import argparse
import csv
import os
import sys


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

    if not os.path.isfile(csv_path):
        open(out_tsv, "w", encoding="utf-8").close()
        print("slides.csv not found; wrote empty slides_iterate.tsv", file=sys.stderr)
        sys.exit(0)

    rows: list[tuple[int, str, str, str]] = []
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

    with open(out_tsv, "w", encoding="utf-8") as out:
        for idx, title, abs_path, rel in rows:
            out.write(f"{idx}\t{title}\t{abs_path}\t{rel}\n")

    print(f"OK {len(rows)} slide(s) -> {out_tsv}")
    sys.exit(0)


if __name__ == "__main__":
    main()
