"""Stroke rasterization backend.

The native extension is used when available. The pure Python fallback keeps tests and
source checkouts usable without a C compiler.
"""

from __future__ import annotations

from collections.abc import Iterable
from functools import lru_cache
from typing import Any

import numpy as np

try:  # pragma: no cover - exercised only when the extension is built
    from biopic.native import _stroke_native  # type: ignore[attr-defined]
except ImportError:  # pragma: no cover - the fallback is covered instead
    _stroke_native = None


Point = tuple[int, int]
FloatPoint = tuple[float, float]
Selection = tuple[int, int, int, int] | None


def native_available() -> bool:
    """Return whether the compiled stroke backend is importable."""
    return _stroke_native is not None


def paint_disks(
    pixels: np.ndarray,
    points: Iterable[Point],
    radius: int,
    value: Any,
    *,
    selection_rect: Selection = None,
    selection_shape: str = "rectangle",
) -> None:
    """Paint hard-edged disks at sampled stroke points."""
    point_list = [(int(x), int(y)) for x, y in points]
    if not point_list:
        return
    if _can_use_native(pixels, value):
        rect = selection_rect if selection_rect is not None else (-1, -1, -1, -1)
        assert _stroke_native is not None
        _stroke_native.paint_disks(
            pixels,
            point_list,
            int(radius),
            float(value),
            tuple(int(item) for item in rect),
            selection_shape == "ellipse",
        )
        return
    _paint_disks_python(
        pixels,
        point_list,
        int(radius),
        value,
        selection_rect=selection_rect,
        selection_shape=selection_shape,
    )


def paint_disks_pair(
    content: np.ndarray,
    alpha: np.ndarray,
    points: Iterable[Point],
    radius: int,
    value: Any,
    *,
    alpha_value: Any = 1.0,
    selection_rect: Selection = None,
    selection_shape: str = "rectangle",
) -> None:
    """Paint hard-edged disks into content and alpha in one native traversal."""
    point_list = [(int(x), int(y)) for x, y in points]
    if not point_list:
        return
    if _can_use_native_pair(content, alpha, value, alpha_value):
        rect = selection_rect if selection_rect is not None else (-1, -1, -1, -1)
        assert _stroke_native is not None
        paint_disks_pair_native = getattr(_stroke_native, "paint_disks_pair", None)
        if paint_disks_pair_native is not None:
            paint_disks_pair_native(
                content,
                alpha,
                point_list,
                int(radius),
                float(value),
                float(alpha_value),
                tuple(int(item) for item in rect),
                selection_shape == "ellipse",
            )
            return
    _paint_disks_python(
        content,
        point_list,
        int(radius),
        value,
        selection_rect=selection_rect,
        selection_shape=selection_shape,
    )
    _paint_disks_python(
        alpha,
        point_list,
        int(radius),
        alpha_value,
        selection_rect=selection_rect,
        selection_shape=selection_shape,
    )


def paint_stroke(
    pixels: np.ndarray,
    points: Iterable[Point],
    radius: int,
    value: Any,
    *,
    selection_rect: Selection = None,
    selection_shape: str = "rectangle",
) -> None:
    """Paint a GIMP-style stroke through control points."""
    point_list = [(int(x), int(y)) for x, y in points]
    if not point_list:
        return
    if _can_use_native(pixels, value):
        rect = selection_rect if selection_rect is not None else (-1, -1, -1, -1)
        assert _stroke_native is not None
        paint_stroke_native = getattr(_stroke_native, "paint_stroke", None)
        if paint_stroke_native is not None:
            paint_stroke_native(
                pixels,
                point_list,
                int(radius),
                float(value),
                tuple(int(item) for item in rect),
                selection_shape == "ellipse",
            )
            return
    paint_disks(
        pixels,
        _stroke_points(point_list, radius),
        radius,
        value,
        selection_rect=selection_rect,
        selection_shape=selection_shape,
    )


def spacing_dabs(
    previous: FloatPoint,
    current: FloatPoint,
    radius: int,
    remainder: float,
) -> tuple[float, list[Point]]:
    """Generate GIMP-style brush-spaced dabs for one float segment."""
    if _stroke_native is not None:
        spacing_dabs_native = getattr(_stroke_native, "spacing_dabs", None)
        if spacing_dabs_native is not None:
            next_remainder, points = spacing_dabs_native(
                float(previous[0]),
                float(previous[1]),
                float(current[0]),
                float(current[1]),
                int(radius),
                float(remainder),
            )
            return float(next_remainder), [(int(x), int(y)) for x, y in points]
    return _spacing_dabs_python(previous, current, int(radius), float(remainder))


def _can_use_native(pixels: np.ndarray, value: Any) -> bool:
    return (
        _stroke_native is not None
        and pixels.ndim == 2
        and pixels.flags.c_contiguous
        and pixels.dtype
        in {
            np.dtype("uint8"),
            np.dtype("uint16"),
            np.dtype("float32"),
            np.dtype("float64"),
        }
        and isinstance(value, (int, float, np.integer, np.floating))
    )


