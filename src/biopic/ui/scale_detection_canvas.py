"""Interactive canvas used by the scale-detection dialog."""

from __future__ import annotations

from math import atan2, cos, sin

import numpy as np
from PySide6.QtCore import QPointF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QMouseEvent, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsSimpleTextItem
from PySide6.QtWidgets import QGraphicsView

from biopic.imaging.scale_detection import (
    measurement_metrics,
    reference_overlay_lengths,
    snapped_measurement_endpoint,
)
from biopic.ui.image_canvas import ImageCanvas


class ScaleDetectionCanvas(ImageCanvas):
    """Image canvas with non-destructive scale measurement overlays."""

    measurementChanged = Signal(float)
    measurementAccepted = Signal(float)

    def __init__(self) -> None:
        super().__init__()
        self._scale_measure_mode = False
        self._measure_start: QPointF | None = None
        self._measure_end: QPointF | None = None
        self._measure_items: list[QGraphicsPathItem | QGraphicsSimpleTextItem] = []
        self._reference_items: list[QGraphicsPathItem | QGraphicsSimpleTextItem] = []
        self._unit_per_pixel: float | None = None
        self._unit = "um"

    def begin_measure_distance(self) -> None:
        self._scale_measure_mode = True
        self._measure_start = None
        self._measure_end = None
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.viewport().setCursor(Qt.CursorShape.CrossCursor)
        self._clear_measurement_overlay()

    def accept_measurement(self) -> None:
        if self._measure_start is None or self._measure_end is None:
            return
        distance = measurement_metrics(
            _point_tuple(self._measure_start),
            _point_tuple(self._measure_end),
        )["distance_pixels"]
        self.measurementAccepted.emit(distance)
        self._scale_measure_mode = False
        self.set_tool_mode("pan")

    def cancel_measurement(self) -> None:
        self._scale_measure_mode = False
        self._measure_start = None
        self._measure_end = None
        self._clear_measurement_overlay()
        self.set_tool_mode("pan")

    def clear_measurement(self) -> None:
        self._measure_start = None
        self._measure_end = None
        self._clear_measurement_overlay()

    def set_calibration_preview(
        self,
        pixels_per_unit: float,
        unit: str,
        *,
        stripe_axis: str = "",
        stripe_positions: tuple[float, ...] = (),
        tick_marks: tuple[dict[str, float | str], ...] = (),
    ) -> None:
        self._unit_per_pixel = 1.0 / pixels_per_unit if pixels_per_unit > 0 else None
        self._unit = unit
        self._draw_reference_overlays(
            pixels_per_unit,
            unit,
            stripe_axis=stripe_axis,
            stripe_positions=stripe_positions,
            tick_marks=tick_marks,
        )
        if self._measure_start is not None and self._measure_end is not None:
            self._draw_measurement_overlay("accepted")

    def clear_calibration_preview(self) -> None:
        self._unit_per_pixel = None
        self._clear_reference_overlays()

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if not self._scale_measure_mode or event.button() != Qt.MouseButton.LeftButton:
            super().mousePressEvent(event)
            return
        point = self.mapToScene(event.position().toPoint())
        if self._measure_start is None:
            self._measure_start = point
            self._measure_end = point
            self._draw_measurement_overlay("start")
            return
        self._measure_end = self._snapped_end(point, event.modifiers())[0]
        self._draw_measurement_overlay("accepted")
        self.accept_measurement()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._scale_measure_mode and self._measure_start is not None:
            point = self.mapToScene(event.position().toPoint())
            self._measure_end, snap = self._snapped_end(point, event.modifiers())
            self._draw_measurement_overlay(snap)
            distance = measurement_metrics(
                _point_tuple(self._measure_start),
                _point_tuple(self._measure_end),
            )["distance_pixels"]
            self.measurementChanged.emit(distance)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._scale_measure_mode:
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: object) -> None:
        if getattr(event, "key", lambda: None)() == Qt.Key.Key_Escape and self._scale_measure_mode:
            self.cancel_measurement()
            return
        super().keyPressEvent(event)

    def _snapped_end(
        self,
        cursor: QPointF,
        modifiers: Qt.KeyboardModifier,
    ) -> tuple[QPointF, str]:
        if self._measure_start is None:
            return cursor, "free"
        free = bool(
            modifiers
            & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.ControlModifier)
        )
        end, snap = snapped_measurement_endpoint(
            _point_tuple(self._measure_start),
            _point_tuple(cursor),
            free_angle=free,
        )
        return QPointF(end[0], end[1]), snap

    def _draw_measurement_overlay(self, snap: str) -> None:
        self._clear_measurement_overlay()
        if self._measure_start is None or self._measure_end is None:
            return
        start = self._measure_start
        end = self._measure_end
        metrics = measurement_metrics(
            _point_tuple(start),
            _point_tuple(end),
            unit_per_pixel=self._unit_per_pixel,
        )
        path = QPainterPath()
        path.moveTo(start)
        path.lineTo(end)
        _add_cap(path, start, end)
        _add_cap(path, end, start)
        item = QGraphicsPathItem(path)
        item.setPen(QPen(QColor("#00d1ff"), 2.0))
        item.setZValue(1000.0)
        self._scene.addItem(item)
        self._measure_items.append(item)
        label = f"{metrics['distance_pixels']:.1f} px"
        if "distance_physical" in metrics:
            label += f" - {metrics['distance_physical']:.3g} {self._unit}"
        label += f" - {metrics['angle_degrees']:.1f} deg"
        if snap in {"horizontal", "vertical"}:
            label += f" - snapped {snap}"
        text = QGraphicsSimpleTextItem(label)
        text.setBrush(QColor("#ffffff"))
        text.setFont(QFont("Arial", 16))
        text.setZValue(1001.0)
        text.setPos((start.x() + end.x()) / 2.0 + 8.0, (start.y() + end.y()) / 2.0 + 8.0)
        self._scene.addItem(text)
        self._measure_items.append(text)

    def _draw_reference_overlays(
        self,
        pixels_per_unit: float,
        unit: str,
        *,
        stripe_axis: str = "",
        stripe_positions: tuple[float, ...] = (),
        tick_marks: tuple[dict[str, float | str], ...] = (),
    ) -> None:
        self._clear_reference_overlays()
        if self._pixels is None or pixels_per_unit <= 0:
            return
        width = float(self._pixels.shape[1])
        height = float(self._pixels.shape[0])
        shown = 0
        for physical, pixels in reference_overlay_lengths(pixels_per_unit):
            if pixels > width * 0.84 and pixels > height * 0.84 and physical > 10:
                continue
            if pixels <= 2:
                continue
            start, end = self._reference_line_points(
                physical,
                pixels,
                shown,
                stripe_axis,
                stripe_positions,
                tick_marks,
            )
            path = QPainterPath()
            path.moveTo(start)
            path.lineTo(end)
            _add_cap(path, start, end)
            _add_cap(path, end, start)
            item = QGraphicsPathItem(path)
            item.setPen(QPen(QColor("#ffe36d"), max(1.5, width * 0.0009)))
            item.setZValue(900.0)
            self._scene.addItem(item)
            self._reference_items.append(item)
            text = QGraphicsSimpleTextItem(f"{physical:g} {unit} - {pixels:.1f} px")
            text.setBrush(QColor("#ffe36d"))
            text.setFont(QFont("Arial", 18))
            text.setZValue(901.0)
            text.setPos(start.x(), start.y() + 8.0)
            self._scene.addItem(text)
            self._reference_items.append(text)
            shown += 1

    def _reference_line_points(
        self,
        physical_length: float,
        length_pixels: float,
        index: int,
        stripe_axis: str,
        stripe_positions: tuple[float, ...],
        tick_marks: tuple[dict[str, float | str], ...],
    ) -> tuple[QPointF, QPointF]:
        if self._pixels is None:
            return QPointF(0, 0), QPointF(length_pixels, 0)
        width = float(self._pixels.shape[1])
        height = float(self._pixels.shape[0])
        margin_x = width * 0.06
        margin_y = height * 0.08
        offset = index * max(34.0, height * 0.055)
        if "vertical" in stripe_axis:
            tick_points = self._vertical_tick_reference_line(
                physical_length,
                length_pixels,
                index,
                tick_marks,
            )
            if tick_points is not None:
                return tick_points
        elif "horizontal" in stripe_axis:
            tick_points = self._horizontal_tick_reference_line(
                physical_length,
                length_pixels,
                index,
                tick_marks,
            )
            if tick_points is not None:
                return tick_points
        if stripe_positions:
            sorted_positions = sorted(float(position) for position in stripe_positions)
            if "vertical" in stripe_axis:
                start_x, end_x = _best_stripe_pair(sorted_positions, length_pixels, width)
                y = min(height - margin_y, margin_y + offset)
                return QPointF(start_x, y), QPointF(end_x, y)
            start_y, end_y = _best_stripe_pair(sorted_positions, length_pixels, height)
            x = min(width - margin_x, margin_x + offset)
            return QPointF(x, start_y), QPointF(x, end_y)
        y = min(height - margin_y, margin_y + offset)
        start_x = margin_x
        end_x = min(width - margin_x, margin_x + length_pixels)
        return QPointF(start_x, y), QPointF(end_x, y)

    def _vertical_tick_reference_line(
        self,
        physical_length: float,
        expected_distance: float,
        index: int,
        tick_marks: tuple[dict[str, float | str], ...] = (),
    ) -> tuple[QPointF, QPointF] | None:
        marks = list(tick_marks) if tick_marks else _detect_vertical_tick_marks(self._pixels)
        pair = _best_tick_pair(marks, physical_length, expected_distance)
        if pair is None:
            return None
        left, right = pair
        if "normal_x" in left and "normal_x" in right:
            return _rotated_tick_reference_line(left, right, physical_length, index, marks)
        y = _reference_y_for_pair(left, right, physical_length, index, marks)
        return QPointF(left["center"], y), QPointF(right["center"], y)

    def _horizontal_tick_reference_line(
        self,
        physical_length: float,
        expected_distance: float,
        index: int,
        tick_marks: tuple[dict[str, float | str], ...] = (),
    ) -> tuple[QPointF, QPointF] | None:
        if self._pixels is None:
            return None
        marks = list(tick_marks)
        if not marks:
            rotated = np.swapaxes(np.asarray(self._pixels), 0, 1)
            marks = _detect_vertical_tick_marks(rotated)
        pair = _best_tick_pair(marks, physical_length, expected_distance)
        if pair is None:
            return None
        top, bottom = pair
        if "normal_x" in top and "normal_x" in bottom:
            return _rotated_tick_reference_line(top, bottom, physical_length, index, marks)
        x = _reference_y_for_pair(top, bottom, physical_length, index, marks)
        return QPointF(x, top["center"]), QPointF(x, bottom["center"])

    def _clear_measurement_overlay(self) -> None:
        for item in self._measure_items:
            self._scene.removeItem(item)
        self._measure_items.clear()

    def _clear_reference_overlays(self) -> None:
        for item in self._reference_items:
            self._scene.removeItem(item)
        self._reference_items.clear()


