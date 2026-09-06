"""Retouch, clone/heal, layer move, and constrained paint helpers."""

from __future__ import annotations

import numpy as np

from biopic.imaging.tiles import TilePaintSession
from biopic.models.editing import EditLayer, LayerLock, RetouchStroke
from biopic.native.stroke_backend import paint_disks, paint_stroke


class EditPaintRetouchMixin:
    """Clone/heal sources, layer movement, and selection-constrained paint helpers."""

    def _set_clone_source_point(self, x: int, y: int) -> None:
        if self._base_pixels is None:
            return
        height, width = self._base_pixels.shape[:2]
        if not (0 <= x < width and 0 <= y < height):
            return
        self._clone_source_point = (x, y)
        self._clone_stroke_anchor = None
        self._clone_source_content = None
        self._clone_source_alpha = None
        self._status(f"Retouch source set: {x}, {y}")

    def _clone_source_buffers(
        self,
        fallback_content: np.ndarray,
        fallback_alpha: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        if self._clone_source_content is not None and self._clone_source_alpha is not None:
            return self._clone_source_content, self._clone_source_alpha
        self._clone_source_content = np.ascontiguousarray(fallback_content).copy()
        self._clone_source_alpha = np.ascontiguousarray(fallback_alpha).copy()
        return self._clone_source_content, self._clone_source_alpha

    def _clone_tile_source_buffers(self, layer: EditLayer) -> tuple[np.ndarray, np.ndarray]:
        if self._clone_source_content is not None and self._clone_source_alpha is not None:
            return self._clone_source_content, self._clone_source_alpha
        content, alpha = self._layer_arrays_for_tile_edit(layer)
        self._clone_source_content = np.ascontiguousarray(content).copy()
        self._clone_source_alpha = np.ascontiguousarray(alpha).copy()
        return self._clone_source_content, self._clone_source_alpha

    def _clone_source_offset(self) -> tuple[int, int]:
        if self._clone_source_point is None or self._clone_stroke_anchor is None:
            return (0, 0)
        source_x, source_y = self._clone_source_point
        anchor_x, anchor_y = self._clone_stroke_anchor
        return source_x - anchor_x, source_y - anchor_y

    def _clone_disk_from_source(
        self,
        content: np.ndarray,
        alpha: np.ndarray,
        source_content: np.ndarray,
        source_alpha: np.ndarray,
        center_x: int,
        center_y: int,
        radius: int,
    ) -> None:
        if self._clone_source_point is None or self._clone_stroke_anchor is None:
            return
        source_x, source_y = self._clone_source_point
        anchor_x, anchor_y = self._clone_stroke_anchor
        offset_x = source_x - anchor_x
        offset_y = source_y - anchor_y
        height, width = content.shape[:2]
        y_min = max(0, center_y - radius)
        y_max = min(height, center_y + radius + 1)
        x_min = max(0, center_x - radius)
        x_max = min(width, center_x + radius + 1)
        if y_min >= y_max or x_min >= x_max:
            return
        yy, xx = np.ogrid[y_min:y_max, x_min:x_max]
        mask = (xx - center_x) ** 2 + (yy - center_y) ** 2 <= radius**2
        if self._selection_rect is not None:
            sx, sy, selection_width, selection_height = self._selection_rect
            mask &= (
                (xx >= sx)
                & (xx < sx + selection_width)
                & (yy >= sy)
                & (yy < sy + selection_height)
            )
            if self._selection_shape == "ellipse":
                center_selection_x = sx + (selection_width - 1) / 2.0
                center_selection_y = sy + (selection_height - 1) / 2.0
                radius_selection_x = max(selection_width / 2.0, 0.5)
                radius_selection_y = max(selection_height / 2.0, 0.5)
                mask &= (
                    ((xx - center_selection_x) / radius_selection_x) ** 2
                    + ((yy - center_selection_y) / radius_selection_y) ** 2
                    <= 1.0
                )
        source_xs = xx + offset_x
        source_ys = yy + offset_y
        source_xs = np.broadcast_to(source_xs, mask.shape)
        source_ys = np.broadcast_to(source_ys, mask.shape)
        mask &= (
            (source_xs >= 0)
            & (source_xs < width)
            & (source_ys >= 0)
            & (source_ys < height)
        )
        if not np.any(mask):
            return
        destination_content = content[y_min:y_max, x_min:x_max]
        destination_alpha = alpha[y_min:y_max, x_min:x_max]
        destination_content[mask] = source_content[source_ys[mask], source_xs[mask]]
        destination_alpha[mask] = source_alpha[source_ys[mask], source_xs[mask]]

    def _heal_disk_from_source(
        self,
        content: np.ndarray,
        alpha: np.ndarray,
        source_content: np.ndarray,
        source_alpha: np.ndarray,
        center_x: int,
        center_y: int,
        radius: int,
    ) -> None:
        session = TilePaintSession(content, content, alpha, tile_size=max(content.shape[:2]))
        session.heal_content_and_alpha(
            [(center_x, center_y)],
            radius,
            source_content,
            source_alpha,
            self._clone_source_offset(),
            selection_rect=self._selection_rect,
            selection_shape=self._selection_shape,
            selection_mask=self._selection_coverage_mask(),
        )
        healed_content, healed_alpha = session.materialize()
        content[...] = healed_content
        alpha[...] = healed_alpha

    def _begin_layer_move(self, _x: int, _y: int) -> None:
        self._move_commit_render_timer.stop()
        layer = self._active_layer()
        if layer is None:
            self._status("Select an editable layer first.")
            return
        if layer.locked or LayerLock.POSITION in layer.lock_flags:
            self._status("Cannot move a locked layer.")
            return
        self._move_before = self._snapshot_edit_state()
        self._move_layer_id = layer.id
        self._move_start_offset = (layer.offset_x, layer.offset_y)
        self._begin_layer_move_canvas_preview(layer)

    def _preview_layer_move(
        self,
        start_x: int,
        start_y: int,
        end_x: int,
        end_y: int,
        *,
        force: bool = False,
    ) -> None:
        if self._move_layer_id is None or self._move_start_offset is None:
            return
        layer = self.project.edit_layers.get(self._move_layer_id)
        if layer is None:
            return
        dx = end_x - start_x
        dy = end_y - start_y
        layer.offset_x = self._move_start_offset[0] + dx
        layer.offset_y = self._move_start_offset[1] + dy
        self.canvas.move_layer_preview_to(float(layer.offset_x), float(layer.offset_y))

    def _finish_layer_move(self, start_x: int, start_y: int, end_x: int, end_y: int) -> None:
        if self._move_before is None:
            self._clear_layer_move()
            return
        self._preview_layer_move(start_x, start_y, end_x, end_y, force=True)
        self._finish_command("move layer", self._move_before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._refresh_history()
        if self.editApplied is not None:
            self.editApplied()
        self._move_commit_render_timer.start()
        self._clear_layer_move()

    def _clear_layer_move(self) -> None:
        self._move_before = None
        self._move_layer_id = None
        self._move_start_offset = None

    def _render_committed_layer_move(self) -> None:
        if self._move_before is not None:
            return
        self.canvas.clear_layer_move_preview()
        self._invalidate_edit_composite_cache()
        self._render_current_adjustment_preview()

    def _begin_layer_move_canvas_preview(self, layer: EditLayer) -> None:
        if self._base_pixels is None or self._current_source_node_id is None:
            return
        content, alpha = self._layer_arrays_for_tile_edit(layer)
        if content is None or alpha is None:
            return
        width = self._base_pixels.shape[1]
        height = self._base_pixels.shape[0]
        background = self._edit_engine.render_region_excluding(
            self._current_source_node_id,
            self._base_pixels,
            (0, 0, width, height),
            layer.id,
        )
        self.canvas.set_pixels(background, "move preview background", fit=False)
        self.canvas.begin_layer_move_preview(
            content,
            alpha,
            layer.offset_x,
            layer.offset_y,
            opacity=layer.opacity,
        )

    def _paint_disk_constrained(
        self,
        pixels: np.ndarray,
        center_x: int,
        center_y: int,
        radius: int,
        value: object,
    ) -> None:
        paint_disks(
            pixels,
            [(center_x, center_y)],
            radius,
            value,
            selection_rect=self._selection_rect,
            selection_shape=self._selection_shape,
        )

    def _paint_points_constrained(
        self,
        pixels: np.ndarray,
        points: list[tuple[int, int]],
        radius: int,
        value: object,
    ) -> None:
        paint_disks(
            pixels,
            points,
            radius,
            value,
            selection_rect=self._selection_rect,
            selection_shape=self._selection_shape,
        )

    def _paint_stroke_constrained(
        self,
        pixels: np.ndarray,
        points: list[tuple[int, int]],
        radius: int,
        value: object,
    ) -> None:
        paint_stroke(
            pixels,
            points,
            radius,
            value,
            selection_rect=self._selection_rect,
            selection_shape=self._selection_shape,
        )

    def _fill_constrained(self, pixels: np.ndarray, value: object) -> None:
        coverage = self._selection_coverage_mask()
        if coverage is None or self._selection_rect is None:
            pixels[...] = value
            return
        sx, sy, width, height = self._selection_rect
        region = pixels[sy : sy + height, sx : sx + width]
        if region.size == 0:
            return
        local_coverage = coverage[sy : sy + height, sx : sx + width]
        if np.all(local_coverage >= 1.0):
            region[...] = value
            return
        if np.issubdtype(region.dtype, np.integer):
            dtype = region.dtype
            target = np.asarray(value, dtype=np.float32)
            alpha = (
                1.0 - local_coverage[..., None]
                if region.ndim == 3
                else 1.0 - local_coverage
            )
            blended = region.astype(np.float32) * alpha
            if region.ndim == 3:
                blended += target * local_coverage[..., None]
            else:
                blended += float(target) * local_coverage
            info = np.iinfo(dtype)
            region[...] = np.clip(np.rint(blended), info.min, info.max).astype(dtype)
            return
        if region.ndim == 3:
            coverage_channels = local_coverage[..., None]
            region[...] = (
                region * (1.0 - coverage_channels)
                + np.asarray(value) * coverage_channels
            )
        else:
            region[...] = region * (1.0 - local_coverage) + float(value) * local_coverage

    def _paint_value(self, pixels: np.ndarray) -> int | float | tuple[int | float, ...]:
        value = self._foreground_value
        if np.issubdtype(pixels.dtype, np.integer):
            max_value = np.iinfo(pixels.dtype).max
            value = max_value * (value / 255.0)
        if pixels.ndim == 3:
            return tuple([value] * pixels.shape[-1])
        return value

    def _record_retouch_stroke(
        self, tool: str, x: int, y: int, radius: int, parameters: dict[str, object]
    ) -> None:
        if self._paint_stroke_before is not None:
            self._paint_stroke_operation = tool
            point = (float(x), float(y))
            if self._should_record_retouch_point(point):
                self._retouch_stroke_points.append(point)
            self._retouch_stroke_radius = float(radius)
            self._retouch_stroke_parameters = dict(parameters)
            return
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        stroke = RetouchStroke(
            image_node_id=source_node,
            tool=tool,
            points=[(float(x), float(y))],
            radius=float(radius),
            parameters=parameters,
        )
        self.project.retouch_strokes[stroke.id] = stroke

    def _should_record_retouch_point(self, point: tuple[float, float]) -> bool:
        if self._selected_tool in {"brush", "pencil", "erase"}:
            return True
        if not self._retouch_stroke_points:
            return True
        previous = self._retouch_stroke_points[-1]
        return (
            (point[0] - previous[0]) ** 2 + (point[1] - previous[1]) ** 2
            >= self._retouch_record_spacing_px**2
        )

    def _commit_batched_retouch_stroke(self) -> None:
        if not self._retouch_stroke_points or self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        stroke = RetouchStroke(
            image_node_id=source_node,
            tool=self._paint_stroke_operation or self._selected_tool,
            points=list(self._retouch_stroke_points),
            radius=self._retouch_stroke_radius,
            parameters=dict(self._retouch_stroke_parameters),
            layer_id=self._paint_stroke_layer_id,
        )
        self.project.retouch_strokes[stroke.id] = stroke

