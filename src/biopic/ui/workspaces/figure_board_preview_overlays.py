"""Figure-board preview overlay drawing helpers."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap

from biopic.models.annotations import AnnotationKind, normalize_wedge_points
from biopic.models.figure_board import (
    FigurePanel,
    adjusted_scale_bar_length,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import (
    Measurement,
    MeasurementKind,
    MeasurementLabelAlignment,
)
from biopic.ui.fonts import safe_font_family


def _annotation_text_rect(anchor: QPointF, font: QFont, text: str) -> QRectF:
    metrics = QFontMetrics(font)
    size = metrics.size(Qt.TextFlag.TextSingleLine, text or "Label")
    return QRectF(anchor, size)


class FigureBoardPreviewOverlayMixin:
    """Selection handles, transform overlays, scale bars, annotations, and measurements."""

    def _draw_panel_handles(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#76a9ff"), 1.5))
        painter.drawRect(rect)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#1f5fa8"), 1.2))
        for handle in self._corner_handles(rect).values():
            painter.drawRect(handle)
        painter.setBrush(QBrush(QColor("#fff1cf")))
        painter.setPen(QPen(QColor("#b86b00"), 1.2))
        for handle in self._panel_resize_handles(rect).values():
            painter.drawRect(handle)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#1f5fa8"), 1.2))
        rotate = self._rotate_handle(rect)
        painter.drawLine(QPointF(rect.center().x(), rect.top()), rotate.center())
        painter.drawEllipse(rotate)
        painter.restore()

    def _draw_image_transform_overlay(
        self,
        painter: QPainter,
        panel: FigurePanel,
        panel_rect: QRectF,
        pixmap: QPixmap,
        page_rect: QRectF,
    ) -> None:
        transform, local_rect, polygon = self._image_transform_geometry(
            panel,
            panel_rect,
            pixmap,
        )
        image_path = QPainterPath()
        image_path.addPolygon(polygon)
        page_path = QPainterPath()
        page_path.addRect(page_rect)
        panel_path = QPainterPath()
        panel_path.addRect(panel_rect)
        outside = image_path.intersected(page_path).subtracted(panel_path)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setClipPath(outside)
        painter.fillPath(outside, QColor(0, 0, 0, 120))
        painter.setOpacity(0.26)
        painter.setTransform(transform, combine=True)
        painter.drawPixmap(local_rect, pixmap, QRectF(pixmap.rect()))
        painter.restore()

        handles = self._image_panel_handle_rects(panel_rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#4aa3ff"), 2.0))
        painter.drawRect(panel_rect)
        rotate = handles.get("rotate")
        if rotate is not None:
            painter.setPen(QPen(QColor("#4aa3ff"), 1.4))
            painter.drawLine(QPointF(panel_rect.center().x(), panel_rect.top()), rotate.center())
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#1f5fa8"), 1.3))
        for name, rect in handles.items():
            if name == "rotate":
                painter.drawEllipse(rect)
            else:
                painter.drawRect(rect)
        painter.setBrush(QBrush(QColor("#fff1cf")))
        painter.setPen(QPen(QColor("#b86b00"), 1.2))
        for rect in self._panel_resize_handles(panel_rect).values():
            painter.drawRect(rect)
        painter.setPen(QColor("#ffffff"))
        painter.setFont(QFont(safe_font_family("Arial"), 8))
        painter.drawText(
            panel_rect.adjusted(4, 4, -4, -4),
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop,
            f"{panel.crop[2] * 100:.0f}%  {panel.rotation:.1f} deg",
        )
        center = self._image_center(panel, panel_rect)
        painter.setBrush(QBrush(QColor("#4aa3ff")))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawEllipse(center, 3.0, 3.0)
        painter.restore()

    def _draw_divider_highlight(self, painter: QPainter, content: QRectF) -> None:
        if self._highlight_divider is None:
            return
        parts = self._highlight_divider.split(":")
        if len(parts) not in {2, 4}:
            return
        try:
            boundary = float(parts[1])
        except ValueError:
            return
        painter.save()
        painter.setPen(QPen(QColor("#76a9ff"), 2.4))
        painter.setBrush(QBrush(QColor("#76a9ff")))
        if parts[0] == "divider_v":
            x = content.x() + boundary * content.width()
            span = (
                (float(parts[2]), float(parts[3]))
                if len(parts) == 4
                else (0.0, 1.0)
            )
            top = content.y() + span[0] * content.height()
            bottom = content.y() + span[1] * content.height()
            painter.drawLine(QPointF(x, top), QPointF(x, bottom))
            painter.drawRect(QRectF(x - 3, (top + bottom) / 2.0 - 18, 6, 36))
        elif parts[0] == "divider_h":
            y = content.y() + boundary * content.height()
            span = (
                (float(parts[2]), float(parts[3]))
                if len(parts) == 4
                else (0.0, 1.0)
            )
            left = content.x() + span[0] * content.width()
            right = content.x() + span[1] * content.width()
            painter.drawLine(QPointF(left, y), QPointF(right, y))
            painter.drawRect(QRectF((left + right) / 2.0 - 18, y - 3, 36, 6))
        painter.restore()

    def _draw_board_handles(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#ffb347"), 2.0))
        painter.drawRect(rect)
        painter.setBrush(QBrush(QColor("#fff1cf")))
        painter.setPen(QPen(QColor("#b86b00"), 1.4))
        for handle in self._board_handles(rect).values():
            painter.drawRect(handle)
        painter.restore()

    def _handle_at(self, point: QPointF, rect: QRectF) -> str | None:
        if self._rotate_handle(rect).contains(point):
            return "rotate"
        for name, handle in self._corner_handles(rect).items():
            if handle.contains(point):
                return f"scale_{name}"
        return None

    def _board_handle_at(self, point: QPointF, rect: QRectF) -> str | None:
        for name, handle in self._board_handles(rect).items():
            if handle.contains(point):
                return f"scale_{name}"
        return None

    def _board_handles(self, rect: QRectF) -> dict[str, QRectF]:
        handles = self._corner_handles(rect)
        size = next(iter(handles.values())).width()
        half = size / 2.0
        side_points = {
            "t": QPointF(rect.center().x(), rect.top()),
            "b": QPointF(rect.center().x(), rect.bottom()),
            "l": QPointF(rect.left(), rect.center().y()),
            "r": QPointF(rect.right(), rect.center().y()),
        }
        handles.update(
            {
                name: QRectF(point.x() - half, point.y() - half, size, size)
                for name, point in side_points.items()
            }
        )
        return handles

    def _corner_handles(self, rect: QRectF) -> dict[str, QRectF]:
        size = max(12.0, min(22.0, rect.width() * 0.055))
        half = size / 2.0
        points = {
            "tl": rect.topLeft(),
            "tr": rect.topRight(),
            "bl": rect.bottomLeft(),
            "br": rect.bottomRight(),
        }
        return {
            name: QRectF(point.x() - half, point.y() - half, size, size)
            for name, point in points.items()
        }

    def _rotate_handle(self, rect: QRectF) -> QRectF:
        size = max(13.0, min(24.0, rect.width() * 0.06))
        return QRectF(rect.center().x() - size / 2.0, rect.top() - size * 3.0, size, size)

    def _draw_panel_scale_bars(
        self,
        painter: QPainter,
        panel: FigurePanel,
        panel_rect: QRectF,
        asset: ImageAsset | None,
        hidden_value: tuple[float, str] | None = None,
    ) -> None:
        if panel.source_node_id is None:
            return
        panel_scale_bars = [
            scale_bar
            for scale_bar in self.project.scale_bars.values()
            if scale_bar.image_node_id == panel.source_node_id
        ]
        for scale_bar in panel_scale_bars:
            pixmap = (
                self._panel_pixmap(panel, panel_rect, asset)
                if asset is not None
                else QPixmap()
            )
            draw_width, _draw_height = self._panel_pixmap_draw_size(
                pixmap,
                panel_rect,
                max(0.1, panel.crop[2]),
                float(panel.rotation),
            )
            source_width = (
                max(1.0, float(asset.width or pixmap.width() or 1))
                if asset is not None
                else 1.0
            )
            display_scale = draw_width / source_width
            physical_length, pixel_length = adjusted_scale_bar_length(
                self._board,
                float(scale_bar.physical_length),
                float(scale_bar.pixel_length),
                display_scale,
                panel_rect.width(),
            )
            length = max(
                4.0,
                pixel_length * display_scale,
            )
            board_zoom = self._board_zoom_scale()
            thickness = max(
                1.0,
                scale_bar.width_px * board_zoom,
            )
            padding_x = max(3.0, panel_rect.width() * 0.02)
            padding_y = max(3.0, panel_rect.height() * 0.02)
            font_size = max(2, int(round(scale_bar.font_size * board_zoom)))
            text_height = max(float(font_size) * 1.6, 6.0)
            x = panel_rect.right() - length - padding_x
            show_value = scale_bar.display_length and hidden_value != (
                round(float(physical_length), 9),
                str(scale_bar.unit),
            )
            y = panel_rect.bottom() - thickness - padding_y - (text_height if show_value else 0.0)
            x = max(panel_rect.left() + padding_x, x)
            y = max(panel_rect.top() + padding_y, y)
            painter.setPen(QPen(QColor(scale_bar.foreground), thickness))
            painter.drawLine(QPointF(x, y), QPointF(x + length, y))
            if show_value:
                painter.setFont(
                    QFont(
                        safe_font_family(scale_bar.font_family),
                        font_size,
                    )
                )
                painter.drawText(
                    QRectF(x, y + thickness + 1.0, length, text_height),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{physical_length:g} {scale_bar.unit}",
                )

    def _draw_panel_annotations(
        self,
        painter: QPainter,
        panel: FigurePanel,
        image_rect: QRectF,
        source_size: QSize,
    ) -> None:
        if panel.source_node_id is None:
            return
        board_zoom = self._board_zoom_scale()
        for annotation in self.project.annotations.values():
            if annotation.image_node_id != panel.source_node_id or not annotation.visible:
                continue
            color = QColor(annotation.color)
            if not color.isValid():
                color = QColor("#ffffff")
            line_width = max(0.5, annotation.line_width * board_zoom)
            painter.setPen(QPen(color, line_width))
            annotation_points = (
                normalize_wedge_points(list(annotation.points))
                if annotation.kind is AnnotationKind.WEDGE
                else annotation.points
            )
            points = [
                QPointF(
                    image_rect.x() + x * image_rect.width(),
                    image_rect.y() + y * image_rect.height(),
                )
                for x, y in annotation_points
            ]
            if annotation.kind is AnnotationKind.TEXT and points:
                font_size = max(2, int(round(annotation.size * board_zoom)))
                anchor = painter.transform().map(points[0])
                painter.save()
                painter.resetTransform()
                painter.setPen(QPen(color, max(0.5, line_width)))
                font = QFont(safe_font_family(annotation.font), font_size)
                painter.setFont(font)
                text = annotation.text or "Label"
                text_rect = _annotation_text_rect(anchor, font, text)
                painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)
                if self._overlay_is_selected("annotation", annotation.id):
                    self._draw_overlay_selection_box(painter, text_rect)
                painter.restore()
            elif len(points) >= 2:
                if annotation.kind is AnnotationKind.WEDGE:
                    fill = QColor(annotation.fill or annotation.color)
                    if not fill.isValid():
                        fill = QColor(annotation.color)
                    fill.setAlphaF(max(0.0, min(1.0, float(annotation.opacity))))
                    mapped = _normal_wedge_triangle(
                        [painter.transform().map(point) for point in points],
                        0.0,
                    )
                    painter.save()
                    painter.resetTransform()
                    path = QPainterPath(mapped[0])
                    for point in mapped[1:]:
                        path.lineTo(point)
                    path.closeSubpath()
                    painter.setPen(QPen(Qt.PenStyle.NoPen))
                    painter.fillPath(path, QBrush(fill))
                    painter.restore()
                else:
                    painter.drawLine(points[0], points[1])
                if self._overlay_is_selected("annotation", annotation.id):
                    mapped = [painter.transform().map(point) for point in points]
                    if annotation.kind is AnnotationKind.WEDGE:
                        mapped = _normal_wedge_triangle(
                            mapped,
                            0.0,
                        )
                    if len(mapped) >= 2:
                        self._draw_annotation_edit_box(painter, mapped)
                    else:
                        self._draw_overlay_selection_box(painter, _points_rect(mapped))

    def _draw_panel_measurements(
        self,
        painter: QPainter,
        panel: FigurePanel,
        image_rect: QRectF,
        source_size: QSize,
    ) -> None:
        if panel.source_node_id is None:
            return
        source_width = max(1.0, float(source_size.width()))
        source_height = max(1.0, float(source_size.height()))
        board_zoom = self._board_zoom_scale()
        for measurement in self.project.measurements.values():
            if measurement.image_node_id != panel.source_node_id:
                continue
            color = QColor(measurement.color)
            if not color.isValid():
                color = QColor("#ffe36d")
            painter.setPen(QPen(color, max(0.5, measurement.line_width * board_zoom)))
            path = _measurement_preview_path(measurement, image_rect, source_width, source_height)
            if not path.isEmpty():
                painter.drawPath(path)
            label_pos = _measurement_preview_label_position(
                measurement,
                image_rect,
                source_width,
                source_height,
            )
            font_size = max(2, int(round(measurement.font_size * board_zoom)))
            font = QFont(safe_font_family(measurement.font_family), font_size)
            font.setBold(measurement.bold)
            font.setItalic(measurement.italic)
            painter.setFont(font)
            for text_value, text_pos, rotate in _measurement_preview_text_items(
                measurement,
                label_pos,
                image_rect.width() / source_width,
                image_rect.height() / source_height,
            ):
                if not text_value:
                    continue
                painter.save()
                if rotate and measurement.label_alignment is MeasurementLabelAlignment.ALIGNED:
                    painter.translate(text_pos)
                    painter.rotate(measurement.line_angle_degrees())
                    painter.drawText(QPointF(0, 0), text_value)
                else:
                    anchor = painter.transform().map(text_pos)
                    painter.resetTransform()
                    painter.drawText(anchor, text_value)
                    if self._overlay_is_selected("measurement", measurement.id, target="label" if text_value == measurement.label_text() else "value"):
                        self._draw_overlay_selection_box(
                            painter,
                            QRectF(anchor, QFontMetrics(font).size(0, text_value)),
                        )
                painter.restore()
            if measurement.kind is MeasurementKind.RECTANGLE and measurement.show_side_lengths:
                font = QFont(safe_font_family(measurement.font_family), font_size)
                font.setBold(measurement.bold)
                font.setItalic(measurement.italic)
                painter.setFont(font)
                unit = measurement.display_unit
                width, height = measurement.rectangle_side_lengths_display(unit)
                decimals = max(0, min(6, int(measurement.decimal_places)))
                points = [
                    _measurement_preview_point(point, image_rect, source_width, source_height)
                    for point in measurement.points[:4]
                ]
                if len(points) >= 4:
                    painter.drawText(
                        _midpoint_preview(points[0], points[1]),
                        f"{width:.{decimals}f} {unit}",
                    )
                    painter.drawText(
                        _midpoint_preview(points[1], points[2]),
                        f"{height:.{decimals}f} {unit}",
                    )

    def _overlay_is_selected(
        self,
        kind: str,
        item_id: str,
        *,
        target: str | None = None,
    ) -> bool:
        selected = getattr(self, "_selected_overlay", None)
        if not isinstance(selected, dict):
            return False
        if selected.get("kind") != kind or selected.get("id") != item_id:
            return False
        return target is None or selected.get("target") == target

    def _draw_overlay_selection_box(self, painter: QPainter, rect: QRectF) -> None:
        painter.save()
        painter.resetTransform()
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#2f7dff"), 1.2, Qt.PenStyle.DashLine))
        painter.drawRect(rect.adjusted(-4.0, -4.0, 4.0, 4.0))
        painter.restore()

    def _draw_annotation_edit_box(self, painter: QPainter, points: list[QPointF]) -> None:
        rect = _points_rect(points).normalized().adjusted(-4.0, -4.0, 4.0, 4.0)
        center = _points_center(points)
        handles = _annotation_handle_points(points)
        painter.save()
        painter.resetTransform()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#2f7dff"), 1.2, Qt.PenStyle.DashLine))
        painter.drawRect(rect)
        rotate = handles.get("rotate")
        if rotate is not None:
            painter.drawLine(center, rotate)
        painter.setBrush(QBrush(QColor("#ffffff")))
        painter.setPen(QPen(QColor("#111111"), 1.2))
        for role, point in handles.items():
            if role == "rotate":
                painter.drawEllipse(point, 5.5, 5.5)
            else:
                painter.drawRect(QRectF(point.x() - 4.5, point.y() - 4.5, 9.0, 9.0))
        painter.restore()

    def _draw_wedge_edit_box(self, painter: QPainter, points: list[QPointF]) -> None:
        self._draw_annotation_edit_box(painter, points)


def _measurement_preview_point(
    point: object,
    image_rect: QRectF,
    source_width: float,
    source_height: float,
) -> QPointF:
    return QPointF(
        image_rect.x() + float(point.x) / source_width * image_rect.width(),
        image_rect.y() + float(point.y) / source_height * image_rect.height(),
    )


def _measurement_preview_path(
    measurement: Measurement,
    image_rect: QRectF,
    source_width: float,
    source_height: float,
) -> QPainterPath:
    path = QPainterPath()
    points = [
        _measurement_preview_point(point, image_rect, source_width, source_height)
        for point in measurement.points
    ]
    if measurement.kind is MeasurementKind.LINE and len(points) >= 2:
        path.moveTo(points[0])
        path.lineTo(points[1])
    elif measurement.kind is MeasurementKind.RECTANGLE:
        if len(points) >= 4:
            path.moveTo(points[0])
            for point in points[1:4]:
                path.lineTo(point)
            path.closeSubpath()
        elif len(points) >= 2:
            path.addRect(QRectF(points[0], points[1]).normalized())
    elif measurement.kind is MeasurementKind.ELLIPSE and len(points) >= 2:
        path.addEllipse(QRectF(points[0], points[1]).normalized())
    elif measurement.kind is MeasurementKind.POLYGON and len(points) >= 3:
        path.moveTo(points[0])
        for point in points[1:]:
            path.lineTo(point)
        path.closeSubpath()
    return path


def _measurement_preview_label_position(
    measurement: Measurement,
    image_rect: QRectF,
    source_width: float,
    source_height: float,
) -> QPointF:
    if not measurement.points:
        return QPointF(image_rect.x(), image_rect.y())
    xs = [point.x for point in measurement.points]
    ys = [point.y for point in measurement.points]
    x = sum(xs) / len(xs) + 6.0
    y = min(ys) - 18.0
    if measurement.kind is MeasurementKind.LINE and len(measurement.points) >= 2:
        a, b = measurement.points[0], measurement.points[1]
        x = (a.x + b.x) / 2.0 + 6.0
        y = (a.y + b.y) / 2.0 + 6.0
    return _measurement_preview_point(
        type("_Point", (), {"x": x, "y": y})(),
        image_rect,
        source_width,
        source_height,
    )


def _measurement_preview_text_items(
    measurement: Measurement,
    base: QPointF,
    x_scale: float,
    y_scale: float,
) -> list[tuple[str, QPointF, bool]]:
    label_pos = QPointF(
        base.x() + measurement.label_offset[0] * x_scale,
        base.y() + measurement.label_offset[1] * y_scale,
    )
    value_y_shift = 18.0 * y_scale if measurement.show_label and measurement.label else 0.0
    value_pos = QPointF(
        base.x() + measurement.value_offset[0] * x_scale,
        base.y() + measurement.value_offset[1] * y_scale + value_y_shift,
    )
    return [
        (measurement.label_text(), label_pos, False),
        (measurement.value_text(), value_pos, True),
    ]


def _midpoint_preview(a: QPointF, b: QPointF) -> QPointF:
    return QPointF((a.x() + b.x()) / 2.0 + 4.0, (a.y() + b.y()) / 2.0 + 4.0)


def _points_rect(points: list[QPointF]) -> QRectF:
    if not points:
        return QRectF()
    left = min(point.x() for point in points)
    top = min(point.y() for point in points)
    right = max(point.x() for point in points)
    bottom = max(point.y() for point in points)
    return QRectF(QPointF(left, top), QPointF(right, bottom))


def _points_center(points: list[QPointF]) -> QPointF:
    return QPointF(
        sum(point.x() for point in points) / max(1, len(points)),
        sum(point.y() for point in points) / max(1, len(points)),
    )


def _annotation_handle_points(points: list[QPointF]) -> dict[str, QPointF]:
    rect = _points_rect(points).normalized().adjusted(-4.0, -4.0, 4.0, 4.0)
    center = _points_center(points)
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


def _wedge_handle_points(points: list[QPointF]) -> dict[str, QPointF]:
    return _annotation_handle_points(points)


def _normal_wedge_triangle(points: list[QPointF], minimum_base_width: float) -> list[QPointF]:
    if len(points) < 2:
        return points
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
        return points
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


def _visible_wedge_points(points: list[QPointF], minimum_base_width: float) -> list[QPointF]:
    return _normal_wedge_triangle(points, minimum_base_width)

