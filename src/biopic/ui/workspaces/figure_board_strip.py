"""Image strip for figure-board asset assignment."""

from __future__ import annotations

import numpy as np
from PIL import Image
from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QKeyEvent, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSizePolicy

from biopic.imaging.project_render import (
    editable_assets,
    project_image_cache_key,
    render_project_image,
)
from biopic.models.annotations import AnnotationKind, normalize_wedge_points
from biopic.models.figure_board import FigureBoard
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.export.raster import _display_compatible
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas import ndarray_to_qimage
from biopic.ui.previews import asset_thumbnail
from biopic.ui.thumbnail_strip import ThumbnailStrip
from biopic.ui.workspace_helpers.common import project_asset_display_name
from biopic.ui.workspaces.figure_board_preview_overlays import _visible_wedge_points


class FigureBoardImageStrip(ThumbnailStrip):
    """Drag source for finished images used by the figure board."""

    assetDeleteRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__(QSize(144, 108))
        self.setFixedHeight(156)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self._drag_active = False
        self._items_signature: tuple[object, ...] | None = None
        self._thumbnail_cache: dict[tuple[object, ...], QPixmap] = {}
        self._thumbnail_queue: list[tuple[Project, ImageAsset, str | None, QListWidgetItem]] = []
        self._thumbnail_timer = QTimer(self)
        self._thumbnail_timer.setSingleShot(False)
        self._thumbnail_timer.setInterval(180)
        self._thumbnail_timer.timeout.connect(self._render_next_thumbnail)

    def set_project_assets(self, project: Project) -> None:
        """Show downstream rendered image thumbnails for figure-board placement."""
        assets = editable_assets(project)
        signature = tuple(
            self._asset_signature(project, asset)
            for asset in assets
        )
        if signature == self._items_signature:
            return
        self._items_signature = signature
        self._thumbnail_timer.stop()
        self._thumbnail_queue.clear()
        self.clear()
        placeholder = self._placeholder_thumbnail()
        for asset in assets:
            node_id = project.source_node_id_for_asset(asset.id)
            label = project_asset_display_name(asset, project.stacks)
            item = QListWidgetItem(QIcon(placeholder), label)
            item.setData(256, asset.id)
            item.setToolTip(
                f"{label}\n"
                f"Figure-board source with upstream edits, scale bars and annotations"
            )
            self.addItem(item)
            self._thumbnail_queue.append((project, asset, node_id, item))
        if self._thumbnail_queue:
            self._thumbnail_timer.start()

    def _render_next_thumbnail(self) -> None:
        if not self._thumbnail_queue:
            self._thumbnail_timer.stop()
            return
        project, asset, node_id, item = self._thumbnail_queue.pop(0)
        if item.listWidget() is not self:
            return
        item.setIcon(QIcon(self._rendered_thumbnail(project, asset, node_id)))
        if not self._thumbnail_queue:
            self._thumbnail_timer.stop()

    def _placeholder_thumbnail(self) -> QPixmap:
        pixmap = QPixmap(self._icon_size)
        pixmap.fill(QColor("#f4f4f4"))
        painter = QPainter(pixmap)
        painter.setPen(QPen(QColor("#b8b8b0"), 1))
        painter.drawRect(pixmap.rect().adjusted(0, 0, -1, -1))
        painter.end()
        return pixmap

    def _rendered_thumbnail(
        self,
        project: Project,
        asset: ImageAsset,
        node_id: str | None,
    ) -> QPixmap:
        cache_key = self._asset_signature(project, asset)
        cached = self._thumbnail_cache.get(cache_key)
        if cached is not None:
            return cached
        rendered = render_project_image(project, node_id) if node_id is not None else None
        if rendered is not None:
            source = QPixmap.fromImage(ndarray_to_qimage(_thumbnail_preview_pixels(rendered)))
        else:
            source = asset_thumbnail(asset, self._icon_size)
        if source.isNull():
            return source
        pixmap = source.scaled(
            self._icon_size,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        if node_id is None:
            return pixmap
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        image_width = max(1.0, float(asset.width or source.width()))
        image_height = max(1.0, float(asset.height or source.height()))
        scale = min(pixmap.width() / image_width, pixmap.height() / image_height)
        for annotation in project.annotations.values():
            if annotation.image_node_id != node_id or not annotation.visible:
                continue
            color = QColor(annotation.color)
            if not color.isValid():
                color = QColor("#ffffff")
            painter.setPen(QPen(color, max(1.0, annotation.line_width * scale)))
            annotation_points = (
                normalize_wedge_points(list(annotation.points))
                if annotation.kind is AnnotationKind.WEDGE
                else annotation.points
            )
            points = [
                QPointF(x * pixmap.width(), y * pixmap.height())
                for x, y in annotation_points
            ]
            if annotation.kind is AnnotationKind.TEXT and points:
                painter.setFont(
                    QFont(
                        safe_font_family(annotation.font),
                        max(2, int(round(annotation.size * scale))),
                    )
                )
                painter.drawText(points[0], annotation.text)
            elif len(points) >= 2:
                if annotation.kind is AnnotationKind.WEDGE:
                    visible = _visible_wedge_points(points, 0.0)
                    path = QPainterPath(visible[0])
                    for point in visible[1:]:
                        path.lineTo(point)
                    path.closeSubpath()
                    painter.setPen(QPen(Qt.PenStyle.NoPen))
                    painter.fillPath(path, QColor(annotation.fill or annotation.color))
                else:
                    painter.drawLine(points[0], points[1])
        for scale_bar in project.scale_bars.values():
            if scale_bar.image_node_id != node_id:
                continue
            length = max(4.0, scale_bar.pixel_length * pixmap.width() / image_width)
            thickness = max(1.0, scale_bar.width_px)
            margin_x = max(2.0, pixmap.width() * 0.02)
            margin_y = max(2.0, pixmap.height() * 0.02)
            font_size = max(2, int(round(scale_bar.font_size)))
            text_height = max(float(font_size) * 1.6, 5.0)
            x = pixmap.width() - length - margin_x
            y = pixmap.height() - thickness - margin_y - (
                text_height if scale_bar.display_length else 0.0
            )
            painter.setPen(QPen(QColor(scale_bar.foreground), thickness))
            painter.drawLine(QPointF(x, y), QPointF(x + length, y))
            if scale_bar.display_length:
                painter.setFont(
                    QFont(
                        safe_font_family(scale_bar.font_family),
                        font_size,
                    )
                )
                painter.drawText(
                    QRectF(x, y + thickness + 1.0, length, text_height),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{scale_bar.physical_length:g} {scale_bar.unit}",
                )
        painter.end()
        self._thumbnail_cache[cache_key] = pixmap
        return pixmap

    def _asset_signature(self, project: Project, asset: ImageAsset) -> tuple[object, ...]:
        node_id = project.source_node_id_for_asset(asset.id)
        return (
            asset.id,
            project_asset_display_name(asset, project.stacks),
            asset.checksum or asset.path,
            node_id,
            project_image_cache_key(project, node_id) if node_id is not None else None,
            self._overlay_signature(project, node_id),
        )

    def _overlay_signature(
        self,
        project: Project,
        node_id: str | None,
    ) -> tuple[object, ...]:
        if node_id is None:
            return ()
        annotations = tuple(
            sorted(
                (
                    annotation.id,
                    annotation.text,
                    annotation.kind.value,
                    annotation.visible,
                    annotation.color,
                    annotation.line_width,
                    annotation.font,
                    annotation.size,
                    tuple(annotation.points),
                )
                for annotation in project.annotations.values()
                if annotation.image_node_id == node_id
            )
        )
        scale_bars = tuple(
            sorted(
                (
                    scale_bar.id,
                    scale_bar.pixel_length,
                    scale_bar.width_px,
                    scale_bar.foreground,
                    scale_bar.display_length,
                    scale_bar.physical_length,
                    scale_bar.unit,
                    scale_bar.font_family,
                )
                for scale_bar in project.scale_bars.values()
                if scale_bar.image_node_id == node_id
            )
        )
        return annotations, scale_bars

    def startDrag(self, _supported_actions: object) -> None:
        if self._drag_active:
            return
        current = self.currentItem()
        if current is None:
            return
        asset_id = str(current.data(256))
        if not asset_id:
            return
        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-biopic-asset-id", asset_id.encode("utf-8"))
        drag.setMimeData(mime)
        icon = current.icon()
        pixmap = icon.pixmap(self.iconSize()) if not icon.isNull() else QPixmap()
        if not pixmap.isNull():
            drag.setPixmap(pixmap)
        self._drag_active = True
        try:
            drag.exec(Qt.DropAction.CopyAction)
        finally:
            self._drag_active = False

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            current = self.currentItem()
            if current is not None:
                self.assetDeleteRequested.emit(str(current.data(256)))
                event.accept()
                return
        super().keyPressEvent(event)


class FigureBoardList(QListWidget):
    """Horizontal selector for saved figure boards."""

    boardSelected = Signal(str)
    boardDeleteRequested = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._icon_size = QSize(128, 92)
        self._items_signature: tuple[object, ...] | None = None
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(self._icon_size)
        self.setMovement(QListWidget.Movement.Static)
        self.setDragDropMode(QListWidget.DragDropMode.NoDragDrop)
        self.setFixedHeight(156)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.currentItemChanged.connect(self._emit_selection)

    def set_project_boards(self, project: Project, current_board_id: str | None) -> None:
        """Show available boards and select the active board."""
        boards = list(project.figure_boards.values())
        signature = tuple(self._board_signature(board) for board in boards), current_board_id
        if signature == self._items_signature:
            return
        self._items_signature = signature
        self.blockSignals(True)
        self.clear()
        selected_item: QListWidgetItem | None = None
        for board in boards:
            item = QListWidgetItem(QIcon(_board_thumbnail(board, self._icon_size)), board.name)
            item.setData(256, board.id)
            item.setToolTip(_board_tooltip(board))
            self.addItem(item)
            if board.id == current_board_id:
                selected_item = item
        if selected_item is not None:
            self.setCurrentItem(selected_item)
        self.blockSignals(False)

    def _emit_selection(self, current: QListWidgetItem | None) -> None:
        if current is not None:
            self.boardSelected.emit(str(current.data(256)))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {
            Qt.Key.Key_Delete,
            Qt.Key.Key_Backspace,
            Qt.Key.Key_Return,
            Qt.Key.Key_Enter,
        }:
            current = self.currentItem()
            if current is not None:
                self.boardDeleteRequested.emit(str(current.data(256)))
                event.accept()
                return
        super().keyPressEvent(event)

    def _board_signature(self, board: FigureBoard) -> tuple[object, ...]:
        return (
            board.id,
            board.name,
            len(board.panels),
            tuple(panel.source_node_id for panel in board.panels),
            tuple(panel.rect for panel in board.panels),
            board.page.width,
            board.page.height,
            board.page.unit.value,
        )


def _board_tooltip(board: FigureBoard) -> str:
    assigned = sum(1 for panel in board.panels if panel.source_node_id is not None)
    width, height = board.page.pixel_dimensions()
    return (
        f"{board.name}\n"
        f"{len(board.panels)} panels, {assigned} assigned\n"
        f"{width} x {height} px"
    )


def _thumbnail_preview_pixels(pixels: object, *, max_edge: int = 512) -> np.ndarray:
    data = np.asarray(pixels)
    if data.ndim < 2:
        return data
    height, width = data.shape[:2]
    if max(width, height) <= max_edge:
        return data
    scale = max_edge / max(1.0, float(max(width, height)))
    target = (max(1, int(round(width * scale))), max(1, int(round(height * scale))))
    image = Image.fromarray(_display_compatible(data))
    return np.asarray(image.resize(target, Image.Resampling.BILINEAR))


def _board_thumbnail(board: FigureBoard, size: QSize) -> QPixmap:
    pixmap = QPixmap(size)
    pixmap.fill(QColor("#f8f8f3"))
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    margin = 8
    page_rect = QRectF(
        margin,
        margin,
        max(1, size.width() - margin * 2),
        max(1, size.height() - margin * 2),
    )
    page_width, page_height = board.page.pixel_dimensions()
    aspect = page_width / max(1, page_height)
    if page_rect.width() / max(1.0, page_rect.height()) > aspect:
        draw_height = page_rect.height()
        draw_width = draw_height * aspect
    else:
        draw_width = page_rect.width()
        draw_height = draw_width / max(0.01, aspect)
    board_rect = QRectF(
        page_rect.center().x() - draw_width / 2.0,
        page_rect.center().y() - draw_height / 2.0,
        draw_width,
        draw_height,
    )
    painter.setBrush(QColor("#ffffff"))
    painter.setPen(QPen(QColor("#2f2f2f"), 1))
    painter.drawRect(board_rect)
    content = QRectF(
        board_rect.x() + board.content_rect[0] * board_rect.width(),
        board_rect.y() + board.content_rect[1] * board_rect.height(),
        board.content_rect[2] * board_rect.width(),
        board.content_rect[3] * board_rect.height(),
    )
    for panel in board.panels:
        rect = QRectF(
            content.x() + panel.rect[0] * content.width(),
            content.y() + panel.rect[1] * content.height(),
            panel.rect[2] * content.width(),
            panel.rect[3] * content.height(),
        ).adjusted(1, 1, -1, -1)
        painter.setBrush(QColor("#b8cfdd") if panel.source_node_id else QColor("#e6e3dc"))
        painter.setPen(QPen(QColor("#555555"), 1))
        painter.drawRect(rect)
    painter.end()
    return pixmap
