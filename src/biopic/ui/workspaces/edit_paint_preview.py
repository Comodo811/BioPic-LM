"""Dirty-region paint preview helpers for the edit workspace."""

from __future__ import annotations

from time import perf_counter

import numpy as np

from biopic.imaging.paint_preview import blend_preview_region
from biopic.imaging.regions import align_rect_outward
from biopic.models.editing import BlendMode, EditLayer
from biopic.ui.workspace_helpers.paint import (
    safe_array_max as _safe_array_max,
)
from biopic.ui.workspace_helpers.paint import (
    safe_array_min as _safe_array_min,
)


class EditPaintPreviewMixin:
    def _flush_paint_display_regions(self) -> None:
        if self._paint_tile_session is None and self._paint_stroke_preview is None:
            self._pending_paint_display_region.clear()
            return
        rects = self._pending_paint_display_region.rectangles()
        if not rects:
            return
        self._pending_paint_display_region.clear()
        if self._paint_tile_session is not None:
            patches = self._paint_preview_patches(rects)
            if patches:
                if self._paint_stroke_preview is not None:
                    for clipped, patch in patches:
                        x, y, width, height = clipped
                        self._paint_stroke_preview[y : y + height, x : x + width] = patch
                    self._publish_live_paint_preview()
                    self.canvas.update_tile_regions(
                        self._current_pixels,
                        [clipped for clipped, _patch in patches],
                    )
                    self._paint_preview_regions_published = True
                else:
                    self.canvas.update_paint_overlay_patches(patches)
            return
        if self._paint_stroke_preview is not None:
            self._update_paint_preview_regions(rects)
            self._repair_corrupt_paint_preview_regions(rects)
            self.canvas.update_paint_overlay_regions(self._paint_stroke_preview, rects)

    def _paint_preview_patches(
        self, rects: list[tuple[int, int, int, int]]
    ) -> list[tuple[tuple[int, int, int, int], np.ndarray]]:
        layer = (
            self.project.edit_layers.get(self._paint_preview_layer_id)
            if self._paint_preview_layer_id is not None
            else None
        )
        if layer is None:
            return []
        patches: list[tuple[tuple[int, int, int, int], np.ndarray]] = []
        for rect in rects:
            clipped = self._clip_paint_rect(rect)
            if clipped is None:
                continue
            patch = self._paint_tile_preview_region(clipped, layer)
            patch = self._repair_corrupt_paint_preview_patch(clipped, patch)
            patches.append((clipped, patch))
        return patches

    def _update_paint_preview_regions(self, rects: list[tuple[int, int, int, int]]) -> None:
        if self._paint_tile_session is None or self._paint_stroke_preview is None:
            return
        layer = (
            self.project.edit_layers.get(self._paint_preview_layer_id)
            if self._paint_preview_layer_id is not None
            else None
        )
        if layer is None:
            return
        for rect in rects:
            clipped = self._clip_paint_rect(rect)
            if clipped is None:
                continue
            x, y, width, height = clipped
            preview_region = self._paint_tile_preview_region(clipped, layer)
            self._paint_stroke_preview[y : y + height, x : x + width] = preview_region

    def _clip_paint_rect(
        self,
        rect: tuple[int, int, int, int],
    ) -> tuple[int, int, int, int] | None:
        reference = self._paint_stroke_preview
        if reference is None:
            reference = (
                self._current_pixels
                if self._current_pixels is not None
                else self._base_pixels
            )
        if reference is None:
            return None
        x, y, width, height = rect
        x0 = max(0, x)
        y0 = max(0, y)
        x1 = min(reference.shape[1], x + width)
        y1 = min(reference.shape[0], y + height)
        if x1 <= x0 or y1 <= y0:
            return None
        return (x0, y0, x1 - x0, y1 - y0)

    def _repair_corrupt_paint_preview_regions(
        self,
        rects: list[tuple[int, int, int, int]],
    ) -> None:
        if self._paint_stroke_preview is None or self._base_pixels is None:
            return
        for rect in rects:
            clipped = self._clip_paint_rect(rect)
            if clipped is None:
                continue
            x, y, width, height = clipped
            preview = self._paint_stroke_preview[y : y + height, x : x + width]
            base = self._base_pixels[y : y + height, x : x + width]
            has_invalid_float = (
                np.issubdtype(preview.dtype, np.floating) and not np.isfinite(preview).all()
            )
            has_blackout = bool(
                preview.size and base.size and np.max(preview) == 0 and np.max(base) > 0
            )
            if has_invalid_float or has_blackout:
                self._record_paint_corruption_event(clipped, preview, base)
                self._paint_stroke_preview[y : y + height, x : x + width] = base

    def _repair_corrupt_paint_preview_patch(
        self,
        rect: tuple[int, int, int, int],
        patch: np.ndarray,
    ) -> np.ndarray:
        if self._base_pixels is None:
            return patch
        x, y, width, height = rect
        base = self._base_pixels[y : y + height, x : x + width]
        has_invalid_float = (
            np.issubdtype(patch.dtype, np.floating) and not np.isfinite(patch).all()
        )
        has_blackout = bool(
            patch.size and base.size and np.max(patch) == 0 and np.max(base) > 0
        )
        if has_invalid_float or has_blackout:
            self._record_paint_corruption_event(rect, patch, base)
            return base.copy()
        return patch

    def _record_paint_corruption_event(
        self,
        rect: tuple[int, int, int, int],
        preview: np.ndarray,
        base: np.ndarray,
    ) -> None:
        if self._paint_corruption_event_count >= 5:
            return
        self._paint_corruption_event_count += 1
        preview_min = _safe_array_min(preview)
        preview_max = _safe_array_max(preview)
        base_min = _safe_array_min(base)
        base_max = _safe_array_max(base)
        tile_min = "n/a"
        tile_max = "n/a"
        if self._paint_tile_session is not None:
            content, alpha = self._paint_tile_session.region_content_alpha(rect)
            tile_min = f"{_safe_array_min(content):g}/{_safe_array_min(alpha):g}"
            tile_max = f"{_safe_array_max(content):g}/{_safe_array_max(alpha):g}"
        self.history.appendPlainText(
            "paint.preview.repair: "
            f"rect={rect}, "
            f"preview={preview_min:g}..{preview_max:g}, "
            f"base={base_min:g}..{base_max:g}, "
            f"tile/alpha={tile_min}..{tile_max}, "
            f"queue={self._paint_work_queue.depth()}"
        )

    def _refresh_projection_after_tile_paint(
        self,
        dirty_rects: list[tuple[int, int, int, int]],
        *,
        update_canvas: bool = True,
    ) -> None:
        if (
            not dirty_rects
            or self._base_pixels is None
            or self._current_source_node_id is None
        ):
            self._invalidate_edit_composite_cache()
            self._render_current_adjustment_preview()
            return
        if self.project.adjustment_layers_for_image(self._current_source_node_id):
            self._invalidate_edit_composite_cache()
            self._render_current_adjustment_preview()
            return
        if self._edit_composite_cache is None:
            self._edit_composite_cache = self._render_edit_composite_cached(
                self._current_source_node_id
            )
        for dirty_rect in dirty_rects:
            x, y, width, height = dirty_rect
            region = self._edit_engine.render_region(
                self._current_source_node_id,
                self._base_pixels,
                dirty_rect,
            )
            self._edit_composite_cache[y : y + height, x : x + width] = region
        self._edit_composite_cache_key = self._edit_composite_key(self._current_source_node_id)
        self._current_pixels = self._edit_composite_cache
        if update_canvas:
            for dirty_rect in dirty_rects:
                self.canvas.update_tile_region(self._current_pixels, dirty_rect)

    def _stage_paint_edit(
        self,
        layer: EditLayer,
        content: np.ndarray,
        alpha: np.ndarray,
        operation: str,
        *,
        dirty_rect: tuple[int, int, int, int] | None = None,
        preview_points: list[tuple[int, int]] | None = None,
        preview_radius: int | None = None,
    ) -> None:
        self._paint_stroke_layer_id = layer.id
        self._paint_stroke_content = content
        self._paint_stroke_alpha = alpha
        self._paint_stroke_operation = operation
        if self._paint_stroke_before is not None:
            if operation == "clone" and dirty_rect is not None:
                preview = self._live_staged_preview(layer, content, alpha, dirty_rect)
                self._current_pixels = preview
                self.canvas.update_tile_region(preview, dirty_rect)
                return
            if preview_points is not None and preview_radius is not None:
                self.canvas.extend_paint_preview(
                    preview_points,
                    preview_radius,
                    self._stroke_preview_color(operation),
                )
            return
        preview = self._live_staged_preview(layer, content, alpha, dirty_rect)
        self._current_pixels = preview
        if self._should_update_live_preview():
            self.canvas.set_pixels(preview, f"{operation} preview", fit=False)

    def _stage_tile_paint_preview(
        self,
        layer: EditLayer,
        operation: str,
        points: list[tuple[int, int]],
        radius: int,
        dirty_rect: tuple[int, int, int, int] | None,
    ) -> None:
        self._paint_stroke_operation = operation
        if (
            dirty_rect is None
            or self._paint_tile_session is None
            or self._base_pixels is None
        ):
            self.canvas.extend_paint_preview(points, radius, self._stroke_preview_color(operation))
            return
        self._paint_preview_layer_id = layer.id
        clipped = self._clip_paint_rect(dirty_rect)
        if clipped is not None and self._paint_stroke_preview is not None:
            x, y, width, height = clipped
            patch = self._paint_tile_preview_region(clipped, layer)
            patch = self._repair_corrupt_paint_preview_patch(clipped, patch)
            self._paint_stroke_preview[y : y + height, x : x + width] = patch
            self._publish_live_paint_preview()
        self._pending_paint_display_region.add(align_rect_outward(dirty_rect, 32, 32))
        if not self._paint_flush_timer.isActive():
            self._paint_flush_timer.start()

    def _publish_live_paint_preview(self) -> None:
        preview = self._paint_stroke_preview
        if preview is not None:
            self._current_pixels = preview

    def _paint_tile_preview_region(
        self,
        rect: tuple[int, int, int, int],
        layer: EditLayer,
    ) -> np.ndarray:
        if self._paint_tile_session is None or self._base_pixels is None:
            x, y, width, height = rect
            assert self._current_pixels is not None
            return self._current_pixels[y : y + height, x : x + width]
        x, y, width, height = rect
        content_region, alpha_region = self._paint_tile_session.region_content_alpha(rect)
        if self._can_fast_preview_tile_paint(layer) and np.all(alpha_region >= 0.999):
            return content_region
        if self._current_source_node_id is not None:
            background = self._edit_engine.render_region_excluding(
                self._current_source_node_id,
                self._base_pixels,
                rect,
                layer.id,
            )
        else:
            background = self._base_pixels[y : y + height, x : x + width]
        return blend_preview_region(
            background,
            content_region,
            alpha_region,
            layer.opacity,
        )

    def _can_fast_preview_tile_paint(self, layer: EditLayer) -> bool:
        return (
            self._paint_stroke_operation != "erase"
            and
            layer.visible
            and layer.blend_mode is BlendMode.NORMAL
            and not layer.mask_enabled
            and layer.opacity >= 0.999
        )

    def _preview_staged_layer(
        self,
        layer: EditLayer,
        content: np.ndarray,
        alpha: np.ndarray,
    ) -> np.ndarray:
        if self._base_pixels is None:
            return content
        base = self._base_pixels.astype(np.float32, copy=False)
        foreground = content.astype(np.float32, copy=False)
        layer_alpha = alpha.astype(np.float32, copy=False) * float(layer.opacity)
        if layer_alpha.ndim == 2 and foreground.ndim == 3:
            layer_alpha = layer_alpha[..., None]
        preview = layer_alpha * foreground + (1.0 - layer_alpha) * base
        if np.issubdtype(self._base_pixels.dtype, np.integer):
            info = np.iinfo(self._base_pixels.dtype)
            return np.clip(preview, info.min, info.max).astype(self._base_pixels.dtype)
        return preview.astype(self._base_pixels.dtype, copy=False)

    def _live_staged_preview(
        self,
        layer: EditLayer,
        content: np.ndarray,
        alpha: np.ndarray,
        dirty_rect: tuple[int, int, int, int] | None,
    ) -> np.ndarray:
        if (
            self._paint_stroke_before is None
            or dirty_rect is None
            or self._paint_stroke_preview is None
            or self._base_pixels is None
        ):
            preview = self._preview_staged_layer(layer, content, alpha)
            if self._paint_stroke_before is not None:
                self._paint_stroke_preview = preview
            return preview
        x, y, width, height = dirty_rect
        if width <= 0 or height <= 0:
            return self._paint_stroke_preview
        preview = self._paint_stroke_preview
        base_region = self._base_pixels[y : y + height, x : x + width]
        content_region = content[y : y + height, x : x + width]
        alpha_region = alpha[y : y + height, x : x + width]
        preview[y : y + height, x : x + width] = blend_preview_region(
            base_region, content_region, alpha_region, layer.opacity
        )
        return preview

    def _should_update_live_preview(self) -> bool:
        if self._paint_stroke_before is None:
            return True
        now = perf_counter()
        if now - self._last_live_preview_at < 1.0 / 45.0:
            return False
        self._last_live_preview_at = now
        return True

    def _stroke_dirty_rect(
        self, points: list[tuple[int, int]], radius: int
    ) -> tuple[int, int, int, int] | None:
        if not points or self._current_pixels is None:
            return None
        image_height, image_width = self._current_pixels.shape[:2]
        x_min = max(0, min(point[0] for point in points) - radius - 1)
        y_min = max(0, min(point[1] for point in points) - radius - 1)
        x_max = min(image_width, max(point[0] for point in points) + radius + 2)
        y_max = min(image_height, max(point[1] for point in points) + radius + 2)
        if self._selection_rect is not None:
            sx, sy, width, height = self._selection_rect
            x_min = max(x_min, sx)
            y_min = max(y_min, sy)
            x_max = min(x_max, sx + width)
            y_max = min(y_max, sy + height)
        if x_max <= x_min or y_max <= y_min:
            return None
        return (x_min, y_min, x_max - x_min, y_max - y_min)