def _point_tuple(point: QPointF) -> tuple[float, float]:
    return float(point.x()), float(point.y())


def _add_cap(path: QPainterPath, point: QPointF, other: QPointF) -> None:
    dx = other.x() - point.x()
    dy = other.y() - point.y()
    angle = atan2(dy, dx) + 1.5707963267948966
    length = 5.0
    cap_dx = cos(angle) * length
    cap_dy = sin(angle) * length
    path.moveTo(QPointF(point.x() - cap_dx, point.y() - cap_dy))
    path.lineTo(QPointF(point.x() + cap_dx, point.y() + cap_dy))


def _best_stripe_pair(
    positions: list[float],
    expected_distance: float,
    image_length: float,
) -> tuple[float, float]:
    margin = image_length * 0.04
    if len(positions) >= 2:
        best = None
        for start in positions:
            if start < margin or start > image_length - margin:
                continue
            for end in positions:
                if end <= start or end > image_length - margin:
                    continue
                distance = end - start
                error = abs(distance - expected_distance)
                if error > max(3.0, expected_distance * 0.18):
                    continue
                if best is None or error < best[0]:
                    best = (error, start, end)
        if best is not None:
            return best[1], best[2]
    start = margin
    return start, min(image_length - margin, start + expected_distance)


def _reference_y_for_pair(
    first: dict[str, float | str],
    second: dict[str, float | str],
    physical_length: float,
    index: int,
    marks: list[dict[str, float | str]] | None = None,
) -> float:
    small_marks = [mark for mark in marks or [] if str(mark["class"]) == "small"]
    if small_marks:
        anchor_x = min(float(first["center"]), float(second["center"]))
        reference = min(small_marks, key=lambda mark: abs(float(mark["center"]) - anchor_x))
        top = max(float(reference["top"]), float(first["top"]), float(second["top"]))
        reference_bottom = float(reference.get("bottom", top + float(reference["height"])))
        bottom = min(
            reference_bottom,
            float(first.get("bottom", float(first["top"]) + float(first["height"]))),
            float(second.get("bottom", float(second["top"]) + float(second["height"]))),
        )
        if bottom <= top:
            top = float(reference["top"])
            bottom = reference_bottom
        span = max(12.0, bottom - top)
        if physical_length >= 99.0:
            return top + span * 0.06
        if physical_length >= 49.0:
            return top + span * 0.36
        return top + span * 0.72
    if physical_length >= 99.0:
        base = min(float(first["top"]), float(second["top"])) + 18.0
    elif physical_length >= 49.0:
        base = max(float(first["top"]), float(second["top"])) - 12.0
    else:
        base = max(float(first["top"]), float(second["top"])) + 8.0
    return max(2.0, base + index * 2.0)


