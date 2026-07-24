"""Selection handling for the edit workspace."""

from __future__ import annotations

import numpy as np

from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.selection import (
    SelectionCombineMode,
    SelectionOptions,
    combine_mask_region,
    selection_shape_region,
)
from biopic.imaging.selection import (
    ellipse_mask as selection_ellipse_mask,
)
from biopic.imaging.selection import (
    polygon_mask as selection_polygon_mask,
)
from biopic.imaging.selection import (
    rectangle_mask as selection_rectangle_mask,
)
from biopic.models.editing import SelectionMask
from biopic.ui.workspace_helpers.common import (
    coerce_polygon_points as _coerce_polygon_points,
)
from biopic.ui.workspace_helpers.common import (
    coverage_bounds as _coverage_bounds,
)
from biopic.ui.workspace_helpers.paint import (
    fuzzy_selection_region as _fuzzy_selection_region,
)


class EditSelectionMixin:
    def _selection_options_changed(self, *_args: object) -> None:
        """Update active selection generation options from the tool panel."""
        self._selection_options = SelectionOptions(
            mode=SelectionCombineMode(str(self.selection_mode_combo.currentData())),
            antialias=bool(self.selection_antialias_check.isChecked()),
            feather=bool(self.selection_feather_check.isChecked()),
            feather_radius_px=(
                float(self.selection_feather_radius.value())
                if self.selection_feather_check.isChecked()
                else 0.0
            ),
        )

    def _refresh_selection_options_visibility(self) -> None:
        self.selection_options_box.setVisible(
            self._selected_tool in {"rectangle_select", "ellipse_select", "free_select"}
        )

    def _load_active_selection(self) -> None:
        """Load persisted document selection for the current source node."""
        if self._current_source_node_id is None or self._current_pixels is None:
            return
        for selection in self.project.selections.values():
            if selection.source_node_id != self._current_source_node_id:
                continue
            coverage = selection.coverage_pixels()
            if coverage is None or coverage.shape != self._current_pixels.shape[:2]:
                continue
            self._selection_coverage = np.clip(coverage.astype(np.float32, copy=False), 0.0, 1.0)
            self._selection_revision = int(selection.revision)
            self._selection_rect = _coverage_bounds(self._selection_coverage)
            self._selection_shape = "mask"
            return

    def _persist_active_selection(self) -> None:
        """Persist the current document-level selection coverage."""
        self._selection_persist_pending = False
        if self._current_source_node_id is None or self._current_pixels is None:
            return
        coverage = self._selection_coverage
        if coverage is None:
            return
        existing = next(
            (
                selection
                for selection in self.project.selections.values()
                if selection.source_node_id == self._current_source_node_id
            ),
            None,
        )
        if existing is None:
            existing = SelectionMask(
                width=int(self._current_pixels.shape[1]),
                height=int(self._current_pixels.shape[0]),
                mask_node_id=f"selection:{self._current_source_node_id}",
                source_node_id=self._current_source_node_id,
            )
            self.project.selections[existing.id] = existing
        existing.width = int(self._current_pixels.shape[1])
        existing.height = int(self._current_pixels.shape[0])
        existing.feather_radius = float(self._selection_options.feather_radius_px)
        existing.revision = self._selection_revision
        existing.set_coverage_pixels(coverage)
        self.project.touch()

    def _schedule_selection_persistence(self) -> None:
        self._selection_persist_pending = True
        self.project.touch()
        if self.editApplied is not None:
            self.editApplied()
        self._selection_persist_timer.start()

    def _flush_pending_selection_persistence(self) -> None:
        if not self._selection_persist_pending:
            return
        self._persist_active_selection()

    def _selection_mask(self) -> np.ndarray | None:
        coverage = self._selection_coverage_mask()
        if coverage is None:
            return None
        return coverage > 0.0

    def _selection_coverage_mask(self) -> np.ndarray | None:
        if self._current_pixels is None:
            return None
        if self._selection_coverage is not None:
            if self._selection_coverage.shape == self._current_pixels.shape[:2]:
                return self._selection_coverage
            self._selection_coverage = None
        if self._selection_rect is None:
            return None
        return self._rasterize_selection_shape(
            self._selection_shape,
            self._selection_rect,
            self._selection_polygon,
        )

    def _rasterize_selection_shape(
        self,
        kind: str,
        rect: tuple[int, int, int, int],
        polygon: list[tuple[float, float]] | None = None,
    ) -> np.ndarray:
        if self._current_pixels is None:
            return np.zeros((1, 1), dtype=np.float32)
        shape = self._current_pixels.shape[:2]
        options = self._selection_options
        feather = options.feather_radius_px if options.feather else 0.0
        if kind == "ellipse":
            return selection_ellipse_mask(
                shape,
                rect,
                antialias=options.antialias,
                feather_radius_px=feather,
            )
        if kind == "free" and polygon and len(polygon) >= 3:
            return selection_polygon_mask(
                shape,
                polygon,
                antialias=options.antialias,
                feather_radius_px=feather,
            )
        return selection_rectangle_mask(
            shape,
            rect,
            antialias=options.antialias,
            feather_radius_px=feather,
        )

    def _tool_rectangle_selected(self, x: int, y: int, width: int, height: int) -> None:
        if self._current_pixels is None:
            return
        image_height, image_width = self._current_pixels.shape[:2]
        x = max(0, min(x, image_width - 1))
        y = max(0, min(y, image_height - 1))
        width = max(1, min(width, image_width - x))
        height = max(1, min(height, image_height - y))
        if self._selected_tool == "crop":
            self._selection_rect = (x, y, width, height)
            result = apply_edit_operation(self._current_pixels, "crop", self._parameters("crop"))
            self._commit_edit_result(result, "crop", self._parameters("crop"))
        elif self._selected_tool == "measure":
            self._selection_rect = (x, y, width, height)
            self.history.appendPlainText(f"measure.selection: {width} x {height}px")
        elif self._selected_tool not in {"rectangle_select", "ellipse_select"}:
            self._commit_selection_shape("rectangle", (x, y, width, height), [])

    def _tool_selection_completed(
        self,
        kind: str,
        x: int,
        y: int,
        width: int,
        height: int,
        polygon: object,
    ) -> None:
        if self._current_pixels is None:
            return
        if self._selected_tool not in {"rectangle_select", "ellipse_select", "free_select"}:
            return
        image_height, image_width = self._current_pixels.shape[:2]
        x = max(0, min(x, image_width - 1))
        y = max(0, min(y, image_height - 1))
        width = max(1, min(width, image_width - x))
        height = max(1, min(height, image_height - y))
        self._commit_selection_shape(kind, (x, y, width, height), _coerce_polygon_points(polygon))

    def _commit_selection_shape(
        self,
        kind: str,
        rect: tuple[int, int, int, int],
        polygon: list[tuple[float, float]],
    ) -> None:
        """Rasterize and combine a preliminary selection into the active mask."""
        if self._current_pixels is None:
            return
        shape = kind if kind in {"rectangle", "ellipse", "free"} else "rectangle"
        image_shape = self._current_pixels.shape[:2]
        options = self._selection_options
        feather = options.feather_radius_px if options.feather else 0.0
        region = selection_shape_region(
            image_shape,
            shape,
            rect,
            polygon,
            antialias=options.antialias,
            feather_radius_px=feather,
        )
        if region is None:
            return
        region_rect, region_coverage = region
        self._selection_coverage = combine_mask_region(
            self._selection_coverage,
            region_coverage,
            region_rect,
            image_shape,
            options.mode,
            copy_existing=False,
        )
        self._selection_revision += 1
        bounds = _coverage_bounds(self._selection_coverage)
        self._selection_rect = bounds
        self._selection_shape = shape
        self._selection_polygon = polygon if shape == "free" else []
        self._schedule_selection_persistence()
        if bounds is None:
            self.canvas.set_selection_rect(None)
        self.history.appendPlainText(
            f"{shape}-select {self._selection_options.mode.value}: {rect[2]} x {rect[3]}px"
        )

    def _fuzzy_select_from_point(self, x: int, y: int) -> None:
        """Select a contiguous region with similar rendered color."""
        if self._current_pixels is None:
            return
        region = _fuzzy_selection_region(
            self._current_pixels,
            x,
            y,
            tolerance=max(0.0, float(self.primary_spin.value())),
        )
        if region is None:
            return
        rect, region_coverage = region
        self._selection_coverage = combine_mask_region(
            self._selection_coverage,
            region_coverage,
            rect,
            self._current_pixels.shape[:2],
            self._selection_options.mode,
            copy_existing=False,
        )
        self._selection_revision += 1
        bounds = _coverage_bounds(self._selection_coverage)
        self._selection_shape = "mask"
        self._selection_rect = bounds
        self._selection_polygon = []
        self._schedule_selection_persistence()
        self.canvas.set_selection_rect(rect)
        self.history.appendPlainText(
            f"fuzzy-select {self._selection_options.mode.value}: "
            f"{rect[2]} x {rect[3]}px at {x}, {y}"
        )

