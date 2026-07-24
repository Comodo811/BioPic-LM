"""Graphics items used by the image canvas."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QMouseEvent, QPainter, QPainterPath, QPen
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
        for y in range(y0, y1, chunk):
            yy = min(y + chunk, y1)
            for x in range(x0, x1, chunk):
                xx = min(x + chunk, x1)
                tile = self._pixels[y:yy, x:xx]
                image = ndarray_to_qimage(tile, self._display_range)
                painter.drawImage(QPointF(float(x), float(y)), image)


class _SelectionHandleItem(QGraphicsEllipseItem):
    """Movable vertex handle for free/lasso selections."""

    def __init__(self, canvas: ImageCanvas, index: int, point: QPointF) -> None:
        super().__init__(-6.0, -6.0, 12.0, 12.0)
        self._canvas = canvas
        self._index = index
        self.setPos(point)
        self.setBrush(QBrush(QColor("#ffffff")))
        self.setPen(QPen(QColor("#111111"), 1.5))
        self.setZValue(16.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeAllCursor)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.addEllipse(QRectF(-11.0, -11.0, 22.0, 22.0))
        return path

    def mousePressEvent(self, event: QMouseEvent) -> None:
        event.accept()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        event.accept()
        super().mouseMoveEvent(event)

    def itemChange(
        self, change: QGraphicsItem.GraphicsItemChange, value: object
    ) -> object:
        if (
            change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged
            and isinstance(value, QPointF)
        ):
            self._canvas._selection_handle_moved(self._index, value)
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        super().mouseReleaseEvent(event)
        self._canvas._selection_handle_released()
