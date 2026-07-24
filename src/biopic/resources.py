"""Resource path helpers for source and PyInstaller builds."""

from __future__ import annotations

import sys
from pathlib import Path


def resource_path(*parts: str) -> Path:
    """Return an application resource path in source or frozen builds."""
    frozen_base = getattr(sys, "_MEIPASS", None)
    if frozen_base:
        return Path(frozen_base).joinpath(*parts)
    return Path(__file__).resolve().parents[2].joinpath(*parts)
