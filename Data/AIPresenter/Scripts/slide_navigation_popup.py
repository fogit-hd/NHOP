"""Compact popup UI utilities for slide navigation and playback control.

Run with pythonw (no console).
- yes/no mode: writes one line to --result-file ('yes' or 'no', UTF-8)
- ok mode: simple blocking acknowledgement popup
- pausecontrol mode: persistent Pause/Continue toggle writing state to --state-file
- countdown mode: auto-close transition popup with countdown timer
"""
from __future__ import annotations

import argparse
import ctypes
import datetime
import math
import os
import subprocess
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
CONTINUE_BG = "#107c10"
CONTINUE_HOVER = "#0b6a0b"
ICON_BTN_BG = "#ffffff"
ICON_BTN_HOVER = "#edf5ff"
ICON_BTN_ACTIVE = "#dbeeff"
ICON_BTN_BORDER = "#c7d8ea"
ICON_BTN_HOVER_BORDER = "#8db8e2"
ICON_BTN_DISABLED_BG = "#f3f2f1"
ICON_BTN_DISABLED_FG = "#a19f9d"

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


def _write_state(path: Path, value: str) -> None:
    normalized = value.strip().lower()
    if not normalized:
        normalized = "running"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(normalized + "\n", encoding="utf-8")


def _read_state(path: Path, default: str = "running") -> str:
    try:
        val = path.read_text(encoding="utf-8", errors="replace").strip().lower()
        return val or default
    except Exception:
        return default


def _process_alive(pid: int) -> bool:
    if pid <= 0:
        return True
    if sys.platform == "win32":
        kernel32 = ctypes.windll.kernel32
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, int(pid))
        if not handle:
            return False
        try:
            exit_code = wintypes.DWORD()
            if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)) == 0:
                return False
            STILL_ACTIVE = 259
            return int(exit_code.value) == STILL_ACTIVE
        finally:
            kernel32.CloseHandle(handle)
    try:
        os.kill(int(pid), 0)
        return True
    except OSError:
        return False


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


