"""Sharpness evaluation metrics."""

from __future__ import annotations

import cv2
import numpy as np
from scipy import ndimage

from biopic.imaging.stacking.focus_metrics import to_luminance


def metric_ids() -> list[str]:
    return [
        "modified_laplacian",
        "tenengrad",
        "laplacian",
        "scharr",
        "brenner",
        "local_variance",
        "wavelet",
    ]


def display_name(metric_id: str) -> str:
    return {
        "modified_laplacian": "Modified Laplacian score",
        "tenengrad": "Tenengrad score",
        "laplacian": "Laplacian variance",
        "scharr": "Scharr energy",
        "brenner": "Brenner gradient",
        "local_variance": "Local variance",
        "wavelet": "Wavelet energy",
    }.get(metric_id, metric_id)


def evaluate_metrics(
    image: np.ndarray,
    mask: np.ndarray | None = None,
    *,
    gaussian_sigma: float = 0.0,
) -> dict[str, float]:
    """Evaluate all supported relative sharpness metrics for one result image."""
    gray = to_luminance(image).astype(np.float32, copy=False)
    if gray.max(initial=0.0) > 1.5:
        gray = gray / np.iinfo(image.dtype).max if np.issubdtype(image.dtype, np.integer) else gray
    if gaussian_sigma > 0:
        gray = ndimage.gaussian_filter(gray, sigma=gaussian_sigma, mode="reflect")
    region = mask if mask is not None else np.ones(gray.shape, dtype=bool)
    region = region.astype(bool, copy=False)
    if not np.any(region):
        region = np.ones(gray.shape, dtype=bool)
    return {
        "modified_laplacian": _mean(_modified_laplacian(gray), region),
        "tenengrad": _mean(_tenengrad(gray), region),
        "laplacian": float(np.var(cv2.Laplacian(gray, cv2.CV_32F, ksize=3)[region])),
        "scharr": _mean(_scharr(gray), region),
        "brenner": _mean(_brenner(gray, 2), region),
        "local_variance": _mean(_local_variance(gray, 9), region),
        "wavelet": _mean(_wavelet_energy(gray), region),
    }


def automatic_foreground_mask(images: list[np.ndarray]) -> np.ndarray:
    """Return a shared foreground-ish mask for all generated results."""
    gray_stack = np.stack([to_luminance(image).astype(np.float32) for image in images], axis=0)
    gray = np.median(gray_stack, axis=0)
    smooth = ndimage.gaussian_filter(gray, sigma=8.0, mode="reflect")
    detail = np.abs(gray - smooth)
    high = float(np.percentile(detail, 95.0))
    if high <= 1e-8:
        return np.ones(gray.shape, dtype=bool)
    mask = detail > high * 0.18
    mask = ndimage.binary_dilation(mask, iterations=8)
    mask = ndimage.binary_fill_holes(mask)
    return mask.astype(bool)


def _mean(values: np.ndarray, mask: np.ndarray) -> float:
    return float(np.mean(values[mask])) if np.any(mask) else float(np.mean(values))


def _modified_laplacian(gray: np.ndarray) -> np.ndarray:
    kx = np.array([[0, 0, 0], [-1, 2, -1], [0, 0, 0]], dtype=np.float32)
    ky = kx.T
    return np.abs(ndimage.convolve(gray, kx, mode="reflect")) + np.abs(
        ndimage.convolve(gray, ky, mode="reflect")
    )


def _tenengrad(gray: np.ndarray) -> np.ndarray:
    sx = ndimage.sobel(gray, axis=1, mode="reflect")
    sy = ndimage.sobel(gray, axis=0, mode="reflect")
    return sx * sx + sy * sy


def _scharr(gray: np.ndarray) -> np.ndarray:
    sx = cv2.Scharr(gray, cv2.CV_32F, 1, 0)
    sy = cv2.Scharr(gray, cv2.CV_32F, 0, 1)
    return sx * sx + sy * sy


def _brenner(gray: np.ndarray, offset: int) -> np.ndarray:
    out = np.zeros_like(gray, dtype=np.float32)
    dx = gray[:, offset:] - gray[:, :-offset]
    dy = gray[offset:, :] - gray[:-offset, :]
    out[:, :-offset] += dx * dx
    out[:-offset, :] += dy * dy
    return out


def _local_variance(gray: np.ndarray, window_size: int) -> np.ndarray:
    mean = ndimage.uniform_filter(gray, size=window_size, mode="reflect")
    mean_sq = ndimage.uniform_filter(gray * gray, size=window_size, mode="reflect")
    return np.maximum(mean_sq - mean * mean, 0.0)


def _wavelet_energy(gray: np.ndarray) -> np.ndarray:
    horizontal = gray[:, 1::2] - gray[:, ::2][:, : gray[:, 1::2].shape[1]]
    vertical = gray[1::2, :] - gray[::2, :][: gray[1::2, :].shape[0], :]
    energy = np.zeros_like(gray, dtype=np.float32)
    energy[:, : horizontal.shape[1]] += horizontal * horizontal
    energy[: vertical.shape[0], :] += vertical * vertical
    return ndimage.uniform_filter(energy, size=3, mode="reflect")
