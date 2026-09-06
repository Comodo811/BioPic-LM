"""Graphics items used by the image canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QImage, QMouseEvent, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsEllipseItem, QGraphicsItem, QStyleOptionGraphicsItem, QWidget

from biopic.ui.image_conversion import ndarray_to_qimage

if TYPE_CHECKING:
    from biopic.ui.image_canvas import ImageCanvas


class _ProjectionItem(QGraphicsItem):
    """Pull-rendered image projection item, inspired by GIMP's display shell."""

    def __init__(self, chunk_size: int) -> None:
        super().__init__()
        self._pixels: np.ndarray | None = None
        self._display_range: tuple[float, float] | None = None
        self._chunk_size = int(chunk_size)
        self._tile_cache: dict[tuple[object, ...], QImage] = {}
        self.setZValue(0.0)
        self.setCacheMode(QGraphicsItem.CacheMode.NoCache)

    def set_pixels(
        self,
        pixels: np.ndarray | None,
        display_range: tuple[float, float] | None,
    ) -> None:
        self.prepareGeometryChange()
        self._pixels = pixels
        self._display_range = display_range
        self._tile_cache.clear()
        self.update()

    def clear(self) -> None:
        self.set_pixels(None, None)

    def boundingRect(self) -> QRectF:
        if self._pixels is None:
            return QRectF(0, 0, 1, 1)
        return QRectF(0, 0, self._pixels.shape[1], self._pixels.shape[0])

    def update_regions(self, rects: list[tuple[int, int, int, int]]) -> None:
        if self._pixels is None:
            return
        for x, y, width, height in rects:
            if width > 0 and height > 0:
                self._invalidate_tile_cache_region(x, y, width, height)
                self.update(QRectF(float(x), float(y), float(width), float(height)))

    def paint(
        self,
        painter: QPainter,
        option: QStyleOptionGraphicsItem,
        widget: QWidget | None = None,
    ) -> None:
        del widget
        if self._pixels is None:
            return
        exposed = option.exposedRect.intersected(self.boundingRect())
        if exposed.isEmpty():
            return
        x0 = max(0, int(np.floor(exposed.left())))
        y0 = max(0, int(np.floor(exposed.top())))
        x1 = min(self._pixels.shape[1], int(np.ceil(exposed.right())) + 1)
        y1 = min(self._pixels.shape[0], int(np.ceil(exposed.bottom())) + 1)
        if x1 <= x0 or y1 <= y0:
            return
        chunk = self._chunk_size
        start_y = (y0 // chunk) * chunk
        start_x = (x0 // chunk) * chunk
        for y in range(start_y, y1, chunk):
            yy = min(y + chunk, self._pixels.shape[0])
            for x in range(start_x, x1, chunk):
                xx = min(x + chunk, self._pixels.shape[1])
                image = self._cached_tile_image(x, y, xx - x, yy - y)
                painter.drawImage(QPointF(float(x), float(y)), image)

    def _cached_tile_image(self, x: int, y: int, width: int, height: int) -> QImage:
        if self._pixels is None:
            return QImage()
        key = (
            id(self._pixels),
            x,
            y,
            width,
            height,
            str(self._pixels.dtype),
            self._pixels.shape,
            self._display_range,
        )
        image = self._tile_cache.get(key)
        if image is None:
            tile = self._pixels[y : y + height, x : x + width]
            image = ndarray_to_qimage(tile, self._display_range)
            self._tile_cache[key] = image
        return image

    def _invalidate_tile_cache_region(self, x: int, y: int, width: int, height: int) -> None:
        if not self._tile_cache:
            return
        chunk = self._chunk_size
        x0 = max(0, (x // chunk) * chunk)
        y0 = max(0, (y // chunk) * chunk)
        x1 = x + width
        y1 = y + height
        stale_tiles = {
            key
            for key in self._tile_cache
            if isinstance(key[1], int)
            and isinstance(key[2], int)
            and key[1] < x1
            and key[2] < y1
            and key[1] + chunk > x0
            and key[2] + chunk > y0
        }
        for key in stale_tiles:
            self._tile_cache.pop(key, None)


class _SelectionHandleItem(QGraphicsEllipseItem):
    """Movable vertex handle for free/lasso selections."""

    def __init__(self, canvas: ImageCanvas, index: int, point: QPointF) -> None:
        super().__init__(-6.0, -6.0, 12.0, 12.0)
        self._canvas = canvas
        self._index = index
        self._dragging = False
        self.setPos(point)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#111111"), 1.5))
        self.setZValue(16.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QRectF(-11.0, -11.0, 22.0, 22.0))
        return path

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._dragging = True
        self._canvas._selection_handle_drag_started(self._index)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            point = event.scenePos()
            self.setPos(point)
            self._canvas._selection_handle_moved(self._index, point)
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            point = event.scenePos()
            self.setPos(point)
            self._canvas._selection_handle_moved(self._index, point)
        self._dragging = False
        event.accept()
        self._canvas._selection_handle_released()


class _AnnotationHandleItem(QGraphicsEllipseItem):
    """Movable transform handle for selected annotation overlays."""

    def __init__(
        self,
        canvas: ImageCanvas,
        annotation_id: str,
        role: str,
        point: QPointF,
    ) -> None:
        super().__init__(-5.0, -5.0, 10.0, 10.0)
        self._canvas = canvas
        self._annotation_id = annotation_id
        self._role = role
        self._dragging = False
        self.setPos(point)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#111111"), 1.25))
        self.setZValue(17.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QRectF(-10.0, -10.0, 20.0, 20.0))
        return path

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self._dragging = True
        self._canvas._annotation_handle_drag_started(self._annotation_id, self._role)
        event.accept()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._canvas._annotation_handle_moved(
                self._annotation_id,
                self._role,
                event.scenePos(),
            )
        event.accept()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._dragging:
            self._canvas._annotation_handle_moved(
                self._annotation_id,
                self._role,
                event.scenePos(),
            )
        self._dragging = False
        event.accept()
        self._canvas._annotation_handle_released()
