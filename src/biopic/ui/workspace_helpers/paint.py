"""Paint, selection, and pixel-value helpers for the edit workspace."""

from __future__ import annotations

import numpy as np
from scipy import ndimage


def paint_disk(
    pixels: np.ndarray, center_x: int, center_y: int, radius: int, value: object
) -> None:
    height, width = pixels.shape[:2]
    y_min = max(0, center_y - radius)
    y_max = min(height, center_y + radius + 1)
    x_min = max(0, center_x - radius)
    x_max = min(width, center_x + radius + 1)
    yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
    mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius**2
    region = pixels[y_min:y_max, x_min:x_max]
    region[mask] = value


def interpolated_points(
    previous: tuple[float, float] | None,
    current: tuple[float, float],
    radius: int,
) -> list[tuple[int, int]]:
    if previous is None:
        return [rounded_point(current)]
    x0, y0 = previous
    x1, y1 = current
    distance = float(np.hypot(x1 - x0, y1 - y0))
    step = max(0.5, radius / 4.0)
    count = max(1, int(np.ceil(distance / step)))
    points = [
        (
            int(round(x0 + (x1 - x0) * index / count)),
            int(round(y0 + (y1 - y0) * index / count)),
        )
        for index in range(1, count + 1)
    ]
    deduped: list[tuple[int, int]] = []
    for point in points:
        if not deduped or deduped[-1] != point:
            deduped.append(point)
    return deduped


def rounded_point(point: tuple[float, float]) -> tuple[int, int]:
    return int(round(point[0])), int(round(point[1]))


def deduplicate_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    result: list[tuple[int, int]] = []
    last: tuple[int, int] | None = None
    for point in points:
        if point != last:
            result.append(point)
            last = point
    return result


def display_scalar_value(value: object, dtype: np.dtype) -> float:
    array = np.asarray(value, dtype=np.float64)
    scalar = float(array.mean())
    if np.issubdtype(dtype, np.integer):
        return float(np.clip(scalar / float(np.iinfo(dtype).max) * 255.0, 0.0, 255.0))
    return float(np.clip(scalar * 255.0 if scalar <= 1.0 else scalar, 0.0, 255.0))


def owned_paint_buffer(pixels: np.ndarray) -> np.ndarray:
    """Return a stroke-owned contiguous preview buffer."""
    return np.ascontiguousarray(pixels).copy()


def safe_array_min(array: np.ndarray) -> float:
    if array.size == 0:
        return 0.0
    if np.issubdtype(array.dtype, np.floating):
        finite = array[np.isfinite(array)]
        return float(np.min(finite)) if finite.size else 0.0
    return float(np.min(array))


def safe_array_max(array: np.ndarray) -> float:
    if array.size == 0:
        return 0.0
    if np.issubdtype(array.dtype, np.floating):
        finite = array[np.isfinite(array)]
        return float(np.max(finite)) if finite.size else 0.0
    return float(np.max(array))


def heal_disk(pixels: np.ndarray, center_x: int, center_y: int, radius: int) -> None:
    height, width = pixels.shape[:2]
    y_min = max(0, center_y - radius)
    y_max = min(height, center_y + radius + 1)
    x_min = max(0, center_x - radius)
    x_max = min(width, center_x + radius + 1)
    region = pixels[y_min:y_max, x_min:x_max]
    if region.size == 0:
        return
    median = np.median(region.reshape(-1, *region.shape[2:]), axis=0)
    paint_disk(pixels, center_x, center_y, radius, median)


def smudge_disk(
    pixels: np.ndarray, center_x: int, center_y: int, radius: int, previous: tuple[int, int] | None
) -> None:
    if previous is None:
        heal_disk(pixels, center_x, center_y, radius)
        return
    px, py = previous
    height, width = pixels.shape[:2]
    if not (0 <= py < height and 0 <= px < width):
        return
    paint_disk(pixels, center_x, center_y, radius, pixels[py, px])


def dodge_burn_disk(
    pixels: np.ndarray, center_x: int, center_y: int, radius: int, *, amount: float
) -> None:
    height, width = pixels.shape[:2]
    y_min = max(0, center_y - radius)
    y_max = min(height, center_y + radius + 1)
    x_min = max(0, center_x - radius)
    x_max = min(width, center_x + radius + 1)
    region = pixels[y_min:y_max, x_min:x_max]
    if np.issubdtype(pixels.dtype, np.integer):
        info = np.iinfo(pixels.dtype)
        region[...] = np.clip(region.astype(np.float32) * (1.0 + amount), info.min, info.max)
    else:
        region[...] = np.clip(region.astype(np.float32) * (1.0 + amount), 0.0, 1.0)


def fuzzy_selection_bounds(
    pixels: np.ndarray,
    seed_x: int,
    seed_y: int,
    *,
    tolerance: float,
) -> tuple[int, int, int, int] | None:
    """Return bounds of a contiguous same-color region around a seed point."""
    region = fuzzy_selection_region(pixels, seed_x, seed_y, tolerance=tolerance)
    return None if region is None else region[0]


def fuzzy_selection_region(
    pixels: np.ndarray,
    seed_x: int,
    seed_y: int,
    *,
    tolerance: float,
) -> tuple[tuple[int, int, int, int], np.ndarray] | None:
    """Return bounds and a local mask for a contiguous similar-color region."""
    array = np.asarray(pixels)
    height, width = array.shape[:2]
    if not (0 <= seed_x < width and 0 <= seed_y < height):
        return None
    scalar = selection_scalar_plane(array)
    seed = float(scalar[seed_y, seed_x])
    if np.issubdtype(scalar.dtype, np.integer):
        scale = float(np.iinfo(scalar.dtype).max)
        allowed = tolerance / 100.0 * scale
    else:
        allowed = tolerance / 100.0
    threshold = np.abs(scalar.astype(np.float32, copy=False) - seed) <= allowed
    labels, count = ndimage.label(
        threshold,
        structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8),
    )
    if count <= 0:
        return None
    label = int(labels[seed_y, seed_x])
    if label <= 0:
        return None
    slices = ndimage.find_objects(labels)
    if label > len(slices) or slices[label - 1] is None:
        return None
    y_slice, x_slice = slices[label - 1]
    local = (labels[y_slice, x_slice] == label).astype(np.float32)
    return (
        (
            int(x_slice.start),
            int(y_slice.start),
            int(x_slice.stop - x_slice.start),
            int(y_slice.stop - y_slice.start),
        ),
        local,
    )


def selection_scalar_plane(pixels: np.ndarray) -> np.ndarray:
    if pixels.ndim == 2:
        return pixels
    return np.asarray(pixels[..., :3]).mean(axis=2)
