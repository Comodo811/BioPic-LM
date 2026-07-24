"""Tile-backed raster editing primitives.

SPDX-License-Identifier: GPL-3.0-or-later
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np

from biopic.imaging.regions import DirtyRegion, union_rects
from biopic.native.stroke_backend import paint_disks, paint_disks_pair

Point = tuple[int, int]
Rect = tuple[int, int, int, int]
TileCoord = tuple[int, int]


@dataclass(slots=True)
class TilePatch:
    """Before/after data for one dirty paint tile."""

    x: int
    y: int
    content_before: np.ndarray
    content_after: np.ndarray
    alpha_before: np.ndarray
    alpha_after: np.ndarray


@dataclass(slots=True)
class TilePaintSession:
    """Edit a raster layer by touching only tiles intersecting the stroke."""

    base_pixels: np.ndarray
    content_pixels: np.ndarray | None
    alpha_pixels: np.ndarray | None
    tile_size: int = 256
    _content_tiles: dict[TileCoord, np.ndarray] = field(default_factory=dict)
    _alpha_tiles: dict[TileCoord, np.ndarray] = field(default_factory=dict)
    _before_content_tiles: dict[TileCoord, np.ndarray] = field(default_factory=dict)
    _before_alpha_tiles: dict[TileCoord, np.ndarray] = field(default_factory=dict)
    _dirty_region: DirtyRegion = field(default_factory=DirtyRegion)
    _last_dirty_rects: list[Rect] = field(default_factory=list)

    def paint(
        self,
        points: list[Point],
        radius: int,
        value: Any,
        *,
        paint_alpha: bool,
        alpha_value: float = 1.0,
        selection_rect: Rect | None = None,
        selection_shape: str = "rectangle",
        selection_mask: np.ndarray | None = None,
    ) -> Rect | None:
        """Paint a stroke into intersecting content/alpha tiles only."""
        if not points:
            return None
        if selection_rect is None and selection_mask is not None:
            selection_rect = _mask_bounds(selection_mask)
        dirty_rects = self._dirty_rects_for_points(points, radius, selection_rect)
        dirty_rect = union_rects(dirty_rects)
        for coord, tile_rect in self._tiles_for_dirty_rects(dirty_rects):
            tile_points = [(x - tile_rect[0], y - tile_rect[1]) for x, y in points]
            tile_selection = _translate_selection(selection_rect, tile_rect)
            before_content = self._content_tile(coord, tile_rect).copy()
            before_alpha = self._alpha_tile(coord, tile_rect).copy()
            if not paint_alpha:
                content = self._content_tile(coord, tile_rect)
                paint_disks(
                    content,
                    tile_points,
                    radius,
                    value,
                    selection_rect=tile_selection,
                    selection_shape=selection_shape,
                )
            alpha = self._alpha_tile(coord, tile_rect)
            paint_disks(
                alpha,
                tile_points,
                radius,
                alpha_value,
                selection_rect=tile_selection,
                selection_shape=selection_shape,
            )
            self._apply_tile_selection_mask(coord, tile_rect, before_content, before_alpha, selection_mask)
        self._dirty_region.add(dirty_rect)
        self._last_dirty_rects = dirty_rects
        return dirty_rect

    def paint_content_and_alpha(
        self,
        points: list[Point],
        radius: int,
        value: Any,
        *,
        alpha_value: float = 1.0,
        selection_rect: Rect | None = None,
        selection_shape: str = "rectangle",
        selection_mask: np.ndarray | None = None,
    ) -> Rect | None:
        """Paint content and opacity together in one tile traversal."""
        if not points:
            return None
        if selection_rect is None and selection_mask is not None:
            selection_rect = _mask_bounds(selection_mask)
        dirty_rects = self._dirty_rects_for_points(points, radius, selection_rect)
        dirty_rect = union_rects(dirty_rects)
        for coord, tile_rect in self._tiles_for_dirty_rects(dirty_rects):
            tile_points = [(x - tile_rect[0], y - tile_rect[1]) for x, y in points]
            tile_selection = _translate_selection(selection_rect, tile_rect)
            before_content = self._content_tile(coord, tile_rect).copy()
            before_alpha = self._alpha_tile(coord, tile_rect).copy()
            paint_disks_pair(
                self._content_tile(coord, tile_rect),
                self._alpha_tile(coord, tile_rect),
                tile_points,
                radius,
                value,
                alpha_value=alpha_value,
                selection_rect=tile_selection,
                selection_shape=selection_shape,
            )
            self._apply_tile_selection_mask(coord, tile_rect, before_content, before_alpha, selection_mask)
        self._dirty_region.add(dirty_rect)
        self._last_dirty_rects = dirty_rects
        return dirty_rect

    def last_dirty_rects(self) -> list[Rect]:
        """Return precise dirty rectangles from the most recent paint operation."""
        return list(self._last_dirty_rects)

    def region_content_alpha(self, rect: Rect) -> tuple[np.ndarray, np.ndarray]:
        """Return a region view with all dirty tile patches overlaid."""
        x, y, width, height = rect
        content = self._base_content()[y : y + height, x : x + width].copy()
        alpha = self._base_alpha()[y : y + height, x : x + width].copy()
        for coord in self._tile_coords_for_rect(rect):
            tile = self._content_tiles.get(coord)
            if tile is None:
                continue
            tile_x, tile_y, tile_width, tile_height = self._tile_rect(coord)
            overlap = _intersect_rect(rect, (tile_x, tile_y, tile_width, tile_height))
            if overlap is None:
                continue
            ox, oy, ow, oh = overlap
            content[oy - y : oy - y + oh, ox - x : ox - x + ow] = tile[
                oy - tile_y : oy - tile_y + oh,
                ox - tile_x : ox - tile_x + ow,
            ]
        for coord in self._tile_coords_for_rect(rect):
            tile = self._alpha_tiles.get(coord)
            if tile is None:
                continue
            tile_x, tile_y, tile_width, tile_height = self._tile_rect(coord)
            overlap = _intersect_rect(rect, (tile_x, tile_y, tile_width, tile_height))
            if overlap is None:
                continue
            ox, oy, ow, oh = overlap
            alpha[oy - y : oy - y + oh, ox - x : ox - x + ow] = tile[
                oy - tile_y : oy - tile_y + oh,
                ox - tile_x : ox - tile_x + ow,
            ]
        return content, alpha

    def materialize(self) -> tuple[np.ndarray, np.ndarray]:
        """Apply dirty tiles into durable layer buffers and return them."""
        content_base = self._base_content()
        alpha_base = self._base_alpha()
        content = (
            content_base
            if self.content_pixels is not None
            and not np.shares_memory(content_base, self.base_pixels)
            else content_base.copy()
        )
        alpha = alpha_base if self.alpha_pixels is not None else alpha_base.copy()
        for coord, tile in self._content_tiles.items():
            x, y, width, height = self._tile_rect(coord)
            content[y : y + height, x : x + width] = tile
        for coord, tile in self._alpha_tiles.items():
            x, y, width, height = self._tile_rect(coord)
            alpha[y : y + height, x : x + width] = tile
        return content, alpha

    def patches(self) -> list[TilePatch]:
        """Return compact dirty-tile before/after patches for undo/redo."""
        patches: list[TilePatch] = []
        for coord in sorted(set(self._content_tiles) | set(self._alpha_tiles)):
            x, y, _width, _height = self._tile_rect(coord)
            content_after = self._content_tiles.get(coord, self._before_content_tiles[coord])
            alpha_after = self._alpha_tiles.get(coord, self._before_alpha_tiles[coord])
            patches.append(
                TilePatch(
                    x=x,
                    y=y,
                    content_before=self._before_content_tiles[coord].copy(),
                    content_after=content_after.copy(),
                    alpha_before=self._before_alpha_tiles[coord].copy(),
                    alpha_after=alpha_after.copy(),
                )
            )
        return patches

    def dirty_rect(self) -> Rect | None:
        """Return the union of dirty tile rectangles."""
        coords = set(self._content_tiles) | set(self._alpha_tiles)
        if not coords:
            return None
        return self._dirty_region.bounds() or union_rects(
            [self._tile_rect(coord) for coord in coords]
        )

    def dirty_rectangles(self) -> list[Rect]:
        """Return precise accumulated dirty rectangles."""
        return self._dirty_region.rectangles()

    def _content_tile(self, coord: TileCoord, rect: Rect) -> np.ndarray:
        if coord not in self._content_tiles:
            tile = self._base_content()[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]]
            self._content_tiles[coord] = tile.copy()
            self._before_content_tiles[coord] = tile.copy()
        if coord not in self._before_alpha_tiles:
            alpha = self._base_alpha()[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]]
            self._before_alpha_tiles[coord] = alpha.copy()
        return self._content_tiles[coord]

    def _alpha_tile(self, coord: TileCoord, rect: Rect) -> np.ndarray:
        if coord not in self._alpha_tiles:
            alpha = self._base_alpha()[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]]
            self._alpha_tiles[coord] = alpha.copy()
            self._before_alpha_tiles[coord] = alpha.copy()
        if coord not in self._before_content_tiles:
            tile = self._base_content()[rect[1] : rect[1] + rect[3], rect[0] : rect[0] + rect[2]]
            self._before_content_tiles[coord] = tile.copy()
        return self._alpha_tiles[coord]

    def _apply_tile_selection_mask(
        self,
        coord: TileCoord,
        rect: Rect,
        before_content: np.ndarray,
        before_alpha: np.ndarray,
        selection_mask: np.ndarray | None,
    ) -> None:
        if selection_mask is None:
            return
        x, y, width, height = rect
        local = selection_mask[y : y + height, x : x + width].astype(np.float32, copy=False)
        if local.size == 0 or np.all(local >= 1.0):
            return
        content = self._content_tiles.get(coord)
        alpha = self._alpha_tiles.get(coord)
        if content is not None:
            if content.ndim == 3:
                blended_content = before_content * (1.0 - local[..., None]) + content * local[..., None]
            else:
                blended_content = before_content * (1.0 - local) + content * local
            self._content_tiles[coord] = _restore_tile_dtype(blended_content, before_content.dtype)
        if alpha is not None:
            self._alpha_tiles[coord] = before_alpha * (1.0 - local) + alpha * local

    def _tiles_for_stroke(
        self, points: list[Point], radius: int, selection_rect: Rect | None
    ) -> list[tuple[TileCoord, Rect]]:
        return self._tiles_for_dirty_rects(
            self._dirty_rects_for_points(points, radius, selection_rect)
        )

    def _dirty_rects_for_points(
        self, points: list[Point], radius: int, selection_rect: Rect | None
    ) -> list[Rect]:
        if len(points) > 64:
            return [
                rect
                for start in range(0, len(points), 32)
                if (
                    rect := self._dirty_rect_for_points(
                        points[start : start + 32],
                        radius,
                        selection_rect,
                    )
                )
                is not None
            ]
        region = DirtyRegion()
        for point_x, point_y in points:
            region.add(self._dirty_rect_for_points([(point_x, point_y)], radius, selection_rect))
        return region.rectangles()

    def _dirty_rect_for_points(
        self,
        points: list[Point],
        radius: int,
        selection_rect: Rect | None,
    ) -> Rect | None:
        if not points:
            return None
        x_min = max(0, min(point[0] for point in points) - radius - 1)
        y_min = max(0, min(point[1] for point in points) - radius - 1)
        x_max = min(self.base_pixels.shape[1], max(point[0] for point in points) + radius + 2)
        y_max = min(self.base_pixels.shape[0], max(point[1] for point in points) + radius + 2)
        if selection_rect is not None:
            sx, sy, width, height = selection_rect
            x_min = max(x_min, sx)
            y_min = max(y_min, sy)
            x_max = min(x_max, sx + width)
            y_max = min(y_max, sy + height)
        if x_max <= x_min or y_max <= y_min:
            return None
        return (x_min, y_min, x_max - x_min, y_max - y_min)

    def _tiles_for_dirty_rects(self, dirty_rects: list[Rect]) -> list[tuple[TileCoord, Rect]]:
        coords: set[TileCoord] = set()
        for rect in dirty_rects:
            for coord in self._tile_coords_for_rect(rect):
                coords.add(coord)
        return [(coord, self._tile_rect(coord)) for coord in sorted(coords)]

    def _tile_rect(self, coord: TileCoord) -> Rect:
        x = coord[0] * self.tile_size
        y = coord[1] * self.tile_size
        width = min(self.tile_size, self.base_pixels.shape[1] - x)
        height = min(self.tile_size, self.base_pixels.shape[0] - y)
        return x, y, width, height

    def _tile_coords_for_rect(self, rect: Rect) -> list[TileCoord]:
        x, y, width, height = rect
        if width <= 0 or height <= 0:
            return []
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(self.base_pixels.shape[1], x + width)
        y1 = min(self.base_pixels.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            return []
        return [
            (tile_x, tile_y)
            for tile_y in range(y0 // self.tile_size, (y1 - 1) // self.tile_size + 1)
            for tile_x in range(x0 // self.tile_size, (x1 - 1) // self.tile_size + 1)
        ]

    def _base_content(self) -> np.ndarray:
        if self.content_pixels is not None:
            return self.content_pixels
        return self.base_pixels

    def _base_alpha(self) -> np.ndarray:
        if self.alpha_pixels is not None:
            return self.alpha_pixels
        return np.ones(self.base_pixels.shape[:2], dtype=np.float32)


def _translate_selection(selection_rect: Rect | None, tile_rect: Rect) -> Rect | None:
    if selection_rect is None:
        return None
    sx, sy, width, height = selection_rect
    tx, ty, tile_width, tile_height = tile_rect
    x_min = max(sx, tx)
    y_min = max(sy, ty)
    x_max = min(sx + width, tx + tile_width)
    y_max = min(sy + height, ty + tile_height)
    if x_max <= x_min or y_max <= y_min:
        return None
    return (x_min - tx, y_min - ty, x_max - x_min, y_max - y_min)


def _mask_bounds(mask: np.ndarray | None) -> Rect | None:
    if mask is None:
        return None
    active = np.asarray(mask) > 0.0
    if not np.any(active):
        return None
    ys, xs = np.nonzero(active)
    x0 = int(xs.min())
    y0 = int(ys.min())
    x1 = int(xs.max()) + 1
    y1 = int(ys.max()) + 1
    return (x0, y0, x1 - x0, y1 - y0)


def _restore_tile_dtype(tile: np.ndarray, dtype: np.dtype) -> np.ndarray:
    target = np.dtype(dtype)
    if np.issubdtype(target, np.integer):
        info = np.iinfo(target)
        return np.clip(np.rint(tile), info.min, info.max).astype(target)
    return tile.astype(target, copy=False)


def _intersect_rect(first: Rect, second: Rect) -> Rect | None:
    ax, ay, aw, ah = first
    bx, by, bw, bh = second
    x0 = max(ax, bx)
    y0 = max(ay, by)
    x1 = min(ax + aw, bx + bw)
    y1 = min(ay + ah, by + bh)
    if x1 <= x0 or y1 <= y0:
        return None
    return (x0, y0, x1 - x0, y1 - y0)
