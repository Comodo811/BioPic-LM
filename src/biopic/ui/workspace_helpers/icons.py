"""Icon helpers for workspace toolbars and layer lists."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QPushButton

from biopic.resources import resource_path


_ICON_DIR = resource_path("icons")

_TOOL_ICON_FILES = {
    "move": "move_icon.png",
    "rectangle_select": "rectangular_select_icon.png",
    "ellipse_select": "ellipse_select_icon.png",
    "free_select": "lasso_icon.png",
    "crop": "crop_tool_icon.png",
    "bucket_fill": "bucket_fill_icon.png",
    "brush": "paintbrush_icon.png",
    "pencil": "pencil_icon.png",
    "erase": "eraser_icon.png",
    "clone": "clone_icon.png",
    "heal": "heal_icon.png",
    "color_picker": "color_picker_icon.png",
    "zoom": "zoom_icon.png",
    "pan": "move_icon.png",
    "rotate": "rotate_icon.png",
}


def icon(filename: str) -> QIcon | None:
    path = _ICON_DIR / filename
    return QIcon(str(path)) if path.exists() else None


def tool_icon(tool_id: str) -> QIcon | None:
    filename = _TOOL_ICON_FILES.get(tool_id)
    return icon(filename) if filename is not None else None


def set_button_icon(button: QPushButton, filename: str, tooltip: str) -> None:
    icon_obj = icon(filename)
    button.setToolTip(tooltip)
    button.setFixedSize(QSize(30, 28))
    if icon_obj is not None:
        button.setIcon(icon_obj)
        button.setIconSize(QSize(18, 18))
    else:
        button.setText(tooltip)
