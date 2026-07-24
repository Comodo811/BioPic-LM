"""Application icon helpers."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPixmap

from biopic.resources import resource_path


def biopic_logo_path() -> Path:
    """Return the bundled BioPic LM logo path."""
    return resource_path("icons", "biopic_logo.png")


@lru_cache(maxsize=1)
def biopic_app_icon() -> QIcon:
    """Return a tight, taskbar-friendly icon built from the BioPic LM logo."""
    logo_path = biopic_logo_path()
    if not logo_path.exists():
        return QIcon()
    image = QImage(str(logo_path)).convertToFormat(QImage.Format.Format_ARGB32)
    if image.isNull():
        return QIcon(str(logo_path))
    bounds = _visual_bounds(image)
    if bounds.isNull():
        return QIcon(str(logo_path))
    cropped = image.copy(bounds)
    icon = QIcon()
    for size in (32, 48, 64, 128, 256):
        canvas = QPixmap(size, size)
        canvas.fill(Qt.GlobalColor.transparent)
        scaled = QPixmap.fromImage(cropped).scaled(
            QSize(size, size),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        painter = QPainter(canvas)
        painter.drawPixmap(
            (size - scaled.width()) // 2,
            (size - scaled.height()) // 2,
            scaled,
        )
        painter.end()
        icon.addPixmap(canvas)
    return icon


def _visual_bounds(image: QImage) -> QRect:
    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    background = image.pixelColor(0, 0)
    for y in range(image.height()):
        for x in range(image.width()):
            color = image.pixelColor(x, y)
            if color.alpha() <= 0:
                continue
            if _similar_color(color, background):
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)
    if right < left or bottom < top:
        return _alpha_bounds(image)
    padding = max(1, int(max(right - left + 1, bottom - top + 1) * 0.01))
    left = max(0, left - padding)
    top = max(0, top - padding)
    right = min(image.width() - 1, right + padding)
    bottom = min(image.height() - 1, bottom + padding)
    return QRect(left, top, right - left + 1, bottom - top + 1)


def _alpha_bounds(image: QImage) -> QRect:
    left = image.width()
    top = image.height()
    right = -1
    bottom = -1
    for y in range(image.height()):
        for x in range(image.width()):
            if image.pixelColor(x, y).alpha() <= 0:
                continue
            left = min(left, x)
            top = min(top, y)
            right = max(right, x)
            bottom = max(bottom, y)
    if right < left or bottom < top:
        return QRect()
    return QRect(left, top, right - left + 1, bottom - top + 1)


def _similar_color(left: QColor, right: QColor) -> bool:
    return (
        abs(left.red() - right.red()) <= 8
        and abs(left.green() - right.green()) <= 8
        and abs(left.blue() - right.blue()) <= 8
        and abs(left.alpha() - right.alpha()) <= 8
    )
