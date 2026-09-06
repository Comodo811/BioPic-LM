"""Geometry and hit-testing helpers for the figure-board preview."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPixmap,
    QPolygonF,
    QTransform,
)

from biopic.imaging.project_render import asset_for_source_node
from biopic.models.figure_board import FigurePanel
from biopic.ui.fonts import safe_font_family


class FigureBoardPreviewGeometryMixin:
    def _page_rect(self) -> QRectF:
        if self._board is None:
            return QRectF()
        width_mm = self._page_width_mm(self._board.page)
        height_mm = self._page_height_mm(self._board.page)
        screen = self.screen()
        pixels_per_mm = (
            screen.physicalDotsPerInch() / 25.4 if screen is not None else 96.0 / 25.4
        )
        bounds = self.rect().adjusted(24, 24, -24, -24)
        scale = self._zoom_percent / 100.0
        page_width = width_mm * pixels_per_mm * scale
        page_height = height_mm * pixels_per_mm * scale
        return QRectF(
            max(24.0, bounds.x() + (bounds.width() - page_width) / 2.0),
            max(24.0, bounds.y() + (bounds.height() - page_height) / 2.0),
            page_width,
            page_height,
        )

    def _printable_rect(self, page_rect: QRectF) -> QRectF:
        if self._board is None:
            return page_rect
        width_mm = self._page_width_mm(self._board.page)
        height_mm = self._page_height_mm(self._board.page)
        left = page_rect.width() * self._board.margin_left / max(1.0, width_mm)
        right = page_rect.width() * self._board.margin_right / max(1.0, width_mm)
        top = page_rect.height() * self._board.margin_top / max(1.0, height_mm)
        bottom = page_rect.height() * self._board.margin_bottom / max(1.0, height_mm)
        caption_height = self._caption_height(page_rect)
        handle_clearance = max(10.0, page_rect.width() * 0.008) if caption_height > 0 else 0.0
        return page_rect.adjusted(left, top, -right, -(bottom + caption_height + handle_clearance))

    def _caption_rect(self, page_rect: QRectF) -> QRectF:
        if self._board is None:
            return QRectF()
        height = self._caption_height(page_rect)
        if height <= 0:
            return QRectF()
        width_mm = self._page_width_mm(self._board.page)
        height_mm = self._page_height_mm(self._board.page)
        left = page_rect.width() * self._board.margin_left / max(1.0, width_mm)
        right = page_rect.width() * self._board.margin_right / max(1.0, width_mm)
        bottom = page_rect.height() * self._board.margin_bottom / max(1.0, height_mm)
        return QRectF(
            page_rect.x() + left,
            page_rect.bottom() - bottom - height,
            page_rect.width() - left - right,
            height,
        )

    def _caption_height(self, page_rect: QRectF) -> float:
        if self._board is None:
            return 0.0
        text = self._board.caption.visible_text().strip()
        if not text:
            return page_rect.height() * 0.08
        lines = max(2, len(text.splitlines()))
        line_height = self._paper_length_px(page_rect, 4.2)
        return min(
            page_rect.height() * 0.35,
            max(page_rect.height() * 0.10, lines * line_height),
        )

    def _draw_workspace_watermark(self, painter: QPainter) -> None:
        if self._watermark_pixmap.isNull():
            return
        target_size = min(self.width(), self.height()) * 0.82
        if target_size <= 1:
            return
        target = QRectF(
            (self.width() - target_size) / 2.0,
            (self.height() - target_size) / 2.0,
            target_size,
            target_size,
        )
        painter.save()
        painter.setOpacity(0.055)
        painter.drawPixmap(target, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))
        painter.restore()

    def _paper_font(
        self,
        page_rect: QRectF,
        point_size: float,
        weight: QFont.Weight = QFont.Weight.Normal,
    ) -> QFont:
        font = QFont("Arial")
        font.setWeight(weight)
        font.setPixelSize(max(1, int(round(self._paper_points_to_px(page_rect, point_size)))))
        return font

    def _draw_panel_label(
        self,
        painter: QPainter,
        panel: FigurePanel,
        panel_rect: QRectF,
        page_rect: QRectF,
    ) -> None:
        label = panel.label.strip()
        if not label:
            return
        weight = QFont.Weight.Bold if panel.label_bold else QFont.Weight.Normal
        font = self._paper_font(page_rect, panel.label_font_size_pt, weight)
        font.setFamily(safe_font_family(panel.label_font_family))
        font.setItalic(panel.label_italic)
        metrics = QFontMetrics(font)
        label_width = max(18, metrics.horizontalAdvance(label) + 10)
        label_height = max(18, metrics.height() + 5)
        raw_offset_x = self._panel_label_offset_px(
            panel.label_offset[0],
            panel_rect.width(),
            page_rect,
        )
        raw_offset_y = self._panel_label_offset_px(
            panel.label_offset[1],
            panel_rect.height(),
            page_rect,
        )
        label_offset_x = max(
            2.0,
            min(raw_offset_x, max(2.0, panel_rect.width() - label_width - 2.0)),
        )
        label_offset_y = max(
            2.0,
            min(raw_offset_y, max(2.0, panel_rect.height() - label_height - 2.0)),
        )
        label_rect = QRectF(
            panel_rect.x() + label_offset_x,
            panel_rect.y() + label_offset_y,
            min(label_width, max(12.0, panel_rect.width() - label_offset_x - 2.0)),
            min(label_height, max(12.0, panel_rect.height() - label_offset_y - 2.0)),
        )
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setFont(font)
        color = QColor(panel.label_color)
        if not color.isValid():
            color = QColor("#111111")
        painter.setPen(color)
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, label)
        painter.restore()

    def _panel_label_offset_px(
        self,
        stored_offset: float,
        panel_length_px: float,
        page_rect: QRectF,
    ) -> float:
        if stored_offset <= 1.0:
            return stored_offset * panel_length_px
        return self._paper_length_px(page_rect, stored_offset)

    def _paper_points_to_px(self, page_rect: QRectF, points: float) -> float:
        return self._paper_length_px(page_rect, points * 25.4 / 72.0)

    def _paper_length_px(self, page_rect: QRectF, length_mm: float) -> float:
        if self._board is None:
            return length_mm * 96.0 / 25.4
        page_width_mm = self._page_width_mm(self._board.page)
        return page_rect.width() * length_mm / max(1.0, page_width_mm)

    def _panel_at(self, position: QPointF) -> FigurePanel | None:
        if self._board is None:
            return None
        printable = self._content_rect(self._printable_rect(self._page_rect()))
        for panel in self._board.panels:
            panel_rect = self._panel_rect(panel, printable)
            if panel_rect.contains(position):
                return panel
        return None

    def _panel_rect(self, panel: FigurePanel, printable: QRectF) -> QRectF:
        if self._board is None:
            return QRectF()
        x = printable.x() + panel.rect[0] * printable.width()
        y = printable.y() + panel.rect[1] * printable.height()
        width = panel.rect[2] * printable.width()
        height = panel.rect[3] * printable.height()
        gutter_x = self._mm_to_preview_px(
            self._board.horizontal_gutter, self._page_width_mm(self._board.page), printable.width()
        )
        gutter_y = self._mm_to_preview_px(
            self._board.vertical_gutter, self._page_height_mm(self._board.page), printable.height()
        )
        left_gap = 0.0 if panel.rect[0] <= 0.0 else gutter_x / 2.0
        right_gap = 0.0 if panel.rect[0] + panel.rect[2] >= 1.0 else gutter_x / 2.0
        top_gap = 0.0 if panel.rect[1] <= 0.0 else gutter_y / 2.0
        bottom_gap = 0.0 if panel.rect[1] + panel.rect[3] >= 1.0 else gutter_y / 2.0
        return QRectF(
            x + left_gap,
            y + top_gap,
            max(1.0, width - left_gap - right_gap),
            max(1.0, height - top_gap - bottom_gap),
        )

    def _content_rect(self, printable: QRectF) -> QRectF:
        if self._board is None:
            return printable
        x, y, width, height = self._board.content_rect
        return QRectF(
            printable.x() + x * printable.width(),
            printable.y() + y * printable.height(),
            width * printable.width(),
            height * printable.height(),
        )

    def _panel_by_id(self, panel_id: str) -> FigurePanel | None:
        if self._board is None:
            return None
        for panel in self._board.panels:
            if panel.id == panel_id:
                return panel
        return None

    def _image_center(self, panel: FigurePanel, panel_rect: QRectF) -> QPointF:
        return QPointF(
            panel_rect.x() + panel.crop[0] * panel_rect.width(),
            panel_rect.y() + panel.crop[1] * panel_rect.height(),
        )

    def _image_transform_geometry(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        pixmap: QPixmap,
    ) -> tuple[QTransform, QRectF, QPolygonF]:
        draw_width, draw_height = self._panel_pixmap_draw_size(
            pixmap,
            panel_rect,
            max(0.1, panel.crop[2]),
            float(panel.rotation),
        )
        local_rect = QRectF(-draw_width / 2.0, -draw_height / 2.0, draw_width, draw_height)
        center = self._image_center(panel, panel_rect)
        transform = QTransform()
        transform.translate(center.x(), center.y())
        if abs(panel.rotation) > 0.001:
            transform.rotate(panel.rotation)
        return transform, local_rect, transform.map(QPolygonF(local_rect))

    def _bounded_image_center(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        center_x: float,
        center_y: float,
    ) -> tuple[float, float]:
        min_visible = 0.20
        draw_width = panel_rect.width() * max(0.1, panel.crop[2])
        draw_height = panel_rect.height() * max(0.1, panel.crop[2])
        if panel.source_node_id is not None:
            asset = asset_for_source_node(self.project, panel.source_node_id)
            if asset is not None:
                pixmap = self._panel_pixmap(panel, panel_rect, asset)
                draw_width, draw_height = self._panel_pixmap_draw_size(
                    pixmap,
                    panel_rect,
                    max(0.1, panel.crop[2]),
                    float(panel.rotation),
                )
        min_x = min_visible - draw_width / max(1.0, panel_rect.width()) / 2.0
        max_x = 1.0 - min_visible + draw_width / max(1.0, panel_rect.width()) / 2.0
        min_y = min_visible - draw_height / max(1.0, panel_rect.height()) / 2.0
        max_y = 1.0 - min_visible + draw_height / max(1.0, panel_rect.height()) / 2.0
        return max(min_x, min(max_x, center_x)), max(min_y, min(max_y, center_y))

    def _image_handle_rects(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        pixmap: QPixmap,
    ) -> dict[str, QRectF]:
        _ = (panel, pixmap)
        return self._image_panel_handle_rects(panel_rect)

    def _image_panel_handle_rects(self, panel_rect: QRectF) -> dict[str, QRectF]:
        """Return only the fixed panel-boundary image transform handles."""
        handles = {
            f"scale_{name}": rect for name, rect in self._corner_handles(panel_rect).items()
        }
        handles["rotate"] = self._rotate_handle(panel_rect)
        return handles

    def _image_handle_at(
        self,
        point: QPointF,
        panel: FigurePanel,
        panel_rect: QRectF,
    ) -> str | None:
        if panel.source_node_id is None:
            return None
        handles = self._image_panel_handle_rects(panel_rect)
        for name, rect in handles.items():
            if rect.contains(point):
                return name
        return None

    def _panel_resize_handles(self, panel_rect: QRectF) -> dict[str, QRectF]:
        panel = self._panel_by_id(self._selected_panel_id) if self._selected_panel_id else None
        size = max(12.0, min(22.0, min(panel_rect.width(), panel_rect.height()) * 0.075))
        half = size / 2.0
        handles = {
            "panel_resize_l": QRectF(
                panel_rect.left() - half, panel_rect.center().y() - half, size, size
            ),
            "panel_resize_r": QRectF(
                panel_rect.right() - half, panel_rect.center().y() - half, size, size
            ),
            "panel_resize_t": QRectF(
                panel_rect.center().x() - half, panel_rect.top() - half, size, size
            ),
            "panel_resize_b": QRectF(
                panel_rect.center().x() - half, panel_rect.bottom() - half, size, size
            ),
        }
        if panel is None:
            return handles
        return {
            name: rect
            for name, rect in handles.items()
            if self._panel_resize_side_is_open(panel, name[-1])
        }

    def _panel_resize_handle_at(self, point: QPointF, panel_rect: QRectF) -> str | None:
        for name, rect in self._panel_resize_handles(panel_rect).items():
            if rect.contains(point):
                return name
        return None

    def _panel_resize_side_is_open(self, panel: FigurePanel, side: str) -> bool:
        if self._board is None:
            return False
        x, y, width, height = panel.rect
        if side == "l":
            if x <= 1e-4:
                return True
            return not any(
                other.id != panel.id
                and abs(other.rect[0] + other.rect[2] - x) < 1e-4
                and _ranges_overlap((other.rect[1], other.rect[1] + other.rect[3]), (y, y + height))
                for other in self._board.panels
            )
        if side == "r":
            boundary = x + width
            if boundary >= 1.0 - 1e-4:
                return True
            return not any(
                other.id != panel.id
                and abs(other.rect[0] - boundary) < 1e-4
                and _ranges_overlap((other.rect[1], other.rect[1] + other.rect[3]), (y, y + height))
                for other in self._board.panels
            )
        if side == "t":
            if y <= 1e-4:
                return True
            return not any(
                other.id != panel.id
                and abs(other.rect[1] + other.rect[3] - y) < 1e-4
                and _ranges_overlap((other.rect[0], other.rect[0] + other.rect[2]), (x, x + width))
                for other in self._board.panels
            )
        if side == "b":
            boundary = y + height
            if boundary >= 1.0 - 1e-4:
                return True
            return not any(
                other.id != panel.id
                and abs(other.rect[1] - boundary) < 1e-4
                and _ranges_overlap((other.rect[0], other.rect[0] + other.rect[2]), (x, x + width))
                for other in self._board.panels
            )
        return False

    def _divider_at(self, position: QPointF, content: QRectF) -> str | None:
        if self._board is None:
            return None
        tolerance = 8.0
        panels = self._board.panels
        for left in panels:
            left_edge = left.rect[0] + left.rect[2]
            edge_x = content.x() + left_edge * content.width()
            if abs(position.x() - edge_x) > tolerance:
                continue
            for right in panels:
                if right.id == left.id or abs(right.rect[0] - left_edge) > 1e-4:
                    continue
                y0 = max(left.rect[1], right.rect[1])
                y1 = min(left.rect[1] + left.rect[3], right.rect[1] + right.rect[3])
                if y1 <= y0:
                    continue
                top = content.y() + y0 * content.height()
                bottom = content.y() + y1 * content.height()
                if top - tolerance <= position.y() <= bottom + tolerance:
                    return self._divider_token("divider_v", left_edge, y0, y1)
        for top_panel in panels:
            top_edge = top_panel.rect[1] + top_panel.rect[3]
            edge_y = content.y() + top_edge * content.height()
            if abs(position.y() - edge_y) > tolerance:
                continue
            for bottom_panel in panels:
                if bottom_panel.id == top_panel.id or abs(bottom_panel.rect[1] - top_edge) > 1e-4:
                    continue
                x0 = max(top_panel.rect[0], bottom_panel.rect[0])
                x1 = min(
                    top_panel.rect[0] + top_panel.rect[2],
                    bottom_panel.rect[0] + bottom_panel.rect[2],
                )
                if x1 <= x0:
                    continue
                left = content.x() + x0 * content.width()
                right = content.x() + x1 * content.width()
                if left - tolerance <= position.x() <= right + tolerance:
                    return self._divider_token("divider_h", top_edge, x0, x1)
        return None

    def _divider_token(
        self,
        orientation: str,
        boundary: float,
        span_start: float,
        span_end: float,
    ) -> str:
        if self._board is None:
            return f"{orientation}:{boundary:.6f}"
        panels = self._board.panels
        if orientation == "divider_v":
            before = [
                panel
                for panel in panels
                if abs(panel.rect[0] + panel.rect[2] - boundary) < 1e-4
            ]
            after = [
                panel for panel in panels if abs(panel.rect[0] - boundary) < 1e-4
            ]
        else:
            before = [
                panel
                for panel in panels
                if abs(panel.rect[1] + panel.rect[3] - boundary) < 1e-4
            ]
            after = [
                panel for panel in panels if abs(panel.rect[1] - boundary) < 1e-4
            ]
        if len(before) > 1 and len(after) > 1:
            return f"{orientation}:{boundary:.6f}:{span_start:.6f}:{span_end:.6f}"
        return f"{orientation}:{boundary:.6f}"

    def _move_divider(self, position: QPointF, content: QRectF) -> None:
        if self._board is None or self._drag_start is None:
            return
        parts = self._drag_mode.split(":") if self._drag_mode is not None else []
        if len(parts) not in {2, 4}:
            return
        orientation = parts[0]
        boundary_text = parts[1]
        try:
            boundary = float(boundary_text)
        except ValueError:
            return
        min_size = 0.05
        if orientation == "divider_v":
            span = (
                (float(parts[2]), float(parts[3]))
                if len(parts) == 4
                else (0.0, 1.0)
            )
            delta = (position.x() - self._drag_start.x()) / max(1.0, content.width())
            left_ids = [
                panel_id
                for panel_id, rect in self._drag_start_panel_rects.items()
                if abs(rect[0] + rect[2] - boundary) < 1e-4
                and _ranges_overlap((rect[1], rect[1] + rect[3]), span)
            ]
            right_ids = [
                panel_id
                for panel_id, rect in self._drag_start_panel_rects.items()
                if abs(rect[0] - boundary) < 1e-4
                and _ranges_overlap((rect[1], rect[1] + rect[3]), span)
            ]
            if not left_ids or not right_ids:
                return
            max_left = min(
                self._drag_start_panel_rects[panel_id][2] - min_size
                for panel_id in left_ids
            )
            max_right = min(
                self._drag_start_panel_rects[panel_id][2] - min_size
                for panel_id in right_ids
            )
            delta = max(-max_left, min(max_right, delta))
            delta = self._snap_divider_delta(boundary, delta, "v")
            for panel_id in left_ids:
                panel = self._panel_by_id(panel_id)
                start = self._drag_start_panel_rects[panel_id]
                if panel is not None:
                    panel.rect = (start[0], start[1], start[2] + delta, start[3])
            for panel_id in right_ids:
                panel = self._panel_by_id(panel_id)
                start = self._drag_start_panel_rects[panel_id]
                if panel is not None:
                    panel.rect = (start[0] + delta, start[1], start[2] - delta, start[3])
        elif orientation == "divider_h":
            span = (
                (float(parts[2]), float(parts[3]))
                if len(parts) == 4
                else (0.0, 1.0)
            )
            delta = (position.y() - self._drag_start.y()) / max(1.0, content.height())
            top_ids = [
                panel_id
                for panel_id, rect in self._drag_start_panel_rects.items()
                if abs(rect[1] + rect[3] - boundary) < 1e-4
                and _ranges_overlap((rect[0], rect[0] + rect[2]), span)
            ]
            bottom_ids = [
                panel_id
                for panel_id, rect in self._drag_start_panel_rects.items()
                if abs(rect[1] - boundary) < 1e-4
                and _ranges_overlap((rect[0], rect[0] + rect[2]), span)
            ]
            if not top_ids or not bottom_ids:
                return
            max_top = min(
                self._drag_start_panel_rects[panel_id][3] - min_size
                for panel_id in top_ids
            )
            max_bottom = min(
                self._drag_start_panel_rects[panel_id][3] - min_size
                for panel_id in bottom_ids
            )
            delta = max(-max_top, min(max_bottom, delta))
            delta = self._snap_divider_delta(boundary, delta, "h")
            for panel_id in top_ids:
                panel = self._panel_by_id(panel_id)
                start = self._drag_start_panel_rects[panel_id]
                if panel is not None:
                    panel.rect = (start[0], start[1], start[2], start[3] + delta)
            for panel_id in bottom_ids:
                panel = self._panel_by_id(panel_id)
                start = self._drag_start_panel_rects[panel_id]
                if panel is not None:
                    panel.rect = (start[0], start[1] + delta, start[2], start[3] - delta)

    def _snap_divider_delta(self, boundary: float, delta: float, orientation: str) -> float:
        snap_points = [0.25, 1.0 / 3.0, 0.5, 2.0 / 3.0, 0.75]
        if self._board is not None:
            if orientation == "v":
                snap_points.extend(
                    panel.rect[0]
                    for panel in self._board.panels
                    if abs(panel.rect[0] - boundary) > 1e-4
                )
                snap_points.extend(
                    panel.rect[0] + panel.rect[2]
                    for panel in self._board.panels
                    if abs(panel.rect[0] + panel.rect[2] - boundary) > 1e-4
                )
            else:
                snap_points.extend(
                    panel.rect[1]
                    for panel in self._board.panels
                    if abs(panel.rect[1] - boundary) > 1e-4
                )
                snap_points.extend(
                    panel.rect[1] + panel.rect[3]
                    for panel in self._board.panels
                    if abs(panel.rect[1] + panel.rect[3] - boundary) > 1e-4
                )
        target = boundary + delta
        for snap in snap_points:
            if abs(target - snap) < 0.015:
                return snap - boundary
        return delta


def _ranges_overlap(
    first: tuple[float, float],
    second: tuple[float, float],
    *,
    tolerance: float = 1e-4,
) -> bool:
    return min(first[1], second[1]) - max(first[0], second[0]) > tolerance
