"""Convert legacy AIPresenter CSV input files to Excel workbooks (.xlsx).

Usage examples:
  py Data\\AIPresenter\\Scripts\\migrate_csv_inputs_to_xlsx.py --root "%CD%"
  py Data\\AIPresenter\\Scripts\\migrate_csv_inputs_to_xlsx.py --root "%CD%" --overwrite
  py Data\\AIPresenter\\Scripts\\migrate_csv_inputs_to_xlsx.py --root "%CD%" --delete-csv
"""
from __future__ import annotations

import argparse
import csv
import os
import re
import sys
from pathlib import Path

try:
    from openpyxl import Workbook
except Exception:  # pragma: no cover - startup guard
    Workbook = None  # type: ignore[assignment]

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent
ILLEGAL_XLSX_CHAR_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F]")

DEFAULT_FILES = (
    os.path.join("Data", "AIPresenter", "Input", "pptx_run_order_template.csv"),
    os.path.join("Data", "AIPresenter", "Input", "slides.csv"),
    os.path.join("Data", "AIPresenter", "Input", "slide_narration_mode.csv"),
    os.path.join("Data", "AIPresenter", "Input", "slide_index_mapping.csv"),
)


def _resolve_path(root: Path, value: str) -> Path:
    raw = Path((value or "").strip())
    if raw.is_absolute():
        return raw
    return (root / raw).resolve()


def _safe_print(message: str, *, is_error: bool = False) -> None:
    stream = sys.stderr if is_error else sys.stdout
    text = message + "\n"
    try:
        stream.write(text)
        stream.flush()
        return
    except UnicodeEncodeError:
        pass

    encoding = getattr(stream, "encoding", None) or "utf-8"
    payload = text.encode(encoding, errors="backslashreplace")
    buffer = getattr(stream, "buffer", None)
    if buffer is not None:
        try:
            buffer.write(payload)
            buffer.flush()
            return
        except Exception:
            pass


def _sanitize_cell_text(value: str) -> str:
    # openpyxl rejects control chars (e.g. vertical tab \x0B) inside a cell.
    return ILLEGAL_XLSX_CHAR_RE.sub(" ", value or "")


def _csv_to_xlsx(csv_path: Path, xlsx_path: Path, overwrite: bool) -> tuple[bool, str]:
    if not csv_path.is_file():
        return False, f"SKIP missing: {csv_path}"

    if xlsx_path.exists() and not overwrite:
        return False, f"SKIP exists:  {xlsx_path} (use --overwrite)"

    rows: list[list[str]] = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.reader(f)
        for row in reader:
            rows.append([_sanitize_cell_text(str(cell or "")) for cell in row])

    wb = Workbook()
    ws = wb.active
    ws.title = "Sheet1"
    for row in rows:
        ws.append(row)

    xlsx_path.parent.mkdir(parents=True, exist_ok=True)
    wb.save(xlsx_path)
    wb.close()
    return True, f"OK converted: {csv_path} -> {xlsx_path}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--root", default=str(PROJECT_ROOT), help="Project root folder")
    p.add_argument(
        "--files",
        nargs="*",
        default=list(DEFAULT_FILES),
        help="CSV file paths (absolute or relative to --root)",
    )
    p.add_argument("--overwrite", action="store_true", help="Overwrite existing .xlsx output files")
    p.add_argument("--delete-csv", action="store_true", help="Delete CSV after successful conversion")
    args = p.parse_args()

    if Workbook is None:
        print(
            "ERROR openpyxl is not installed. Install requirements first.",
            file=sys.stderr,
        )
        sys.exit(2)

    root = Path(args.root).resolve()
    converted = 0
    skipped = 0
    deleted = 0

    for raw_path in args.files:
        csv_path = _resolve_path(root, raw_path)
        if csv_path.suffix.lower() != ".csv":
            _safe_print(f"SKIP not .csv: {csv_path}")
            skipped += 1
            continue

        xlsx_path = csv_path.with_suffix(".xlsx")
        try:
            did_convert, msg = _csv_to_xlsx(csv_path, xlsx_path, overwrite=bool(args.overwrite))
            _safe_print(msg)
            if not did_convert:
                skipped += 1
                continue
            converted += 1
            if args.delete_csv:
                try:
                    csv_path.unlink(missing_ok=True)
                    deleted += 1
                    _safe_print(f"OK deleted CSV: {csv_path}")
                except OSError as e:
                    _safe_print(f"WARN could not delete CSV: {csv_path} ({e})", is_error=True)
        except Exception as e:
            _safe_print(f"ERROR convert failed: {csv_path} ({e})", is_error=True)

    _safe_print(f"SUMMARY converted={converted} skipped={skipped} deleted={deleted}")
    sys.exit(0 if converted > 0 else 1)


if __name__ == "__main__":
    main()
