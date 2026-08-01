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
    SCHARR = "scharr"
    BRENNER = "brenner"
    LOCAL_VARIANCE = "local_variance"
    WAVELET = "wavelet"


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
    elif metric is FocusMetric.SCHARR:
        score = _scharr_energy(gray)
    elif metric is FocusMetric.BRENNER:
        score = _brenner_gradient(gray, offset=max(1, radius))
    elif metric is FocusMetric.LOCAL_VARIANCE:
        score = _local_variance(gray, radius)
    elif metric is FocusMetric.WAVELET:
        score = _wavelet_energy(gray)
    else:
        raise ValueError(f"Unsupported focus metric: {metric}")
    if radius > 0 and metric not in {FocusMetric.LOCAL_VARIANCE, FocusMetric.BRENNER}:
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


def _scharr_energy(gray: np.ndarray) -> np.ndarray:
    kernel_x = np.array([[3, 0, -3], [10, 0, -10], [3, 0, -3]], dtype=np.float32)
    kernel_y = kernel_x.T
    sx = ndimage.convolve(gray, kernel_x, mode="reflect")
    sy = ndimage.convolve(gray, kernel_y, mode="reflect")
    return sx * sx + sy * sy


def _brenner_gradient(gray: np.ndarray, offset: int = 2) -> np.ndarray:
    offset = max(1, int(offset))
    score = np.zeros_like(gray, dtype=np.float32)
    dx = gray[:, offset:] - gray[:, :-offset]
    dy = gray[offset:, :] - gray[:-offset, :]
    score[:, :-offset] += dx * dx
    score[:-offset, :] += dy * dy
    return score


def _wavelet_energy(gray: np.ndarray) -> np.ndarray:
    horizontal = gray[:, 1::2] - gray[:, ::2][:, : gray[:, 1::2].shape[1]]
    vertical = gray[1::2, :] - gray[::2, :][: gray[1::2, :].shape[0], :]
    energy = np.zeros_like(gray, dtype=np.float32)
    energy[:, : horizontal.shape[1]] += horizontal * horizontal
    energy[: vertical.shape[0], :] += vertical * vertical
    return ndimage.uniform_filter(energy, size=3, mode="reflect")
