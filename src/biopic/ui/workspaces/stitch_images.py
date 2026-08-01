"""Workspace for feature-based stitching of standalone images."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QMimeData, QSize, Qt, Signal
from PySide6.QtGui import QDrag, QDragEnterEvent, QDropEvent, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from biopic.export.raster import export_image
from biopic.imaging.io import SUPPORTED_EXTENSIONS, import_images, read_image_asset
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.project import Project
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.workers.image_stitch_worker import ImageStitchJob, ImageStitchWorker, StitchResult


class StandaloneImageList(QListWidget):
    """Drag source for standalone project images."""

    def startDrag(self, _supported_actions: object) -> None:
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
        pixmap = icon.pixmap(self.iconSize()) if not icon.isNull() else None
        if pixmap is not None and not pixmap.isNull():
            drag.setPixmap(pixmap)
        drag.exec(Qt.DropAction.CopyAction)


class StitchImagesWorkspace(QWidget):
    """Select standalone images and create a stitched output image."""

    stitchCreated = Signal(list)

    def minimumSizeHint(self) -> QSize:
        """Allow splitter panes to collapse instead of forcing the main window wide."""
        return QSize(320, 220)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._worker: ImageStitchWorker | None = None
        self._selected_asset_ids: list[str] = []
        self._undo_stack: list[list[str]] = []
        self._redo_stack: list[list[str]] = []
        self.setAcceptDrops(True)
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.import_button = QPushButton("Import Images")
        self.add_button = QPushButton("Add")
        self.remove_button = QPushButton("Remove")
        self.move_up_button = QPushButton("Move Up")
        self.move_down_button = QPushButton("Move Down")
        self.clear_button = QPushButton("Clear")
        self.undo_button = QPushButton("Undo")
        self.redo_button = QPushButton("Redo")
        self.stitch_button = QPushButton("Stitch Images")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        for button in (
            self.import_button,
            self.add_button,
            self.remove_button,
            self.move_up_button,
            self.move_down_button,
            self.clear_button,
            self.undo_button,
            self.redo_button,
            self.stitch_button,
            self.cancel_button,
        ):
            controls.addWidget(button)
        controls.addStretch(1)
        layout.addLayout(controls)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        layout.addWidget(self.progress)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Available Images"))
        self.available_list = StandaloneImageList()
        self.available_list.setIconSize(QSize(140, 96))
        self.available_list.setUniformItemSizes(True)
        self.available_list.setDragEnabled(True)
        left_layout.addWidget(self.available_list)
        middle = QWidget()
        middle_layout = QVBoxLayout(middle)
        middle_layout.addWidget(QLabel("Stitching Order"))
        self.selected_list = QListWidget()
        self.selected_list.setIconSize(QSize(140, 96))
        self.selected_list.setUniformItemSizes(True)
        self.selected_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        middle_layout.addWidget(self.selected_list)
        self.empty_label = QLabel(
            "Drag at least two standalone images here, then click Stitch Images."
        )
        self.empty_label.setWordWrap(True)
        middle_layout.addWidget(self.empty_label)
        self.canvas = ImageCanvas()
        splitter.addWidget(left)
        splitter.addWidget(middle)
        splitter.addWidget(self.canvas)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 0)
        splitter.setStretchFactor(2, 1)
        splitter.setSizes([260, 280, 720])
        layout.addWidget(splitter, 1)
        self.import_button.clicked.connect(self.import_images)
        self.add_button.clicked.connect(self.add_selected_available_images)
        self.remove_button.clicked.connect(self.remove_selected_image)
        self.move_up_button.clicked.connect(lambda: self.move_selected(-1))
        self.move_down_button.clicked.connect(lambda: self.move_selected(1))
        self.clear_button.clicked.connect(self.clear_selection)
        self.undo_button.clicked.connect(self.undo)
        self.redo_button.clicked.connect(self.redo)
        self.stitch_button.clicked.connect(self.stitch_images)
        self.cancel_button.clicked.connect(self.cancel_stitching)
        self.available_list.itemDoubleClicked.connect(
            lambda _item: self.add_selected_available_images()
        )
        self.selected_list.model().rowsMoved.connect(self._selected_rows_moved)

    def refresh(self) -> None:
        current_available = [item.data(256) for item in self.available_list.selectedItems()]
        self.available_list.blockSignals(True)
        self.available_list.clear()
        for asset in self._standalone_assets():
            item = QListWidgetItem(QIcon(asset_thumbnail(asset, QSize(140, 96))), asset.filename)
            item.setData(256, asset.id)
            self.available_list.addItem(item)
            if asset.id in current_available:
                item.setSelected(True)
        self.available_list.blockSignals(False)
        self._refresh_selected_list()
        self._update_buttons()

    def import_images(self) -> None:
        filters = "Images (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)) + ")"
        filenames, _selected = QFileDialog.getOpenFileNames(self, "Import Images", "", filters)
        if not filenames:
            return
        try:
            assets = import_images(self.project, [Path(filename) for filename in filenames])
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Import Images Failed", str(exc))
            return
        self._push_undo()
        for asset in assets:
            self._append_asset(asset.id)
        self.project.touch()
        self.refresh()

    def add_selected_available_images(self) -> None:
        ids = [str(item.data(256)) for item in self.available_list.selectedItems()]
        if not ids and self.available_list.currentItem() is not None:
            ids = [str(self.available_list.currentItem().data(256))]
        if not ids:
            return
        self._push_undo()
        for asset_id in ids:
            self._append_asset(asset_id)
        self._refresh_selected_list()

    def remove_selected_image(self) -> None:
        row = self.selected_list.currentRow()
        if row < 0 or row >= len(self._selected_asset_ids):
            return
        self._push_undo()
        self._selected_asset_ids.pop(row)
        self._refresh_selected_list()

    def move_selected(self, direction: int) -> None:
        row = self.selected_list.currentRow()
        target = row + direction
        if row < 0 or target < 0 or target >= len(self._selected_asset_ids):
            return
        self._push_undo()
        self._selected_asset_ids[row], self._selected_asset_ids[target] = (
            self._selected_asset_ids[target],
            self._selected_asset_ids[row],
        )
        self._refresh_selected_list()
        self.selected_list.setCurrentRow(target)

    def clear_selection(self) -> None:
        if not self._selected_asset_ids:
            return
        self._push_undo()
        self._selected_asset_ids.clear()
        self._refresh_selected_list()

    def undo(self) -> None:
        if not self._undo_stack:
            return
        self._redo_stack.append(list(self._selected_asset_ids))
        self._selected_asset_ids = self._undo_stack.pop()
        self._refresh_selected_list()

    def redo(self) -> None:
        if not self._redo_stack:
            return
        self._undo_stack.append(list(self._selected_asset_ids))
        self._selected_asset_ids = self._redo_stack.pop()
        self._refresh_selected_list()

    def stitch_images(self) -> None:
        assets = [
            self.project.assets[asset_id]
            for asset_id in self._selected_asset_ids
            if asset_id in self.project.assets
        ]
        if len(assets) < 2:
            QMessageBox.warning(self, "Stitch Images", "Select at least two images to stitch.")
            return
        self._worker = ImageStitchWorker(ImageStitchJob(assets))
        self._worker.progressChanged.connect(self._show_progress)
        self._worker.stitchFinished.connect(self._stitch_finished)
        self._worker.stitchFailed.connect(self._stitch_failed)
        self._worker.finished.connect(self._worker_finished)
        self.stitch_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        self._worker.start()

    def cancel_stitching(self) -> None:
        if self._worker is not None:
            self._worker.cancel()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if (
            event.mimeData().hasFormat("application/x-biopic-asset-id")
            or event.mimeData().hasUrls()
        ):
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        if event.mimeData().hasFormat("application/x-biopic-asset-id"):
            asset_id = bytes(event.mimeData().data("application/x-biopic-asset-id")).decode("utf-8")
            self._push_undo()
            self._append_asset(asset_id)
            self._refresh_selected_list()
            event.acceptProposedAction()
            return
        paths = [
            Path(url.toLocalFile())
            for url in event.mimeData().urls()
            if url.isLocalFile() and Path(url.toLocalFile()).suffix.lower() in SUPPORTED_EXTENSIONS
        ]
        if paths:
            try:
                assets = import_images(self.project, paths)
            except (OSError, ValueError) as exc:
                QMessageBox.critical(self, "Import Images Failed", str(exc))
                return
            self._push_undo()
            for asset in assets:
                self._append_asset(asset.id)
            self.refresh()
            event.acceptProposedAction()

    def _stitch_finished(self, result: object) -> None:
        if not isinstance(result, StitchResult):
            self._stitch_failed("Unexpected stitch result.")
            return
        output_dir = (Path.cwd() / ".biopic_cache" / self.project.id / "stitched").resolve()
        output_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        path = output_dir / f"stitched_{timestamp}_{uuid4().hex[:8]}.png"
        try:
            export_image(result.pixels, path)
            read_result = read_image_asset(path, load_pixels=False)
        except (OSError, ValueError) as exc:
            self._stitch_failed(str(exc))
            return
        asset = read_result.asset
        asset.kind = ImageAssetKind.EDIT_DERIVATIVE
        asset.display_name = f"Stitched image {len(self._session_stitched_ids()) + 1}"
        asset.metadata.update(result.metadata)
        asset.metadata.update(
            {
                "operation": "stitch_images",
                "created_at": datetime.now(UTC).isoformat(),
                "stitch_session": True,
            }
        )
        self.project.add_asset(asset)
        self.canvas.set_pixels(result.pixels, asset.filename)
        self.progress.setFormat("Stitch complete")
        self.stitchCreated.emit([asset.id])

    def _stitch_failed(self, message: str) -> None:
        QMessageBox.warning(self, "Stitch Images", message)
        self.progress.setFormat(message)

    def _worker_finished(self) -> None:
        self.stitch_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None

    def _show_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(max(0.0, min(1.0, float(fraction))) * 100.0))
        self.progress.setFormat(message)

    def _selected_rows_moved(self) -> None:
        ids = []
        for row in range(self.selected_list.count()):
            ids.append(str(self.selected_list.item(row).data(256)))
        if ids != self._selected_asset_ids:
            self._push_undo()
            self._selected_asset_ids = ids
            self._update_buttons()

    def _standalone_assets(self) -> list[ImageAsset]:
        stacked_ids = {
            asset_id
            for stack in self.project.stacks.values()
            for asset_id in stack.asset_ids
        }
        return [
            asset
            for asset in self.project.assets.values()
            if asset.id not in stacked_ids
            and asset.kind is not ImageAssetKind.STACK_SOURCE
            and asset.metadata.get("temporary_preview") is not True
        ]

    def _append_asset(self, asset_id: str) -> None:
        if asset_id not in self._selected_asset_ids and asset_id in self.project.assets:
            self._selected_asset_ids.append(asset_id)

    def _refresh_selected_list(self) -> None:
        current = self.selected_list.currentRow()
        self.selected_list.blockSignals(True)
        self.selected_list.clear()
        for index, asset_id in enumerate(self._selected_asset_ids, start=1):
            asset = self.project.assets.get(asset_id)
            if asset is None:
                continue
            item = QListWidgetItem(
                QIcon(asset_thumbnail(asset, QSize(140, 96))),
                f"{index}. {asset.filename}",
            )
            item.setData(256, asset.id)
            self.selected_list.addItem(item)
        self.selected_list.blockSignals(False)
        if self.selected_list.count():
            self.selected_list.setCurrentRow(max(0, min(current, self.selected_list.count() - 1)))
        self.empty_label.setVisible(not self._selected_asset_ids)
        self._update_buttons()

    def _push_undo(self) -> None:
        self._undo_stack.append(list(self._selected_asset_ids))
        self._redo_stack.clear()

    def _session_stitched_ids(self) -> list[str]:
        return [
            asset.id
            for asset in self.project.assets.values()
            if asset.metadata.get("stitch_session") is True
        ]

    def _update_buttons(self) -> None:
        has_selection = bool(self._selected_asset_ids)
        self.remove_button.setEnabled(has_selection)
        self.clear_button.setEnabled(has_selection)
        self.stitch_button.setEnabled(len(self._selected_asset_ids) >= 2 and self._worker is None)
        self.undo_button.setEnabled(bool(self._undo_stack))
        self.redo_button.setEnabled(bool(self._redo_stack))
