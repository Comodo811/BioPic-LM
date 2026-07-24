"""GPL editor round-trip integration for GIMP and Krita.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import tifffile


@dataclass(frozen=True, slots=True)
class ExternalEditor:
    """A discovered external GPL image editor executable."""

    name: str
    path: Path


WINDOWS_EDITOR_CANDIDATES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "GIMP",
        (
            "gimp-3.0.exe",
            "gimp-2.10.exe",
            r"C:\Program Files\GIMP 3\bin\gimp-3.0.exe",
            r"C:\Program Files\GIMP 2\bin\gimp-2.10.exe",
        ),
    ),
    (
        "Krita",
        (
            "krita.exe",
            r"C:\Program Files\Krita (x64)\bin\krita.exe",
            r"C:\Program Files\Krita\bin\krita.exe",
        ),
    ),
)


def find_external_editor(preferred: str | None = None) -> ExternalEditor | None:
    """Return a discovered GIMP/Krita executable, preferring the requested family."""
    normalized = (preferred or "").strip().lower()
    candidates = list(WINDOWS_EDITOR_CANDIDATES)
    if normalized:
        candidates.sort(key=lambda item: 0 if normalized in item[0].lower() else 1)
    for name, executable_names in candidates:
        for executable in executable_names:
            discovered = shutil.which(executable)
            path = Path(discovered) if discovered is not None else Path(executable)
            if path.exists():
                return ExternalEditor(name=name, path=path)
    return None


def external_edit_cache_path(project_id: str, asset_id: str) -> Path:
    """Return the lossless handoff path used for external editor round trips."""
    safe_project = _safe_path_part(project_id)
    safe_asset = _safe_path_part(asset_id)
    return (
        Path.cwd()
        / ".biopic_cache"
        / safe_project
        / "external_edit"
        / f"{safe_asset}.external-edit.tif"
    ).resolve()


def write_external_edit_image(path: Path, pixels: np.ndarray) -> Path:
    """Write the current rendered image to a lossless editor handoff file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tifffile.imwrite(path, np.asarray(pixels), photometric=_photometric(pixels))
    return path


def read_external_edit_image(
    path: Path, base_pixels: np.ndarray
) -> tuple[np.ndarray, np.ndarray | None]:
    """Load an externally edited image and adapt it to the active BioPic LM document."""
    edited = tifffile.imread(path)
    pixels, alpha = _split_alpha(np.asarray(edited))
    return _match_base_shape_and_dtype(pixels, base_pixels), alpha


def _split_alpha(pixels: np.ndarray) -> tuple[np.ndarray, np.ndarray | None]:
    if pixels.ndim == 3 and pixels.shape[-1] == 4:
        alpha = pixels[..., 3].astype(np.float32)
        max_value = (
            float(np.iinfo(pixels.dtype).max)
            if np.issubdtype(pixels.dtype, np.integer)
            else 1.0
        )
        return pixels[..., :3], np.clip(alpha / max_value, 0.0, 1.0)
    return pixels, None


def _match_base_shape_and_dtype(pixels: np.ndarray, base_pixels: np.ndarray) -> np.ndarray:
    result: np.ndarray = pixels
    if base_pixels.ndim == 2 and result.ndim == 3:
        result = result[..., :3].astype(np.float32).mean(axis=2)
    elif base_pixels.ndim == 3 and result.ndim == 2:
        channels = base_pixels.shape[-1]
        result = np.repeat(result[..., None], channels, axis=2)
    if result.shape[:2] != base_pixels.shape[:2]:
        cropped = np.zeros(base_pixels.shape, dtype=result.dtype)
        height = min(cropped.shape[0], result.shape[0])
        width = min(cropped.shape[1], result.shape[1])
        cropped[:height, :width] = result[:height, :width]
        result = cropped
    return _convert_dtype(result, base_pixels.dtype)


def _convert_dtype(pixels: np.ndarray, dtype: np.dtype) -> np.ndarray:
    source = np.asarray(pixels)
    target_dtype = np.dtype(dtype)
    if source.dtype == target_dtype:
        return source.copy()
    if np.issubdtype(target_dtype, np.integer):
        target_info = np.iinfo(target_dtype)
        if np.issubdtype(source.dtype, np.integer):
            source_info = np.iinfo(source.dtype)
            scaled: np.ndarray = (
                source.astype(np.float32) / float(source_info.max) * float(target_info.max)
            )
        else:
            scaled = source.astype(np.float32) * float(target_info.max)
        return np.clip(scaled, target_info.min, target_info.max).astype(target_dtype)
    if np.issubdtype(source.dtype, np.integer):
        source_info = np.iinfo(source.dtype)
        return (source.astype(np.float32) / float(source_info.max)).astype(target_dtype)
    return source.astype(target_dtype)


def _photometric(pixels: np.ndarray) -> str:
    return "rgb" if pixels.ndim == 3 and pixels.shape[-1] in {3, 4} else "minisblack"


def _safe_path_part(value: str) -> str:
    return "".join(
        character if character.isalnum() or character in {"-", "_"} else "_"
        for character in value
    )
