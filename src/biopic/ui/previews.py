"""Small cached image previews for resource-friendly UI lists."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter, QPixmap

from biopic.imaging.io import RAW_EXTENSIONS, RAW_STACK_BRIGHTNESS, load_asset_pixels
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


def asset_preview_pixels(asset: ImageAsset, *, max_edge: int = 1600) -> np.ndarray:
    """Return display-only preview pixels without decoding more than needed."""
    image = _read_scaled_image(asset, QSize(max_edge, max_edge))
    if image.width() > max_edge or image.height() > max_edge:
        image = image.scaled(
            QSize(max_edge, max_edge),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation,
        )
    return _qimage_to_rgb_array(image)


def _read_scaled_image(asset: ImageAsset, size: QSize) -> QImage:
    if Path(asset.path).suffix.lower() in RAW_EXTENSIONS:
        raw_preview = _read_raw_thumbnail(asset, size)
        if raw_preview is not None:
            return raw_preview
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


def _qimage_to_rgb_array(image: QImage) -> np.ndarray:
    converted = image.convertToFormat(QImage.Format.Format_RGB888)
    width = converted.width()
    height = converted.height()
    bytes_per_line = converted.bytesPerLine()
    bits = converted.bits()
    array = np.frombuffer(bits, dtype=np.uint8).reshape(height, bytes_per_line)
    return array[:, : width * 3].reshape(height, width, 3).copy()


def _read_raw_thumbnail(asset: ImageAsset, size: QSize) -> QImage | None:
    try:
        import rawpy  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        with rawpy.imread(str(Path(asset.path))) as raw:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                image = QImage()
                if image.loadFromData(thumb.data):
                    return image
            array = np.asarray(thumb.data)
            if array.size:
                return ndarray_to_qimage(array)
            preview = raw.postprocess(
                half_size=True,
                output_bps=8,
                no_auto_bright=True,
                bright=RAW_STACK_BRIGHTNESS,
                use_camera_wb=True,
            )
            return ndarray_to_qimage(preview)
    except Exception:
        return None
