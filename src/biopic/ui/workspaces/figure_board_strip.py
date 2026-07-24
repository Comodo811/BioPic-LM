"""Image strip for figure-board asset assignment."""

from __future__ import annotations

from PySide6.QtCore import QMimeData, QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QDrag, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QListWidget, QListWidgetItem, QSizePolicy

from biopic.imaging.project_render import editable_assets, render_project_image
from biopic.models.annotations import AnnotationKind
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.ui.fonts import safe_font_family
from biopic.ui.image_canvas import ndarray_to_qimage
from biopic.ui.previews import asset_thumbnail
from biopic.ui.thumbnail_strip import ThumbnailStrip
from biopic.ui.workspace_helpers.common import project_asset_display_name


class FigureBoardImageStrip(ThumbnailStrip):
    """Drag source for finished images used by the figure board."""

    def __init__(self) -> None:
        super().__init__(QSize(144, 108))
        self.setFixedHeight(156)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setDragEnabled(True)
        self.setDragDropMode(QListWidget.DragDropMode.DragOnly)
        self._drag_active = False

    def set_project_assets(self, project: Project) -> None:
        """Show downstream rendered image thumbnails for figure-board placement."""
        self.clear()
        for asset in editable_assets(project):
            node_id = project.source_node_id_for_asset(asset.id)
            pixmap = self._rendered_thumbnail(project, asset, node_id)
            label = project_asset_display_name(asset, project.stacks)
            item = QListWidgetItem(QIcon(pixmap), label)
            item.setData(256, asset.id)
            item.setToolTip(
                f"{label}\n"
                f"Figure-board source with upstream edits, scale bars and annotations"
            )
            self.addItem(item)

    def _rendered_thumbnail(
        self,
        project: Project,
        asset: ImageAsset,
        node_id: str | None,
    ) -> QPixmap:
        rendered = render_project_image(project, node_id) if node_id is not None else None
        if rendered is not None:
            source = QPixmap.fromImage(ndarray_to_qimage(rendered))
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
            points = [
                QPointF(x * pixmap.width(), y * pixmap.height())
                for x, y in annotation.points
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
                painter.drawLine(points[0], points[1])
        for scale_bar in project.scale_bars.values():
            if scale_bar.image_node_id != node_id:
                continue
            length = max(4.0, scale_bar.pixel_length * pixmap.width() / image_width)
            thickness = max(1.0, scale_bar.width_px * pixmap.width() / image_width)
            margin_x = max(2.0, pixmap.width() * 0.02)
            margin_y = max(2.0, pixmap.height() * 0.02)
            text_height = max(5.0, pixmap.height() * 0.08)
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
                        max(2, int(round(text_height * 0.55))),
                    )
                )
                painter.drawText(
                    QRectF(x, y + thickness + 1.0, length, text_height),
                    Qt.AlignmentFlag.AlignCenter,
                    f"{scale_bar.physical_length:g} {scale_bar.unit}",
                )
        painter.end()
        return pixmap

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
