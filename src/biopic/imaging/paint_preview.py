"""Paint preview compositing helpers.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

import numpy as np

from biopic.native.composite_backend import blend_normal_in_place


def blend_preview_region(
    base_region: np.ndarray,
    content_region: np.ndarray,
    alpha_region: np.ndarray,
    opacity: float,
) -> np.ndarray:
    """Composite a staged paint region using the native normal-blend hot path."""
    background = np.ascontiguousarray(base_region.astype(np.float32, copy=False))
    alpha = np.ascontiguousarray(alpha_region.astype(np.float32, copy=False))
    if blend_normal_in_place(
        background,
        np.ascontiguousarray(content_region),
        alpha,
        opacity=float(opacity),
    ):
        return _restore_dtype(background, base_region.dtype)
    return _blend_preview_region_python(base_region, content_region, alpha_region, opacity)


def _blend_preview_region_python(
    base_region: np.ndarray,
    content_region: np.ndarray,
    alpha_region: np.ndarray,
    opacity: float,
) -> np.ndarray:
    alpha = alpha_region.astype(np.float32, copy=False) * float(opacity)
    if alpha.ndim == 2 and content_region.ndim == 3:
        alpha = alpha[..., None]
    preview = (
        alpha * content_region.astype(np.float32, copy=False)
        + (1.0 - alpha) * base_region.astype(np.float32, copy=False)
    )
    return _restore_dtype(preview, base_region.dtype)


def _restore_dtype(pixels: np.ndarray, dtype: np.dtype) -> np.ndarray:
    if np.issubdtype(dtype, np.integer):
        info = np.iinfo(dtype)
        return np.clip(pixels, info.min, info.max).astype(dtype)
    return pixels.astype(dtype, copy=False)
