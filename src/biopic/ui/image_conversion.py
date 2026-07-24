"""Qt image conversion helpers for scientific pixel arrays."""

from __future__ import annotations

import numpy as np
from PySide6.QtGui import QImage

from biopic.native.display_backend import to_display_uint8 as native_to_display_uint8


def ndarray_to_qimage(
    pixels: np.ndarray, display_range: tuple[float, float] | None = None
) -> QImage:
    """Convert scientific image data to an 8-bit display QImage."""
    display = _to_display_uint8(pixels, display_range)
    display = _checkerboard_transparent_pixels(display)
    display = np.ascontiguousarray(display)
    if display.ndim == 2:
        height, width = display.shape
        bytes_per_line = display.strides[0]
        return QImage(
            display.data, width, height, bytes_per_line, QImage.Format.Format_Grayscale8
        ).copy()
    if display.shape[2] == 3:
        height, width, _channels = display.shape
        bytes_per_line = display.strides[0]
        return QImage(
            display.data, width, height, bytes_per_line, QImage.Format.Format_RGB888
        ).copy()
    height, width, _channels = display.shape
    bytes_per_line = display.strides[0]
    return QImage(display.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888).copy()


def layer_preview_qimage(
    content: np.ndarray,
    alpha: np.ndarray,
    display_range: tuple[float, float] | None = None,
    *,
    opacity: float = 1.0,
) -> QImage:
    """Convert one layer into a transparent preview QImage."""
    display = _to_display_uint8(content, display_range)
    if display.ndim == 2:
        rgb = np.repeat(display[..., None], 3, axis=2)
        source_alpha = None
    elif display.shape[2] == 4:
        rgb = display[..., :3]
        source_alpha = display[..., 3].astype(np.float32) / 255.0
    else:
        rgb = display[..., :3]
        source_alpha = None
    layer_alpha = np.asarray(alpha, dtype=np.float32)
    if layer_alpha.ndim > 2:
        layer_alpha = layer_alpha[..., 0]
    if layer_alpha.shape != rgb.shape[:2]:
        layer_alpha = np.ones(rgb.shape[:2], dtype=np.float32)
    layer_alpha = np.clip(layer_alpha * max(0.0, min(1.0, opacity)), 0.0, 1.0)
    if source_alpha is not None:
        layer_alpha *= source_alpha
    rgba = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = np.ascontiguousarray(rgb)
    rgba[..., 3] = np.clip(layer_alpha * 255.0, 0, 255).astype(np.uint8)
    rgba = np.ascontiguousarray(rgba)
    height, width, _channels = rgba.shape
    bytes_per_line = rgba.strides[0]
    return QImage(rgba.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888).copy()


def paint_overlay_qimage(
    preview: np.ndarray,
    base: np.ndarray,
    display_range: tuple[float, float] | None = None,
) -> QImage:
    """Convert a paint preview tile into a transparent changed-pixel overlay."""
    if preview.shape[:2] != base.shape[:2] or preview.size == 0:
        return QImage()
    preview_display = _to_display_uint8(preview, display_range)
    base_display = _to_display_uint8(base, display_range)
    if preview_display.shape[:2] != base_display.shape[:2]:
        return QImage()
    if preview_display.ndim == 2:
        preview_rgb = np.repeat(preview_display[..., None], 3, axis=2)
        base_rgb = np.repeat(base_display[..., None], 3, axis=2)
    else:
        preview_rgb = preview_display[..., :3]
        base_rgb = base_display[..., :3] if base_display.ndim == 3 else base_display[..., None]
        if base_rgb.shape[-1] == 1:
            base_rgb = np.repeat(base_rgb, 3, axis=2)
    changed = np.any(preview_rgb != base_rgb, axis=2)
    if not np.any(changed):
        return QImage()
    changed_fraction = float(np.count_nonzero(changed)) / float(changed.size)
    if changed_fraction > 0.85 and int(np.max(preview_rgb)) == 0 and int(np.max(base_rgb)) > 0:
        return QImage()
    rgba = np.zeros((*preview_rgb.shape[:2], 4), dtype=np.uint8)
    rgba[..., :3] = np.ascontiguousarray(preview_rgb)
    rgba[..., 3] = np.where(changed, 255, 0).astype(np.uint8)
    rgba = np.ascontiguousarray(rgba)
    height, width, _channels = rgba.shape
    bytes_per_line = rgba.strides[0]
    return QImage(rgba.data, width, height, bytes_per_line, QImage.Format.Format_RGBA8888).copy()


def first_display_plane_view(pixels: np.ndarray) -> np.ndarray:
    """Return the displayable plane without copying when possible."""
    array = np.asarray(pixels)
    while array.ndim > 3:
        array = array[0]
    if array.ndim == 3 and array.shape[-1] not in {3, 4}:
        array = array[0]
    return array


def owned_first_display_plane(pixels: np.ndarray) -> np.ndarray:
    """Return an owned contiguous display plane."""
    return np.ascontiguousarray(first_display_plane_view(pixels)).copy()


def display_range(pixels: np.ndarray) -> tuple[float, float] | None:
    """Return a display range for non-8-bit pixel arrays."""
    array = np.asarray(pixels)
    if array.dtype == np.uint8:
        return None
    finite = array[np.isfinite(array)] if np.issubdtype(array.dtype, np.floating) else array
    if finite.size == 0:
        return (0.0, 1.0)
    low = float(np.min(finite))
    high = float(np.max(finite))
    if high > low:
        return (low, high)
    if np.issubdtype(array.dtype, np.integer):
        info = np.iinfo(array.dtype)
        return (float(info.min), float(info.max))
    return (0.0, 1.0)


def _checkerboard_transparent_pixels(display: np.ndarray) -> np.ndarray:
    if display.ndim != 3 or display.shape[2] != 4:
        return display
    alpha = display[..., 3].astype(np.float32) / 255.0
    if np.all(alpha >= 1.0):
        return display
    height, width = display.shape[:2]
    yy, xx = np.indices((height, width))
    checker = np.where(((xx // 8) + (yy // 8)) % 2 == 0, 74, 94).astype(np.float32)
    result = display.copy()
    for channel in range(3):
        result[..., channel] = (
            display[..., channel].astype(np.float32) * alpha + checker * (1.0 - alpha)
        ).astype(np.uint8)
    result[..., 3] = 255
    return np.ascontiguousarray(result)


def _to_display_uint8(
    pixels: np.ndarray, display_range_value: tuple[float, float] | None = None
) -> np.ndarray:
    array = np.asarray(pixels)
    if np.issubdtype(array.dtype, np.floating):
        array = np.nan_to_num(array, nan=0.0, posinf=1.0, neginf=0.0)
    if array.dtype == np.uint8:
        return np.ascontiguousarray(array)
    if display_range_value is None:
        display_range_value = display_range(array)
    if display_range_value is None:
        return np.ascontiguousarray(array.astype(np.uint8, copy=False))
    low, high = display_range_value
    if high <= low:
        return np.zeros(array.shape, dtype=np.uint8)
    native = native_to_display_uint8(array, (low, high))
    if native is not None:
        return np.ascontiguousarray(native)
    scaled = (array.astype(np.float32) - low) / (high - low)
    return np.ascontiguousarray(np.clip(scaled * 255.0, 0, 255).astype(np.uint8))
