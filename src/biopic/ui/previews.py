"""Small cached image previews for resource-friendly UI lists."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap

from biopic.imaging.io import load_asset_pixels
from biopic.models.image_asset import ImageAsset
from biopic.ui.image_canvas import ndarray_to_qimage

_PREVIEW_CACHE: dict[tuple[str, int, int], QPixmap] = {}


def asset_thumbnail(asset: ImageAsset, size: QSize, *, fast: bool = True) -> QPixmap:
    """Return a cached fixed-size thumbnail without keeping full image arrays around."""
    key = (asset.checksum or asset.path, size.width(), size.height())
    cached = _PREVIEW_CACHE.get(key)
    if cached is not None:
        return cached
    image = _read_scaled_image(asset, size)
    mode = (
        Qt.TransformationMode.FastTransformation
        if fast
        else Qt.TransformationMode.SmoothTransformation
    )
    scaled = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio, mode)
    canvas = QPixmap(size)
    canvas.fill(QColor("#f4f4f4"))
    painter = QPainter(canvas)
    x = (size.width() - scaled.width()) // 2
    y = (size.height() - scaled.height()) // 2
    painter.drawImage(x, y, scaled)
    painter.end()
    _PREVIEW_CACHE[key] = canvas
    return canvas


def _read_scaled_image(asset: ImageAsset, size: QSize) -> QImage:
    reader = QImageReader(str(Path(asset.path)))
    reader.setAutoTransform(True)
    native_size = reader.size()
    if native_size.isValid():
        native_size.scale(size, Qt.AspectRatioMode.KeepAspectRatio)
        reader.setScaledSize(native_size)
    image = reader.read()
    if not image.isNull():
        return image
    return ndarray_to_qimage(load_asset_pixels(asset))
