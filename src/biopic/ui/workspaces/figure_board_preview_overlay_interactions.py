"""Overlay hit-testing and movement for figure-board preview."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, QSize
from PySide6.QtGui import QFont, QPainterPath, QPainterPathStroker

from biopic.imaging.project_render import asset_for_source_node
from biopic.models.annotations import AnnotationKind, normalize_wedge_points
from biopic.models.figure_board import adjusted_scale_bar_length
from biopic.models.measurement import MeasurementKind, MeasurementLabelAlignment
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas_overlays import _transformed_wedge_points
from biopic.ui.workspace_helpers.common import point_distance as _point_distance
from biopic.ui.workspaces.figure_board_preview_overlays import (
    _annotation_handle_points,
    _annotation_text_rect,
    _measurement_preview_label_position,
    _measurement_preview_path,
    _measurement_preview_point,
    _measurement_preview_text_items,
    _midpoint_preview,
    _points_center,
    _visible_wedge_points,
)


class FigureBoardPreviewOverlayInteractionMixin:
    def _overlay_at(self, position: QPointF) -> dict[str, object] | None:
        if self._board is None:
            return None
        printable = self._printable_rect(self._page_rect())
        content_rect = self._content_rect(printable)
        for panel in reversed(self._board.panels):
            if panel.source_node_id is None:
                continue
            panel_rect = self._panel_rect(panel, content_rect)
            geometry = self._panel_image_hit_geometry(panel, panel_rect)
            if geometry is None:
                continue
            transform, local_rect, source_size = geometry
            hit = self._annotation_overlay_at(panel.source_node_id, position, transform, local_rect)
            if hit is not None:
                hit["panel_id"] = panel.id
                return hit
            hit = self._measurement_overlay_at(
                panel.source_node_id,
                position,
                transform,
                local_rect,
                source_size,
            )
            if hit is not None:
                hit["panel_id"] = panel.id
                return hit
        return None

    def _common_displayed_scale_bar_value_key(
        self,
        content_rect: QRectF,
    ) -> tuple[float, str] | None:
        if self._board is None or not self._board.hide_common_scale_bar_value:
            return None
        counts: dict[tuple[float, str], int] = {}
        for panel in self._board.panels:
            if panel.source_node_id is None:
                continue
            asset = asset_for_source_node(self.project, panel.source_node_id)
            if asset is None:
                continue
            panel_rect = self._panel_rect(panel, content_rect)
            pixmap = self._panel_pixmap(panel, panel_rect, asset)
            draw_width, _draw_height = self._panel_pixmap_draw_size(
                pixmap,
                panel_rect,
                max(0.1, panel.crop[2]),
                float(panel.rotation),
            )
            source_width = max(1.0, float(asset.width or pixmap.width() or 1))
            display_scale = draw_width / source_width
            for scale_bar in self.project.scale_bars.values():
                if scale_bar.image_node_id != panel.source_node_id or not scale_bar.display_length:
                    continue
                physical_length, _pixel_length = adjusted_scale_bar_length(
                    self._board,
                    float(scale_bar.physical_length),
                    float(scale_bar.pixel_length),
                    display_scale,
                    panel_rect.width(),
                )
                key = (round(float(physical_length), 9), str(scale_bar.unit))
                counts[key] = counts.get(key, 0) + 1
        repeated = [(count, key) for key, count in counts.items() if count > 1]
        if not repeated:
            return None
        repeated.sort(key=lambda item: (-item[0], item[1]))
        return repeated[0][1]

    def _panel_image_hit_geometry(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
    ) -> tuple[object, QRectF, QSize] | None:
        asset = asset_for_source_node(self.project, panel.source_node_id or "")
        if asset is None:
            return None
        pixmap = self._panel_pixmap(panel, panel_rect, asset)
        if pixmap.isNull():
            return None
        transform, local_rect, _polygon = self._image_transform_geometry(panel, panel_rect, pixmap)
        source_size = QSize(
            max(1, int(asset.width or pixmap.width())),
            max(1, int(asset.height or pixmap.height())),
        )
        return transform, local_rect, source_size

    def _measurement_overlay_at(
        self,
        source_node_id: str,
        position: QPointF,
        transform: object,
        image_rect: QRectF,
        source_size: QSize,
    ) -> dict[str, object] | None:
        source_width = max(1.0, float(source_size.width()))
        source_height = max(1.0, float(source_size.height()))
        x_scale = image_rect.width() / source_width
        y_scale = image_rect.height() / source_height
        for measurement in reversed(list(self.project.measurements.values())):
            if measurement.image_node_id != source_node_id:
                continue
            base = _measurement_preview_label_position(
                measurement,
                image_rect,
                source_width,
                source_height,
            )
            for target, (_text, local_pos, _rotate) in zip(
                ("label", "value"),
                _measurement_preview_text_items(measurement, base, x_scale, y_scale),
                strict=True,
            ):
                widget_pos = transform.map(local_pos)
                if _point_distance(position, widget_pos) <= 28.0:
                    return {
                        "kind": "measurement",
                        "id": measurement.id,
                        "target": target,
                        "transform": transform,
                        "image_rect": image_rect,
                        "source_size": source_size,
                        "start_label_offset": measurement.label_offset,
                        "start_value_offset": measurement.value_offset,
                    }
            local_position = transform.inverted()[0].map(position)
            path = _measurement_preview_path(
                measurement,
                image_rect,
                source_width,
                source_height,
            )
            stroker = QPainterPathStroker()
            stroker.setWidth(max(10.0, 18.0 / max(0.05, self._board_zoom_scale())))
            if stroker.createStroke(path).contains(local_position):
                return {
                    "kind": "measurement",
                    "id": measurement.id,
                    "target": "geometry",
                    "transform": transform,
                    "image_rect": image_rect,
                    "source_size": source_size,
                    "start_points": [
                        (point.x, point.y)
                        for point in measurement.points
                    ],
                }
        return None

    def _annotation_overlay_at(
        self,
        source_node_id: str,
        position: QPointF,
        transform: object,
        image_rect: QRectF,
    ) -> dict[str, object] | None:
        for annotation in reversed(list(self.project.annotations.values())):
            if annotation.image_node_id != source_node_id or not annotation.visible:
                continue
            annotation_points = (
                normalize_wedge_points(list(annotation.points))
                if annotation.kind is AnnotationKind.WEDGE
                else annotation.points
            )
            points = [
                transform.map(
                    QPointF(
                        image_rect.x() + x * image_rect.width(),
                        image_rect.y() + y * image_rect.height(),
                    )
                )
                for x, y in annotation_points
            ]
            local_points = [
                QPointF(
                    image_rect.x() + x * image_rect.width(),
                    image_rect.y() + y * image_rect.height(),
                )
                for x, y in annotation_points
            ]
            if (
                annotation.kind in {AnnotationKind.WEDGE, AnnotationKind.LINE, AnnotationKind.ARROW}
                and len(points) >= 2
                and self._overlay_is_selected("annotation", annotation.id)
            ):
                role = _annotation_handle_at(points, position)
                if role is not None:
                    return {
                        "kind": "annotation",
                        "id": annotation.id,
                        "target": role,
                        "transform": transform,
                        "image_rect": image_rect,
                        "start_points": list(annotation.points),
                        "start_local_points": local_points,
                        "start_center": _points_center(local_points),
                        "start_handle_point": _annotation_local_handle_point(local_points, role),
                    }
            if annotation.kind is AnnotationKind.TEXT and points:
                font_size = max(2, int(round(annotation.size * self._board_zoom_scale())))
                font = QFont(safe_font_family(annotation.font), font_size)
                text_rect = _annotation_text_rect(
                    points[0],
                    font,
                    annotation.text or "Label",
                ).adjusted(-4.0, -4.0, 4.0, 4.0)
                if text_rect.contains(position):
                    return {
                        "kind": "annotation",
                        "id": annotation.id,
                        "transform": transform,
                        "image_rect": image_rect,
                        "start_points": list(annotation.points),
                }
                continue
            if annotation.kind is AnnotationKind.WEDGE and len(points) >= 2:
                visible_points = _visible_wedge_points(
                    points,
                    0.0,
                )
                path = QPainterPath(visible_points[0])
                for point in visible_points[1:]:
                    path.lineTo(point)
                path.closeSubpath()
                if path.contains(position):
                    return {
                        "kind": "annotation",
                        "id": annotation.id,
                        "transform": transform,
                        "image_rect": image_rect,
                        "start_points": list(annotation.points),
                    }
            if annotation.kind in {AnnotationKind.LINE, AnnotationKind.ARROW} and len(points) >= 2:
                path = QPainterPath(points[0])
                path.lineTo(points[1])
                stroker = QPainterPathStroker()
                stroker.setWidth(max(10.0, 18.0 / max(0.05, self._board_zoom_scale())))
                if stroker.createStroke(path).contains(position):
                    return {
                        "kind": "annotation",
                        "id": annotation.id,
                        "transform": transform,
                        "image_rect": image_rect,
                        "start_points": list(annotation.points),
                    }
            if any(_point_distance(position, point) <= 12.0 for point in points):
                return {
                    "kind": "annotation",
                    "id": annotation.id,
                    "transform": transform,
                    "image_rect": image_rect,
                    "start_points": list(annotation.points),
                }
        return None

    def _move_overlay_drag(self, position: QPointF) -> None:
        drag = self._overlay_drag
        if drag is None:
            return
        start_position = drag.get("start_position")
        transform = drag.get("transform")
        if not isinstance(start_position, QPointF) or transform is None:
            return
        inverse, invertible = transform.inverted()
        if not invertible:
            return
        start_local = inverse.map(start_position)
        current_local = inverse.map(position)
        delta_local = current_local - start_local
        if drag.get("kind") == "annotation":
            annotation = self.project.annotations.get(str(drag.get("id")))
            image_rect = drag.get("image_rect")
            start_points = drag.get("start_points")
            if annotation is None or not isinstance(image_rect, QRectF) or not isinstance(start_points, list):
                return
            target = str(drag.get("target") or "")
            if target in {"start", "end", "length", "width_a", "width_b", "scale", "rotate"}:
                start_local_points = drag.get("start_local_points")
                center = drag.get("start_center")
                handle_point = drag.get("start_handle_point")
                if (
                    not isinstance(start_local_points, list)
                    or not isinstance(center, QPointF)
                    or not isinstance(handle_point, QPointF)
                    or len(start_local_points) < 2
                ):
                    return
                updated = _transformed_wedge_points(
                    start_local_points,
                    center,
                    target,
                    handle_point,
                    current_local,
                )
                fitted = updated
                annotation.points = [
                    (
                        (point.x() - image_rect.x()) / max(1.0, image_rect.width()),
                        (point.y() - image_rect.y()) / max(1.0, image_rect.height()),
                    )
                    for point in fitted
                ]
                if annotation.kind is AnnotationKind.WEDGE:
                    annotation.points = normalize_wedge_points(annotation.points)
                return
            dx = delta_local.x() / max(1.0, image_rect.width())
            dy = delta_local.y() / max(1.0, image_rect.height())
            if annotation.kind is AnnotationKind.WEDGE:
                annotation.points = [(float(x) + dx, float(y) + dy) for x, y in start_points]
                annotation.points = normalize_wedge_points(annotation.points)
            else:
                annotation.points = [
                    (
                        max(0.0, min(1.0, float(x) + dx)),
                        max(0.0, min(1.0, float(y) + dy)),
                    )
                    for x, y in start_points
                ]
            return
        measurement = self.project.measurements.get(str(drag.get("id")))
        source_size = drag.get("source_size")
        image_rect = drag.get("image_rect")
        if measurement is None or not isinstance(source_size, QSize) or not isinstance(image_rect, QRectF):
            return
        dx = delta_local.x() / max(1.0, image_rect.width()) * source_size.width()
        dy = delta_local.y() / max(1.0, image_rect.height()) * source_size.height()
        if drag.get("target") == "geometry":
            start_points = drag.get("start_points")
            if not isinstance(start_points, list):
                return
            measurement.points = [
                type(point)(
                    max(0.0, min(float(source_size.width()), float(x) + dx)),
                    max(0.0, min(float(source_size.height()), float(y) + dy)),
                )
                for point, (x, y) in zip(measurement.points, start_points, strict=False)
            ]
        elif drag.get("target") == "label":
            start_offset = drag.get("start_label_offset")
            if isinstance(start_offset, tuple):
                measurement.label_offset = (float(start_offset[0]) + dx, float(start_offset[1]) + dy)
        else:
            start_offset = drag.get("start_value_offset")
            if isinstance(start_offset, tuple):
                measurement.value_offset = (float(start_offset[0]) + dx, float(start_offset[1]) + dy)


def _annotation_handle_at(points: list[QPointF], position: QPointF) -> str | None:
    handles = _annotation_handle_points(points)
    for role in ("rotate", "scale", "start", "end", "length", "width_a", "width_b"):
        handle = handles.get(role)
        if handle is None:
            continue
        if _point_distance(position, handle) <= 10.0:
            return role
    return None


def _annotation_local_handle_point(points: list[QPointF], role: str) -> QPointF:
    handles = _annotation_handle_points(points)
    return QPointF(handles.get(role, _points_center(points)))


def _fit_points_inside_rect(points: list[QPointF], rect: QRectF) -> list[QPointF]:
    if not points:
        return []
    normalized_rect = rect.normalized()
    min_x = min(point.x() for point in points)
    max_x = max(point.x() for point in points)
    min_y = min(point.y() for point in points)
    max_y = max(point.y() for point in points)
    shape_width = max_x - min_x
    shape_height = max_y - min_y
    scale = 1.0
    if shape_width > normalized_rect.width() and shape_width > 0.0:
        scale = min(scale, normalized_rect.width() / shape_width)
    if shape_height > normalized_rect.height() and shape_height > 0.0:
        scale = min(scale, normalized_rect.height() / shape_height)
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
    if min_x < normalized_rect.left():
        dx = normalized_rect.left() - min_x
    elif max_x > normalized_rect.right():
        dx = normalized_rect.right() - max_x
    if min_y < normalized_rect.top():
        dy = normalized_rect.top() - min_y
    elif max_y > normalized_rect.bottom():
        dy = normalized_rect.bottom() - max_y
    return [QPointF(point.x() + dx, point.y() + dy) for point in fitted]