def _can_use_native_pair(
    content: np.ndarray,
    alpha: np.ndarray,
    value: Any,
    alpha_value: Any,
) -> bool:
    return (
        _can_use_native(content, value)
        and _can_use_native(alpha, alpha_value)
        and content.shape == alpha.shape
    )


def _spacing_dabs_python(
    previous: FloatPoint,
    current: FloatPoint,
    radius: int,
    remainder: float,
) -> tuple[float, list[Point]]:
    x0, y0 = _avoid_exact_integer(previous)
    x1, y1 = _avoid_exact_integer(current)
    dx = x1 - x0
    dy = y1 - y0
    distance = float(np.hypot(dx, dy))
    if distance <= 1e-9:
        return remainder, []
    spacing = _brush_spacing_pixels(radius)
    if remainder < 0.0 or remainder >= spacing:
        remainder = float(np.fmod(max(0.0, remainder), spacing))
    distance_to_next = spacing - remainder
    points: list[Point] = []
    while distance_to_next <= distance + 1e-9:
        t = distance_to_next / distance
        point = (int(round(x0 + dx * t)), int(round(y0 + dy * t)))
        if not points or points[-1] != point:
            points.append(point)
        distance_to_next += spacing
    return float(np.fmod(remainder + distance, spacing)), points


def _avoid_exact_integer(point: FloatPoint) -> FloatPoint:
    return _avoid_exact_integer_value(point[0]), _avoid_exact_integer_value(point[1])


def _avoid_exact_integer_value(value: float) -> float:
    epsilon = 1e-6
    integral = float(np.floor(value))
    fractional = value - integral
    if fractional < epsilon:
        return integral + epsilon
    if fractional > 1.0 - epsilon:
        return integral + 1.0 - epsilon
    return value


def _brush_spacing_pixels(radius: int) -> float:
    diameter = max(1.0, float(radius) * 2.0 + 1.0)
    return max(0.5, diameter * 0.15)


def _paint_disks_python(
    pixels: np.ndarray,
    points: list[Point],
    radius: int,
    value: Any,
    *,
    selection_rect: Selection,
    selection_shape: str,
) -> None:
    y_offsets, x_offsets = _disk_offsets(int(radius))
    height, width = pixels.shape[:2]
    for center_x, center_y in points:
        ys = center_y + y_offsets
        xs = center_x + x_offsets
        valid = (ys >= 0) & (ys < height) & (xs >= 0) & (xs < width)
        if selection_rect is not None:
            sx, sy, selection_width, selection_height = selection_rect
            valid &= (
                (xs >= sx)
                & (xs < sx + selection_width)
                & (ys >= sy)
                & (ys < sy + selection_height)
            )
            if selection_shape == "ellipse":
                valid &= _points_in_ellipse(xs, ys, selection_rect)
        if np.any(valid):
            pixels[ys[valid], xs[valid]] = value


@lru_cache(maxsize=256)
def _disk_offsets(radius: int) -> tuple[np.ndarray, np.ndarray]:
    radius = max(0, int(radius))
    yy, xx = np.indices((radius * 2 + 1, radius * 2 + 1), dtype=np.intp)
    yy = yy - radius
    xx = xx - radius
    mask = xx**2 + yy**2 <= radius**2
    return yy[mask].astype(np.intp), xx[mask].astype(np.intp)


def _points_in_ellipse(xs: np.ndarray, ys: np.ndarray, rect: Selection) -> np.ndarray:
    if rect is None:
        return np.ones(xs.shape, dtype=bool)
    sx, sy, width, height = rect
    center_x = sx + (width - 1) / 2.0
    center_y = sy + (height - 1) / 2.0
    radius_x = max(width / 2.0, 0.5)
    radius_y = max(height / 2.0, 0.5)
    return ((xs - center_x) / radius_x) ** 2 + ((ys - center_y) / radius_y) ** 2 <= 1.0


def _paint_disk(
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


def _stroke_points(points: list[Point], radius: int) -> list[Point]:
    if len(points) <= 1:
        return points
    samples: list[Point] = [points[0]]
    spacing = max(0.25, radius / 6.0)
    for start, end in zip(points, points[1:], strict=False):
        distance = float(np.hypot(end[0] - start[0], end[1] - start[1]))
        count = max(1, int(np.ceil(distance / spacing)))
        for index in range(1, count + 1):
            t = index / count
            sample = (
                int(round(start[0] + (end[0] - start[0]) * t)),
                int(round(start[1] + (end[1] - start[1]) * t)),
            )
            if samples[-1] != sample:
                samples.append(sample)
    return samples


def _ellipse_mask(width: int, height: int) -> np.ndarray:
    yy, xx = np.ogrid[:height, :width]
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0
    radius_x = max(width / 2.0, 0.5)
    radius_y = max(height / 2.0, 0.5)
    return ((xx - center_x) / radius_x) ** 2 + ((yy - center_y) / radius_y) ** 2 <= 1.0
