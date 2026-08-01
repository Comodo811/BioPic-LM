"""Project overview workspace."""

from __future__ import annotations

from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QPainter, QPixmap
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack
from biopic.models.project import Project
from biopic.resources import resource_path
from biopic.ui.previews import asset_thumbnail
from biopic.ui.workspace_helpers.common import (
    clear_layout,
    project_asset_display_name,
    stack_display_name,
    stack_thumbnail,
)

OVERVIEW_THUMBNAIL_SIZE = QSize(140, 96)
STACK_THUMBNAIL_SIZE = QSize(120, 88)


class OverviewWorkspace(QWidget):
    """Project overview with resource-friendly image previews."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.setStyleSheet(_EDITOR_STYLESHEET)
        self._watermark_pixmap = QPixmap(str(resource_path("icons", "biopic_logo.png")))
        layout = QVBoxLayout(self)
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.content)
        layout.addWidget(self.scroll_area)

    def paintEvent(self, _event: object) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), self.palette().color(self.backgroundRole()))
        self._draw_watermark(painter)

    def _draw_watermark(self, painter: QPainter) -> None:
        if self._watermark_pixmap.isNull():
            return
        target_size = min(self.width(), self.height()) * 0.50
        if target_size <= 1:
            return
        target = QRectF(
            (self.width() - target_size) / 2.0,
            (self.height() - target_size) / 2.0,
            target_size,
            target_size,
        )
        painter.save()
        painter.setOpacity(0.06)
        painter.drawPixmap(target, self._watermark_pixmap, QRectF(self._watermark_pixmap.rect()))
        painter.restore()

    def refresh(self) -> None:
        """Refresh overview categories from the project."""
        clear_layout(self.content_layout)
        stacked_asset_ids = {
            asset_id for stack in self.project.stacks.values() for asset_id in stack.asset_ids
        }
        self._add_asset_category(
            "Raw images",
            [
                asset
                for asset in self.project.assets.values()
                if asset.kind is not ImageAssetKind.STACK_SOURCE
                and asset.id not in stacked_asset_ids
            ],
        )
        self._add_stack_category(
            "Raw image stacks",
            list(self.project.stacks.values()),
        )
        self._add_text_category(
            "Stacked images",
            [
                project_asset_display_name(asset, self.project.stacks)
                for asset in self.project.assets.values()
                if asset.origin_node_id
                in {
                    node.id
                    for node in self.project.graph.nodes.values()
                    if node.operation == "focus_stack"
                }
            ],
        )
        self._add_text_category(
            "Edited images",
            [
                f"{node.operation.removeprefix('edit.').replace('_', ' ').title()}: {node.id}"
                for node in self.project.graph.nodes.values()
                if node.operation.startswith("edit.")
            ],
        )
        self._add_text_category(
            "Scaled images",
            [
                f"Calibration {node_id}: {calibration.unit_per_pixel:.6g} {calibration.unit}/px"
                for node_id, calibration in self.project.calibrations.items()
            ]
            + [
                f"Scale bar {scale_bar.id}: {scale_bar.physical_length:g} {scale_bar.unit}"
                for scale_bar in self.project.scale_bars.values()
            ],
        )
        self._add_text_category(
            "Annotated images",
            [
                f"{annotation.text or annotation.kind.value}: {annotation.image_node_id}"
                for annotation in self.project.annotations.values()
            ],
        )
        self._add_text_category(
            "Figure board",
            [
                f"{board.name}: {len(board.panels)} panel(s)"
                for board in self.project.figure_boards.values()
            ],
        )

    def _add_asset_category(self, label: str, assets: list[ImageAsset]) -> None:
        if not assets:
            return
        grid = self._add_category_grid(label)
        for index, asset in enumerate(assets):
            card = _ImageCard(asset.filename, asset_thumbnail(asset, OVERVIEW_THUMBNAIL_SIZE))
            grid.addWidget(card, index // 4, index % 4)

    def _add_stack_category(self, label: str, stacks: list[ImageStack]) -> None:
        if not stacks:
            return
        grid = self._add_category_grid(label)
        for index, stack in enumerate(stacks):
            stack_assets = [
                self.project.assets[asset_id]
                for asset_id in stack.asset_ids
                if asset_id in self.project.assets
            ]
            card = _ImageCard(
                stack_display_name(stack, self.project.assets),
                stack_thumbnail(stack_assets, STACK_THUMBNAIL_SIZE),
            )
            grid.addWidget(card, index // 4, index % 4)

    def _add_text_category(self, label: str, entries: list[str]) -> None:
        if not entries:
            return
        self.content_layout.addWidget(QLabel(label))
        for entry in entries:
            self.content_layout.addWidget(QLabel(entry))

    def _add_category_grid(self, label: str) -> QGridLayout:
        self.content_layout.addWidget(QLabel(label))
        row = QGridLayout()
        row.setAlignment(Qt.AlignmentFlag.AlignLeft)
        self.content_layout.addLayout(row)
        return row


class _ImageCard(QWidget):
    """Fixed-size preview card used by the project overview."""

    def __init__(self, label: str, pixmap: QPixmap) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        preview = QLabel()
        preview.setFixedSize(OVERVIEW_THUMBNAIL_SIZE)
        preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview.setPixmap(pixmap)
        title = QLabel(label)
        title.setFixedWidth(OVERVIEW_THUMBNAIL_SIZE.width())
        title.setWordWrap(True)
        layout.addWidget(preview)
        layout.addWidget(title)


_EDITOR_STYLESHEET = """
QWidget {
    background: palette(window);
    color: palette(window-text);
}
QListWidget, QPlainTextEdit {
    background: palette(base);
    border: 1px solid palette(dark);
    selection-background-color: palette(highlight);
    selection-color: palette(highlighted-text);
}
"""