def _rotated_tick_reference_line(
    first: dict[str, float | str],
    second: dict[str, float | str],
    physical_length: float,
    index: int,
    marks: list[dict[str, float | str]] | None = None,
) -> tuple[QPointF, QPointF]:
    v = _reference_y_for_pair(first, second, physical_length, index, marks)
    return _rotated_tick_point(first, v), _rotated_tick_point(second, v)


def _rotated_tick_point(mark: dict[str, float | str], v: float) -> QPointF:
    u = float(mark["u"])
    normal_x = float(mark["normal_x"])
    normal_y = float(mark["normal_y"])
    tangent_x = float(mark["tangent_x"])
    tangent_y = float(mark["tangent_y"])
    return QPointF(
        normal_x * u + tangent_x * v,
        normal_y * u + tangent_y * v,
    )


def _detect_vertical_tick_marks(pixels: object) -> list[dict[str, float | str]]:
    if pixels is None:
        return []
    array = np.asarray(pixels)
    if array.ndim == 3:
        gray = array[..., :3].astype(np.float32, copy=False).mean(axis=2)
    else:
        gray = array.astype(np.float32, copy=False)
    if gray.size == 0:
        return []
    try:
        import cv2  # type: ignore[import-untyped]
    except ImportError:
        return _detect_vertical_tick_marks_by_projection(gray)
    dark_cutoff = min(
        float(np.percentile(gray, 2.5)) + 18.0,
        float(np.percentile(gray, 18.0)),
    )
    mask = (gray <= dark_cutoff).astype(np.uint8) * 255
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 9))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)
    count, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, 8)
    marks: list[dict[str, float | str]] = []
    min_height = max(18, int(gray.shape[0] * 0.12))
    max_width = max(18, int(gray.shape[1] * 0.04))
    for label in range(1, count):
        x = int(stats[label, cv2.CC_STAT_LEFT])
        y = int(stats[label, cv2.CC_STAT_TOP])
        width = int(stats[label, cv2.CC_STAT_WIDTH])
        height = int(stats[label, cv2.CC_STAT_HEIGHT])
        area = int(stats[label, cv2.CC_STAT_AREA])
        if height < min_height or width > max_width or area < height * 1.2:
            continue
        if height / max(1, width) < 6.0:
            continue
        marks.append(
            {
                "center": float(centroids[label][0]),
                "top": float(y),
                "bottom": float(y + height - 1),
                "height": float(height),
                "class": "small",
            }
        )
    if len(marks) < 2:
        return _detect_vertical_tick_marks_by_projection(gray)
    return _classify_tick_marks(marks)


