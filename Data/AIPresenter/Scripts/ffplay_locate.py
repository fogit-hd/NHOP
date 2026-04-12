"""Find ffplay.exe: env AI_PRESENTER_FFPLAY, Tools folder, next to ffmpeg, or PATH (shutil.which)."""
from __future__ import annotations

import os
import shutil
from pathlib import Path


def _resolve_under_project(p: str, project_root: Path) -> Path:
    raw = Path(p.strip())
    if raw.is_file():
        return raw.resolve()
    if raw.is_absolute():
        return raw.resolve()
    return (project_root / raw).resolve()


def resolve_ffplay(ffmpeg_arg: str, project_root: Path) -> Path | None:
    """Return path to ffplay.exe if found, else None."""
    env = (os.environ.get("AI_PRESENTER_FFPLAY") or "").strip()
    if env:
        cand = Path(os.path.expandvars(env))
        if not cand.is_absolute():
            cand = (project_root / cand).resolve()
        else:
            cand = cand.resolve()
        if cand.is_file():
            return cand

    tools = project_root / "Data" / "AIPresenter" / "Tools" / "ffplay.exe"
    if tools.is_file():
        return tools.resolve()

    if ffmpeg_arg.strip():
        ffmpeg = _resolve_under_project(ffmpeg_arg, project_root)
        if ffmpeg.is_file():
            sibling = ffmpeg.parent / "ffplay.exe"
            if sibling.is_file():
                return sibling.resolve()

    for name in ("ffplay.exe", "ffplay"):
        found = shutil.which(name)
        if found:
            p = Path(found)
            if p.is_file():
                return p.resolve()

    return None


def ffplay_hint_stderr() -> str:
    return (
        "ffplay.exe not found. Options: (1) Add the folder that contains ffplay.exe to Windows PATH, "
        "then restart UiPath/Studio. (2) Copy ffplay.exe to Data\\AIPresenter\\Tools\\. "
        "(3) Copy ffplay.exe next to ffmpeg.exe (same FULL build from e.g. gyan.dev). "
        "(4) Set user env AI_PRESENTER_FFPLAY=C:\\full\\path\\to\\ffplay.exe"
    )
