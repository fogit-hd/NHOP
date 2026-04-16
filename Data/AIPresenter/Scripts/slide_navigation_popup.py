"""Compact slide navigation popup shown in a screen corner.

Run with pythonw (no console). In yes/no mode, writes one line to --result-file:
'yes' or 'no' (UTF-8). Fallback uses ctypes MessageBoxW on Windows.
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import sys
import time
from ctypes import wintypes
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent.parent.parent

BG = "#f5f6f8"
FG = "#1b1b1b"
ACCENT = "#0078d4"
ACCENT_HOVER = "#106ebe"
MUTED = "#605e5c"
BTN_SEC_BG = "#ffffff"
BTN_SEC_FG = "#323130"
BORDER = "#e1e1e1"

# Corner margin from screen edges (px); extra bottom offset for typical taskbar
MARGIN_X = 20
MARGIN_Y_BOTTOM = 56
MIN_ANCHOR_RECT_WIDTH = 640
MIN_ANCHOR_RECT_HEIGHT = 360


class _RECT(ctypes.Structure):
    _fields_ = [
        ("left", ctypes.c_long),
        ("top", ctypes.c_long),
        ("right", ctypes.c_long),
        ("bottom", ctypes.c_long),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", _RECT),
        ("rcWork", _RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _resolve_result_path(p: str) -> Path:
    raw = Path(p.strip())
    if raw.is_absolute():
        return raw
    return (PROJECT_ROOT / raw).resolve()


def _append_debug_line(text: str) -> None:
    try:
        dbg = (PROJECT_ROOT / "Data" / "AIPresenter" / "Temp" / "popup_position_debug.log").resolve()
        dbg.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")
        with dbg.open("a", encoding="utf-8", newline="\n") as f:
            f.write(f"{ts} | {text}\n")
    except Exception:
        pass


def _pin_window_topmost(hwnd: int, x: int | None = None, y: int | None = None, w: int | None = None, h: int | None = None) -> None:
    if sys.platform != "win32":
        return
    user32 = ctypes.windll.user32
    HWND_TOPMOST = -1
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_SHOWWINDOW = 0x0040
    SW_SHOW = 5
    try:
        user32.ShowWindow(hwnd, SW_SHOW)
        if x is None or y is None or w is None or h is None:
            flags = SWP_NOSIZE | SWP_NOMOVE | SWP_SHOWWINDOW
            user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags)
        else:
            user32.SetWindowPos(hwnd, HWND_TOPMOST, int(x), int(y), int(w), int(h), SWP_SHOWWINDOW)
    except Exception:
        pass


def _get_foreground_work_area() -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return None
    MONITOR_DEFAULTTONEAREST = 2
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    wa = mi.rcWork
    return wa.left, wa.top, wa.right, wa.bottom


def _get_primary_work_area() -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    SPI_GETWORKAREA = 0x0030
    r = _RECT()
    if user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(r), 0):
        if r.right > r.left and r.bottom > r.top:
            return r.left, r.top, r.right, r.bottom
    sw = int(user32.GetSystemMetrics(0))
    sh = int(user32.GetSystemMetrics(1))
    if sw > 0 and sh > 0:
        return 0, 0, sw, sh
    return None


def _read_pid(pid_file: str) -> int | None:
    raw = pid_file.strip()
    if not raw:
        return None
    try:
        p = Path(raw)
        if not p.is_absolute():
            p = (PROJECT_ROOT / p).resolve()
        txt = p.read_text(encoding="utf-8", errors="replace").strip()
        if not txt:
            return None
        return int(txt)
    except Exception:
        return None


def _get_window_rect(hwnd: int) -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    r = _RECT()
    if not user32.GetWindowRect(hwnd, ctypes.byref(r)):
        return None
    if r.right <= r.left or r.bottom <= r.top:
        return None
    return r.left, r.top, r.right, r.bottom


def _get_window_for_pid(pid: int) -> int | None:
    if sys.platform != "win32":
        return None
    user32 = ctypes.windll.user32
    target = int(pid)
    found: list[tuple[int, int, int]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _enum_cb(hwnd, _lparam):
        if not user32.IsWindowVisible(hwnd):
            return True
        pid_out = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_out))
        if int(pid_out.value) == target:
            rect = _get_window_rect(int(hwnd))
            if rect is not None:
                w = rect[2] - rect[0]
                h = rect[3] - rect[1]
                area = max(0, w * h)
                title_len = int(user32.GetWindowTextLengthW(hwnd))
                found.append((area, title_len, int(hwnd)))
        return True

    user32.EnumWindows(_enum_cb, 0)
    if not found:
        return None
    found.sort(key=lambda t: (t[0], t[1]), reverse=True)
    return found[0][2]


def _get_window_rect_for_pid(pid: int) -> tuple[int, int, int, int] | None:
    hwnd = _get_window_for_pid(pid)
    if not hwnd:
        return None
    return _get_window_rect(hwnd)


def _get_work_area_for_pid(pid: int) -> tuple[int, int, int, int] | None:
    if sys.platform != "win32":
        return None
    hwnd = _get_window_for_pid(pid)
    if not hwnd:
        return None
    user32 = ctypes.windll.user32
    MONITOR_DEFAULTTONEAREST = 2
    hmon = user32.MonitorFromWindow(hwnd, MONITOR_DEFAULTTONEAREST)
    if not hmon:
        return None
    mi = _MONITORINFO()
    mi.cbSize = ctypes.sizeof(_MONITORINFO)
    if not user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
        return None
    wa = mi.rcWork
    return wa.left, wa.top, wa.right, wa.bottom


def _run_tkinter(title: str, message: str, mode: str = "yesno", ok_text: str = "OK", anchor_pid_file: str = "") -> str:
    import tkinter as tk
    from tkinter import font as tkfont

    choice: dict[str, str | None] = {"v": None}
    opened_at = time.monotonic()

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    try:
        root.attributes("-alpha", 0.96)
    except tk.TclError:
        pass

    outer = tk.Frame(root, bg=BG, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
    outer.pack(fill="both", expand=True)

    body_f = tkfont.Font(family="Segoe UI", size=9)

    if title.strip():
        tk.Label(
            outer,
            text=title,
            font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
            bg=BG,
            fg=MUTED,
            anchor="w",
        ).pack(fill="x", pady=(0, 4))

    tk.Label(
        outer,
        text=message,
        font=body_f,
        bg=BG,
        fg=FG,
        wraplength=240,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 4))
    # Keep the popup compact so slide content remains visible.
    
    row_pad_top = 10

    row = tk.Frame(outer, bg=BG)
    row.pack(anchor="e", pady=(row_pad_top, 0))

    def on_yes() -> None:
        choice["v"] = "yes"
        root.destroy()

    def on_no() -> None:
        choice["v"] = "no"
        root.destroy()

    def on_ok() -> None:
        choice["v"] = "ok"
        root.destroy()

    if mode == "ok":
        btn_ok = tk.Button(
            row,
            text=ok_text.strip() or "OK",
            font=body_f,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            padx=18,
            pady=5,
            cursor="hand2",
            command=on_ok,
            borderwidth=0,
            highlightthickness=0,
        )
        btn_ok.grid(row=0, column=0)
        btn_ok.bind("<Enter>", lambda e: btn_ok.configure(bg=ACCENT_HOVER))
        btn_ok.bind("<Leave>", lambda e: btn_ok.configure(bg=ACCENT))
    else:
        btn_yes = tk.Button(
            row,
            text="Yes",
            font=body_f,
            bg=ACCENT,
            fg="white",
            activebackground=ACCENT_HOVER,
            activeforeground="white",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=on_yes,
            borderwidth=0,
            highlightthickness=0,
        )
        btn_no = tk.Button(
            row,
            text="No",
            font=body_f,
            bg=BTN_SEC_BG,
            fg=BTN_SEC_FG,
            activebackground="#f3f2f1",
            relief="flat",
            padx=14,
            pady=5,
            cursor="hand2",
            command=on_no,
            borderwidth=1,
            highlightthickness=0,
            highlightbackground=BORDER,
        )
        btn_yes.grid(row=0, column=0, padx=(0, 8))
        btn_no.grid(row=0, column=1)
        btn_yes.bind("<Enter>", lambda e: btn_yes.configure(bg=ACCENT_HOVER))
        btn_yes.bind("<Leave>", lambda e: btn_yes.configure(bg=ACCENT))

    shown_at = time.monotonic()

    def _hotkey_ready() -> bool:
        # Ignore sticky Enter/Esc from the previous interaction right after opening.
        return (time.monotonic() - shown_at) >= 0.35

    root.protocol("WM_DELETE_WINDOW", on_ok if mode == "ok" else on_no)
    if mode == "ok":
        root.bind("<Return>", lambda e: (on_ok() if _hotkey_ready() else "break"))
        root.bind("<Escape>", lambda e: (on_ok() if _hotkey_ready() else "break"))
    else:
        root.bind("<Return>", lambda e: (on_yes() if _hotkey_ready() else "break"))
        root.bind("<Escape>", lambda e: (on_no() if _hotkey_ready() else "break"))

    root.update_idletasks()
    w = max(root.winfo_reqwidth(), 260)
    h = max(root.winfo_reqheight(), 88)
    pid = _read_pid(anchor_pid_file)
    vx = int(root.winfo_vrootx())
    vy = int(root.winfo_vrooty())
    vw = int(root.winfo_vrootwidth())
    vh = int(root.winfo_vrootheight())
    if vw <= 0:
        vx = 0
        vw = int(root.winfo_screenwidth())
    if vh <= 0:
        vy = 0
        vh = int(root.winfo_screenheight())
    min_x = vx + MARGIN_X
    max_x = vx + max(MARGIN_X, vw - w - MARGIN_X)
    min_y = vy + MARGIN_X
    max_y = vy + max(MARGIN_X, vh - h - MARGIN_X)
    x = max_x  # top-right
    y = min_y
    x = min(max(x, min_x), max_x)
    y = min(max(y, min_y), max_y)
    _append_debug_line(f"tk-vroot pid={pid} vroot=({vx},{vy},{vw},{vh}) popup=({x},{y},{w},{h})")

    root.geometry(f"{w}x{h}+{x}+{y}")
    root.deiconify()

    def reinforce_topmost(remaining: int = 24) -> None:
        if remaining <= 0:
            return
        try:
            root.geometry(f"{w}x{h}+{x}+{y}")
            root.attributes("-topmost", True)
            root.lift()
            _pin_window_topmost(int(root.winfo_id()))
        except Exception:
            pass
        root.after(120, lambda: reinforce_topmost(remaining - 1))

    try:
        if mode == "ok":
            btn_ok.focus_set()
        else:
            btn_yes.focus_set()
    except Exception:
        pass

    root.lift()
    try:
        root.focus_force()
    except Exception:
        pass
    reinforce_topmost()

    root.mainloop()
    elapsed = time.monotonic() - opened_at
    if elapsed < 0.8 and choice["v"] is None:
        raise RuntimeError("tk popup closed too quickly")
    if choice["v"] in {"yes", "no", "ok"}:
        return choice["v"]
    return "ok" if mode == "ok" else "no"


def _run_ctypes(message: str, title: str) -> str:
    MB_YESNO = 0x4
    MB_ICONQUESTION = 0x20
    MB_TOPMOST = 0x40000
    MB_SYSTEMMODAL = 0x1000
    MB_SETFOREGROUND = 0x10000
    flags = MB_YESNO | MB_ICONQUESTION | MB_TOPMOST | MB_SYSTEMMODAL | MB_SETFOREGROUND
    r = ctypes.windll.user32.MessageBoxW(0, message, title, flags)
    IDYES = 6
    return "yes" if r == IDYES else "no"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--result-file", default="", help="UTF-8 file for popup result")
    p.add_argument("--mode", choices=["yesno", "ok"], default="yesno")
    p.add_argument("--ok-text", default="OK")
    p.add_argument("--anchor-pid-file", default="")
    p.add_argument("--title", default="Slide complete")
    p.add_argument("--message", default="Press Next to continue to the next slide.")
    args = p.parse_args()

    out_path: Path | None = None
    if args.result_file.strip():
        out_path = _resolve_result_path(args.result_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    elif args.mode == "yesno":
        raise SystemExit("--result-file is required when --mode yesno")

    try:
        text = _run_tkinter(args.title, args.message, args.mode, args.ok_text, args.anchor_pid_file)
    except Exception:
        if args.mode == "ok":
            text = "ok"
        else:
            text = _run_ctypes(args.message, args.title) if sys.platform == "win32" else "no"

    if args.mode == "ok":
        text = "ok"
    else:
        text = "yes" if text.strip().lower().startswith("y") else "no"

    if out_path is not None:
        out_path.write_text(text + "\n", encoding="utf-8")
    sys.exit(0)


if __name__ == "__main__":
    main()
