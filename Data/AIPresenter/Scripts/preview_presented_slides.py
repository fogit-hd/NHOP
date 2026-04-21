"""Preview previously presented slides while workflow is paused.

The window auto-closes when pause state changes away from "paused".
No audio is played; image-only preview.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

try:
    from PIL import Image, ImageTk  # type: ignore
except Exception:  # pragma: no cover - optional dependency
    Image = None
    ImageTk = None


@dataclass
class SlideRow:
    ordinal: int
    title: str
    abs_path: str
    rel_path: str


def _parse_row_ordinal(raw_index: str, fallback_ordinal: int) -> int:
    token = (raw_index or "").strip()
    if token:
        try:
            declared = int(float(token))
            if declared > 0:
                return declared - 1
        except ValueError:
            pass
    return fallback_ordinal


def _resolve_under_project(path_value: str) -> Path:
    raw = Path(path_value.strip())
    if raw.is_absolute():
        return raw.resolve()
    return (PROJECT_ROOT / raw).resolve()


def _read_text(path: Path, default: str = "") -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return default


def _read_state(state_file: Path) -> str:
    return (_read_text(state_file, "running").strip().lower() or "running")


def _read_int(path: Path, default: int) -> int:
    txt = _read_text(path, "").strip()
    if not txt:
        return default
    try:
        return int(txt)
    except ValueError:
        m = re.search(r"-?\d+", txt)
        if m:
            try:
                return int(m.group(0))
            except ValueError:
                return default
        return default


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        STILL_ACTIVE = 259
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD(0)
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0:
                return False
            return int(exit_code.value) == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _load_rows(tsv_path: Path) -> list[SlideRow]:
    try:
        with tsv_path.open("r", encoding="utf-8", errors="replace", newline="") as f:
            # Keep physical rows intact; splitlines() would break on vertical-tab characters
            # that can appear in PPTX-derived titles.
            lines = [ln.rstrip("\r\n") for ln in f if ln.strip()]
    except Exception:
        lines = [ln for ln in _read_text(tsv_path, "").split("\n") if ln.strip()]

    rows: list[SlideRow] = []
    for physical_ordinal, line in enumerate(lines):
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        # Expected format: index, title, abs_path, rel_path. If title contains tabs,
        # keep the trailing two columns as paths and join the middle pieces back.
        title = parts[1].strip() if len(parts) == 4 else "\t".join(parts[1:-2]).strip()
        abs_path = parts[-2].strip()
        rel_path = parts[-1].strip()

        rows.append(
            SlideRow(
                ordinal=_parse_row_ordinal(parts[0], physical_ordinal),
                title=title,
                abs_path=abs_path,
                rel_path=rel_path,
            )
        )
    return rows


def _resolve_slide_image(row: SlideRow) -> Path | None:
    if row.abs_path:
        abs_path = Path(row.abs_path)
        if abs_path.is_file():
            return abs_path
    if row.rel_path:
        rel_path = _resolve_under_project(row.rel_path)
        if rel_path.is_file():
            return rel_path
    return None


def _load_tk_image(path: Path, max_w: int, max_h: int):
    import tkinter as tk

    if Image is not None and ImageTk is not None:
        try:
            img = Image.open(path)
            img.thumbnail((max_w, max_h), Image.LANCZOS)
            return ImageTk.PhotoImage(img), ""
        except Exception as ex:
            return None, f"Unable to load image: {ex}"

    try:
        img = tk.PhotoImage(file=str(path))
        iw, ih = int(img.width()), int(img.height())
        if iw > 0 and ih > 0:
            factor = int(max(iw / max_w, ih / max_h))
            if factor > 1:
                img = img.subsample(factor, factor)
        return img, ""
    except Exception as ex:
        return None, f"Unable to load image (install Pillow for broader format support): {ex}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file", required=True)
    p.add_argument("--slides-tsv", required=True)
    p.add_argument("--last-completed-ordinal-file", required=True)
    p.add_argument("--owner-pid", type=int, default=0)
    p.add_argument("--title", default="Presented Slides Preview")
    args = p.parse_args()

    state_file = _resolve_under_project(args.state_file)
    slides_tsv = _resolve_under_project(args.slides_tsv)
    completed_file = _resolve_under_project(args.last_completed_ordinal_file)
    owner_pid = int(args.owner_pid or 0)

    import tkinter as tk
    from tkinter import font as tkfont

    root = tk.Tk()
    root.configure(bg="#05070a")
    root.overrideredirect(True)
    root.attributes("-topmost", False)
    screen_w = int(root.winfo_screenwidth())
    screen_h = int(root.winfo_screenheight())
    root.geometry(f"{screen_w}x{screen_h}+0+0")

    text_f = tkfont.Font(family="Segoe UI", size=9)

    body = tk.Frame(root, bg="#05070a", padx=2, pady=2)
    body.pack(fill="both", expand=True)

    canvas_frame = tk.Frame(body, bg="#05070a")
    canvas_frame.pack(fill="both", expand=True)
    img_label = tk.Label(canvas_frame, text="", bg="#05070a", fg="#d8dbe0", borderwidth=0, highlightthickness=0)
    img_label.pack(fill="both", expand=True)

    nav = tk.Frame(body, bg="#05070a")
    nav.pack(fill="x", pady=(2, 0))

    state = {
        "rows": [],
        "index": 0,
        "photo": None,
        "last_loaded_stamp": 0.0,
    }

    def refresh_rows(force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - state["last_loaded_stamp"]) < 0.4:
            return
        state["last_loaded_stamp"] = now

        rows = _load_rows(slides_tsv)
        completed = _read_int(completed_file, -1)
        presented = [r for r in rows if r.ordinal <= completed]
        state["rows"] = presented
        if state["index"] >= len(presented):
            state["index"] = max(0, len(presented) - 1)

    def render() -> None:
        refresh_rows(force=False)
        rows: list[SlideRow] = state["rows"]

        if not rows:
            img_label.configure(
                text="No completed slide is available for preview yet.\nPause after at least one slide is completed.",
                image="",
                compound="none",
                font=text_f,
                justify="center",
            )
            btn_prev.configure(state="disabled")
            btn_next.configure(state="disabled")
            lbl_page.configure(text="0 / 0")
            state["photo"] = None
            return

        idx = int(state["index"])
        row = rows[idx]
        slide_path = _resolve_slide_image(row)
        lbl_page.configure(text=f"{idx + 1} / {len(rows)}")

        btn_prev.configure(state=("normal" if idx > 0 else "disabled"))
        btn_next.configure(state=("normal" if idx < len(rows) - 1 else "disabled"))

        if slide_path is None:
            img_label.configure(
                text="Slide image not found for this entry.\n" + (row.abs_path or row.rel_path),
                image="",
                compound="none",
                font=text_f,
                justify="center",
            )
            state["photo"] = None
            return

        root.update_idletasks()
        max_w = max(320, img_label.winfo_width() - 4)
        max_h = max(240, img_label.winfo_height() - 4)
        photo, err = _load_tk_image(slide_path, max_w, max_h)
        if photo is None:
            img_label.configure(
                text=(err + "\n" + str(slide_path)),
                image="",
                compound="none",
                font=text_f,
                justify="center",
            )
            state["photo"] = None
            return

        state["photo"] = photo
        img_label.configure(image=photo, text="", compound="center")

    def on_prev() -> None:
        if state["index"] > 0:
            state["index"] -= 1
            render()

    def on_next() -> None:
        rows = state["rows"]
        if state["index"] < (len(rows) - 1):
            state["index"] += 1
            render()

    btn_prev = tk.Button(nav, text="Previous", padx=12, pady=4, command=on_prev)
    btn_prev.pack(side="left")

    btn_next = tk.Button(nav, text="Next", padx=12, pady=4, command=on_next)
    btn_next.pack(side="left", padx=(8, 0))

    lbl_page = tk.Label(nav, text="0 / 0", bg="#05070a", fg="#d2d7de", font=text_f)
    lbl_page.pack(side="right")

    def monitor() -> None:
        if owner_pid > 0 and not _process_alive(owner_pid):
            root.destroy()
            return
        if _read_state(state_file) != "paused":
            root.destroy()
            return
        render()
        root.after(250, monitor)

    root.bind("<Left>", lambda _e: on_prev())
    root.bind("<Right>", lambda _e: on_next())
    root.bind("<Escape>", lambda _e: root.destroy())

    refresh_rows(force=True)
    state["index"] = max(0, len(state["rows"]) - 1)
    render()
    monitor()
    root.mainloop()

    sys.exit(0)


if __name__ == "__main__":
    main()
