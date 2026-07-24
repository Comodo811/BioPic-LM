"""Dtype and intensity-range helpers."""

from __future__ import annotations

import numpy as np


def dtype_range(dtype: np.dtype) -> tuple[float, float]:
    """Return the representable numeric range for an image dtype."""
    target = np.dtype(dtype)
    if np.issubdtype(target, np.integer):
        info = np.iinfo(target)
        return float(info.min), float(info.max)
    return 0.0, 1.0


def to_float(image: np.ndarray) -> tuple[np.ndarray, np.dtype]:
    """Convert image data to float32 in display/scientific normalized range."""
    array = np.asarray(image)
    original_dtype = array.dtype
    if np.issubdtype(original_dtype, np.floating):
        return array.astype(np.float32, copy=False), original_dtype
    low, high = dtype_range(original_dtype)
    return ((array.astype(np.float32) - low) / (high - low)), original_dtype


def restore_dtype(image: np.ndarray, dtype: np.dtype) -> np.ndarray:
    """Restore normalized float data to a target dtype."""
    target = np.dtype(dtype)
    if np.issubdtype(target, np.floating):
        return image.astype(target, copy=False)
    low, high = dtype_range(target)
    scaled = np.clip(image, 0.0, 1.0) * (high - low) + low
    return scaled.astype(target)
