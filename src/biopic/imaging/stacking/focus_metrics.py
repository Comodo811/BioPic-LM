"""Focus metrics for microscopy focus stacking."""

from __future__ import annotations

from enum import StrEnum

import numpy as np
from scipy import ndimage


class FocusMetric(StrEnum):
    """Supported local sharpness metrics."""

    LAPLACIAN = "laplacian"
    MODIFIED_LAPLACIAN = "modified_laplacian"
    TENEGRAD = "tenengrad"
    LOCAL_VARIANCE = "local_variance"


def focus_measure(image: np.ndarray, metric: FocusMetric, radius: int) -> np.ndarray:
    """Return a local focus score image."""
    gray = to_luminance(image).astype(np.float32, copy=False)
    if metric is FocusMetric.LAPLACIAN:
        score = np.abs(ndimage.laplace(gray, mode="reflect"))
    elif metric is FocusMetric.MODIFIED_LAPLACIAN:
        score = _modified_laplacian(gray)
    elif metric is FocusMetric.TENEGRAD:
        sx = ndimage.sobel(gray, axis=1, mode="reflect")
        sy = ndimage.sobel(gray, axis=0, mode="reflect")
        score = sx * sx + sy * sy
    elif metric is FocusMetric.LOCAL_VARIANCE:
        score = _local_variance(gray, radius)
    else:
        raise ValueError(f"Unsupported focus metric: {metric}")
    if radius > 0 and metric is not FocusMetric.LOCAL_VARIANCE:
        size = radius * 2 + 1
        score = ndimage.uniform_filter(score, size=size, mode="reflect")
    return np.asarray(score, dtype=np.float32)


def to_luminance(image: np.ndarray) -> np.ndarray:
    """Convert an image to luminance without changing scientific source data."""
    array = np.asarray(image)
    if array.ndim == 2:
        return array
    if array.ndim == 3 and array.shape[-1] >= 3:
        rgb = array[..., :3].astype(np.float32, copy=False)
        return rgb[..., 0] * 0.2126 + rgb[..., 1] * 0.7152 + rgb[..., 2] * 0.0722
    while array.ndim > 2:
        array = array[0]
    return array


def _modified_laplacian(gray: np.ndarray) -> np.ndarray:
    kernel_x = np.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=np.float32)
    kernel_y = np.array([[0, -1, 0], [0, 2, 0], [0, -1, 0]], dtype=np.float32)
    return np.abs(ndimage.convolve(gray, kernel_x, mode="reflect")) + np.abs(
        ndimage.convolve(gray, kernel_y, mode="reflect")
    )


def _local_variance(gray: np.ndarray, radius: int) -> np.ndarray:
    size = max(1, radius * 2 + 1)
    mean = ndimage.uniform_filter(gray, size=size, mode="reflect")
    mean_sq = ndimage.uniform_filter(gray * gray, size=size, mode="reflect")
    return np.maximum(mean_sq - mean * mean, 0.0)