def _run_pause_control(
    title: str,
    message: str,
    state_file: Path,
    owner_pid: int = 0,
    pid_file: Path | None = None,
    preview_script: Path | None = None,
    slides_tsv: Path | None = None,
    last_completed_ordinal_file: Path | None = None,
) -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)
    target_alpha = 0.96
    supports_alpha = True
    try:
        root.attributes("-alpha", 0.0)
    except tk.TclError:
        supports_alpha = False

    _write_state(state_file, "running")
    if pid_file is not None:
        try:
            pid_file.parent.mkdir(parents=True, exist_ok=True)
            pid_file.write_text(str(os.getpid()) + "\n", encoding="utf-8")
        except Exception:
            pass

    outer = tk.Frame(root, bg=BG, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
    outer.pack(fill="both", expand=True)

    icon_frame = tk.Frame(root, bg=BG, padx=4, pady=4, highlightthickness=1, highlightbackground=BORDER)

    body_f = tkfont.Font(family="Segoe UI", size=9)
    small_f = tkfont.Font(family="Segoe UI", size=8)
    try:
        icon_f = tkfont.Font(family="Segoe UI Symbol", size=11, weight="bold")
    except tk.TclError:
        icon_f = tkfont.Font(family="Segoe UI", size=11, weight="bold")

    header = tk.Frame(outer, bg=BG)
    header.pack(fill="x", pady=(0, 4))

    tk.Label(
        header,
        text=(title.strip() or "Presentation control"),
        font=tkfont.Font(family="Segoe UI", size=9, weight="bold"),
        bg=BG,
        fg=MUTED,
        anchor="w",
    ).pack(side="left", fill="x", expand=True)

    btn_compact = tk.Button(
        header,
        text="\u25be",
        font=small_f,
        bg=BTN_SEC_BG,
        fg=BTN_SEC_FG,
        activebackground="#f3f2f1",
        relief="flat",
        padx=6,
        pady=2,
        cursor="hand2",
        borderwidth=1,
        highlightthickness=0,
        highlightbackground=BORDER,
    )
    btn_compact.pack(side="right", padx=(8, 0))

    icon_row = tk.Frame(icon_frame, bg=BG)
    icon_row.pack(fill="both", expand=True)

    btn_icon_toggle = tk.Button(
        icon_row,
        text="\u23f8",
        font=icon_f,
        width=3,
        bg=ACCENT,
        fg="white",
        activebackground=ACCENT_HOVER,
        activeforeground="white",
        relief="flat",
        padx=2,
        pady=2,
        cursor="hand2",
        borderwidth=0,
        highlightthickness=1,
        highlightbackground=ICON_BTN_BORDER,
    )
    btn_icon_toggle.pack(side="top", fill="x", pady=(0, 4))

    btn_icon_preview = tk.Button(
        icon_row,
        text="\u25c9",
        font=icon_f,
        width=3,
        bg=BTN_SEC_BG,
        fg=BTN_SEC_FG,
        activebackground="#f3f2f1",
        relief="flat",
        padx=2,
        pady=2,
        cursor="hand2",
        borderwidth=1,
        highlightthickness=1,
        highlightbackground=ICON_BTN_BORDER,
        state="disabled",
    )
    btn_icon_preview.pack(side="top", fill="x", pady=(0, 4))

    btn_icon_expand = tk.Button(
        icon_row,
        text="\u2197",
        font=icon_f,
        width=3,
        bg=BTN_SEC_BG,
        fg=BTN_SEC_FG,
        activebackground="#f3f2f1",
        relief="flat",
        padx=2,
        pady=2,
        cursor="hand2",
        borderwidth=1,
        highlightthickness=1,
        highlightbackground=ICON_BTN_BORDER,
    )
    btn_icon_expand.pack(side="top", fill="x")

    running_message = message.strip() or "Auto mode is running. Click Pause to stop at checkpoints."
    paused_message = "Workflow is paused. Click Continue to resume."

    lbl_status = tk.Label(
        outer,
        text=running_message,
        font=body_f,
        bg=BG,
        fg=FG,
        wraplength=280,
        justify="left",
        anchor="w",
    )
    lbl_status.pack(fill="x", pady=(0, 8))

    row = tk.Frame(outer, bg=BG)
    row.pack(anchor="e")

    state = {"paused": False, "icon_only": False, "pulse_tick": 0}
    win = {"w": 0, "h": 0, "x": 0, "y": 0}
    preview_proc: dict[str, subprocess.Popen | None] = {"p": None}
    compact_btn_state = {"hovered": False}

    def _refresh_compact_button() -> None:
        base_bg = "#eef5ff" if state["icon_only"] else BTN_SEC_BG
        hover_bg = "#deecff"
        bg = hover_bg if compact_btn_state["hovered"] else base_bg
        btn_compact.configure(
            text=("\u25b8" if state["icon_only"] else "\u25be"),
            bg=bg,
            fg=BTN_SEC_FG,
            activebackground=hover_bg,
            activeforeground=BTN_SEC_FG,
            highlightbackground=(ICON_BTN_HOVER_BORDER if compact_btn_state["hovered"] else ICON_BTN_BORDER),
        )

    def _refresh_icon_button(btn: tk.Button) -> None:
        base_bg = str(getattr(btn, "_fx_base_bg", ICON_BTN_BG))
        hover_bg = str(getattr(btn, "_fx_hover_bg", ICON_BTN_HOVER))
        fg = str(getattr(btn, "_fx_fg", BTN_SEC_FG))
        border = str(getattr(btn, "_fx_border", ICON_BTN_BORDER))
        hovered = bool(getattr(btn, "_fx_hovered", False))
        is_disabled = str(btn.cget("state")).lower() == "disabled"

        if is_disabled:
            btn.configure(
                bg=ICON_BTN_DISABLED_BG,
                fg=ICON_BTN_DISABLED_FG,
                activebackground=ICON_BTN_DISABLED_BG,
                activeforeground=ICON_BTN_DISABLED_FG,
                highlightbackground=BORDER,
            )
            return

        btn.configure(
            bg=(hover_bg if hovered else base_bg),
            fg=fg,
            activebackground=hover_bg,
            activeforeground=fg,
            highlightbackground=(ICON_BTN_HOVER_BORDER if hovered else border),
        )

    def _set_icon_button_theme(btn: tk.Button, *, base_bg: str, hover_bg: str, fg: str, border: str) -> None:
        setattr(btn, "_fx_base_bg", base_bg)
        setattr(btn, "_fx_hover_bg", hover_bg)
        setattr(btn, "_fx_fg", fg)
        setattr(btn, "_fx_border", border)
        _refresh_icon_button(btn)

    def _bind_icon_button_effects(btn: tk.Button) -> None:
        try:
            base_pad = int(str(btn.cget("pady")).split()[0])
        except (TypeError, ValueError, IndexError):
            base_pad = 2
        setattr(btn, "_fx_base_pad", base_pad)
        setattr(btn, "_fx_hovered", False)

        def _on_enter(_event) -> None:
            setattr(btn, "_fx_hovered", True)
            _refresh_icon_button(btn)

        def _on_leave(_event) -> None:
            setattr(btn, "_fx_hovered", False)
            _refresh_icon_button(btn)

        def _on_press(_event) -> None:
            if str(btn.cget("state")).lower() == "disabled":
                return
            btn.configure(pady=max(0, int(getattr(btn, "_fx_base_pad", 2)) - 1))

        def _on_release(_event) -> None:
            btn.configure(pady=int(getattr(btn, "_fx_base_pad", 2)))
            _refresh_icon_button(btn)

        btn.bind("<Enter>", _on_enter, add="+")
        btn.bind("<Leave>", _on_leave, add="+")
        btn.bind("<ButtonPress-1>", _on_press, add="+")
        btn.bind("<ButtonRelease-1>", _on_release, add="+")

    def _animate_compact_icon_enter() -> None:
        for idx, button in enumerate((btn_icon_toggle, btn_icon_preview, btn_icon_expand)):
            def _flash(btn: tk.Button = button) -> None:
                if not state["icon_only"] or str(btn.cget("state")).lower() == "disabled":
                    return
                btn.configure(bg=ICON_BTN_ACTIVE)
                root.after(90, lambda b=btn: _refresh_icon_button(b))

            root.after(idx * 55, _flash)

    def _on_compact_enter(_event) -> None:
        compact_btn_state["hovered"] = True
        _refresh_compact_button()

    def _on_compact_leave(_event) -> None:
        compact_btn_state["hovered"] = False
        _refresh_compact_button()

    def _on_compact_press(_event) -> None:
        btn_compact.configure(pady=1)

    def _on_compact_release(_event) -> None:
        btn_compact.configure(pady=2)
        _refresh_compact_button()

    btn_compact.bind("<Enter>", _on_compact_enter, add="+")
    btn_compact.bind("<Leave>", _on_compact_leave, add="+")
    btn_compact.bind("<ButtonPress-1>", _on_compact_press, add="+")
    btn_compact.bind("<ButtonRelease-1>", _on_compact_release, add="+")

    _bind_icon_button_effects(btn_icon_toggle)
    _bind_icon_button_effects(btn_icon_preview)
    _bind_icon_button_effects(btn_icon_expand)
    _set_icon_button_theme(
        btn_icon_preview,
        base_bg=ICON_BTN_BG,
        hover_bg=ICON_BTN_HOVER,
        fg=BTN_SEC_FG,
        border=ICON_BTN_BORDER,
    )
    _set_icon_button_theme(
        btn_icon_expand,
        base_bg=ICON_BTN_BG,
        hover_bg=ICON_BTN_HOVER,
        fg=BTN_SEC_FG,
        border=ICON_BTN_BORDER,
    )
    _refresh_compact_button()

    def can_preview() -> bool:
        return (
            preview_script is not None
            and slides_tsv is not None
            and last_completed_ordinal_file is not None
            and preview_script.is_file()
            and slides_tsv.is_file()
            and last_completed_ordinal_file.exists()
        )

    def launch_preview() -> None:
        if not state["paused"]:
            return
        proc = preview_proc["p"]
        if proc is not None and proc.poll() is None:
            return
        if not can_preview():
            lbl_status.configure(text="Preview is unavailable. Check slides/status temp files.")
            return

        cmd = [
            sys.executable,
            str(preview_script),
            "--state-file",
            str(state_file),
            "--slides-tsv",
            str(slides_tsv),
            "--last-completed-ordinal-file",
            str(last_completed_ordinal_file),
            "--title",
            "Presented slides preview",
        ]
        if owner_pid > 0:
            cmd.extend(["--owner-pid", str(owner_pid)])

        kwargs: dict = {}
        if sys.platform == "win32" and hasattr(subprocess, "CREATE_NO_WINDOW"):
            kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            si.wShowWindow = 0
            kwargs["startupinfo"] = si

        try:
            preview_proc["p"] = subprocess.Popen(cmd, cwd=str(PROJECT_ROOT), **kwargs)
        except Exception:
            lbl_status.configure(text="Unable to open preview window.")

    btn_toggle = tk.Button(
        row,
        text="Pause",
        font=body_f,
        bg=ACCENT,
        fg="white",
        activebackground=ACCENT_HOVER,
        activeforeground="white",
        relief="flat",
        padx=18,
        pady=5,
        cursor="hand2",
        borderwidth=0,
        highlightthickness=0,
    )
    btn_toggle.grid(row=0, column=0, padx=(0, 8))

    btn_preview = tk.Button(
        row,
        text="Preview",
        font=body_f,
        bg=BTN_SEC_BG,
        fg=BTN_SEC_FG,
        activebackground="#f3f2f1",
        relief="flat",
        padx=14,
        pady=5,
        cursor="hand2",
        command=launch_preview,
        borderwidth=1,
        highlightthickness=0,
        highlightbackground=BORDER,
        state="disabled",
    )
    btn_preview.grid(row=0, column=1)

    def update_preview_state() -> None:
        can_use_preview = state["paused"] and can_preview()
        btn_preview.configure(state=("normal" if can_use_preview else "disabled"))
        btn_icon_preview.configure(state=("normal" if can_use_preview else "disabled"))
        _set_icon_button_theme(
            btn_icon_preview,
            base_bg=ICON_BTN_BG,
            hover_bg=ICON_BTN_HOVER,
            fg=BTN_SEC_FG,
            border=ICON_BTN_BORDER,
        )

    def update_icon_visual() -> None:
        if state["paused"]:
            phase = int(state["pulse_tick"]) % 6
            icon_bg = "#168816" if phase < 3 else CONTINUE_BG
            btn_icon_toggle.configure(text="\u25b6")
            _set_icon_button_theme(
                btn_icon_toggle,
                base_bg=icon_bg,
                hover_bg=CONTINUE_HOVER,
                fg="white",
                border="#0f5d0f",
            )
            state["pulse_tick"] = int(state["pulse_tick"]) + 1
        else:
            state["pulse_tick"] = 0
            btn_icon_toggle.configure(text="\u23f8")
            _set_icon_button_theme(
                btn_icon_toggle,
                base_bg=ACCENT,
                hover_bg=ACCENT_HOVER,
                fg="white",
                border="#005a9e",
            )
        _set_icon_button_theme(
            btn_icon_expand,
            base_bg=ICON_BTN_BG,
            hover_bg=ICON_BTN_HOVER,
            fg=BTN_SEC_FG,
            border=ICON_BTN_BORDER,
        )

    def relayout_window() -> None:
        root.update_idletasks()

        min_w = 42 if state["icon_only"] else 320
        min_h = 116 if state["icon_only"] else 110
        w = max(root.winfo_reqwidth(), min_w)
        h = max(root.winfo_reqheight(), min_h)

        screen_w = int(root.winfo_screenwidth())
        screen_h = int(root.winfo_screenheight())

        min_x = MARGIN_X
        max_x = max(MARGIN_X, screen_w - w - MARGIN_X)
        min_y = MARGIN_X
        max_y = max(MARGIN_X, screen_h - h - MARGIN_X)

        # Keep the control docked to the right edge when resizing/compacting.
        x = max_x
        y = min_y
        x = min(max(x, min_x), max_x)
        y = min(max(y, min_y), max_y)

        win["w"] = int(w)
        win["h"] = int(h)
        win["x"] = int(x)
        win["y"] = int(y)

        root.geometry(f"{win['w']}x{win['h']}+{win['x']}+{win['y']}")

    def set_icon_only(icon_only: bool) -> None:
        state["icon_only"] = bool(icon_only)
        if state["icon_only"]:
            if outer.winfo_manager():
                outer.pack_forget()
            if not icon_frame.winfo_manager():
                icon_frame.pack(fill="both", expand=True)
            _refresh_compact_button()
            _animate_compact_icon_enter()
        else:
            if icon_frame.winfo_manager():
                icon_frame.pack_forget()
            if not outer.winfo_manager():
                outer.pack(fill="both", expand=True)
            btn_preview.grid()
            _refresh_compact_button()

        update_preview_state()
        update_icon_visual()
        relayout_window()

    def set_paused(paused: bool, write_file: bool = True) -> None:
        state["paused"] = paused
        update_icon_visual()
        if paused:
            btn_toggle.configure(
                text="Continue",
                bg=CONTINUE_BG,
                fg="white",
                activebackground=CONTINUE_HOVER,
                activeforeground="white",
            )
            lbl_status.configure(text=paused_message)
        else:
            btn_toggle.configure(
                text="Pause",
                bg=ACCENT,
                fg="white",
                activebackground=ACCENT_HOVER,
                activeforeground="white",
            )
            lbl_status.configure(text=running_message)

        update_preview_state()

        if write_file:
            try:
                _write_state(state_file, "paused" if paused else "running")
            except Exception:
                pass

    def on_toggle() -> None:
        set_paused(not state["paused"], write_file=True)

    def on_compact_toggle() -> None:
        set_icon_only(not state["icon_only"])

    def on_icon_expand() -> None:
        set_icon_only(False)

    btn_toggle.configure(command=on_toggle)
    btn_compact.configure(command=on_compact_toggle)
    btn_icon_toggle.configure(command=on_toggle)
    btn_icon_preview.configure(command=launch_preview)
    btn_icon_expand.configure(command=on_icon_expand)
    btn_toggle.bind("<Enter>", lambda _e: btn_toggle.configure(bg=(CONTINUE_HOVER if state["paused"] else ACCENT_HOVER)))
    btn_toggle.bind("<Leave>", lambda _e: btn_toggle.configure(bg=(CONTINUE_BG if state["paused"] else ACCENT)))

    # Keep keyboard shortcuts from accidentally closing the control while running.
    root.protocol("WM_DELETE_WINDOW", lambda: None)
    root.bind("<Escape>", lambda _e: "break")

    set_icon_only(False)
    relayout_window()
    root.deiconify()

    def fade_in(alpha_value: float = 0.0) -> None:
        if not supports_alpha:
            return
        if alpha_value >= target_alpha:
            try:
                root.attributes("-alpha", target_alpha)
            except Exception:
                pass
            return
        try:
            root.attributes("-alpha", alpha_value)
        except Exception:
            return
        root.after(20, lambda: fade_in(alpha_value + 0.08))

    def reinforce_topmost(remaining: int = 24) -> None:
        if remaining <= 0:
            return
        try:
            root.geometry(f"{win['w']}x{win['h']}+{win['x']}+{win['y']}")
            root.attributes("-topmost", True)
            root.lift()
            _pin_window_topmost(int(root.winfo_id()))
        except Exception:
            pass
        root.after(120, lambda: reinforce_topmost(remaining - 1))

    def monitor_state() -> None:
        try:
            root.geometry(f"{win['w']}x{win['h']}+{win['x']}+{win['y']}")
            root.attributes("-topmost", True)
            root.lift()
            _pin_window_topmost(int(root.winfo_id()))
        except Exception:
            pass

        proc = preview_proc["p"]
        if proc is not None and proc.poll() is not None:
            preview_proc["p"] = None

        if owner_pid > 0 and not _process_alive(owner_pid):
            try:
                root.destroy()
            except Exception:
                pass
            return

        current = _read_state(state_file, "running")
        if current == "stop":
            try:
                root.destroy()
            except Exception:
                pass
            return

        if current == "paused" and not state["paused"]:
            set_paused(True, write_file=False)
        elif current == "running" and state["paused"]:
            set_paused(False, write_file=False)

        if state["icon_only"]:
            update_icon_visual()

        root.after(250, monitor_state)

    fade_in(0.0)
    reinforce_topmost()
    monitor_state()
    root.mainloop()

    proc = preview_proc["p"]
    if proc is not None and proc.poll() is None:
        try:
            proc.terminate()
        except Exception:
            pass


def _run_countdown_popup(
    title: str,
    message: str,
    countdown_seconds: float,
    owner_pid: int = 0,
) -> None:
    import tkinter as tk
    from tkinter import font as tkfont

    root = tk.Tk()
    root.withdraw()
    root.overrideredirect(True)
    root.configure(bg=BG)
    root.resizable(False, False)
    root.attributes("-topmost", True)

    total_seconds = max(1.0, float(countdown_seconds))
    end_at = time.monotonic() + total_seconds

    outer = tk.Frame(root, bg=BG, padx=12, pady=10, highlightthickness=1, highlightbackground=BORDER)
    outer.pack(fill="both", expand=True)

    title_f = tkfont.Font(family="Segoe UI", size=9, weight="bold")
    body_f = tkfont.Font(family="Segoe UI", size=9)
    count_f = tkfont.Font(family="Segoe UI", size=14, weight="bold")

    tk.Label(
        outer,
        text=(title.strip() or "Preparing next presentation file"),
        font=title_f,
        bg=BG,
        fg=MUTED,
        anchor="w",
    ).pack(fill="x", pady=(0, 4))

    tk.Label(
        outer,
        text=(message.strip() or "Switching to next file. Countdown runs in parallel with the next slide."),
        font=body_f,
        bg=BG,
        fg=FG,
        wraplength=320,
        justify="left",
        anchor="w",
    ).pack(fill="x", pady=(0, 8))

    lbl_countdown = tk.Label(
        outer,
        text="",
        font=count_f,
        bg=BG,
        fg=ACCENT,
        anchor="e",
        justify="right",
    )
    lbl_countdown.pack(fill="x")

    root.update_idletasks()
    w = max(root.winfo_reqwidth(), 360)
    h = max(root.winfo_reqheight(), 118)
    screen_w = int(root.winfo_screenwidth())
    screen_h = int(root.winfo_screenheight())
    x = max(MARGIN_X, screen_w - w - MARGIN_X)
    y = MARGIN_X
    y = min(max(y, MARGIN_X), max(MARGIN_X, screen_h - h - MARGIN_X))

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

    def tick() -> None:
        if owner_pid > 0 and not _process_alive(owner_pid):
            try:
                root.destroy()
            except Exception:
                pass
            return

        remaining = max(0, int(math.ceil(end_at - time.monotonic())))
        if remaining > 0:
            lbl_countdown.configure(text=f"{remaining}s")
            root.after(120, tick)
            return

        try:
            root.destroy()
        except Exception:
            pass

    # Allow Escape to dismiss quickly, while remaining fully non-blocking to caller.
    root.bind("<Escape>", lambda _e: root.destroy())

    reinforce_topmost()
    tick()
    root.mainloop()


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
    p.add_argument("--mode", choices=["yesno", "ok", "pausecontrol", "countdown"], default="yesno")
    p.add_argument("--ok-text", default="OK")
    p.add_argument("--anchor-pid-file", default="")
    p.add_argument("--state-file", default="", help="UTF-8 state file for pausecontrol mode")
    p.add_argument("--pid-file", default="", help="Optional PID output file for pausecontrol mode")
    p.add_argument("--owner-pid", type=int, default=0, help="Optional owner process PID; popup exits when owner exits")
    p.add_argument("--countdown-seconds", type=float, default=6.0, help="Auto-close seconds for countdown mode")
    p.add_argument("--preview-script", default="", help="Optional preview script for presented slides")
    p.add_argument("--slides-tsv", default="", help="slides_iterate.tsv path")
    p.add_argument("--last-completed-ordinal-file", default="", help="Path to last completed slide ordinal")
    p.add_argument("--title", default="Slide complete")
    p.add_argument("--message", default="Press Next to continue to the next slide.")
    args = p.parse_args()

    out_path: Path | None = None
    if args.result_file.strip():
        out_path = _resolve_result_path(args.result_file)
        out_path.parent.mkdir(parents=True, exist_ok=True)
    elif args.mode == "yesno":
        raise SystemExit("--result-file is required when --mode yesno")

    state_path: Path | None = None
    if args.state_file.strip():
        state_path = _resolve_result_path(args.state_file)

    pid_path: Path | None = None
    if args.pid_file.strip():
        pid_path = _resolve_result_path(args.pid_file)

    preview_script_path: Path | None = None
    if args.preview_script.strip():
        preview_script_path = _resolve_result_path(args.preview_script)

    slides_tsv_path: Path | None = None
    if args.slides_tsv.strip():
        slides_tsv_path = _resolve_result_path(args.slides_tsv)

    last_completed_path: Path | None = None
    if args.last_completed_ordinal_file.strip():
        last_completed_path = _resolve_result_path(args.last_completed_ordinal_file)

    if args.mode == "pausecontrol":
        if state_path is None:
            raise SystemExit("--state-file is required when --mode pausecontrol")
        _run_pause_control(
            title=args.title,
            message=args.message,
            state_file=state_path,
            owner_pid=int(args.owner_pid or 0),
            pid_file=pid_path,
            preview_script=preview_script_path,
            slides_tsv=slides_tsv_path,
            last_completed_ordinal_file=last_completed_path,
        )
        sys.exit(0)

    if args.mode == "countdown":
        _run_countdown_popup(
            title=args.title,
            message=args.message,
            countdown_seconds=float(args.countdown_seconds),
            owner_pid=int(args.owner_pid or 0),
        )
        sys.exit(0)

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
