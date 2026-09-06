"""Free-selection interaction helpers for the image canvas."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPainterPath, QPen

from biopic.ui.image_canvas_items import _SelectionHandleItem


class ImageCanvasSelectionMixin:
    def _update_drag_selection_preview(self, rect: QRectF) -> None:
        if self._tool_mode == "ellipse_select":
            path = QPainterPath()
            path.addEllipse(rect)
            self._selection_path_item.setPath(path)
            self._selection_path_item.setVisible(True)
            self._selection_shadow_item.setPath(path)
            self._set_selection_path_visible(True)
            return
        path = QPainterPath()
        path.addRect(rect)
        self._selection_path_item.setPath(path)
        self._selection_shadow_item.setPath(path)
        self._set_selection_path_visible(True)

    def _update_free_selection_preview(self, *, close: bool) -> None:
        if not self._free_selection_points:
            self._selection_path_item.setVisible(False)
            self._selection_shadow_item.setVisible(False)
            self._stop_selection_marching_ants_if_hidden()
            return
        path = QPainterPath(self._free_selection_points[0])
        for point in self._free_selection_points[1:]:
            path.lineTo(point)
        if (
            not close
            and self._free_selection_drawing
            and self._free_selection_hover is not None
            and len(self._free_selection_points) >= 1
        ):
            path.lineTo(self._free_selection_hover)
        if close and len(self._free_selection_points) > 2:
            path.closeSubpath()
        self._selection_path_item.setPath(path)
        self._selection_shadow_item.setPath(path)
        self._set_selection_path_visible(True)

    def _is_free_selection_close_hit(self, point: QPointF) -> bool:
        return (
            len(self._free_selection_points) >= 3
            and _distance_points(self._free_selection_points[0], point)
            <= self._free_selection_close_radius()
        )

    def _free_selection_close_radius(self) -> float:
        zoom = max(0.001, float(self.transform().m11()))
        return max(10.0, 22.0 / zoom)

    def _free_selection_sample_distance(self) -> float:
        zoom = max(0.001, float(self.transform().m11()))
        return max(0.6, 2.0 / zoom)

    def _append_free_selection_point(
        self, point: QPointF, *, minimum_distance: float
    ) -> None:
        if (
            not self._free_selection_points
            or _distance_points(self._free_selection_points[-1], point) >= minimum_distance
        ):
            self._free_selection_points.append(point)

    def _close_free_selection(self) -> None:
        if len(self._free_selection_points) < 3:
            return
        self._free_selection_drawing = False
        self._free_selection_closed = True
        self._free_selection_hover = None
        self._free_selection_press_point = None
        self._free_selection_press_started_new = False
        self._free_selection_dragging = False
        self._update_free_selection_preview(close=True)
        self._set_free_selection_handles(self._free_selection_points)

    def _commit_free_selection(self) -> None:
        if len(self._free_selection_points) < 3:
            return
        rect = _points_bounding_rect(self._free_selection_points)
        if rect.width() < 1 or rect.height() < 1:
            return
        polygon = [(float(p.x()), float(p.y())) for p in self._free_selection_points]
        self.selectionCompleted.emit(
            "free",
            int(rect.x()),
            int(rect.y()),
            int(rect.width()),
            int(rect.height()),
            polygon,
        )
        self._free_selection_closed = False
        self._clear_selection_handles()

    def commit_pending_free_selection(self) -> bool:
        """Commit an in-progress free selection before commands consume selection state."""
        if self._tool_mode != "free_select" or len(self._free_selection_points) < 3:
            return False
        if self._free_selection_drawing:
            self._close_free_selection()
        if self._free_selection_closed:
            self._commit_free_selection()
            return True
        return False

    def _reopen_free_selection(self) -> None:
        self._free_selection_closed = False
        self._free_selection_drawing = True
        self._free_selection_hover = (
            self._free_selection_points[-1] if self._free_selection_points else None
        )
        self._update_free_selection_preview(close=False)

    def _cancel_free_selection(self) -> None:
        self._free_selection_drawing = False
        self._free_selection_closed = False
        self._free_selection_hover = None
        self._free_selection_press_point = None
        self._free_selection_press_started_new = False
        self._free_selection_dragging = False
        self._free_selection_points = []
        self._clear_selection_handles()
        self.set_selection_rect(None)

    def _remove_last_free_selection_point(self) -> None:
        if not self._free_selection_points:
            return
        self._free_selection_points.pop()
        self._set_free_selection_handles(self._free_selection_points)
        if not self._free_selection_points:
            self._cancel_free_selection()
            return
        self._free_selection_hover = self._free_selection_points[-1]
        self._update_free_selection_preview(close=False)

    def _set_free_selection_handles(self, points: list[QPointF]) -> None:
        self._clear_selection_handles()
        for index, point in self._visible_free_selection_handle_points(points):
            handle = _SelectionHandleItem(self, index, point)
            self._selection_handles.append(handle)
            self._scene.addItem(handle)

    def _visible_free_selection_handle_points(
        self, points: list[QPointF]
    ) -> list[tuple[int, QPointF]]:
        if len(points) <= 2:
            return list(enumerate(points))
        zoom = max(0.001, float(self.transform().m11()))
        minimum_spacing = max(10.0, 24.0 / zoom)
        visible: list[tuple[int, QPointF]] = [(0, points[0])]
        last_visible = points[0]
        for index, point in enumerate(points[1:-1], start=1):
            if _distance_points(last_visible, point) >= minimum_spacing:
                visible.append((index, point))
                last_visible = point
        if _distance_points(visible[-1][1], points[-1]) >= minimum_spacing * 0.5:
            visible.append((len(points) - 1, points[-1]))
        return visible

    def _lasso_handle_at(self, view_pos: object) -> _SelectionHandleItem | None:
        item = self.itemAt(view_pos)
        while item is not None:
            if isinstance(item, _SelectionHandleItem):
                return item
            item = item.parentItem()
        return None

    def _clear_selection_handles(self) -> None:
        for handle in self._selection_handles:
            self._scene.removeItem(handle)
        self._selection_handles.clear()
        self._lasso_drag_snapshot = None

    def _selection_handle_drag_started(self, index: int) -> None:
        if not 0 <= index < len(self._free_selection_points):
            self._lasso_drag_snapshot = None
            return
        points = list(self._free_selection_points)
        visible_indices = [
            visible_index
            for visible_index, _point in self._visible_free_selection_handle_points(points)
        ]
        if index not in visible_indices:
            visible_indices.append(index)
            visible_indices.sort()
        self._lasso_drag_snapshot = {
            "index": index,
            "points": points,
            "visible_indices": visible_indices,
            "closed": self._free_selection_closed,
        }

    def _selection_handle_moved(self, index: int, point: QPointF) -> None:
        if not 0 <= index < len(self._free_selection_points):
            return
        snapshot = getattr(self, "_lasso_drag_snapshot", None)
        if isinstance(snapshot, dict) and snapshot.get("index") == index:
            original = list(snapshot.get("points", []))
            visible_indices = list(snapshot.get("visible_indices", []))
            closed = bool(snapshot.get("closed", self._free_selection_closed))
            if not 0 <= index < len(original):
                return
            old_point = original[index]
        else:
            original = list(self._free_selection_points)
            visible_indices = [
                visible_index
                for visible_index, _point in self._visible_free_selection_handle_points(original)
            ]
            closed = self._free_selection_closed
            old_point = original[index]
        delta = QPointF(point.x() - old_point.x(), point.y() - old_point.y())
        if abs(delta.x()) < 1e-6 and abs(delta.y()) < 1e-6:
            return
        self._move_lasso_handle_neighborhood(index, point, delta, original, visible_indices, closed)
        self._update_free_selection_preview(close=True)

    def _selection_handle_released(self) -> None:
        if len(self._free_selection_points) < 3:
            return
        if self._free_selection_closed:
            self._set_free_selection_handles(self._free_selection_points)
            self._update_free_selection_preview(close=True)
            self._lasso_drag_snapshot = None
            return
        rect = _points_bounding_rect(self._free_selection_points)
        if rect.width() < 1 or rect.height() < 1:
            return
        polygon = [(float(p.x()), float(p.y())) for p in self._free_selection_points]
        self.selectionCompleted.emit(
            "free",
            int(rect.x()),
            int(rect.y()),
            int(rect.width()),
            int(rect.height()),
            polygon,
        )
        self._lasso_drag_snapshot = None

    def _move_lasso_handle_neighborhood(
        self,
        index: int,
        point: QPointF,
        delta: QPointF,
        original: list[QPointF],
        visible_indices: list[int],
        closed: bool,
    ) -> None:
        """Move the visible handle and bend adjacent hidden freehand samples with it."""
        if index not in visible_indices:
            visible_indices.append(index)
            visible_indices.sort()
        previous_index = _previous_visible_lasso_index(
            visible_indices,
            index,
            len(original),
            closed=closed,
        )
        next_index = _next_visible_lasso_index(
            visible_indices,
            index,
            len(original),
            closed=closed,
        )
        updated = list(original)
        if previous_index is not None:
            self._blend_lasso_handle_delta(
                updated,
                original,
                previous_index,
                index,
                delta,
                increasing=True,
            )
        if next_index is not None:
            self._blend_lasso_handle_delta(
                updated,
                original,
                index,
                next_index,
                delta,
                increasing=False,
            )
        updated[index] = point
        self._free_selection_points = updated

    def _blend_lasso_handle_delta(
        self,
        updated: list[QPointF],
        original: list[QPointF],
        start_index: int,
        end_index: int,
        delta: QPointF,
        *,
        increasing: bool,
    ) -> None:
        sequence = _lasso_index_sequence(start_index, end_index, len(original))
        if len(sequence) <= 2:
            return
        denominator = float(len(sequence) - 1)
        for offset, point_index in enumerate(sequence[1:-1], start=1):
            t = offset / denominator
            weight = t if increasing else 1.0 - t
            source = original[point_index]
            updated[point_index] = QPointF(
                source.x() + delta.x() * weight,
                source.y() + delta.y() * weight,
            )

    def _closed_free_selection_contains(self, point: QPointF) -> bool:
        if len(self._free_selection_points) < 3:
            return False
        path = QPainterPath(self._free_selection_points[0])
        for item in self._free_selection_points[1:]:
            path.lineTo(item)
        path.closeSubpath()
        return path.contains(point)

    def _set_selection_path_visible(self, visible: bool) -> None:
        self._selection_item.setVisible(False)
        self._selection_path_item.setVisible(visible)
        self._selection_shadow_item.setVisible(visible)
        if visible:
            self._selection_path_item.setZValue(15.1)
            self._selection_shadow_item.setZValue(15.0)
            if not self._selection_timer.isActive():
                self._selection_timer.start()
        else:
            self._stop_selection_marching_ants_if_hidden()

    def _advance_selection_marching_ants(self) -> None:
        self._selection_dash_offset = (self._selection_dash_offset + 1.0) % 12.0
        self._update_selection_pens()

    def _update_selection_pens(self) -> None:
        shadow_pen = QPen(QColor("#000000"), 1.0)
        shadow_pen.setCosmetic(True)
        shadow_pen.setDashPattern([4.0, 4.0])
        shadow_pen.setDashOffset(self._selection_dash_offset)
        light_pen = QPen(QColor("#ffffff"), 1.0)
        light_pen.setCosmetic(True)
        light_pen.setDashPattern([4.0, 4.0])
        light_pen.setDashOffset(self._selection_dash_offset + 4.0)
        self._selection_shadow_item.setPen(shadow_pen)
        self._selection_path_item.setPen(light_pen)

    def _stop_selection_marching_ants_if_hidden(self) -> None:
        if (
            not self._selection_path_item.isVisible()
            and not self._selection_shadow_item.isVisible()
            and self._selection_timer.isActive()
        ):
            self._selection_timer.stop()



def _distance_points(a: QPointF, b: QPointF) -> float:
    dx = float(a.x() - b.x())
    dy = float(a.y() - b.y())
    return (dx * dx + dy * dy) ** 0.5


def _points_bounding_rect(points: list[QPointF]) -> QRectF:
    if not points:
        return QRectF()
    xs = [float(point.x()) for point in points]
    ys = [float(point.y()) for point in points]
    x0 = min(xs)
    y0 = min(ys)
    return QRectF(x0, y0, max(xs) - x0, max(ys) - y0)


def _previous_visible_lasso_index(
    visible_indices: list[int],
    index: int,
    point_count: int,
    *,
    closed: bool,
) -> int | None:
    before = [item for item in visible_indices if item < index]
    if before:
        return before[-1]
    if closed and visible_indices and point_count > 1:
        return visible_indices[-1]
    return None


def _next_visible_lasso_index(
    visible_indices: list[int],
    index: int,
    point_count: int,
    *,
    closed: bool,
) -> int | None:
    after = [item for item in visible_indices if item > index]
    if after:
        return after[0]
    if closed and visible_indices and point_count > 1:
        return visible_indices[0]
    return None


def _lasso_index_sequence(start_index: int, end_index: int, point_count: int) -> list[int]:
    if point_count <= 0:
        return []
    if start_index <= end_index:
        return list(range(start_index, end_index + 1))
    return list(range(start_index, point_count)) + list(range(0, end_index + 1))


