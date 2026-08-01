"""Interactive figure-board preview widget."""

from __future__ import annotations

from math import atan2, degrees

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu, QWidget

from biopic.imaging.project_render import asset_for_source_node, render_project_image
from biopic.models.annotations import AnnotationKind
from biopic.models.figure_board import (
    FigureBoard,
    FigurePanel,
    PageFormat,
    adjusted_scale_bar_length,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.resources import resource_path
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas import ndarray_to_qimage
from biopic.ui.previews import asset_thumbnail
from biopic.ui.workspace_helpers.common import (
    page_dimension_mm as _page_dimension_mm,
)
from biopic.ui.workspace_helpers.common import (
    point_distance as _point_distance,
)
from biopic.ui.workspaces.figure_board_preview_geometry import FigureBoardPreviewGeometryMixin


class FigureBoardPreview(FigureBoardPreviewGeometryMixin, QWidget):
    """Lightweight publication board preview with real panel placeholders."""

    imageDropped = Signal(str, str)
    panelSelected = Signal(str)
    panelTransformed = Signal(str)
    panelDivideRequested = Signal(str, str)
    panelDeleteRequested = Signal(str)
    panelsMergeRequested = Signal(list)
    panelImageClearRequested = Signal(str)
    panelLabelColorRequested = Signal(str)
    boardEditStarted = Signal(object)
    undoRequested = Signal()
    redoRequested = Signal()
    imageScaleChanged = Signal(float)
    zoomChanged = Signal(int)
    captionClicked = Signal()

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._board: FigureBoard | None = None
        self._highlight_panel_id: str | None = None
        self._selected_panel_id: str | None = None
        self._selected_panel_ids: set[str] = set()
        self._highlight_divider: str | None = None
        self._drag_mode: str | None = None
        self._drag_start: QPointF | None = None
        self._drag_start_crop: tuple[float, float, float] | None = None
        self._drag_start_panel_rect: tuple[float, float, float, float] | None = None
        self._drag_start_content_rect: tuple[float, float, float, float] | None = None
        self._drag_start_panel_rects: dict[str, tuple[float, float, float, float]] = {}
        self._drag_start_rotation = 0.0
        self._is_interacting = False
        self._zoom_percent = 100
        self._panel_pixmap_cache: dict[tuple[object, ...], QPixmap] = {}
        self._watermark_pixmap = QPixmap(str(resource_path("icons", "biopic_logo.png")))
        self._workspace_watermark_visible = True
        self._panel_cache_generation = 0
        self._canvas_size = QSize()
        self._zoom_update_timer = QTimer(self)
        self._zoom_update_timer.setSingleShot(True)
        self._zoom_update_timer.setInterval(24)
        self._zoom_update_timer.timeout.connect(self._apply_zoom_update)
        self._interaction_quality_timer = QTimer(self)
        self._interaction_quality_timer.setSingleShot(True)
        self._interaction_quality_timer.setInterval(140)
        self._interaction_quality_timer.timeout.connect(self._finish_interaction_quality)
        self.setMinimumSize(QSize(1, 1))
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAcceptDrops(True)
        self.setAutoFillBackground(False)

    def set_workspace_watermark_visible(self, visible: bool) -> None:
        self._workspace_watermark_visible = bool(visible)
        self.update()

    def set_board(self, board: FigureBoard | None) -> None:
        """Set the board shown in the preview."""
        self._board = board
        valid_ids = set() if board is None else {panel.id for panel in board.panels}
        self._selected_panel_ids.intersection_update(valid_ids)
        if self._selected_panel_id not in valid_ids and self._selected_panel_id != "__board__":
            self._selected_panel_id = None
        self._panel_pixmap_cache.clear()
        self._update_canvas_size(force=True)
        self.update()

    def invalidate_render_cache(self) -> None:
        """Drop cached panel pixmaps after upstream image or overlay changes."""
        self._panel_cache_generation += 1
        self._panel_pixmap_cache.clear()
        self.update()

    def sizeHint(self) -> QSize:
        """Prefer the current page preview size without forcing the window minimum."""
        return self._canvas_size if self._canvas_size.isValid() else QSize(360, 280)

    def minimumSizeHint(self) -> QSize:
        """Allow the main window to shrink; clipped previews remain interactive."""
        return QSize(1, 1)

    def set_zoom_percent(self, percent: int) -> None:
        """Set board zoom where 100% equals page output pixels."""
        next_zoom = max(10, min(400, int(percent)))
        if next_zoom == self._zoom_percent and not self._zoom_update_timer.isActive():
            return
        self._zoom_percent = next_zoom
        self._is_interacting = True
        self._zoom_update_timer.start()
        self._interaction_quality_timer.start()
        self.zoomChanged.emit(self._zoom_percent)

    def _apply_zoom_update(self) -> None:
        self._update_canvas_size()
        self.update()

    def _finish_interaction_quality(self) -> None:
        if self._drag_mode is None:
            self._is_interacting = False
            self.update()

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
                    draw_width, draw_height = self._panel_pixmap_draw_size(
                        pixmap,
                        panel_rect,
                        max(0.1, panel.crop[2]),
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
                    self._draw_panel_annotations(
                        painter,
                        panel,
                        image_rect,
                        QSize(
                            max(1, int(asset.width or pixmap.width())),
                    max(1, int(asset.height or pixmap.height())),
                        ),
                    )
                    painter.restore()
                else:
                    painter.setBrush(QBrush(QColor("#c9d4dc")))
                    painter.setPen(QPen(QColor("#36556b"), 1))
                    painter.drawRect(panel_rect)
                self._draw_panel_scale_bars(painter, panel, panel_rect, asset)
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

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-biopic-asset-id"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        panel = self._panel_at(event.position())
        self._highlight_panel_id = None if panel is None else panel.id
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._highlight_panel_id = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._board is None:
            super().dropEvent(event)
            return
        mime = event.mimeData()
        if not mime.hasFormat("application/x-biopic-asset-id"):
            super().dropEvent(event)
            return
        panel = self._panel_at(event.position())
        if panel is None:
            return
        asset_id = bytes(mime.data("application/x-biopic-asset-id").data()).decode("utf-8")
        self._highlight_panel_id = None
        self.imageDropped.emit(panel.id, asset_id)
        event.acceptProposedAction()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 10 if event.angleDelta().y() > 0 else -10
            self.set_zoom_percent(self._zoom_percent + delta)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.RightButton and self._board is not None:
            printable = self._printable_rect(self._page_rect())
            panel = self._panel_at(event.position())
            if panel is not None:
                self._selected_panel_id = panel.id
                if panel.id not in self._selected_panel_ids:
                    self._selected_panel_ids = {panel.id}
                self.panelSelected.emit(panel.id)
                menu = QMenu(self)
                clear_image = None
                if panel.source_node_id is not None:
                    clear_image = menu.addAction("Remove Image")
                delete_outline = menu.addAction("Delete Outline")
                merge_selected = None
                if len(self._selected_panel_ids) == 2:
                    merge_selected = menu.addAction("Merge Selected Outlines")
                divide_horizontal = menu.addAction("Divide Horizontally")
                divide_vertical = menu.addAction("Divide Vertically")
                change_label_color = menu.addAction("Change Letter Color")
                selected = menu.exec(event.globalPosition().toPoint())
                if selected == clear_image:
                    self.panelImageClearRequested.emit(panel.id)
                elif selected == delete_outline:
                    self.panelDeleteRequested.emit(panel.id)
                elif selected == merge_selected:
                    self.panelsMergeRequested.emit(list(self._selected_panel_ids))
                elif selected == divide_horizontal:
                    self.panelDivideRequested.emit(panel.id, "horizontal")
                elif selected == divide_vertical:
                    self.panelDivideRequested.emit(panel.id, "vertical")
                elif selected == change_label_color:
                    self.panelLabelColorRequested.emit(panel.id)
                self.update(
                    self._content_rect(printable).adjusted(-48, -48, 48, 48).toAlignedRect()
                )
                event.accept()
                return
        if self._board is not None and self._caption_rect(self._page_rect()).contains(
            event.position()
        ):
            self.captionClicked.emit()
            event.accept()
            return
        printable = self._printable_rect(self._page_rect())
        content_rect = self._content_rect(printable)
        selected_panel = (
            self._panel_by_id(self._selected_panel_id)
            if self._selected_panel_id not in {None, "__board__"}
            else None
        )
        if selected_panel is not None:
            selected_panel_rect = self._panel_rect(selected_panel, content_rect)
            panel_handle = self._panel_resize_handle_at(event.position(), selected_panel_rect)
            if panel_handle is not None:
                self._drag_mode = panel_handle
                self._drag_start = event.position()
                self._drag_start_panel_rect = selected_panel.rect
                self._is_interacting = True
                self._emit_board_edit_started()
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            selected_handle = self._image_handle_at(
                event.position(),
                selected_panel,
                selected_panel_rect,
            )
            if selected_handle is not None:
                self._drag_mode = selected_handle
                self._drag_start = event.position()
                self._drag_start_crop = selected_panel.crop
                self._drag_start_panel_rect = selected_panel.rect
                self._drag_start_rotation = selected_panel.rotation
                self._is_interacting = True
                self._emit_board_edit_started()
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
        divider = self._divider_at(event.position(), content_rect)
        if divider is not None:
            self._selected_panel_id = "__board__"
            self._selected_panel_ids.clear()
            self._highlight_divider = divider
            self._drag_mode = divider
            self._drag_start = event.position()
            self._drag_start_panel_rects = {
                panel.id: panel.rect for panel in self._board.panels
            }
            self._is_interacting = True
            self._emit_board_edit_started()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        if content_rect.contains(event.position()) and self._board_handle_at(
            event.position(), content_rect
        ) is not None:
            self._selected_panel_id = "__board__"
            self._selected_panel_ids.clear()
            self.panelSelected.emit("__board__")
            self._drag_mode = "board_" + (
                self._board_handle_at(event.position(), content_rect) or "move"
            )
            self._drag_start = event.position()
            self._drag_start_content_rect = self._board.content_rect
            self._is_interacting = True
            self._emit_board_edit_started()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        if content_rect.contains(event.position()) and self._panel_at(event.position()) is None:
            self._selected_panel_id = None
            self._selected_panel_ids.clear()
            self._drag_mode = None
            self._drag_start = None
            self._drag_start_content_rect = None
            self._is_interacting = False
            self.unsetCursor()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        panel = self._panel_at(event.position())
        if panel is not None:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if panel.id in self._selected_panel_ids:
                    self._selected_panel_ids.remove(panel.id)
                else:
                    self._selected_panel_ids.add(panel.id)
                if len(self._selected_panel_ids) > 2:
                    self._selected_panel_ids = {panel.id}
                self._selected_panel_id = panel.id
            else:
                self._selected_panel_ids = {panel.id}
                self._selected_panel_id = panel.id
            self.panelSelected.emit(panel.id)
            panel_rect = self._panel_rect(panel, content_rect)
            image_handle = self._image_handle_at(event.position(), panel, panel_rect)
            self._drag_mode = image_handle or "move"
            self._drag_start = event.position()
            self._drag_start_crop = panel.crop
            self._drag_start_panel_rect = panel.rect
            self._drag_start_rotation = panel.rotation
            self._is_interacting = True
            self._emit_board_edit_started()
            self.update(panel_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        self._selected_panel_id = None
        self._selected_panel_ids.clear()
        self._drag_mode = None
        self._drag_start = None
        self._drag_start_content_rect = None
        self._is_interacting = False
        self.unsetCursor()
        self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._board is not None
            and self._selected_panel_id is not None
            and self._drag_mode is not None
            and self._drag_start is not None
        ):
            printable = self._printable_rect(self._page_rect())
            content_rect = self._content_rect(printable)
            if self._drag_mode.startswith("divider_"):
                self._move_divider(event.position(), content_rect)
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            if self._drag_mode.startswith("board_"):
                self._move_or_resize_board(event.position(), printable)
                self.update(printable.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            if self._drag_mode.startswith("panel_resize_"):
                panel = self._panel_by_id(self._selected_panel_id)
                if panel is not None:
                    self._resize_panel_outline(panel, event.position(), content_rect)
                    self.update(content_rect.adjusted(-96, -96, 96, 96).toAlignedRect())
                return
            if self._drag_start_crop is None:
                return
            panel = self._panel_by_id(self._selected_panel_id)
            if panel is None:
                return
            panel_rect = self._panel_rect(panel, content_rect)
            if self._drag_mode == "move":
                delta = event.position() - self._drag_start
                next_x = self._drag_start_crop[0] + delta.x() / panel_rect.width()
                next_y = self._drag_start_crop[1] + delta.y() / panel_rect.height()
                next_x, next_y = self._bounded_image_center(panel, panel_rect, next_x, next_y)
                panel.crop = (
                    next_x,
                    next_y,
                    self._drag_start_crop[2],
                )
            elif self._drag_mode == "rotate":
                center = self._image_center(panel, panel_rect)
                start_angle = degrees(
                    atan2(self._drag_start.y() - center.y(), self._drag_start.x() - center.x())
                )
                current_angle = degrees(
                    atan2(event.position().y() - center.y(), event.position().x() - center.x())
                )
                rotation = self._drag_start_rotation + current_angle - start_angle
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    rotation = round(rotation / 15.0) * 15.0
                panel.rotation = rotation
            elif self._drag_mode.startswith("scale"):
                center = self._image_center(panel, panel_rect)
                start_distance = max(1.0, _point_distance(self._drag_start, center))
                current_distance = max(1.0, _point_distance(event.position(), center))
                zoom = self._drag_start_crop[2] * current_distance / start_distance
                panel.crop = (
                    self._drag_start_crop[0],
                    self._drag_start_crop[1],
                    max(0.1, min(10.0, zoom)),
                )
                self.imageScaleChanged.emit(panel.crop[2] * 100.0)
            self.update(content_rect.adjusted(-96, -96, 96, 96).toAlignedRect())
            return
        if self._board is not None:
            printable = self._printable_rect(self._page_rect())
            content_rect = self._content_rect(printable)
            divider = self._divider_at(event.position(), content_rect)
            if divider != self._highlight_divider:
                self._highlight_divider = divider
                self.update(content_rect.adjusted(-16, -16, 16, 16).toAlignedRect())
            if divider is not None:
                self.setCursor(
                    Qt.CursorShape.SizeHorCursor
                    if divider.startswith("divider_v")
                    else Qt.CursorShape.SizeVerCursor
                )
                return
            selected_panel = (
                self._panel_by_id(self._selected_panel_id)
                if self._selected_panel_id not in {None, "__board__"}
                else None
            )
            if selected_panel is not None:
                panel_handle = self._panel_resize_handle_at(
                    event.position(),
                    self._panel_rect(selected_panel, content_rect),
                )
                if panel_handle is not None:
                    self.setCursor(
                        Qt.CursorShape.SizeHorCursor
                        if panel_handle.endswith(("_l", "_r"))
                        else Qt.CursorShape.SizeVerCursor
                    )
                    return
                handle = self._image_handle_at(
                    event.position(),
                    selected_panel,
                    self._panel_rect(selected_panel, content_rect),
                )
                if handle == "rotate":
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    return
                if handle is not None:
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    return
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode is not None:
            panel_id = self._selected_panel_id
            self._drag_mode = None
            self._drag_start = None
            self._drag_start_crop = None
            self._drag_start_panel_rect = None
            self._drag_start_content_rect = None
            self._drag_start_panel_rects = {}
            self._highlight_divider = None
            self._interaction_quality_timer.stop()
            self._is_interacting = False
            self.update()
            if panel_id is not None:
                self.panelTransformed.emit(panel_id)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            panel = (
                self._panel_by_id(self._selected_panel_id)
                if self._selected_panel_id not in {None, "__board__"}
                else None
            )
            if panel is not None and panel.source_node_id is not None:
                self.panelImageClearRequested.emit(panel.id)
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _panel_pixmap(
        self,
        panel: FigurePanel,
        panel_rect: QRectF,
        asset: ImageAsset,
    ) -> QPixmap:
        if panel.source_node_id is None:
            return QPixmap()
        key = (
            panel.source_node_id,
            self._panel_cache_generation,
        )
        cached = self._panel_pixmap_cache.get(key)
        if cached is not None:
            return cached
        rendered = render_project_image(self.project, panel.source_node_id)
        if rendered is not None:
            source = QPixmap.fromImage(ndarray_to_qimage(rendered))
        else:
            source = asset_thumbnail(
                asset,
                QSize(max(1, int(panel_rect.width())), max(1, int(panel_rect.height()))),
            )
        source = self._bounded_preview_pixmap(source)
        self._panel_pixmap_cache[key] = source
        return source

    def _bounded_preview_pixmap(self, pixmap: QPixmap) -> QPixmap:
        if pixmap.isNull():
            return pixmap
        max_edge = 2200
        if pixmap.width() <= max_edge and pixmap.height() <= max_edge:
            return pixmap
        return pixmap.scaled(
            QSize(max_edge, max_edge),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )

    def _panel_pixmap_draw_size(
        self,
        pixmap: QPixmap,
        panel_rect: QRectF,
        zoom: float,
    ) -> tuple[float, float]:
        target_width = max(1.0, panel_rect.width() * max(0.1, zoom))
        target_height = max(1.0, panel_rect.height() * max(0.1, zoom))
        if pixmap.isNull() or pixmap.height() <= 0:
            return target_width, target_height
        source_aspect = pixmap.width() / max(1.0, pixmap.height())
        target_aspect = target_width / max(1.0, target_height)
        if source_aspect > target_aspect:
            return target_height * source_aspect, target_height
        return target_width, target_width / max(1e-6, source_aspect)

    def _emit_board_edit_started(self) -> None:
        if self._board is not None:
            self.boardEditStarted.emit(self._board.to_dict())

    def _move_or_resize_board(self, position: QPointF, printable: QRectF) -> None:
        if self._board is None or self._drag_start is None or self._drag_start_content_rect is None:
            return
        x, y, width, height = self._drag_start_content_rect
        dx = (position.x() - self._drag_start.x()) / max(1.0, printable.width())
        dy = (position.y() - self._drag_start.y()) / max(1.0, printable.height())
        mode = self._drag_mode or ""
        min_size = 0.12
        if mode == "board_move":
            x = max(0.0, min(1.0 - width, x + dx))
            y = max(0.0, min(1.0 - height, y + dy))
        elif mode.startswith("board_scale_"):
            handle = mode.removeprefix("board_scale_")
            horizontal = "l" in handle or "r" in handle
            vertical = "t" in handle or "b" in handle
            if horizontal and "l" in handle:
                next_x = max(0.0, min(x + width - min_size, x + dx))
                width = width + x - next_x
                x = next_x
            if horizontal and "r" in handle:
                width = max(min_size, min(1.0 - x, width + dx))
            if vertical and "t" in handle:
                next_y = max(0.0, min(y + height - min_size, y + dy))
                height = height + y - next_y
                y = next_y
            if vertical and "b" in handle:
                height = max(min_size, min(1.0 - y, height + dy))
        self._board.content_rect = (x, y, width, height)

    def _resize_panel_outline(
        self,
        panel: FigurePanel,
        position: QPointF,
        content: QRectF,
    ) -> None:
        if self._drag_start is None or self._drag_start_panel_rect is None:
            return
        x, y, width, height = self._drag_start_panel_rect
        dx = (position.x() - self._drag_start.x()) / max(1.0, content.width())
        dy = (position.y() - self._drag_start.y()) / max(1.0, content.height())
        min_size = 0.04
        mode = self._drag_mode or ""
        if mode.endswith("_l"):
            next_x = max(0.0, min(x + width - min_size, x + dx))
            width = width + x - next_x
            x = next_x
        elif mode.endswith("_r"):
            width = max(min_size, min(1.0 - x, width + dx))
        elif mode.endswith("_t"):
            next_y = max(0.0, min(y + height - min_size, y + dy))
            height = height + y - next_y
            y = next_y
        elif mode.endswith("_b"):
            height = max(min_size, min(1.0 - y, height + dy))
        panel.rect = (x, y, width, height)

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
    ) -> None:
        if panel.source_node_id is None:
            return
        for scale_bar in self.project.scale_bars.values():
            if scale_bar.image_node_id != panel.source_node_id:
                continue
            pixmap = (
                self._panel_pixmap(panel, panel_rect, asset)
                if asset is not None
                else QPixmap()
            )
            draw_width, _draw_height = self._panel_pixmap_draw_size(
                pixmap,
                panel_rect,
                max(0.1, panel.crop[2]),
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
            thickness = max(
                1.0,
                scale_bar.width_px * display_scale,
            )
            padding_x = max(3.0, panel_rect.width() * 0.02)
            padding_y = max(3.0, panel_rect.height() * 0.02)
            text_height = max(6.0, panel_rect.height() * 0.035)
            x = panel_rect.right() - length - padding_x
            y = panel_rect.bottom() - thickness - padding_y - (
                text_height if scale_bar.display_length else 0.0
            )
            x = max(panel_rect.left() + padding_x, x)
            y = max(panel_rect.top() + padding_y, y)
            painter.setPen(QPen(QColor(scale_bar.foreground), thickness))
            painter.drawLine(QPointF(x, y), QPointF(x + length, y))
            if scale_bar.display_length:
                painter.setFont(
                    QFont(
                        safe_font_family(scale_bar.font_family),
                        max(3, int(round(text_height * 0.65))),
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
        source_width = max(1.0, float(source_size.width()))
        source_height = max(1.0, float(source_size.height()))
        display_scale = min(
            image_rect.width() / source_width,
            image_rect.height() / source_height,
        )
        for annotation in self.project.annotations.values():
            if annotation.image_node_id != panel.source_node_id or not annotation.visible:
                continue
            color = QColor(annotation.color)
            if not color.isValid():
                color = QColor("#ffffff")
            line_width = max(0.5, annotation.line_width * display_scale)
            painter.setPen(QPen(color, line_width))
            points = [
                QPointF(
                    image_rect.x() + x * image_rect.width(),
                    image_rect.y() + y * image_rect.height(),
                )
                for x, y in annotation.points
            ]
            if annotation.kind is AnnotationKind.TEXT and points:
                font_size = max(2, int(round(annotation.size * display_scale)))
                anchor = painter.transform().map(points[0])
                painter.save()
                painter.resetTransform()
                painter.setPen(QPen(color, max(0.5, line_width)))
                painter.setFont(QFont(safe_font_family(annotation.font), font_size))
                painter.drawText(anchor, annotation.text)
                painter.restore()
            elif len(points) >= 2:
                painter.drawLine(points[0], points[1])

    def _mm_to_preview_px(self, value_mm: float, page_mm: float, preview_px: float) -> float:
        return preview_px * value_mm / max(1.0, page_mm)

    def _page_width_mm(self, page: PageFormat) -> float:
        return _page_dimension_mm(page.width, page.unit)

    def _page_height_mm(self, page: PageFormat) -> float:
        return _page_dimension_mm(page.height, page.unit)

    def _update_canvas_size(self, *, force: bool = False) -> None:
        if self._board is None:
            size = QSize(360, 280)
            if force or size != self._canvas_size:
                self._canvas_size = size
                self.updateGeometry()
            return
        width_mm = self._page_width_mm(self._board.page)
        height_mm = self._page_height_mm(self._board.page)
        screen = self.screen()
        pixels_per_mm = (
            screen.physicalDotsPerInch() / 25.4 if screen is not None else 96.0 / 25.4
        )
        scale = self._zoom_percent / 100.0
        size = QSize(
            max(360, int(width_mm * pixels_per_mm * scale) + 96),
            max(280, int(height_mm * pixels_per_mm * scale) + 96),
        )
        if force or size != self._canvas_size:
            self._canvas_size = size
            self.updateGeometry()
