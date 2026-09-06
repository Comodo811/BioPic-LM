"""Overlay drawing helpers for ImageCanvas."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QPainterPath, QPen, QTransform
from PySide6.QtWidgets import QGraphicsPathItem, QGraphicsRectItem, QGraphicsSimpleTextItem

from biopic.models.annotations import AnnotationKind, AnnotationObject, fit_points_inside_unit_square, normalize_wedge_points
from biopic.models.measurement import Measurement, MeasurementKind, MeasurementLabelAlignment, ScaleBar
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas_items import _AnnotationHandleItem


class ImageCanvasOverlaysMixin:
    """Vector overlays and live paint preview drawing for ImageCanvas."""

    def set_scale_bars(self, scale_bars: list[ScaleBar]) -> None:
        """Display vector scale-bar overlays for the current image."""
        self._clear_scale_bars()
        if self._pixels is None:
            return
        image_width = float(self._pixels.shape[1])
        image_height = float(self._pixels.shape[0])
        for scale_bar in scale_bars:
            length = max(1.0, float(scale_bar.pixel_length))
            thickness = max(1.0, float(scale_bar.width_px))
            is_vertical = scale_bar.orientation == "vertical"
            bar_width = thickness if is_vertical else length
            bar_height = length if is_vertical else thickness
            x, y = _scale_bar_origin(scale_bar, image_width, image_height, bar_width, bar_height)
            background = _optional_color(scale_bar.background)
            if background is not None:
                pad = max(4.0, thickness * 2.0)
                rect = QGraphicsRectItem(
                    QRectF(x - pad, y - pad, bar_width + pad * 2.0, bar_height + pad * 2.0)
                )
                rect.setBrush(QBrush(background))
                rect.setPen(QPen(Qt.PenStyle.NoPen))
                rect.setOpacity(scale_bar.opacity)
                rect.setZValue(8.0)
                self._scene.addItem(rect)
                self._scale_bar_items.append(rect)
            path = QPainterPath()
            if is_vertical:
                path.moveTo(x + thickness / 2.0, y)
                path.lineTo(x + thickness / 2.0, y + length)
            else:
                path.moveTo(x, y + thickness / 2.0)
                path.lineTo(x + length, y + thickness / 2.0)
            item = QGraphicsPathItem(path)
            item.setPen(
                QPen(QColor(scale_bar.foreground), thickness, Qt.PenStyle.SolidLine)
            )
            item.setOpacity(scale_bar.opacity)
            item.setZValue(9.0)
            self._scene.addItem(item)
            self._scale_bar_items.append(item)
            if scale_bar.display_length:
                text = QGraphicsSimpleTextItem(
                    f"{scale_bar.physical_length:g} {scale_bar.unit}"
                )
                font = QFont(
                    safe_font_family(scale_bar.font_family),
                    max(1, int(round(scale_bar.font_size))),
                )
                font.setBold(scale_bar.bold)
                font.setItalic(scale_bar.italic)
                text.setFont(font)
                text.setBrush(QBrush(QColor(scale_bar.foreground)))
                text.setOpacity(scale_bar.opacity)
                text.setZValue(10.0)
                bounds = text.boundingRect()
                if is_vertical:
                    text.setPos(x + thickness + 6.0, y + length / 2.0 - bounds.height() / 2.0)
                else:
                    text.setPos(
                        x + length / 2.0 - bounds.width() / 2.0,
                        y + thickness + 4.0,
                    )
                self._scene.addItem(text)
                self._scale_bar_items.append(text)

    def set_annotations(self, annotations: list[AnnotationObject]) -> None:
        """Display editable vector annotation overlays for the current image."""
        self._clear_annotations()
        self._clear_annotation_edit_items()
        self._annotation_pixel_points.clear()
        if self._pixels is None:
            return
        image_width = float(self._pixels.shape[1])
        image_height = float(self._pixels.shape[0])
        for annotation in annotations:
            if not annotation.visible or not annotation.points:
                continue
            annotation_points = (
                normalize_wedge_points(
                    list(annotation.points),
                    padding=max(
                        float(annotation.line_width) / (2.0 * image_width),
                        float(annotation.line_width) / (2.0 * image_height),
                    ),
                )
                if annotation.kind is AnnotationKind.WEDGE
                else annotation.points
            )
            points = [
                QPointF(float(x) * image_width, float(y) * image_height)
                for x, y in annotation_points
            ]
            self._annotation_pixel_points[annotation.id] = points
            color = QColor(annotation.color)
            if not color.isValid():
                color = QColor("#ffffff")
            opacity = max(0.0, min(1.0, float(annotation.opacity)))
            if annotation.kind is AnnotationKind.TEXT:
                text_item = QGraphicsSimpleTextItem(annotation.text or "Label")
                font = QFont(
                    safe_font_family(annotation.font),
                    max(1, int(round(annotation.size))),
                )
                text_item.setFont(font)
                text_item.setBrush(QBrush(color))
                text_item.setOpacity(opacity)
                text_item.setPos(points[0])
                text_item.setZValue(12.0)
                self._scene.addItem(text_item)
                self._annotation_items.append(text_item)
                continue
            if len(points) < 2:
                continue
            path = _annotation_path(annotation.kind, points, max(1.0, annotation.line_width))
            path_item = QGraphicsPathItem(path)
            pen = QPen(color, max(1.0, annotation.line_width), Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            if annotation.kind is AnnotationKind.WEDGE:
                fill = QColor(annotation.fill or annotation.color)
                fill.setAlphaF(opacity)
                path_item.setPen(QPen(Qt.PenStyle.NoPen))
                path_item.setBrush(QBrush(fill))
            else:
                path_item.setPen(pen)
            path_item.setOpacity(opacity)
            path_item.setZValue(12.0)
            self._scene.addItem(path_item)
            self._annotation_items.append(path_item)
        self._refresh_selected_annotation_handles()

    def _refresh_selected_annotation_handles(self) -> None:
        self._clear_annotation_edit_items()
        if self._pixels is None or self._selected_annotation_id is None:
            return
        points = self._annotation_pixel_points.get(self._selected_annotation_id)
        if points is None or len(points) < 2:
            return
        rect = _points_bounding_rect(points).adjusted(-4.0, -4.0, 4.0, 4.0)
        box = QGraphicsRectItem(rect)
        box.setPen(QPen(QColor("#ffffff"), 1.0, Qt.PenStyle.DashLine))
        box.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        box.setZValue(16.0)
        self._scene.addItem(box)
        self._annotation_edit_items.append(box)
        center = _centroid(points)
        handles = _annotation_handle_points(points)
        rotate = handles.get("rotate")
        rotate_line = QGraphicsPathItem()
        if rotate is not None:
            path = QPainterPath(center)
            path.lineTo(rotate)
            rotate_line.setPath(path)
            rotate_line.setPen(QPen(QColor("#ffffff"), 1.0, Qt.PenStyle.DashLine))
            rotate_line.setZValue(16.0)
            self._scene.addItem(rotate_line)
            self._annotation_edit_items.append(rotate_line)
        for role, point in handles.items():
            handle = _AnnotationHandleItem(self, self._selected_annotation_id, role, point)
            self._scene.addItem(handle)
            self._annotation_edit_items.append(handle)

    def _annotation_handle_drag_started(self, annotation_id: str, role: str) -> None:
        points = self._annotation_pixel_points.get(annotation_id)
        if points is None or len(points) < 2:
            self._annotation_handle_snapshot = None
            return
        center = _centroid(points)
        handle_point = _annotation_handle_point(points, role)
        self._annotation_handle_snapshot = {
            "id": annotation_id,
            "role": role,
            "points": [QPointF(point) for point in points],
            "center": center,
            "handle_point": handle_point,
        }

    def _annotation_handle_moved(self, annotation_id: str, role: str, point: QPointF) -> None:
        snapshot = self._annotation_handle_snapshot
        if not isinstance(snapshot, dict) or snapshot.get("id") != annotation_id:
            return
        original = snapshot.get("points")
        center = snapshot.get("center")
        handle_point = snapshot.get("handle_point")
        if (
            not isinstance(original, list)
            or not isinstance(center, QPointF)
            or not isinstance(handle_point, QPointF)
            or len(original) < 2
        ):
            return
        updated = _transformed_annotation_points(original, center, role, handle_point, point)
        if self._pixels is None:
            return
        width = max(1.0, float(self._pixels.shape[1]))
        height = max(1.0, float(self._pixels.shape[0]))
        fitted = _fit_points_inside_rect(updated, width, height) if len(updated) >= 3 else updated
        normalized = [
            _normalized_point(point, width, height, clamp=True)
            for point in fitted
        ]
        if len(updated) >= 3:
            normalized = normalize_wedge_points(
                normalized,
                padding=max(
                    1.0 / (2.0 * width),
                    1.0 / (2.0 * height),
                ),
            )
            fitted = [QPointF(x * width, y * height) for x, y in normalized]
        self._annotation_pixel_points[annotation_id] = fitted
        self.annotationTransformed.emit(annotation_id, normalized)
        self._refresh_selected_annotation_handles()

    def _annotation_handle_released(self) -> None:
        self._annotation_handle_snapshot = None
        self.annotationTransformFinished.emit()

    def _annotation_at_point(self, point: QPointF) -> str | None:
        for annotation_id, points in reversed(list(self._annotation_pixel_points.items())):
            if len(points) < 2:
                continue
            if len(points) >= 3:
                path = QPainterPath(points[0])
                for item in points[1:]:
                    path.lineTo(item)
                path.closeSubpath()
                if path.contains(point):
                    return annotation_id
                continue
            distance = _distance_to_segment(point, points[0], points[1])
            if distance <= 8.0:
                return annotation_id
        return None

    def set_measurements(self, measurements: list[Measurement]) -> None:
        """Display calibrated measurement overlays for the current image."""
        self._clear_measurements()
        if self._pixels is None:
            return
        for measurement in measurements:
            if not measurement.points:
                continue
            path = _measurement_path(measurement)
            if path.isEmpty():
                continue
            color = QColor(measurement.color)
            if not color.isValid():
                color = QColor("#ffe36d")
            path_item = QGraphicsPathItem(path)
            pen = QPen(color, max(1.0, float(measurement.line_width)), Qt.PenStyle.SolidLine)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            path_item.setPen(pen)
            path_item.setBrush(QBrush(Qt.BrushStyle.NoBrush))
            path_item.setZValue(13.0)
            self._scene.addItem(path_item)
            self._measurement_items.append(path_item)
            font = QFont(
                safe_font_family(measurement.font_family),
                max(1, int(round(measurement.font_size))),
            )
            font.setBold(measurement.bold)
            font.setItalic(measurement.italic)
            for text_value, position, rotate in _measurement_text_items(measurement):
                if not text_value:
                    continue
                text = QGraphicsSimpleTextItem(text_value)
                text.setBrush(QBrush(color))
                text.setFont(font)
                text.setPos(position)
                if rotate and measurement.label_alignment is MeasurementLabelAlignment.ALIGNED:
                    text.setRotation(measurement.line_angle_degrees())
                text.setZValue(14.0)
                self._scene.addItem(text)
                self._measurement_items.append(text)
            if measurement.kind is MeasurementKind.RECTANGLE and measurement.show_side_lengths:
                for label, position in _measurement_side_labels(measurement):
                    side_text = QGraphicsSimpleTextItem(label)
                    side_text.setBrush(QBrush(color))
                    side_text.setFont(font)
                    side_text.setPos(position)
                    side_text.setZValue(14.0)
                    self._scene.addItem(side_text)
                    self._measurement_items.append(side_text)

    def extend_paint_preview(
        self, points: list[tuple[int, int]], radius: int, color: QColor
    ) -> None:
        """Draw a lightweight live stroke overlay without replacing the image pixmap."""
        if not points:
            return
        path = QPainterPath()
        first_x, first_y = self._paint_preview_tail or points[0]
        path.moveTo(float(first_x), float(first_y))
        if self._paint_preview_tail is None and len(points) == 1:
            size = max(1.0, float(radius))
            path.addEllipse(QPointF(float(first_x), float(first_y)), size, size)
        for x, y in _preview_points(points):
            path.lineTo(float(x), float(y))
        self._paint_preview_tail = points[-1]
        pen = QPen(color, float(max(1, radius * 2 + 1)))
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        item = QGraphicsPathItem()
        item.setPen(pen)
        item.setPath(path)
        item.setVisible(True)
        item.setZValue(10.0)
        self._paint_preview_segments.append(item)
        self._scene.addItem(item)
        self._trim_paint_preview_segments()

    def clear_paint_preview(self) -> None:
        """Remove the live paint overlay."""
        self._paint_preview_item.setPath(QPainterPath())
        self._paint_preview_item.setVisible(False)
        for item in self._paint_preview_segments:
            self._scene.removeItem(item)
        self._paint_preview_segments.clear()
        self._paint_preview_tail = None
        self._clear_paint_overlay_items()

    def _clear_scale_bars(self) -> None:
        for item in self._scale_bar_items:
            self._scene.removeItem(item)
        self._scale_bar_items.clear()

    def _clear_annotations(self) -> None:
        for item in self._annotation_items:
            self._scene.removeItem(item)
        self._annotation_items.clear()

    def _clear_annotation_edit_items(self) -> None:
        for item in self._annotation_edit_items:
            self._scene.removeItem(item)
        self._annotation_edit_items.clear()

    def _clear_measurements(self) -> None:
        for item in self._measurement_items:
            self._scene.removeItem(item)
        self._measurement_items.clear()


def _preview_points(points: list[tuple[int, int]]) -> list[tuple[int, int]]:
    """Return enough points for a smooth preview without overloading the scene."""
    if len(points) <= 24:
        return points
    step = max(1, len(points) // 24)
    sampled = points[::step]
    if sampled[-1] != points[-1]:
        sampled.append(points[-1])
    return sampled


def _rects_intersect(
    a: tuple[int, int, int, int], b: tuple[int, int, int, int]
) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def _scale_bar_origin(
    scale_bar: ScaleBar,
    image_width: float,
    image_height: float,
    bar_width: float,
    bar_height: float,
) -> tuple[float, float]:
    offset_x = float(scale_bar.offset_x)
    offset_y = float(scale_bar.offset_y)
    if scale_bar.location == "Upper Left":
        return offset_x, offset_y
    if scale_bar.location == "Upper Right":
        return image_width - bar_width - offset_x, offset_y
    if scale_bar.location == "Lower Left":
        return offset_x, image_height - bar_height - offset_y
    return image_width - bar_width - offset_x, image_height - bar_height - offset_y


def _optional_color(value: str | None) -> QColor | None:
    if not value:
        return None
    color = QColor(value)
    if not color.isValid() and len(value) == 9 and value.startswith("#"):
        color = QColor(value[:7])
        color.setAlpha(int(value[7:9], 16))
    return color if color.isValid() else None


def _pixel_value(pixels: np.ndarray, point: QPointF) -> str:
    value = pixels[int(point.y()), int(point.x())]
    if np.isscalar(value):
        return str(value.item() if hasattr(value, "item") else value)
    return ", ".join(str(item) for item in np.asarray(value).tolist())


def _annotation_path(
    kind: AnnotationKind, points: list[QPointF], line_width: float
) -> QPainterPath:
    path = QPainterPath()
    start = points[0]
    end = points[1]
    if kind is AnnotationKind.WEDGE:
        triangle = _normal_wedge_points(points, 0.0)
        path.moveTo(triangle[0])
        for point in triangle[1:]:
            path.lineTo(point)
        path.closeSubpath()
        return path
    path.moveTo(start)
    path.lineTo(end)
    if kind is AnnotationKind.ARROW:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        length = max(1.0, (dx * dx + dy * dy) ** 0.5)
        ux = dx / length
        uy = dy / length
        nx = -uy
        ny = ux
        head = max(8.0, line_width * 5.0)
        back_x = end.x() - ux * head
        back_y = end.y() - uy * head
        path.moveTo(end)
        path.lineTo(back_x + nx * head * 0.45, back_y + ny * head * 0.45)
        path.moveTo(end)
        path.lineTo(back_x - nx * head * 0.45, back_y - ny * head * 0.45)
    return path


def _normal_wedge_points(points: list[QPointF], minimum_base_width: float) -> list[QPointF]:
    if len(points) == 2:
        base_mid = points[0]
        tip = points[1]
        axis_x = tip.x() - base_mid.x()
        axis_y = tip.y() - base_mid.y()
        axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
        perp_x = -axis_y / axis_length
        perp_y = axis_x / axis_length
        half = max(minimum_base_width / 2.0, axis_length * 0.22, 0.5)
        return [
            QPointF(tip),
            QPointF(base_mid.x() - perp_x * half, base_mid.y() - perp_y * half),
            QPointF(base_mid.x() + perp_x * half, base_mid.y() + perp_y * half),
        ]
    tip = points[0]
    base_a = points[1]
    base_b = points[2]
    base_mid = QPointF((base_a.x() + base_b.x()) / 2.0, (base_a.y() + base_b.y()) / 2.0)
    dx = base_b.x() - base_a.x()
    dy = base_b.y() - base_a.y()
    base_width = (dx * dx + dy * dy) ** 0.5
    if base_width >= minimum_base_width:
        return [QPointF(tip), QPointF(base_a), QPointF(base_b)]
    axis_x = tip.x() - base_mid.x()
    axis_y = tip.y() - base_mid.y()
    axis_length = max(1.0, (axis_x * axis_x + axis_y * axis_y) ** 0.5)
    perp_x = -axis_y / axis_length
    perp_y = axis_x / axis_length
    half = max(minimum_base_width / 2.0, 0.5)
    return [
        QPointF(tip),
        QPointF(base_mid.x() - perp_x * half, base_mid.y() - perp_y * half),
        QPointF(base_mid.x() + perp_x * half, base_mid.y() + perp_y * half),
    ]


def _measurement_path(measurement: Measurement) -> QPainterPath:
    path = QPainterPath()
    points = [QPointF(point.x, point.y) for point in measurement.points]
    if measurement.kind is MeasurementKind.LINE and len(points) >= 2:
        path.moveTo(points[0])
        path.lineTo(points[1])
        return path
    if measurement.kind is MeasurementKind.RECTANGLE:
        if len(points) >= 4:
            path.moveTo(points[0])
            for point in points[1:4]:
                path.lineTo(point)
            path.closeSubpath()
        elif len(points) >= 2:
            path.addRect(QRectF(points[0], points[1]).normalized())
        return path
    if measurement.kind is MeasurementKind.ELLIPSE:
        if len(points) >= 3:
            center = points[0]
            major = points[1]
            minor = points[2]
            width = 2.0 * _distance_qpoints(center, major)
            height = 2.0 * _distance_qpoints(center, minor)
            angle = np_degrees_qpoints(center, major)
            path.addEllipse(QRectF(-width / 2.0, -height / 2.0, width, height))
            transform = QTransform()
            transform.translate(center.x(), center.y())
            transform.rotate(angle)
            return transform.map(path)
        if len(points) >= 2:
            path.addEllipse(QRectF(points[0], points[1]).normalized())
        return path
    if measurement.kind in {MeasurementKind.POLYGON, MeasurementKind.POLYLINE} and len(points) >= 2:
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        if measurement.kind is MeasurementKind.POLYGON:
            path.closeSubpath()
    return path


def _measurement_label_position(measurement: Measurement) -> QPointF:
    if not measurement.points:
        return QPointF(0, 0)
    if measurement.kind is MeasurementKind.LINE and len(measurement.points) >= 2:
        a, b = measurement.points[0], measurement.points[1]
        return QPointF((a.x + b.x) / 2.0 + 6.0, (a.y + b.y) / 2.0 + 6.0)
    xs = [point.x for point in measurement.points]
    ys = [point.y for point in measurement.points]
    return QPointF(sum(xs) / len(xs) + 6.0, min(ys) - 18.0)


def _measurement_text_items(measurement: Measurement) -> list[tuple[str, QPointF, bool]]:
    base = _measurement_label_position(measurement)
    label_pos = QPointF(
        base.x() + measurement.label_offset[0],
        base.y() + measurement.label_offset[1],
    )
    value_y_shift = 18.0 if measurement.show_label and measurement.label else 0.0
    value_pos = QPointF(
        base.x() + measurement.value_offset[0],
        base.y() + measurement.value_offset[1] + value_y_shift,
    )
    return [
        (measurement.label_text(), label_pos, False),
        (measurement.value_text(), value_pos, True),
    ]


def _measurement_side_labels(measurement: Measurement) -> list[tuple[str, QPointF]]:
    if len(measurement.points) < 4:
        return []
    unit = measurement.display_unit
    width, height = measurement.rectangle_side_lengths_display(unit)
    decimals = max(0, min(6, int(measurement.decimal_places)))
    points = [QPointF(point.x, point.y) for point in measurement.points[:4]]
    return [
        (f"{width:.{decimals}f} {unit}", _midpoint(points[0], points[1])),
        (f"{height:.{decimals}f} {unit}", _midpoint(points[1], points[2])),
    ]


def _midpoint(a: QPointF, b: QPointF) -> QPointF:
    return QPointF((a.x() + b.x()) / 2.0 + 4.0, (a.y() + b.y()) / 2.0 + 4.0)


def _distance_qpoints(a: QPointF, b: QPointF) -> float:
    return float(((b.x() - a.x()) ** 2 + (b.y() - a.y()) ** 2) ** 0.5)


def _points_bounding_rect(points: list[QPointF]) -> QRectF:
    min_x = min(point.x() for point in points)
    max_x = max(point.x() for point in points)
    min_y = min(point.y() for point in points)
    max_y = max(point.y() for point in points)
    return QRectF(QPointF(min_x, min_y), QPointF(max_x, max_y)).normalized()


def _centroid(points: list[QPointF]) -> QPointF:
    return QPointF(
        sum(point.x() for point in points) / max(1, len(points)),
        sum(point.y() for point in points) / max(1, len(points)),
    )


def _transformed_wedge_points(
    original: list[QPointF],
    center: QPointF,
    role: str,
    handle_point: QPointF,
    point: QPointF,
) -> list[QPointF]:
    return _transformed_annotation_points(original, center, role, handle_point, point)


def _transformed_annotation_points(
    original: list[QPointF],
    center: QPointF,
    role: str,
    handle_point: QPointF,
    point: QPointF,
) -> list[QPointF]:
    if len(original) == 2:
        if role == "start":
            return [point, original[1]]
        if role == "end":
            return [original[0], point]
        if role == "rotate":
            angle = _angle(point - center) - _angle(handle_point - center)
            return [_rotate_about(item, center, angle) for item in original]
        if role == "scale":
            start = max(1.0, _distance_qpoints(handle_point, center))
            scale = max(0.02, _distance_qpoints(point, center) / start)
            return [
                QPointF(
                    center.x() + (item.x() - center.x()) * scale,
                    center.y() + (item.y() - center.y()) * scale,
                )
                for item in original
            ]
        return original
    if len(original) < 3:
        return original
    tip, base_a, base_b = original[:3]
    base_mid = QPointF((base_a.x() + base_b.x()) / 2.0, (base_a.y() + base_b.y()) / 2.0)
    axis = _unit_vector(QPointF(tip.x() - base_mid.x(), tip.y() - base_mid.y()))
    perpendicular = QPointF(-axis.y(), axis.x())
    if role == "rotate":
        angle = _angle(point - center) - _angle(handle_point - center)
        return [_rotate_about(item, center, angle) for item in original]
    if role == "scale":
        start = max(1.0, _distance_qpoints(handle_point, center))
        scale = max(0.02, _distance_qpoints(point, center) / start)
        return [
            QPointF(
                center.x() + (item.x() - center.x()) * scale,
                center.y() + (item.y() - center.y()) * scale,
            )
            for item in original
        ]
    if role == "length":
        length = max(0.2, _dot(point - base_mid, axis))
        return [
            QPointF(base_mid.x() + axis.x() * length, base_mid.y() + axis.y() * length),
            base_a,
            base_b,
        ]
    if role in {"width_a", "width_b"}:
        half_width = max(0.2, abs(_dot(point - base_mid, perpendicular)))
        return [
            tip,
            QPointF(base_mid.x() - perpendicular.x() * half_width, base_mid.y() - perpendicular.y() * half_width),
            QPointF(base_mid.x() + perpendicular.x() * half_width, base_mid.y() + perpendicular.y() * half_width),
        ]
    return original


def _annotation_handle_point(points: list[QPointF], role: str) -> QPointF:
    return QPointF(_annotation_handle_points(points).get(role, _centroid(points)))


def _annotation_handle_points(points: list[QPointF]) -> dict[str, QPointF]:
    rect = _points_bounding_rect(points).adjusted(-4.0, -4.0, 4.0, 4.0)
    center = _centroid(points)
    if len(points) == 2:
        return {
            "start": QPointF(points[0]),
            "end": QPointF(points[1]),
            "scale": rect.bottomRight(),
            "rotate": QPointF(center.x(), rect.top() - max(14.0, rect.height() * 0.25)),
        }
    if len(points) < 3:
        return {}
    return {
        "length": QPointF(points[0]),
        "width_a": QPointF(points[1]),
        "width_b": QPointF(points[2]),
        "scale": rect.bottomRight(),
        "rotate": QPointF(center.x(), rect.top() - max(14.0, rect.height() * 0.25)),
    }


def _wedge_handle_point(points: list[QPointF], role: str) -> QPointF:
    return _annotation_handle_point(points, role)


def _distance_to_segment(point: QPointF, start: QPointF, end: QPointF) -> float:
    dx = end.x() - start.x()
    dy = end.y() - start.y()
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-9:
        return _distance_qpoints(point, start)
    t = ((point.x() - start.x()) * dx + (point.y() - start.y()) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    projected = QPointF(start.x() + t * dx, start.y() + t * dy)
    return _distance_qpoints(point, projected)


def _normalized_point(point: QPointF, width: float, height: float, *, clamp: bool = True) -> tuple[float, float]:
    x = point.x() / width
    y = point.y() / height
    if not clamp:
        return (x, y)
    return (
        max(0.0, min(1.0, x)),
        max(0.0, min(1.0, y)),
    )


def _fit_points_inside_rect(points: list[QPointF], width: float, height: float) -> list[QPointF]:
    if not points:
        return []
    min_x = min(point.x() for point in points)
    max_x = max(point.x() for point in points)
    min_y = min(point.y() for point in points)
    max_y = max(point.y() for point in points)
    shape_width = max_x - min_x
    shape_height = max_y - min_y
    scale = 1.0
    if shape_width > width and shape_width > 0.0:
        scale = min(scale, width / shape_width)
    if shape_height > height and shape_height > 0.0:
        scale = min(scale, height / shape_height)
    center = QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)
    fitted = [
        QPointF(
            center.x() + (point.x() - center.x()) * scale,
            center.y() + (point.y() - center.y()) * scale,
        )
        for point in points
    ]
    min_x = min(point.x() for point in fitted)
    max_x = max(point.x() for point in fitted)
    min_y = min(point.y() for point in fitted)
    max_y = max(point.y() for point in fitted)
    dx = 0.0
    dy = 0.0
    if min_x < 0.0:
        dx = -min_x
    elif max_x > width:
        dx = width - max_x
    if min_y < 0.0:
        dy = -min_y
    elif max_y > height:
        dy = height - max_y
    return [QPointF(point.x() + dx, point.y() + dy) for point in fitted]


def _unit_vector(vector: QPointF) -> QPointF:
    length = max(1.0, (vector.x() * vector.x() + vector.y() * vector.y()) ** 0.5)
    return QPointF(vector.x() / length, vector.y() / length)


def _dot(a: QPointF, b: QPointF) -> float:
    return float(a.x() * b.x() + a.y() * b.y())


def _angle(vector: QPointF) -> float:
    return float(np.arctan2(vector.y(), vector.x()))


def _rotate_about(point: QPointF, center: QPointF, angle: float) -> QPointF:
    cosine = float(np.cos(angle))
    sine = float(np.sin(angle))
    dx = point.x() - center.x()
    dy = point.y() - center.y()
    return QPointF(
        center.x() + dx * cosine - dy * sine,
        center.y() + dx * sine + dy * cosine,
    )


def np_degrees_qpoints(a: QPointF, b: QPointF) -> float:
    from math import atan2, degrees

    return degrees(atan2(b.y() - a.y(), b.x() - a.x()))

