"""Image import preview workspace."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.workspace_helpers.common import asset_metadata_text


class ImportWorkspace(QWidget):
    """Image import, metadata, and canvas navigation workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.assetSelected: Callable[[str], None] | None = None
        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.fit_button = QPushButton("Fit")
        self.actual_button = QPushButton("100%")
        toolbar.addWidget(self.fit_button)
        toolbar.addWidget(self.actual_button)
        toolbar.addStretch(1)
        self.coordinate_label = QLabel("x: -, y: -, value: -")
        toolbar.addWidget(self.coordinate_label)
        layout.addLayout(toolbar)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.asset_list = QListWidget()
        self.canvas = ImageCanvas()
        self.metadata = QPlainTextEdit()
        self.metadata.setReadOnly(True)
        splitter.addWidget(self.asset_list)
        splitter.addWidget(self.canvas)
        splitter.addWidget(self.metadata)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)

        self.fit_button.clicked.connect(self.canvas.fit_to_window)
        self.actual_button.clicked.connect(self.canvas.actual_size)
        self.asset_list.currentRowChanged.connect(self._select_row)
        self.canvas.pixelInspected.connect(self._show_pixel)

    def refresh(self) -> None:
        """Refresh the asset list from the project."""
        self.asset_list.clear()
        for asset in self.project.assets.values():
            self.asset_list.addItem(asset.filename)
        if self.project.assets and self.asset_list.currentRow() < 0:
            self.asset_list.setCurrentRow(0)

    def _select_row(self, row: int) -> None:
        assets = list(self.project.assets.values())
        if row < 0 or row >= len(assets):
            return
        asset = assets[row]
        self.show_asset(asset)
        if self.assetSelected is not None:
            self.assetSelected(asset.id)

    def show_asset(self, asset: ImageAsset) -> None:
        """Display an imported asset and metadata."""
        self.canvas.set_asset(asset)
        self.metadata.setPlainText(asset_metadata_text(asset))

    def _show_pixel(self, x: int, y: int, value: str) -> None:
        self.coordinate_label.setText(f"x: {x}, y: {y}, value: {value}")
