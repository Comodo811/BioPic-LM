"""Paint, retouch, and layer-move interactions for the edit workspace."""

from __future__ import annotations

from time import perf_counter
from uuid import uuid4

import numpy as np
from PySide6.QtGui import QColor

from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.layer_buffers import (
    ensure_unique_layer_buffers,
    layer_alpha_buffer,
    layer_content_buffer,
    set_layer_buffers,
)
from biopic.imaging.paint_engine import PaintCoordinates, PaintWorkItem, PaintWorkType
from biopic.imaging.tiles import TilePaintSession
from biopic.models.editing import (
    EditLayer,
    LayerContentKind,
    LayerLock,
    RetouchStroke,
    pixels_to_payload,
)
from biopic.native.stroke_backend import paint_disks, paint_stroke
from biopic.ui.workspace_helpers.paint import (
    deduplicate_points as _deduplicate_points,
)
from biopic.ui.workspace_helpers.paint import (
    display_scalar_value as _display_scalar_value,
)
from biopic.ui.workspace_helpers.paint import (
    dodge_burn_disk as _dodge_burn_disk,
)
from biopic.ui.workspace_helpers.paint import (
    interpolated_points as _interpolated_points,
)
from biopic.ui.workspace_helpers.paint import (
    owned_paint_buffer as _owned_paint_buffer,
)
from biopic.ui.workspace_helpers.paint import (
    paint_disk as _paint_disk,
)
from biopic.ui.workspace_helpers.paint import (
    rounded_point as _rounded_point,
)
from biopic.ui.workspace_helpers.paint import (
    smudge_disk as _smudge_disk,
)
from biopic.ui.workspaces.edit_constants import (
    TRANSFORM_TOOL_OPERATIONS as _TRANSFORM_TOOL_OPERATIONS,
)
from biopic.ui.workspaces.edit_paint_retouch import EditPaintRetouchMixin


