"""Document-level selection masks and rasterization helpers."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import numpy as np
from scipy import ndimage
from skimage.draw import polygon as draw_polygon


class SelectionCombineMode(StrEnum):
    """GIMP-style selection combination modes."""

    REPLACE = "replace"
    ADD = "add"
    SUBTRACT = "subtract"
    INTERSECT = "intersect"


@dataclass(slots=True)
class SelectionOptions:
    """Common selection tool options."""

    mode: SelectionCombineMode = SelectionCombineMode.REPLACE
    antialias: bool = True
    feather: bool = False
    feather_radius_px: float = 0.0


@dataclass(slots=True)
class DocumentSelection:
    """One image-aligned floating-point selection mask."""

    coverage: np.ndarray
    revision: int = 0
    inverted: bool = False

    @classmethod
    def empty(cls, width: int, height: int) -> DocumentSelection:
        return cls(np.zeros((height, width), dtype=np.float32))

    @property
    def is_empty(self) -> bool:
        return not bool(np.any(self.effective_coverage() > 0.0))

    @property
    def bounds(self) -> tuple[int, int, int, int] | None:
        mask = self.effective_coverage() > 0.0
        if not np.any(mask):
            return None
        ys, xs = np.nonzero(mask)
        x0 = int(xs.min())
        y0 = int(ys.min())
        x1 = int(xs.max()) + 1
        y1 = int(ys.max()) + 1
        return (x0, y0, x1 - x0, y1 - y0)

    def effective_coverage(self) -> np.ndarray:
        coverage = np.asarray(self.coverage, dtype=np.float32)
        if self.inverted:
            return 1.0 - coverage
        return coverage

    def combine(self, new_mask: np.ndarray, mode: SelectionCombineMode) -> None:
        self.coverage = combine_masks(self.coverage, new_mask, mode)
        self.revision += 1


def combine_masks(
    existing: np.ndarray | None, new_mask: np.ndarray, mode: SelectionCombineMode | str
) -> np.ndarray:
    """Combine soft masks using GIMP-style selection modes."""
    mode = SelectionCombineMode(mode)
    new = np.clip(np.asarray(new_mask, dtype=np.float32), 0.0, 1.0)
    if existing is None or np.asarray(existing).shape != new.shape or mode is SelectionCombineMode.REPLACE:
        return new.copy()
    old = np.clip(np.asarray(existing, dtype=np.float32), 0.0, 1.0)
    if mode is SelectionCombineMode.ADD:
        return np.maximum(old, new)
    if mode is SelectionCombineMode.SUBTRACT:
        return old * (1.0 - new)
    if mode is SelectionCombineMode.INTERSECT:
        return old * new
    raise ValueError(f"Unsupported selection mode: {mode}")


def combine_mask_region(
    existing: np.ndarray | None,
    region_mask: np.ndarray,
    region_rect: tuple[int, int, int, int],
    image_shape: tuple[int, int],
    mode: SelectionCombineMode | str,
    *,
    copy_existing: bool = True,
) -> np.ndarray:
    """Combine a local soft mask into an image-sized selection channel."""
    mode = SelectionCombineMode(mode)
    height, width = image_shape
    x, y, rect_width, rect_height = _clip_rect(region_rect, width, height)
    if rect_width <= 0 or rect_height <= 0:
        if existing is not None and np.asarray(existing).shape == image_shape:
            return np.asarray(existing, dtype=np.float32)
        return np.zeros(image_shape, dtype=np.float32)
    local = np.clip(
        np.asarray(region_mask[:rect_height, :rect_width], dtype=np.float32),
        0.0,
        1.0,
    )
    if existing is None or np.asarray(existing).shape != image_shape or mode is SelectionCombineMode.REPLACE:
        result = np.zeros(image_shape, dtype=np.float32)
        result[y : y + rect_height, x : x + rect_width] = local
        return result
    existing_array = np.asarray(existing, dtype=np.float32)
    result = existing_array.copy() if copy_existing else existing_array
    target = result[y : y + rect_height, x : x + rect_width]
    if mode is SelectionCombineMode.ADD:
        np.maximum(target, local, out=target)
    elif mode is SelectionCombineMode.SUBTRACT:
        target *= 1.0 - local
    elif mode is SelectionCombineMode.INTERSECT:
        if y > 0:
            result[:y, :] = 0.0
        if y + rect_height < height:
            result[y + rect_height :, :] = 0.0
        if x > 0:
            result[y : y + rect_height, :x] = 0.0
        if x + rect_width < width:
            result[y : y + rect_height, x + rect_width :] = 0.0
        target *= local
    else:
        raise ValueError(f"Unsupported selection mode: {mode}")
    return result


def selection_shape_region(
    shape: tuple[int, int],
    kind: str,
    rect: tuple[int, int, int, int],
    points: list[tuple[float, float]] | None = None,
    *,
    antialias: bool = True,
    feather_radius_px: float = 0.0,
) -> tuple[tuple[int, int, int, int], np.ndarray] | None:
    """Rasterize only the affected region of a selection shape."""
    height, width = shape
    if kind == "free" and points and len(points) >= 3:
        return _polygon_mask_region(
            shape,
            points,
            antialias=antialias,
            feather_radius_px=feather_radius_px,
        )
    margin = int(np.ceil(max(0.0, feather_radius_px))) + (1 if antialias else 0)
    x, y, rect_width, rect_height = _clip_rect(
        _expand_rect(rect, margin),
        width,
        height,
    )
    if rect_width <= 0 or rect_height <= 0:
        return None
    local_rect = (rect[0] - x, rect[1] - y, rect[2], rect[3])
    local_shape = (rect_height, rect_width)
    if kind == "ellipse":
        local = ellipse_mask(
            local_shape,
            local_rect,
            antialias=antialias,
            feather_radius_px=feather_radius_px,
        )
    else:
        local = rectangle_mask(
            local_shape,
            local_rect,
            antialias=antialias,
            feather_radius_px=feather_radius_px,
        )
    return (x, y, rect_width, rect_height), local


def rectangle_mask(
    shape: tuple[int, int],
    rect: tuple[int, int, int, int],
    *,
    antialias: bool = True,
    feather_radius_px: float = 0.0,
) -> np.ndarray:
    """Rasterize a rectangular selection into float coverage."""
    height, width = shape
    x, y, rect_width, rect_height = _clip_rect(rect, width, height)
    mask = np.zeros((height, width), dtype=np.float32)
    if rect_width <= 0 or rect_height <= 0:
        return mask
    mask[y : y + rect_height, x : x + rect_width] = 1.0
    del antialias
    return feather_mask(mask, feather_radius_px)


def ellipse_mask(
    shape: tuple[int, int],
    rect: tuple[int, int, int, int],
    *,
    antialias: bool = True,
    feather_radius_px: float = 0.0,
) -> np.ndarray:
    """Rasterize an elliptical selection into float coverage."""
    height, width = shape
    x, y, rect_width, rect_height = _clip_rect(rect, width, height)
    mask = np.zeros((height, width), dtype=np.float32)
    if rect_width <= 0 or rect_height <= 0:
        return mask
    cx = x + rect_width / 2.0
    cy = y + rect_height / 2.0
    rx = max(rect_width / 2.0, 0.5)
    ry = max(rect_height / 2.0, 0.5)
    xs = ((np.arange(x, x + rect_width, dtype=np.float32) + 0.5 - cx) / rx) ** 2
    ys = ((np.arange(y, y + rect_height, dtype=np.float32) + 0.5 - cy) / ry) ** 2
    local = ys[:, None] + xs[None, :]
    if antialias:
        np.sqrt(local, out=local)
        local *= -min(rx, ry)
        local += min(rx, ry) + 0.5
        np.clip(local, 0.0, 1.0, out=local)
    else:
        local = (local <= 1.0).astype(np.float32)
    mask[y : y + rect_height, x : x + rect_width] = local
    return feather_mask(mask, feather_radius_px)


def polygon_mask(
    shape: tuple[int, int],
    points: list[tuple[float, float]],
    *,
    antialias: bool = True,
    feather_radius_px: float = 0.0,
) -> np.ndarray:
    """Rasterize a closed polygon/free-select path into float coverage."""
    height, width = shape
    if len(points) < 3:
        return np.zeros((height, width), dtype=np.float32)
    scale = 3 if antialias else 1
    scaled_height = height * scale
    scaled_width = width * scale
    scaled_points = np.asarray(points, dtype=np.float64) * scale + (scale - 1) / 2.0
    rows, cols = draw_polygon(
        scaled_points[:, 1],
        scaled_points[:, 0],
        shape=(scaled_height, scaled_width),
    )
    high = np.zeros((scaled_height, scaled_width), dtype=np.float32)
    high[rows, cols] = 1.0
    if scale > 1:
        mask = high.reshape(height, scale, width, scale).mean(axis=(1, 3))
    else:
        mask = high
    return feather_mask(mask, feather_radius_px)


def _polygon_mask_region(
    shape: tuple[int, int],
    points: list[tuple[float, float]],
    *,
    antialias: bool,
    feather_radius_px: float,
) -> tuple[tuple[int, int, int, int], np.ndarray] | None:
    height, width = shape
    point_array = np.asarray(points, dtype=np.float64)
    if point_array.shape[0] < 3:
        return None
    margin = int(np.ceil(max(0.0, feather_radius_px))) + (1 if antialias else 0)
    min_x = int(np.floor(point_array[:, 0].min())) - margin
    min_y = int(np.floor(point_array[:, 1].min())) - margin
    max_x = int(np.ceil(point_array[:, 0].max())) + margin + 1
    max_y = int(np.ceil(point_array[:, 1].max())) + margin + 1
    x, y, rect_width, rect_height = _clip_rect(
        (min_x, min_y, max_x - min_x, max_y - min_y),
        width,
        height,
    )
    if rect_width <= 0 or rect_height <= 0:
        return None
    scale = 3 if antialias else 1
    scaled_points = (point_array - np.array([x, y], dtype=np.float64)) * scale + (
        scale - 1
    ) / 2.0
    rows, cols = draw_polygon(
        scaled_points[:, 1],
        scaled_points[:, 0],
        shape=(rect_height * scale, rect_width * scale),
    )
    high = np.zeros((rect_height * scale, rect_width * scale), dtype=np.float32)
    high[rows, cols] = 1.0
    if scale > 1:
        local = high.reshape(rect_height, scale, rect_width, scale).mean(axis=(1, 3))
    else:
        local = high
    return (x, y, rect_width, rect_height), feather_mask(local, feather_radius_px)


def feather_mask(mask: np.ndarray, radius_px: float) -> np.ndarray:
    """Apply symmetric signed-distance feathering to a selection mask."""
    radius = float(radius_px)
    coverage = np.clip(np.asarray(mask, dtype=np.float32), 0.0, 1.0)
    if radius <= 0.0 or coverage.size == 0:
        return coverage
    hard = coverage >= 0.5
    if not np.any(hard):
        return coverage
    if np.all(hard):
        return coverage
    inside = ndimage.distance_transform_edt(hard)
    outside = ndimage.distance_transform_edt(~hard)
    signed = inside - outside
    feathered = np.clip((signed + radius) / (2.0 * radius), 0.0, 1.0)
    return feathered.astype(np.float32, copy=False)


def _supersampled_shape_mask(
    shape: tuple[int, int],
    rect: tuple[int, int, int, int],
    predicate: object,
    *,
    antialias: bool,
    feather_radius_px: float,
) -> np.ndarray:
    height, width = shape
    x, y, rect_width, rect_height = _clip_rect(rect, width, height)
    mask = np.zeros((height, width), dtype=np.float32)
    if rect_width <= 0 or rect_height <= 0:
        return mask
    scale = 3 if antialias else 1
    yy, xx = np.mgrid[0 : rect_height * scale, 0 : rect_width * scale]
    xx = x + (xx + 0.5) / scale
    yy = y + (yy + 0.5) / scale
    cx = x + rect_width / 2.0
    cy = y + rect_height / 2.0
    rx = max(rect_width / 2.0, 0.5)
    ry = max(rect_height / 2.0, 0.5)
    high = predicate(xx, yy, cx, cy, rx, ry).astype(np.float32)
    if scale > 1:
        local = high.reshape(rect_height, scale, rect_width, scale).mean(axis=(1, 3))
    else:
        local = high
    mask[y : y + rect_height, x : x + rect_width] = local
    return feather_mask(mask, feather_radius_px)


def _clip_rect(
    rect: tuple[int, int, int, int], width: int, height: int
) -> tuple[int, int, int, int]:
    x, y, rect_width, rect_height = rect
    x = max(0, min(int(x), width))
    y = max(0, min(int(y), height))
    rect_width = max(0, min(int(rect_width), width - x))
    rect_height = max(0, min(int(rect_height), height - y))
    return x, y, rect_width, rect_height


def _expand_rect(
    rect: tuple[int, int, int, int], margin: int
) -> tuple[int, int, int, int]:
    x, y, width, height = rect
    return (x - margin, y - margin, width + margin * 2, height + margin * 2)