def _detect_vertical_tick_marks_by_projection(gray: np.ndarray) -> list[dict[str, float | str]]:
    dark_threshold = float(np.percentile(gray, 12.0))
    dark = np.clip(dark_threshold - gray, 0.0, None)
    if float(np.max(dark)) <= 0:
        return []
    column_strength = dark.sum(axis=0)
    active_threshold = max(
        float(np.percentile(column_strength, 82.0)),
        float(np.max(column_strength)) * 0.14,
    )
    active = column_strength >= active_threshold
    groups = _active_runs(active)
    marks: list[dict[str, float | str]] = []
    for start, end in groups:
        if end - start > max(14, gray.shape[1] * 0.035):
            continue
        local = dark[:, start:end]
        row_strength = local.max(axis=1)
        row_threshold = max(
            float(np.percentile(row_strength, 70.0)),
            float(np.max(row_strength)) * 0.18,
        )
        rows = np.nonzero(row_strength >= row_threshold)[0]
        if rows.size < max(8, gray.shape[0] * 0.08):
            continue
        weights = column_strength[start:end]
        columns = np.arange(start, end, dtype=np.float32)
        center = float(np.sum(columns * weights) / max(1e-6, float(np.sum(weights))))
        top = float(rows.min())
        bottom = float(rows.max())
        marks.append(
            {
                "center": center,
                "top": top,
                "bottom": bottom,
                "height": bottom - top,
                "class": "small",
            }
        )
    return _classify_tick_marks(marks)


