"""Focus stacking workspace."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from biopic.export.raster import export_image
from biopic.imaging.io import file_checksum, read_image_asset
from biopic.imaging.stacking import (
    AlignmentMode,
    FocusMetric,
    FocusStackParameters,
    FocusStackResult,
    StackingMethod,
)
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.thumbnail_strip import ThumbnailStrip
from biopic.ui.workspace_helpers.common import stack_result_metadata, stack_thumbnail
from biopic.workers.focus_stack_worker import FocusStackJob, FocusStackWorker

STACK_THUMBNAIL_SIZE = QSize(120, 88)


class StackWorkspace(QWidget):
    """Focus-stack workspace shell with ordered thumbnails and preview panes."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._worker: FocusStackWorker | None = None
        self._current_stack_id: str | None = None
        self._running_stack_id: str | None = None
        self._last_stack_result: np.ndarray | None = None
        self._stack_results: dict[str, np.ndarray] = {}
        self.stackCompleted: Callable[[], None] | None = None
        layout = QVBoxLayout(self)
        self.stack_list = QListWidget()
        self.stack_list.setFlow(QListWidget.Flow.LeftToRight)
        self.stack_list.setWrapping(False)
        self.stack_list.setIconSize(STACK_THUMBNAIL_SIZE)
        self.stack_list.setUniformItemSizes(True)
        self.stack_list.setFixedHeight(128)
        layout.addWidget(QLabel("Stacks"))
        layout.addWidget(self.stack_list)
        self.thumbnails = ThumbnailStrip(QSize(72, 54))
        self.thumbnails.setUniformItemSizes(True)
        self.thumbnails.setFixedHeight(96)
        layout.addWidget(QLabel("Sources"))
        layout.addWidget(self.thumbnails)

        controls = QHBoxLayout()
        self.method_combo = QComboBox()
        self.method_combo.addItem("Depth Map", StackingMethod.DEPTH_MAP.value)
        self.method_combo.addItem(
            "Pyramid Max Contrast", StackingMethod.PYRAMID_MAX_CONTRAST.value
        )
        self.metric_combo = QComboBox()
        for metric in FocusMetric:
            self.metric_combo.addItem(metric.value.replace("_", " ").title(), metric.value)
        self.patch_size_spin = QSpinBox()
        self.patch_size_spin.setRange(1, 51)
        self.patch_size_spin.setSingleStep(2)
        self.patch_size_spin.setValue(7)
        self.smoothing_spin = QDoubleSpinBox()
        self.smoothing_spin.setRange(0.0, 20.0)
        self.smoothing_spin.setSingleStep(0.5)
        self.smoothing_spin.setValue(2.0)
        self.noise_suppression_spin = QDoubleSpinBox()
        self.noise_suppression_spin.setRange(0.0, 10.0)
        self.noise_suppression_spin.setSingleStep(0.25)
        self.noise_suppression_spin.setValue(1.0)
        self.score_threshold_spin = QSpinBox()
        self.score_threshold_spin.setRange(0, 29)
        self.score_threshold_spin.setValue(4)
        self.region_bias_spin = QSpinBox()
        self.region_bias_spin.setRange(-10, 10)
        self.region_bias_spin.setValue(0)
        self.scale_preset_spin = QSpinBox()
        self.scale_preset_spin.setRange(1, 5)
        self.scale_preset_spin.setValue(3)
        self.adaptive_weighting_check = QCheckBox("Adaptive")
        self.adaptive_weighting_check.setChecked(True)
        self.detail_scale_label = QLabel("Detail scale")
        self.detail_scale_spin = QSpinBox()
        self.detail_scale_spin.setRange(1, 10)
        self.detail_scale_spin.setValue(4)
        self.align_check = QCheckBox("Align")
        self.align_check.setChecked(True)
        self.preview_check = QCheckBox("Preview")
        self.preview_check.setChecked(True)
        self.run_button = QPushButton("Stack")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.reverse_button = QPushButton("Reverse")
        self.remove_button = QPushButton("Remove Image")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        controls.addWidget(QLabel("Method"))
        controls.addWidget(self.method_combo)
        controls.addWidget(QLabel("Metric"))
        controls.addWidget(self.metric_combo)
        controls.addWidget(QLabel("Patch size"))
        controls.addWidget(self.patch_size_spin)
        controls.addWidget(QLabel("Smooth"))
        controls.addWidget(self.smoothing_spin)
        controls.addWidget(QLabel("Noise suppression"))
        controls.addWidget(self.noise_suppression_spin)
        controls.addWidget(QLabel("Score gate"))
        controls.addWidget(self.score_threshold_spin)
        controls.addWidget(QLabel("Region bias"))
        controls.addWidget(self.region_bias_spin)
        controls.addWidget(QLabel("Scale preset"))
        controls.addWidget(self.scale_preset_spin)
        controls.addWidget(self.adaptive_weighting_check)
        controls.addWidget(self.detail_scale_label)
        controls.addWidget(self.detail_scale_spin)
        controls.addWidget(self.align_check)
        controls.addWidget(self.preview_check)
        controls.addWidget(self.reverse_button)
        controls.addWidget(self.remove_button)
        controls.addWidget(self.run_button)
        controls.addWidget(self.cancel_button)
        controls.addWidget(self.progress)
        layout.addLayout(controls)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_canvas = ImageCanvas()
        self.result_canvas = ImageCanvas()
        self.source_canvas.set_empty_watermark_visible(False)
        self.result_canvas.set_empty_watermark_visible(False)
        splitter.addWidget(self.source_canvas)
        splitter.addWidget(self.result_canvas)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([640, 640])
        layout.addWidget(splitter)
        layout.setStretchFactor(splitter, 1)
        self.stack_list.currentItemChanged.connect(self._select_stack_item)
        self.thumbnails.assetSelected.connect(self.select_asset)
        self.run_button.clicked.connect(self.run_stacking)
        self.cancel_button.clicked.connect(self.cancel_stacking)
        self.reverse_button.clicked.connect(self.reverse_current_stack)
        self.remove_button.clicked.connect(self.remove_selected_image)

    def refresh(self) -> None:
        """Refresh thumbnails from the most recent stack or all assets."""
        current = self._current_stack_id
        self.stack_list.blockSignals(True)
        self.stack_list.clear()
        for stack in self.project.stacks.values():
            assets = [
                self.project.assets[asset_id]
                for asset_id in stack.asset_ids
                if asset_id in self.project.assets
            ]
            item = QListWidgetItem(
                QIcon(stack_thumbnail(assets, STACK_THUMBNAIL_SIZE)),
                f"{stack.name}\n{len(stack.asset_ids)} frames",
            )
            item.setData(256, stack.id)
            self.stack_list.addItem(item)
        self.stack_list.blockSignals(False)
        if current is not None:
            for row in range(self.stack_list.count()):
                if self.stack_list.item(row).data(256) == current:
                    self.stack_list.setCurrentRow(row)
                    break
        if self.stack_list.count() and self.stack_list.currentRow() < 0:
            self.stack_list.setCurrentRow(0)
        assets = self._current_stack_assets()
        self.thumbnails.set_assets(assets)
        if assets:
            self.source_canvas.set_asset(assets[0])
        else:
            self.source_canvas.set_asset(None)
        self._refresh_result_canvas()

    def select_asset(self, asset_id: str) -> None:
        """Show the selected source asset."""
        asset = self.project.assets.get(asset_id)
        if asset is not None:
            self.source_canvas.set_asset(asset)

    def select_stack(self, stack_id: str) -> None:
        """Select a stack by id after external creation."""
        self._current_stack_id = stack_id
        self.refresh()

    def run_stacking(self) -> None:
        """Run focus stacking for the current stack."""
        assets = self._current_stack_assets()
        stack = self._current_stack()
        if stack is None:
            return
        if len(assets) < 1:
            return
        self._running_stack_id = stack.id
        self.run_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        job = FocusStackJob(assets=assets, parameters=self._parameters())
        self._worker = FocusStackWorker(job)
        self._worker.progressChanged.connect(self._show_progress)
        self._worker.stackFinished.connect(self._stack_finished)
        self._worker.stackFailed.connect(self._stack_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def cancel_stacking(self) -> None:
        """Request cancellation of the current stack job."""
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)

    def _parameters(self) -> FocusStackParameters:
        alignment = (
            AlignmentMode.TRANSLATION if self.align_check.isChecked() else AlignmentMode.NONE
        )
        patch_size = self.patch_size_spin.value()
        return FocusStackParameters(
            stacking_method=StackingMethod(str(self.method_combo.currentData())),
            focus_metric=FocusMetric(str(self.metric_combo.currentData())),
            focus_radius=max(1, patch_size // 2),
            smoothing_sigma=self.smoothing_spin.value(),
            halo_suppression_sigma=self.noise_suppression_spin.value(),
            score_threshold=self.score_threshold_spin.value(),
            region_bias=self.region_bias_spin.value(),
            scale_preset=self.scale_preset_spin.value(),
            adaptive_weighting=self.adaptive_weighting_check.isChecked(),
            detail_scale=self.detail_scale_spin.value(),
            alignment_mode=alignment,
            preview_scale=0.35 if self.preview_check.isChecked() else 1.0,
        )

    def _current_stack_assets(self) -> list[ImageAsset]:
        stack = (
            self.project.stacks.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        if stack is None:
            return []
        return [
            self.project.assets[asset_id]
            for asset_id in stack.asset_ids
            if asset_id in set(stack.enabled_asset_ids or []) and asset_id in self.project.assets
        ]

    def _show_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 100))
        self.progress.setFormat(f"{message} %p%")

    def _stack_finished(self, result: object) -> None:
        stack_result = result
        if not isinstance(stack_result, FocusStackResult):
            self._stack_failed("Unexpected stack result type.")
            return
        stack_id = self._running_stack_id
        if stack_id is None or stack_id not in self.project.stacks:
            self._stack_failed("Stack no longer exists.")
            return
        self._last_stack_result = stack_result.image
        self._stack_results[stack_id] = stack_result.image
        if self._current_stack_id == stack_id:
            self.result_canvas.set_pixels(stack_result.image, "Focus-stacked result")
        source_node_ids = [
            node_id
            for asset in self._stack_assets(stack_id)
            if (node_id := self.project.source_node_id_for_asset(asset.id)) is not None
        ]
        node = ProcessingNode(
            operation="focus_stack",
            inputs=tuple(source_node_ids),
            parameters=stack_result.parameters.to_dict(),
            provenance={
                "transforms": [transform.to_dict() for transform in stack_result.transforms],
                "reference": (
                    "Independent BioPic LM implementation; decomp.txt used only for behavior."
                ),
            },
        )
        self.project.graph.add_node(node)
        self._register_stack_result_asset(stack_result, node, stack_id)
        self.project.touch()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _stack_failed(self, message: str) -> None:
        self.progress.setFormat(message)

    def _worker_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None
        self._running_stack_id = None

    def save_last_result(self, path: str) -> bool:
        """Save the most recent focus-stacked result."""
        result = (
            self._stack_results.get(self._current_stack_id)
            if self._current_stack_id is not None
            else self._last_stack_result
        )
        if result is None:
            return False
        export_image(result, Path(path))
        return True

    def reverse_current_stack(self) -> None:
        """Reverse the selected stack order."""
        stack = self._current_stack()
        if stack is None:
            return
        stack.asset_ids.reverse()
        if stack.enabled_asset_ids is not None:
            stack.enabled_asset_ids.reverse()
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def remove_selected_image(self) -> None:
        """Remove the selected source image from the current stack."""
        stack = self._current_stack()
        current = self.thumbnails.currentItem()
        if stack is None or current is None:
            return
        asset_id = str(current.data(256))
        stack.asset_ids = [item for item in stack.asset_ids if item != asset_id]
        stack.enabled_asset_ids = [
            item for item in (stack.enabled_asset_ids or []) if item != asset_id
        ]
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _select_stack_item(self, current: QListWidgetItem | None) -> None:
        self._current_stack_id = None if current is None else str(current.data(256))
        assets = self._current_stack_assets()
        self.thumbnails.set_assets(assets)
        if assets:
            self.source_canvas.set_asset(assets[0])
        else:
            self.source_canvas.set_asset(None)
        self._refresh_result_canvas()

    def _current_stack(self) -> ImageStack | None:
        if self._current_stack_id is None:
            return None
        return self.project.stacks.get(self._current_stack_id)

    def _stack_assets(self, stack_id: str) -> list[ImageAsset]:
        stack = self.project.stacks.get(stack_id)
        if stack is None:
            return []
        enabled = set(stack.enabled_asset_ids or [])
        return [
            self.project.assets[asset_id]
            for asset_id in stack.asset_ids
            if asset_id in enabled and asset_id in self.project.assets
        ]

    def _refresh_result_canvas(self) -> None:
        if self._current_stack_id is None:
            self.result_canvas.set_asset(None)
            return
        result = self._stack_results.get(self._current_stack_id)
        if result is not None:
            self.result_canvas.set_pixels(result, "Focus-stacked result")
            return
        asset = self._stack_result_asset(self._current_stack_id)
        if asset is not None:
            self.result_canvas.set_asset(asset)
            return
        self.result_canvas.set_asset(None)

    def _stack_result_asset(self, stack_id: str) -> ImageAsset | None:
        return next(
            (
                asset
                for asset in self.project.assets.values()
                if asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
            ),
            None,
        )

    def _register_stack_result_asset(
        self, result: FocusStackResult, node: ProcessingNode, stack_id: str | None = None
    ) -> None:
        stack = (
            self.project.stacks.get(stack_id)
            if stack_id is not None
            else self._current_stack()
        )
        if stack is None:
            return
        cache_dir = (Path.cwd() / ".biopic_cache" / self.project.id / "stack_results").resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)
        path = cache_dir / f"{stack.id}_stacked.tif"
        export_image(result.image, path)
        read_result = read_image_asset(path, load_pixels=False)
        existing = next(
            (
                asset
                for asset in self.project.assets.values()
                if asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack.id
            ),
            None,
        )
        if existing is None:
            asset = read_result.asset
            asset.kind = ImageAssetKind.STACK_RESULT
            asset.display_name = f"{stack.name} - stacked result"
            asset.origin_node_id = node.id
            asset.metadata.update(stack_result_metadata(stack, node, result))
            self.project.add_asset(asset)
            return
        existing.path = str(path)
        existing.checksum = file_checksum(path)
        existing.width = read_result.asset.width
        existing.height = read_result.asset.height
        existing.frames = read_result.asset.frames
        existing.dtype = read_result.asset.dtype
        existing.color_model = read_result.asset.color_model
        existing.display_name = f"{stack.name} - stacked result"
        existing.origin_node_id = node.id
        existing.metadata.update(stack_result_metadata(stack, node, result))
