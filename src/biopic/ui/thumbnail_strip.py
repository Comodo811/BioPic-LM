"""Thumbnail strip for source images and stacks."""

from __future__ import annotations

from PySide6.QtCore import QSize, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QListWidget, QListWidgetItem

from biopic.models.image_asset import ImageAsset
from biopic.ui.previews import asset_thumbnail


class ThumbnailStrip(QListWidget):
    """Horizontal list of imported image assets."""

    assetSelected = Signal(str)

    def __init__(self, icon_size: QSize | None = None) -> None:
        super().__init__()
        self._icon_size = icon_size or QSize(96, 72)
        self.setFlow(QListWidget.Flow.LeftToRight)
        self.setWrapping(False)
        self.setIconSize(self._icon_size)
        self.setMovement(QListWidget.Movement.Snap)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.currentItemChanged.connect(self._emit_selection)

    def set_assets(self, assets: list[ImageAsset]) -> None:
        """Replace thumbnail contents."""
        self.clear()
        for asset in assets:
            item = QListWidgetItem(
                QIcon(asset_thumbnail(asset, self._icon_size)), asset.filename
            )
            item.setData(256, asset.id)
            item.setToolTip(
                f"{asset.filename}\n"
                f"{asset.width} x {asset.height}, {asset.dtype}, {asset.color_model}"
            )
            self.addItem(item)

    def _emit_selection(self, current: QListWidgetItem | None) -> None:
        if current is not None:
            self.assetSelected.emit(str(current.data(256)))