def _classify_tick_marks(marks: list[dict[str, float | str]]) -> list[dict[str, float | str]]:
    if not marks:
        return []
    max_height = max(float(mark["height"]) for mark in marks)
    for mark in marks:
        ratio = float(mark["height"]) / max(1.0, max_height)
        if ratio >= 0.82:
            mark["class"] = "large"
        elif ratio >= 0.48:
            mark["class"] = "medium"
        else:
            mark["class"] = "small"
    return sorted(marks, key=lambda mark: float(mark["center"]))


def _active_runs(active: np.ndarray) -> list[tuple[int, int]]:
    runs: list[tuple[int, int]] = []
    start: int | None = None
    for index, value in enumerate(active):
        if bool(value) and start is None:
            start = index
        elif not bool(value) and start is not None:
            runs.append((start, index))
            start = None
    if start is not None:
        runs.append((start, int(active.size)))
    return runs


def _best_tick_pair(
    marks: list[dict[str, float | str]],
    physical_length: float,
    expected_distance: float,
) -> tuple[dict[str, float | str], dict[str, float | str]] | None:
    if len(marks) < 2 or expected_distance <= 0:
        return None
    desired = _desired_tick_classes(physical_length)
    anchor_pair = _left_anchor_tick_pair(marks, desired, physical_length, expected_distance)
    if anchor_pair is not None:
        return anchor_pair
    best: tuple[float, dict[str, float | str], dict[str, float | str]] | None = None
    tolerance = max(4.0, expected_distance * 0.22)
    for left_index, left in enumerate(marks[:-1]):
        for right in marks[left_index + 1 :]:
            distance = float(right["center"]) - float(left["center"])
            error = abs(distance - expected_distance)
            if error > tolerance:
                continue
            class_pair = (str(left["class"]), str(right["class"]))
            class_penalty = _tick_class_penalty(class_pair, desired)
            # Prefer the left-most correct pair, matching how users read the micrometer.
            position_penalty = float(left["center"]) * 0.002
            score = error + class_penalty + position_penalty
            if best is None or score < best[0]:
                best = (score, left, right)
    if best is not None:
        return best[1], best[2]
    return None


def _left_anchor_tick_pair(
    marks: list[dict[str, float | str]],
    desired: set[tuple[str, str]],
    physical_length: float,
    expected_distance: float,
) -> tuple[dict[str, float | str], dict[str, float | str]] | None:
    tolerance = max(4.0, expected_distance * 0.24)
    ordered = sorted(marks, key=lambda mark: float(mark["center"]))
    if len(ordered) < 2:
        return None
    interval_target = max(1, int(round(physical_length / 10.0)))
    anchors = _preferred_tick_anchors(ordered)
    for anchor in anchors:
        anchor_index = ordered.index(anchor)
        candidate_index = anchor_index + interval_target
        if candidate_index < len(ordered):
            candidate = ordered[candidate_index]
            distance = float(candidate["center"]) - float(anchor["center"])
            if abs(distance - expected_distance) <= tolerance:
                return anchor, candidate
    for anchor in anchors:
        candidates: list[tuple[float, float, dict[str, float | str]]] = []
        for candidate in ordered:
            if candidate is anchor:
                continue
            distance = float(candidate["center"]) - float(anchor["center"])
            if distance <= 0:
                continue
            error = abs(distance - expected_distance)
            if error > tolerance:
                continue
            class_pair = (str(anchor["class"]), str(candidate["class"]))
            class_penalty = _tick_class_penalty(class_pair, desired)
            candidates.append((class_penalty, error, candidate))
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            return anchor, candidates[0][2]
    return None


def _preferred_tick_anchors(
    ordered: list[dict[str, float | str]],
) -> list[dict[str, float | str]]:
    anchors: list[dict[str, float | str]] = []
    for class_name in ("large", "medium"):
        anchors.extend(mark for mark in ordered if str(mark["class"]) == class_name)
    anchors.extend(ordered)
    unique: list[dict[str, float | str]] = []
    for anchor in anchors:
        if not any(anchor is existing for existing in unique):
            unique.append(anchor)
    return unique


def _desired_tick_classes(physical_length: float) -> set[tuple[str, str]]:
    if physical_length >= 99.0:
        return {("large", "large")}
    if physical_length >= 49.0:
        return {("large", "medium"), ("medium", "large")}
    return {
        ("large", "small"),
        ("small", "large"),
        ("medium", "small"),
        ("small", "medium"),
        ("small", "small"),
    }


def _tick_class_penalty(
    class_pair: tuple[str, str],
    desired: set[tuple[str, str]],
) -> float:
    if class_pair in desired:
        return 0.0
    if class_pair[::-1] in desired:
        return 2.0
    if "large" in class_pair and any("large" in pair for pair in desired):
        return 8.0
    return 20.0
