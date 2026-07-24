"""Uniform-background helpers for the edit workspace."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def mean_background_color(image: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Return the mean color for pixels selected by mask."""
    pixels = np.asarray(image)[mask]
    if pixels.size == 0:
        return np.zeros(image.shape[2:] if image.ndim > 2 else (), dtype=np.asarray(image).dtype)
    color = pixels.reshape(-1, *np.asarray(image).shape[2:]).mean(axis=0)
    if np.issubdtype(np.asarray(image).dtype, np.integer):
        info = np.iinfo(np.asarray(image).dtype)
        color = np.clip(np.rint(color), info.min, info.max)
    return np.asarray(color, dtype=np.asarray(image).dtype)


def background_pixels_from_selection(
    image: np.ndarray,
    background_color: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int,
) -> np.ndarray:
    """Build a uniform background with the original border-aware transition."""
    result = np.empty_like(image)
    result[...] = np.asarray(background_color, dtype=image.dtype)
    outside = ~selection_mask
    if transition_px <= 0 or not np.any(outside):
        return result
    distance, nearest_indices = ndimage.distance_transform_edt(
        outside,
        return_indices=True,
    )
    band = outside & (distance <= float(transition_px))
    if not np.any(band):
        return result
    border_reference = _local_selection_border_reference(
        image,
        selection_mask,
        transition_px,
    )
    nearest_y = nearest_indices[0][band]
    nearest_x = nearest_indices[1][band]
    start_values = border_reference[nearest_y, nearest_x].astype(np.float32, copy=False)
    bg_values = np.asarray(background_color, dtype=np.float32)
    t = np.clip(distance[band] / float(max(1, transition_px)), 0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    if image.ndim == 3:
        t = t[..., None]
    blended = start_values * (1.0 - t) + bg_values * t
    if np.issubdtype(image.dtype, np.integer):
        info = np.iinfo(image.dtype)
        blended = np.clip(np.rint(blended), info.min, info.max)
    result[band] = blended.astype(image.dtype, copy=False)
    return result


def _local_selection_border_reference(
    image: np.ndarray,
    selection_mask: np.ndarray,
    transition_px: int,
) -> np.ndarray:
    sample_width = max(1, min(8, int(round(max(1, transition_px) / 3.0))))
    inside_distance = ndimage.distance_transform_edt(selection_mask)
    inner_border = selection_mask & (inside_distance <= float(sample_width))
    if not np.any(inner_border):
        return image
    sigma = max(1.0, sample_width / 2.0)
    image_float = image.astype(np.float32, copy=False)
    weights = inner_border.astype(np.float32)
    if image.ndim == 3:
        smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
        channels = []
        for channel in range(image.shape[2]):
            weighted = ndimage.gaussian_filter(
                image_float[..., channel] * weights,
                sigma=sigma,
                mode="nearest",
            )
            channels.append(weighted / np.maximum(smooth_weights, 1e-6))
        reference = np.stack(channels, axis=-1)
    else:
        smooth_weights = ndimage.gaussian_filter(weights, sigma=sigma, mode="nearest")
        weighted = ndimage.gaussian_filter(image_float * weights, sigma=sigma, mode="nearest")
        reference = weighted / np.maximum(smooth_weights, 1e-6)
    return reference.astype(np.float32, copy=False)