class EditPaintMixin(EditPaintRetouchMixin):
    def _tool_point_clicked(self, x: int, y: int) -> None:
        if self._should_queue_paint_point():
            self._enqueue_paint_point(float(x), float(y))
            return
        self._apply_tool_point_clicked(x, y)

    def _paint_point_moved(self, x: float, y: float) -> None:
        if self._should_queue_paint_point():
            self._update_queued_paint_tail_preview(x, y)
            self._enqueue_paint_point(x, y)
            return
        if self._should_vector_preview_paint_point():
            self._record_vector_preview_paint_point(x, y)
            return
        self._apply_tool_point_clicked(int(round(x)), int(round(y)))

    def _should_vector_preview_paint_point(self) -> bool:
        return (
            self._paint_stroke_before is not None
            and self._selected_tool in {"brush", "pencil", "erase"}
        )

    def _record_vector_preview_paint_point(self, x: float, y: float) -> None:
        radius = max(1, int(round(self.primary_spin.value())))
        paint_radius = 1 if self._selected_tool == "pencil" else radius
        self._paint_live_points.append((x, y))
        points = self._vector_preview_segment_points((x, y), paint_radius)
        self.canvas.extend_paint_preview(
            points,
            paint_radius,
            self._stroke_preview_color(self._selected_tool),
        )

    def _vector_preview_segment_points(
        self,
        point: tuple[float, float],
        radius: int,
    ) -> list[tuple[int, int]]:
        if len(self._paint_live_points) < 2:
            return [_rounded_point(point)]
        previous = self._paint_live_points[-2]
        if self._selected_tool == "pencil":
            return _interpolated_points(previous, point, radius)
        return self._gimp_paint_core.motion(PaintCoordinates(point[0], point[1]), radius)

    def _should_queue_paint_point(self) -> bool:
        return (
            not self._flushing_paint_queue
            and self._paint_stroke_before is not None
            and self._selected_tool in {"brush", "pencil", "erase"}
        )

    def _enqueue_paint_point(self, x: float, y: float) -> None:
        if self._paint_stroke_id is None:
            self._paint_stroke_id = str(uuid4())
        self._paint_sequence += 1
        item = PaintWorkItem(
            PaintWorkType.INTERPOLATE,
            self._paint_stroke_id,
            PaintCoordinates(x, y, timestamp=self._paint_sequence),
            self._paint_sequence,
        )
        self._paint_work_queue.push_motion(item)
        self._queued_paint_points = []
        if not self._paint_flush_timer.isActive():
            self._paint_flush_timer.start()

    def _update_queued_paint_tail_preview(self, x: float, y: float) -> None:
        radius = max(1, int(round(self.primary_spin.value())))
        paint_radius = 1 if self._selected_tool == "pencil" else radius
        point = (x, y)
        previous = self._last_tool_point
        if previous is None:
            points = [_rounded_point(point)]
        elif self._selected_tool == "pencil":
            points = _interpolated_points(previous, point, paint_radius)
        else:
            points = _interpolated_points(previous, point, max(1, paint_radius // 2))
        self.canvas.clear_paint_preview()
        self.canvas.extend_paint_preview(
            points,
            paint_radius,
            self._stroke_preview_color(self._selected_tool),
        )

    def _apply_tool_point_clicked(self, x: int, y: int) -> None:
        if self._current_pixels is None:
            return
        if self._pending_white_balance_spot_sample_size is not None:
            self._apply_white_balance_spot_from_point(x, y)
            return
        if self._selected_tool == "zoom":
            return
        if self._selected_tool in _TRANSFORM_TOOL_OPERATIONS:
            operation = _TRANSFORM_TOOL_OPERATIONS[self._selected_tool]
            result = apply_edit_operation(
                self._current_pixels,
                operation,
                self._parameters(operation),
            )
            self._commit_edit_result(result, operation, {"tool": self._selected_tool})
            return
        if self._selected_tool == "color_picker":
            value = self._current_pixels[y, x]
            self.history.appendPlainText(f"color-picker: {x}, {y} -> {np.asarray(value).tolist()}")
            picked = _display_scalar_value(value, self._current_pixels.dtype)
            self._foreground_value = picked
            self.secondary_spin.blockSignals(True)
            self.secondary_spin.setValue(picked)
            self.secondary_spin.blockSignals(False)
            self._update_foreground_swatch()
            return
        if self._selected_tool == "fuzzy_select":
            self._fuzzy_select_from_point(x, y)
            return
        layer = self._editable_active_layer()
        if layer is None:
            return
        if self._selected_tool in {"brush", "pencil", "erase"}:
            self._apply_paint_tool_point(float(x), float(y))
            return
        self._apply_non_paint_tool_point(layer, x, y)

    def _apply_non_paint_tool_point(self, layer: EditLayer, x: int, y: int) -> None:
        single_point_tile_paint = False
        clear_single_point_tile_paint = False
        if (
            self._selected_tool in {"clone", "heal"}
            and self._paint_tile_session is None
            and self._base_pixels is not None
        ):
            self._begin_tile_paint_session(layer)
            single_point_tile_paint = self._paint_stroke_before is not None
        before = self._paint_stroke_before or self._snapshot_edit_state()
        if self._paint_tile_session is None:
            result = (
                self._paint_stroke_content
                if self._paint_stroke_layer_id == layer.id
                and self._paint_stroke_content is not None
                else self._layer_content_for_edit(layer)
            )
            alpha = (
                self._paint_stroke_alpha
                if self._paint_stroke_layer_id == layer.id and self._paint_stroke_alpha is not None
                else self._layer_alpha_for_edit(layer)
            )
        else:
            result = self._paint_tile_session.base_pixels
            alpha = np.empty(self._paint_tile_session.base_pixels.shape[:2], dtype=np.float32)
        radius = max(1, int(round(self.primary_spin.value())))
        if self._selected_tool in {"clone", "heal"}:
            if self._clone_source_point is None:
                self._status("Ctrl-click a source first.")
                return
            if self._clone_stroke_anchor is None:
                self._clone_stroke_anchor = (x, y)
            if self._paint_tile_session is not None:
                source_content, source_alpha = self._clone_tile_source_buffers(layer)
                source_offset = self._clone_source_offset()
                points = self._linear_stroke_points((x, y), radius)
                if self._selected_tool == "heal":
                    dirty_rect = self._paint_tile_session.heal_content_and_alpha(
                        points,
                        radius,
                        source_content,
                        source_alpha,
                        source_offset,
                        selection_rect=self._selection_rect,
                        selection_shape=self._selection_shape,
                        selection_mask=self._selection_coverage_mask(),
                    )
                else:
                    dirty_rect = self._paint_tile_session.clone_content_and_alpha(
                        points,
                        radius,
                        source_content,
                        source_alpha,
                        source_offset,
                        selection_rect=self._selection_rect,
                        selection_shape=self._selection_shape,
                        selection_mask=self._selection_coverage_mask(),
                    )
                self._stage_tile_paint_preview(layer, self._selected_tool, points, radius, dirty_rect)
            else:
                source_content, source_alpha = self._clone_source_buffers(result, alpha)
                if self._selected_tool == "heal":
                    self._heal_disk_from_source(
                        result,
                        alpha,
                        source_content,
                        source_alpha,
                        x,
                        y,
                        radius,
                    )
                else:
                    self._clone_disk_from_source(
                        result,
                        alpha,
                        source_content,
                        source_alpha,
                        x,
                        y,
                        radius,
                    )
                self._stage_paint_edit(
                    layer,
                    result,
                    alpha,
                    self._selected_tool,
                    dirty_rect=self._stroke_dirty_rect([(x, y)], radius),
                    preview_points=[(x, y)],
                    preview_radius=radius,
                )
            self._record_retouch_stroke(
                self._selected_tool,
                x,
                y,
                radius,
                {
                    "source": self._clone_source_point,
                    "anchor": self._clone_stroke_anchor,
                },
            )
            if single_point_tile_paint or self._paint_stroke_before is None:
                self._commit_staged_paint(layer, self._selected_tool, before)
                self._commit_batched_retouch_stroke()
                clear_single_point_tile_paint = single_point_tile_paint
        elif self._selected_tool == "smudge":
            previous = _rounded_point(self._last_tool_point) if self._last_tool_point else None
            _smudge_disk(result, x, y, radius, previous)
            _paint_disk(alpha, x, y, radius, 1.0)
            self._stage_paint_edit(
                layer,
                result,
                alpha,
                "smudge",
                dirty_rect=self._stroke_dirty_rect([(x, y)], radius),
                preview_points=[(x, y)],
                preview_radius=radius,
            )
            self._record_retouch_stroke("smudge", x, y, radius, {})
            if self._paint_stroke_before is None:
                self._commit_staged_paint(layer, "smudge", before)
        elif self._selected_tool == "dodge_burn":
            _dodge_burn_disk(result, x, y, radius, amount=0.1)
            _paint_disk(alpha, x, y, radius, 1.0)
            self._stage_paint_edit(
                layer,
                result,
                alpha,
                "dodge_burn",
                dirty_rect=self._stroke_dirty_rect([(x, y)], radius),
                preview_points=[(x, y)],
                preview_radius=radius,
            )
            self._record_retouch_stroke("dodge_burn", x, y, radius, {})
            if self._paint_stroke_before is None:
                self._commit_staged_paint(layer, "dodge_burn", before)
        elif self._selected_tool in {"bucket_fill", "gradient"}:
            value = self._paint_value(result)
            self._fill_constrained(result, value)
            self._fill_constrained(alpha, 1.0)
            self._stage_paint_edit(layer, result, alpha, self._selected_tool)
            self._record_retouch_stroke(self._selected_tool, x, y, radius, {})
            if self._paint_stroke_before is None:
                self._commit_staged_paint(layer, self._selected_tool, before)
        elif self._selected_tool == "text":
            self.add_empty_layer()
            self.history.appendPlainText(f"text: {self.tool_text.text() or 'Text'} at {x}, {y}")
        if self._paint_stroke_before is None or clear_single_point_tile_paint:
            self._clear_paint_stroke()
        self._last_tool_point = (x, y)

    def _apply_paint_tool_point(self, x: float, y: float) -> None:
        if self._current_pixels is None:
            return
        layer = self._editable_active_layer()
        if layer is None:
            return
        single_point_tile_paint = False
        clear_single_point_tile_paint = False
        if self._paint_tile_session is None and self._base_pixels is not None:
            self._begin_tile_paint_session(layer)
            single_point_tile_paint = self._paint_stroke_before is not None
        before = self._paint_stroke_before or self._snapshot_edit_state()
        radius = max(1, int(round(self.primary_spin.value())))
        if self._selected_tool in {"brush", "pencil"}:
            paint_radius = 1 if self._selected_tool == "pencil" else radius
            points = (
                self._linear_stroke_points((x, y), paint_radius)
                if self._selected_tool == "pencil"
                else self._smoothed_stroke_points((x, y), paint_radius)
            )
            if self._paint_tile_session is None:
                return
            value = self._paint_value(self._paint_tile_session.base_pixels)
            dirty_rect = self._paint_tile_session.paint_content_and_alpha(
                points,
                paint_radius,
                value,
                alpha_value=1.0,
                selection_rect=self._selection_rect,
                selection_shape=self._selection_shape,
                selection_mask=self._selection_coverage_mask(),
            )
            self._stage_tile_paint_preview(
                layer, self._selected_tool, points, paint_radius, dirty_rect
            )
            self._record_retouch_stroke(
                self._selected_tool,
                int(round(x)),
                int(round(y)),
                radius,
                {"value": self.secondary_spin.value()},
            )
            if single_point_tile_paint or self._paint_stroke_before is None:
                self._commit_staged_paint(layer, self._selected_tool, before)
                self._commit_batched_retouch_stroke()
                clear_single_point_tile_paint = single_point_tile_paint
        elif self._selected_tool == "erase":
            points = self._smoothed_stroke_points((x, y), radius)
            if self._paint_tile_session is None:
                return
            dirty_rect = self._paint_tile_session.paint(
                points,
                radius,
                0.0,
                paint_alpha=True,
                alpha_value=0.0,
                selection_rect=self._selection_rect,
                selection_shape=self._selection_shape,
                selection_mask=self._selection_coverage_mask(),
            )
            self._stage_tile_paint_preview(layer, "erase", points, radius, dirty_rect)
            self._record_retouch_stroke("erase", int(round(x)), int(round(y)), radius, {})
            if single_point_tile_paint or self._paint_stroke_before is None:
                self._commit_staged_paint(layer, "erase", before)
                self._commit_batched_retouch_stroke()
                clear_single_point_tile_paint = single_point_tile_paint
        if self._paint_stroke_before is None or clear_single_point_tile_paint:
            self._clear_paint_stroke()
        self._last_tool_point = (x, y)

    def _flush_queued_paint_points(self) -> None:
        if self._paint_work_queue.depth() == 0:
            self._queued_paint_points = []
            return
        self._flushing_paint_queue = True
        try:
            processed = 0
            deadline = perf_counter() + self._paint_flush_budget_seconds
            while processed < self._paint_flush_budget_points:
                item = self._paint_work_queue.pop_nowait()
                if item is None:
                    break
                if item.type is PaintWorkType.FINISH_BARRIER:
                    self._paint_finish_barrier_seen = True
                    break
                if item.type is not PaintWorkType.INTERPOLATE:
                    continue
                if self._paint_stroke_id is not None and item.stroke != self._paint_stroke_id:
                    continue
                self._apply_paint_tool_point(item.coordinates.x, item.coordinates.y)
                processed += 1
                if perf_counter() >= deadline:
                    break
        finally:
            self._flushing_paint_queue = False
        self._queued_paint_points = []
        if self._paint_work_queue.depth() and not self._paint_flush_timer.isActive():
            self._paint_flush_timer.start()
        if (
            self._paint_work_queue.depth() == 0
            and not self._pending_paint_display_region.rectangles()
        ):
            self._paint_flush_timer.stop()

    def _paint_timer_tick(self) -> None:
        self._flush_queued_paint_points()
        self._flush_paint_display_regions()
        if (
            self._paint_work_queue.depth() == 0
            and not self._pending_paint_display_region.rectangles()
        ):
            self._paint_flush_timer.stop()

    def _flush_all_queued_paint_points(self) -> None:
        if self._paint_live_points:
            return
        while self._paint_work_queue.depth():
            self._flush_queued_paint_points()
        self._flush_paint_display_regions()

    def _editable_active_layer(self) -> EditLayer | None:
        layer = self._active_layer()
        if layer is None:
            self._status("Select an editable layer first.")
            return None
        if layer.locked or LayerLock.PIXELS in layer.lock_flags:
            self._status("Cannot edit a locked layer.")
            return None
        return layer

    def _active_layer(self) -> EditLayer | None:
        if self._current_source_node_id is None:
            return None
        layer_id = self.project.active_edit_layers.get(self._current_source_node_id)
        if layer_id is None:
            layer_id = self._current_layer_id
        return self.project.edit_layers.get(layer_id) if layer_id is not None else None

    def _layer_content_for_edit(self, layer: EditLayer) -> np.ndarray:
        live_content = layer_content_buffer(layer.id)
        if live_content is not None:
            return live_content.copy()
        if layer.content_kind is LayerContentKind.SOURCE:
            if self._base_pixels is None:
                raise ValueError("No base image is loaded")
            layer.content_kind = LayerContentKind.RASTER
            alpha = np.ones(self._base_pixels.shape[:2], dtype=np.float32)
            set_layer_buffers(layer.id, self._base_pixels.copy(), alpha)
            return self._base_pixels.copy()
        content = layer.content_pixels()
        if content is None:
            if self._base_pixels is None:
                raise ValueError("No base image is loaded")
            content = np.zeros_like(self._base_pixels)
            layer.content_kind = LayerContentKind.RASTER
        return content.copy()

    def _layer_alpha_for_edit(self, layer: EditLayer) -> np.ndarray:
        alpha = layer_alpha_buffer(layer.id)
        if alpha is None:
            alpha = layer.alpha_pixels()
        if alpha is None:
            if self._base_pixels is None:
                raise ValueError("No base image is loaded")
            alpha = np.zeros(self._base_pixels.shape[:2], dtype=np.float32)
        return alpha.astype(np.float32, copy=True)

    def _layer_arrays_for_tile_edit(
        self, layer: EditLayer
    ) -> tuple[np.ndarray | None, np.ndarray | None]:
        if self._base_pixels is None:
            raise ValueError("No base image is loaded")
        content = layer_content_buffer(layer.id)
        alpha = layer_alpha_buffer(layer.id)
        if content is None:
            content = layer.content_pixels()
        if alpha is None:
            alpha = layer.alpha_pixels()
        if layer.content_kind is LayerContentKind.SOURCE and content is None:
            content = self._base_pixels
            alpha = np.ones(self._base_pixels.shape[:2], dtype=np.float32)
        elif content is None:
            content = np.zeros_like(self._base_pixels)
            alpha = np.zeros(self._base_pixels.shape[:2], dtype=np.float32)
        elif alpha is None:
            alpha = np.ones(self._base_pixels.shape[:2], dtype=np.float32)
        return content, alpha.astype(np.float32, copy=False)

    def _finish_layer_edit(self, operation: str, before: dict[str, object]) -> None:
        self._finish_command(operation, before)
        self._invalidate_edit_composite_cache()
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_history()
        self.canvas.refresh_display_tiles()
        if self.editApplied is not None:
            self.editApplied()

    def _finish_tile_paint_edit(
        self, layer: EditLayer, operation: str, before: dict[str, object]
    ) -> None:
        if self._paint_tile_session is None:
            return
        patches = self._paint_tile_session.patches()
        if not patches:
            return
        dirty_rect = self._paint_tile_session.dirty_rect()
        dirty_rects = self._paint_tile_session.dirty_rectangles()
        layer.bump_generation()
        self.project.touch()
        self.project.undo_stack.append(
            {
                "kind": "tile_paint",
                "description": operation,
                "layer_id": layer.id,
                "before_content_kind": before.get(
                    "before_content_kind", LayerContentKind.RASTER.value
                ),
                "after_content_kind": layer.content_kind.value,
                "patches": [
                    {
                        "x": patch.x,
                        "y": patch.y,
                        "content_before": pixels_to_payload(patch.content_before),
                        "content_after": pixels_to_payload(patch.content_after),
                        "alpha_before": pixels_to_payload(patch.alpha_before),
                        "alpha_after": pixels_to_payload(patch.alpha_after),
                    }
                    for patch in patches
                ],
            }
        )
        self.project.redo_stack.clear()
        self.project.history.append({"operation": operation})
        self._refresh_projection_after_tile_paint(
            dirty_rects or ([dirty_rect] if dirty_rect is not None else []),
            update_canvas=not self._paint_preview_regions_published,
        )
        self._publish_committed_paint_pixels()
        self._refresh_layers()
        self._refresh_history()
        if self.editApplied is not None:
            self.editApplied()

    def _publish_committed_paint_pixels(self) -> None:
        if self._current_pixels is None:
            return
        self.canvas.clear_paint_preview()
        if self._paint_preview_regions_published:
            return
        self.canvas.set_pixels(self._current_pixels, "paint committed", fit=False)

    def _begin_paint_stroke(self) -> None:
        layer = self._editable_active_layer()
        if layer is None:
            return
        self._paint_work_queue.clear()
        self._paint_sequence = 0
        self._paint_stroke_id = str(uuid4())
        self._paint_finish_barrier_seen = False
        self._paint_corruption_event_count = 0
        self._queued_paint_points = []
        self._paint_stroke_layer_id = layer.id
        if self._selected_tool in {"brush", "pencil", "erase", "clone", "heal"} and self._base_pixels is not None:
            self._begin_tile_paint_session(layer)
        else:
            self._paint_stroke_before = self._snapshot_edit_state()
            self._paint_tile_session = None
            self._paint_stroke_content = self._layer_content_for_edit(layer)
            self._paint_stroke_alpha = self._layer_alpha_for_edit(layer)
        self._paint_stroke_preview = (
            _owned_paint_buffer(self._current_pixels)
            if self._current_pixels is not None
            else None
        )
        self._paint_stroke_operation = self._selected_tool
        self._paint_stroke_points = []
        self._gimp_paint_core.begin()
        self._last_live_preview_at = 0.0
        self._last_tool_point = None

    def _begin_tile_paint_session(self, layer: EditLayer) -> None:
        if self._base_pixels is None:
            return
        ensure_unique_layer_buffers(layer.id)
        self._paint_stroke_layer_id = layer.id
        self._paint_stroke_before = {
            "kind": "tile_paint",
            "layer_id": layer.id,
            "before_content_kind": layer.content_kind.value,
            "after_content_kind": LayerContentKind.RASTER.value,
        }
        content, alpha = self._layer_arrays_for_tile_edit(layer)
        self._paint_tile_session = TilePaintSession(self._base_pixels, content, alpha)
        self._paint_stroke_content = None
        self._paint_stroke_alpha = None

    def _finish_paint_stroke(self) -> None:
        if self._paint_live_points:
            self._paint_work_queue.clear()
            self._pending_paint_display_region.clear()
            self._commit_vector_preview_paint_stroke()
        if self._paint_stroke_id is not None and self._paint_work_queue.depth():
            self._paint_sequence += 1
            self._paint_work_queue.insert_finish_barrier(
                self._paint_stroke_id,
                self._paint_sequence,
            )
        self._flush_all_queued_paint_points()
        if (
            self._paint_stroke_before is None
            or self._paint_stroke_layer_id is None
            or (
                self._paint_tile_session is None
                and (self._paint_stroke_content is None or self._paint_stroke_alpha is None)
            )
        ):
            self._clear_paint_stroke()
            return
        layer = self.project.edit_layers.get(self._paint_stroke_layer_id)
        if layer is not None:
            self._commit_staged_paint(
                layer,
                self._paint_stroke_operation or self._selected_tool,
                self._paint_stroke_before,
            )
            self._commit_batched_retouch_stroke()
        self._clear_paint_stroke()

    def _commit_staged_paint(
        self,
        layer: EditLayer,
        operation: str,
        before: dict[str, object],
    ) -> None:
        if self._paint_tile_session is not None:
            self._paint_stroke_content, self._paint_stroke_alpha = (
                self._paint_tile_session.materialize()
            )
        if self._paint_stroke_content is None or self._paint_stroke_alpha is None:
            return
        self.canvas.clear_paint_preview()
        layer.content_kind = LayerContentKind.RASTER
        if self._paint_tile_session is not None and before.get("kind") == "tile_paint":
            set_layer_buffers(layer.id, self._paint_stroke_content, self._paint_stroke_alpha)
            self._finish_tile_paint_edit(layer, operation, before)
        else:
            layer.set_content_pixels(self._paint_stroke_content)
            layer.set_alpha_pixels(self._paint_stroke_alpha)
            set_layer_buffers(layer.id, self._paint_stroke_content, self._paint_stroke_alpha)
            self._finish_layer_edit(operation, before)

    def _commit_vector_preview_paint_stroke(self) -> None:
        if (
            self._paint_stroke_layer_id is None
            or self._paint_stroke_before is None
            or not self._paint_live_points
        ):
            return
        layer = self.project.edit_layers.get(self._paint_stroke_layer_id)
        if layer is None:
            return
        if self._paint_tile_session is None:
            self._begin_tile_paint_session(layer)
        if self._paint_tile_session is None:
            return
        radius = max(1, int(round(self.primary_spin.value())))
        paint_radius = 1 if self._selected_tool == "pencil" else radius
        points = self._raster_points_for_live_stroke(paint_radius)
        if not points:
            return
        if self._selected_tool in {"brush", "pencil"}:
            value = self._paint_value(self._paint_tile_session.base_pixels)
            self._paint_tile_session.paint_content_and_alpha(
                points,
                paint_radius,
                value,
                alpha_value=1.0,
                selection_rect=self._selection_rect,
                selection_shape=self._selection_shape,
            )
        elif self._selected_tool == "erase":
            self._paint_tile_session.paint(
                points,
                radius,
                0.0,
                paint_alpha=True,
                alpha_value=0.0,
                selection_rect=self._selection_rect,
                selection_shape=self._selection_shape,
            )

    def _raster_points_for_live_stroke(self, radius: int) -> list[tuple[int, int]]:
        points: list[tuple[int, int]] = []
        previous: tuple[float, float] | None = None
        for point in self._paint_live_points:
            if previous is None:
                points.append(_rounded_point(point))
            elif self._selected_tool == "pencil":
                points.extend(_interpolated_points(previous, point, radius))
            else:
                points.extend(_interpolated_points(previous, point, max(1, radius // 2)))
            previous = point
        return _deduplicate_points(points)

    def _clear_paint_stroke(self) -> None:
        self._paint_stroke_before = None
        self._paint_stroke_layer_id = None
        self._paint_stroke_content = None
        self._paint_stroke_alpha = None
        self._paint_stroke_preview = None
        self._paint_tile_session = None
        self._paint_stroke_operation = None
        self._paint_preview_layer_id = None
        self._paint_preview_regions_published = False
        self._paint_stroke_points = []
        self._paint_live_points = []
        self._gimp_paint_core.reset()
        self._clone_stroke_anchor = None
        self._clone_source_content = None
        self._clone_source_alpha = None
        self._retouch_stroke_points = []
        self._retouch_stroke_radius = 1.0
        self._retouch_stroke_parameters = {}
        self._queued_paint_points = []
        self._paint_work_queue.clear()
        self._paint_stroke_id = None
        self._paint_sequence = 0
        self._paint_finish_barrier_seen = False
        self._pending_paint_display_region.clear()
        self._flushing_paint_queue = False
        self._paint_flush_timer.stop()
        self._last_live_preview_at = 0.0
        self._last_tool_point = None
        self.canvas.clear_paint_preview()

    def _stroke_preview_color(self, operation: str) -> QColor:
        if operation == "erase":
            return QColor(255, 92, 92, 190)
        value = int(max(0, min(255, round(self._foreground_value))))
        return QColor(value, value, value, 220)

    def _linear_stroke_points(
        self,
        point: tuple[float, float],
        radius: int,
    ) -> list[tuple[int, int]]:
        previous = self._last_tool_point
        self._paint_stroke_points.append(point)
        if previous is None:
            return [_rounded_point(point)]
        return _interpolated_points(previous, point, radius)

    def _smoothed_stroke_points(
        self,
        point: tuple[float, float],
        radius: int,
    ) -> list[tuple[int, int]]:
        previous = self._last_tool_point
        self._paint_stroke_points.append(point)
        points = self._gimp_paint_core.motion(
            PaintCoordinates(point[0], point[1]),
            radius,
        )
        if previous is None:
            return points or [_rounded_point(point)]
        return _deduplicate_points([*points, *_interpolated_points(previous, point, radius)])

