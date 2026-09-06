"""Painting for the interactive figure-board preview."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QPixmap

from biopic.imaging.project_render import asset_for_source_node
from biopic.models.image_asset import ImageAsset


class FigureBoardPreviewPaintingMixin:
    def paintEvent(self, _event: object) -> None:
        """Paint the page, printable area, placeholders and panel labels."""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(
            QPainter.RenderHint.SmoothPixmapTransform,
            not self._is_interacting,
        )
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        if self._workspace_watermark_visible and self._board is None:
            self._draw_workspace_watermark(painter)
        if self._board is None:
            painter.setPen(QColor("#b7b7b7"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "No figure board")
            return
        page_rect = self._page_rect()
        painter.setBrush(QBrush(QColor("#f7f7f2")))
        painter.setPen(QPen(QColor("#101010"), 1))
        painter.drawRect(page_rect)
        printable = self._printable_rect(page_rect)
        caption_rect = self._caption_rect(page_rect)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(QColor("#9a9a9a"), 1, Qt.PenStyle.DashLine))
        content = self._content_rect(printable)
        painter.drawRect(content)
        selected_image_overlay: tuple[FigurePanel, QRectF, QPixmap] | None = None
        vector_overlay_jobs: list[tuple[FigurePanel, QRectF, QSize, float, float]] = []
        hidden_scale_bar_value = self._common_displayed_scale_bar_value_key(content)
        for panel in self._board.panels:
            panel_rect = self._panel_rect(panel, content)
            if panel.source_node_id is None:
                painter.setBrush(QBrush(QColor("#e7e7e2")))
                painter.setPen(QPen(QColor("#555555"), 1))
                painter.drawRect(panel_rect)
                painter.setPen(QColor("#777777"))
                painter.setFont(self._paper_font(page_rect, 9.0))
                painter.drawText(panel_rect, Qt.AlignmentFlag.AlignCenter, "Drop image")
            else:
                asset = asset_for_source_node(self.project, panel.source_node_id)
                if asset is not None:
                    pixmap = self._panel_pixmap(panel, panel_rect, asset)
                    draw_original_panel_image = True
                    baked_pixmap = self._baked_empty_background_pixmap(panel, panel_rect)
                    if not baked_pixmap.isNull():
                        painter.drawPixmap(panel_rect, baked_pixmap, QRectF(baked_pixmap.rect()))
                        draw_original_panel_image = False
                    elif panel.fill_empty_background:
                        filled_pixmap = self._filled_panel_pixmap(panel, panel_rect, asset)
                        if not filled_pixmap.isNull():
                            painter.drawPixmap(panel_rect, filled_pixmap, QRectF(filled_pixmap.rect()))
                            draw_original_panel_image = False
                    if draw_original_panel_image:
                        draw_width, draw_height = self._panel_pixmap_draw_size(
                            pixmap,
                            panel_rect,
                            max(0.1, panel.crop[2]),
                            float(panel.rotation),
                        )
                        painter.save()
                        painter.setClipRect(panel_rect)
                        center_x = panel_rect.x() + panel.crop[0] * panel_rect.width()
                        center_y = panel_rect.y() + panel.crop[1] * panel_rect.height()
                        painter.translate(center_x, center_y)
                        if abs(panel.rotation) > 0.001:
                            painter.rotate(panel.rotation)
                        image_rect = QRectF(
                            -draw_width / 2.0,
                            -draw_height / 2.0,
                            draw_width,
                            draw_height,
                        )
                        painter.drawPixmap(
                            image_rect,
                            pixmap,
                            QRectF(pixmap.rect()),
                        )
                        vector_overlay_jobs.append(
                            (
                                panel,
                                image_rect,
                                QSize(
                                    max(1, int(asset.width or pixmap.width())),
                                    max(1, int(asset.height or pixmap.height())),
                                ),
                                center_x,
                                center_y,
                            )
                        )
                        painter.restore()
                    else:
                        draw_width, draw_height = self._panel_pixmap_draw_size(
                            pixmap,
                            panel_rect,
                            max(0.1, panel.crop[2]),
                            float(panel.rotation),
                        )
                        painter.save()
                        painter.setClipRect(panel_rect)
                        center_x = panel_rect.x() + panel.crop[0] * panel_rect.width()
                        center_y = panel_rect.y() + panel.crop[1] * panel_rect.height()
                        painter.translate(center_x, center_y)
                        if abs(panel.rotation) > 0.001:
                            painter.rotate(panel.rotation)
                        image_rect = QRectF(
                            -draw_width / 2.0,
                            -draw_height / 2.0,
                            draw_width,
                            draw_height,
                        )
                        source_size = QSize(
                            max(1, int(asset.width or pixmap.width() or panel_rect.width())),
                            max(1, int(asset.height or pixmap.height() or panel_rect.height())),
                        )
                        vector_overlay_jobs.append(
                            (
                                panel,
                                image_rect,
                                source_size,
                                center_x,
                                center_y,
                            )
                        )
                        painter.restore()
                else:
                    painter.setBrush(QBrush(QColor("#c9d4dc")))
                    painter.setPen(QPen(QColor("#36556b"), 1))
                    painter.drawRect(panel_rect)
                self._draw_panel_scale_bars(
                    painter,
                    panel,
                    panel_rect,
                    asset,
                    hidden_scale_bar_value,
                )
        for panel, image_rect, source_size, center_x, center_y in vector_overlay_jobs:
            painter.save()
            painter.translate(center_x, center_y)
            if abs(panel.rotation) > 0.001:
                painter.rotate(panel.rotation)
            self._draw_panel_annotations(painter, panel, image_rect, source_size)
            self._draw_panel_measurements(painter, panel, image_rect, source_size)
            painter.restore()
        for panel in self._board.panels:
            panel_rect = self._panel_rect(panel, content)
            asset = (
                asset_for_source_node(self.project, panel.source_node_id)
                if panel.source_node_id is not None
                else None
            )
            self._draw_panel_label(painter, panel, panel_rect, page_rect)
            if panel.id == self._highlight_panel_id:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#76a9ff"), 3))
                painter.drawRect(panel_rect.adjusted(1, 1, -1, -1))
            if panel.id in self._selected_panel_ids:
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.setPen(QPen(QColor("#76a9ff"), 2))
                painter.drawRect(panel_rect.adjusted(2, 2, -2, -2))
            if panel.id == self._selected_panel_id:
                if panel.source_node_id is not None and asset is not None:
                    pixmap = self._panel_pixmap(panel, panel_rect, asset)
                    selected_image_overlay = (panel, panel_rect, pixmap)
                else:
                    self._draw_panel_handles(painter, panel_rect)
        if not caption_rect.isEmpty():
            painter.setBrush(QBrush(QColor("#f7f7f2")))
            painter.setPen(QPen(QColor("#c0c0ba"), 1))
            painter.drawRect(caption_rect)
            painter.setPen(QColor("#111111"))
            painter.setFont(self._paper_font(page_rect, 9.0))
            caption_padding = self._paper_length_px(page_rect, 2.5)
            painter.drawText(
                caption_rect.adjusted(
                    caption_padding,
                    caption_padding,
                    -caption_padding,
                    -caption_padding,
                ),
                Qt.AlignmentFlag.AlignLeft
                | Qt.AlignmentFlag.AlignTop
                | Qt.TextFlag.TextWordWrap,
                self._board.caption.visible_text(),
            )
        if self._highlight_divider is not None:
            self._draw_divider_highlight(painter, content)
        if self._selected_panel_id == "__board__":
            self._draw_board_handles(painter, content)
        if selected_image_overlay is not None:
            panel, panel_rect, pixmap = selected_image_overlay
            self._draw_image_transform_overlay(painter, panel, panel_rect, pixmap, page_rect)


