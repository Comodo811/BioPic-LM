"""Focus stacking workspace."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from pathlib import Path

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from biopic.export.raster import export_image
from biopic.imaging.io import SUPPORTED_EXTENSIONS, file_checksum, import_images, read_image_asset
from biopic.imaging.stacking import (
    AlignmentMode,
    BackgroundMode,
    FocusMetric,
    FocusStackParameters,
    FocusStackResult,
    StackingMethod,
    gpu_backend_status,
)
from biopic.imaging.stacking.gpu_memory import plan_gpu_memory_from_shapes
from biopic.imaging.stacking.private_methods import private_method_available
from biopic.models.image_asset import ImageAsset, ImageAssetKind
from biopic.models.image_stack import ImageStack
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode
from biopic.sharpness_comparison.config_models import SharpnessComparisonSummary
from biopic.sharpness_comparison.dialog import SharpnessComparisonDialog
from biopic.sharpness_comparison.metrics import display_name as sharpness_metric_display_name
from biopic.sharpness_comparison.workers import (
    SharpnessComparisonJob,
    SharpnessComparisonWorker,
)
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.settings import remembered_open_files, set_settings_json, settings_json
from biopic.ui.stack_import_resolution import resolve_stack_import_paths
from biopic.ui.thumbnail_strip import ThumbnailStrip
from biopic.ui.workspace_helpers.common import stack_result_metadata, stack_thumbnail
from biopic.workers.focus_stack_worker import FocusStackJob, FocusStackWorker

STACK_THUMBNAIL_SIZE = QSize(120, 88)
STACK_DEFAULTS_KEY = "stack/default_parameters"


class StackWorkspace(QWidget):
    """Focus-stack workspace shell with ordered thumbnails and preview panes."""

    def minimumSizeHint(self) -> QSize:
        """Keep controls scrollable instead of imposing their total width on the window."""
        return QSize(320, 220)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._worker: FocusStackWorker | None = None
        self._comparison_worker: SharpnessComparisonWorker | None = None
        self._current_stack_id: str | None = None
        self._running_stack_id: str | None = None
        self._running_preview = False
        self._last_stack_result: np.ndarray | None = None
        self._stack_results: dict[str, np.ndarray] = {}
        self._comparison_summaries: dict[str, SharpnessComparisonSummary] = {}
        self._comparison_assets: dict[str, list[ImageAsset]] = {}
        self._selected_result_pixels: np.ndarray | None = None
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

        controls_container = QWidget()
        controls = QHBoxLayout(controls_container)
        controls.setContentsMargins(0, 0, 0, 0)
        self.method_combo = QComboBox()
        self.method_combo.addItem("Depth Map", StackingMethod.DEPTH_MAP.value)
        self.method_combo.addItem(
            "Pyramid Max Contrast", StackingMethod.PYRAMID_MAX_CONTRAST.value
        )
        if private_method_available("custom"):
            self.method_combo.addItem("Custom", StackingMethod.CUSTOM.value)
        if private_method_available("custom2"):
            self.method_combo.addItem("Custom2", StackingMethod.CUSTOM2.value)
        self.metric_combo = QComboBox()
        for metric in FocusMetric:
            self.metric_combo.addItem(metric.value.replace("_", " ").title(), metric.value)
        self.patch_size_spin = QSpinBox()
        self.patch_size_spin.setRange(-10, 10)
        self.patch_size_spin.setSingleStep(1)
        self.patch_size_spin.setValue(0)
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
        self.scale_preset_spin = QSpinBox()
        self.scale_preset_spin.setRange(1, 5)
        self.scale_preset_spin.setValue(3)
        self.background_combo = QComboBox()
        self.background_combo.addItem("Median BG", BackgroundMode.MEDIAN.value)
        self.background_combo.addItem("Mixed BG", BackgroundMode.MIXED.value)
        self.background_combo.addItem("Dark BG", BackgroundMode.DARKEST.value)
        self.background_combo.addItem("Bright BG", BackgroundMode.BRIGHTEST.value)
        self.background_combo.addItem("First BG", BackgroundMode.FIRST.value)
        self.background_combo.addItem("Last BG", BackgroundMode.LAST.value)
        self.confidence_cleanup_check = QCheckBox("Clean map")
        self.confidence_cleanup_check.setChecked(True)
        self.adaptive_weighting_check = QCheckBox("Adaptive")
        self.adaptive_weighting_check.setChecked(True)
        self.detail_scale_label = QLabel("Detail scale")
        self.detail_scale_spin = QSpinBox()
        self.detail_scale_spin.setRange(1, 10)
        self.detail_scale_spin.setValue(4)
        self.align_check = QCheckBox("Align")
        self.align_check.setChecked(True)
        self.cuda_check = QCheckBox("Use CUDA")
        self.cuda_check.setChecked(False)
        self.gpu_limit_spin = QSpinBox()
        self.gpu_limit_spin.setRange(2, 24)
        self.gpu_limit_spin.setValue(4)
        self.gpu_limit_spin.setSuffix(" GB")
        self._refresh_cuda_tooltip()
        self.run_button = QPushButton("Stack")
        self.comparison_button = QPushButton("Sharpness Comparison")
        self.preview_button = QPushButton("Low-Res Preview")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.reverse_button = QPushButton("Reverse")
        self.add_images_button = QPushButton("Add Images")
        self.remove_button = QPushButton("Remove Image")
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        controls.addWidget(QLabel("Method"))
        controls.addWidget(self.method_combo)
        controls.addWidget(QLabel("Metric"))
        controls.addWidget(self.metric_combo)
        controls.addWidget(QLabel("Patch adjust"))
        controls.addWidget(self.patch_size_spin)
        controls.addWidget(QLabel("Smooth"))
        controls.addWidget(self.smoothing_spin)
        controls.addWidget(QLabel("Noise suppression"))
        controls.addWidget(self.noise_suppression_spin)
        controls.addWidget(QLabel("Score gate"))
        controls.addWidget(self.score_threshold_spin)
        controls.addWidget(QLabel("Scale preset"))
        controls.addWidget(self.scale_preset_spin)
        controls.addWidget(QLabel("Background"))
        controls.addWidget(self.background_combo)
        controls.addWidget(self.confidence_cleanup_check)
        controls.addWidget(self.adaptive_weighting_check)
        controls.addWidget(self.detail_scale_label)
        controls.addWidget(self.detail_scale_spin)
        controls.addWidget(self.align_check)
        controls.addWidget(self.cuda_check)
        controls.addWidget(QLabel("GPU limit"))
        controls.addWidget(self.gpu_limit_spin)
        controls.addWidget(self.add_images_button)
        controls.addWidget(self.remove_button)
        controls.addWidget(self.preview_button)
        controls.addWidget(self.run_button)
        controls.addWidget(self.progress)
        self._restore_parameter_defaults()
        controls_scroll = QScrollArea()
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        controls_scroll.setMinimumWidth(1)
        controls_scroll.setWidget(controls_container)
        layout.addWidget(controls_scroll)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.source_canvas = ImageCanvas()
        self.result_canvas = ImageCanvas()
        self.result_summary_label = QLabel("")
        self.result_summary_label.setWordWrap(True)
        self.result_table = QTableWidget()
        self.result_table.setSortingEnabled(True)
        self.result_table_panel = QWidget()
        result_table_layout = QVBoxLayout(self.result_table_panel)
        result_table_layout.setContentsMargins(0, 0, 0, 0)
        result_table_layout.addWidget(self.result_summary_label)
        result_table_layout.addWidget(self.result_table)
        self.result_view_stack = QStackedWidget()
        self.result_view_stack.addWidget(self.result_canvas)
        self.result_view_stack.addWidget(self.result_table_panel)
        self.source_canvas.set_empty_watermark_visible(False)
        self.result_canvas.set_empty_watermark_visible(False)
        splitter.addWidget(self.source_canvas)
        splitter.addWidget(self.result_view_stack)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([640, 640])
        layout.addWidget(splitter)
        layout.setStretchFactor(splitter, 1)
        self.stack_list.currentItemChanged.connect(self._select_stack_item)
        self.thumbnails.assetSelected.connect(self.select_asset)
        for key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            shortcut = QShortcut(QKeySequence(key), self.thumbnails)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self.remove_selected_image)
        self.run_button.clicked.connect(self.run_stacking)
        self.comparison_button.clicked.connect(self.open_sharpness_comparison)
        self.preview_button.clicked.connect(self.run_low_res_preview)
        self.cancel_button.clicked.connect(self.cancel_stacking)
        self.add_images_button.clicked.connect(self.add_images_to_current_stack)
        self.reverse_button.clicked.connect(self.reverse_current_stack)
        self.remove_button.clicked.connect(self.remove_selected_image)
        self.thumbnails.currentItemChanged.connect(self._select_stack_entry_item)
        self.result_table.cellClicked.connect(self._select_comparison_result_row)
        self.result_table.cellDoubleClicked.connect(self._select_comparison_result_row)
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        self.gpu_limit_spin.valueChanged.connect(lambda _value: self._refresh_cuda_tooltip())
        self._update_comparison_button_enabled()

    def _method_changed(self, _index: int) -> None:
        self._refresh_cuda_tooltip()

    def refresh(self) -> None:
        """Refresh thumbnails from the most recent stack or all assets."""
        self._remove_empty_stacks()
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
        self._refresh_stack_entries()
        self._update_comparison_button_enabled()
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
        self._start_stacking(preview=False)

    def open_sharpness_comparison(self) -> None:
        """Run a sharpness comparison for the current stack."""
        assets = self._current_stack_assets()
        stack = self._current_stack()
        if (
            stack is None
            or len(assets) < 2
            or self._worker is not None
            or self._comparison_worker is not None
        ):
            return
        dialog = SharpnessComparisonDialog(self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self._running_stack_id = stack.id
        self.run_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.comparison_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        job = SharpnessComparisonJob(
            assets=assets,
            base_parameters=self._parameters(),
            config=dialog.config(),
            project_id=self.project.id,
            stack_name=stack.name,
        )
        self._comparison_worker = SharpnessComparisonWorker(job)
        self._comparison_worker.progressChanged.connect(self._show_progress)
        self._comparison_worker.comparisonFinished.connect(self._comparison_finished)
        self._comparison_worker.comparisonFailed.connect(self._stack_failed)
        self._comparison_worker.finished.connect(self._worker_finished)
        self._comparison_worker.start()

    def run_low_res_preview(self) -> None:
        """Run a temporary low-resolution focus-stack preview."""
        self._start_stacking(preview=True)

    def _start_stacking(self, preview: bool) -> None:
        """Run focus stacking for the current stack or a temporary preview."""
        assets = self._current_stack_assets()
        stack = self._current_stack()
        if stack is None:
            return
        if len(assets) < 1:
            return
        self._running_stack_id = stack.id
        self._running_preview = preview
        self.run_button.setEnabled(False)
        self.preview_button.setEnabled(False)
        self.comparison_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        self.progress.setValue(0)
        parameters = self._parameters()
        if preview:
            parameters = replace(parameters, preview_scale=0.35)
        else:
            self._save_parameter_defaults(parameters)
        job = FocusStackJob(assets=assets, parameters=parameters)
        self._worker = FocusStackWorker(job)
        self._worker.progressChanged.connect(self._show_progress)
        self._worker.stackPreviewChanged.connect(self._show_stack_preview)
        self._worker.stackFinished.connect(self._stack_finished)
        self._worker.stackFailed.connect(self._stack_failed)
        self._worker.finished.connect(self._worker_finished)
        self._worker.start()

    def cancel_stacking(self) -> None:
        """Request cancellation of the current stack job."""
        if self._worker is not None:
            self._worker.cancel()
            self.cancel_button.setEnabled(False)
        if self._comparison_worker is not None:
            self._comparison_worker.cancel()
            self.cancel_button.setEnabled(False)

    def _parameters(self) -> FocusStackParameters:
        alignment = (
            AlignmentMode.TRANSLATION if self.align_check.isChecked() else AlignmentMode.NONE
        )
        patch_adjustment = self.patch_size_spin.value()
        return FocusStackParameters(
            stacking_method=StackingMethod(str(self.method_combo.currentData())),
            focus_metric=FocusMetric(str(self.metric_combo.currentData())),
            focus_radius=3,
            smoothing_sigma=self.smoothing_spin.value(),
            halo_suppression_sigma=self.noise_suppression_spin.value(),
            score_threshold=self.score_threshold_spin.value(),
            region_bias=patch_adjustment,
            scale_preset=self.scale_preset_spin.value(),
            adaptive_weighting=self.adaptive_weighting_check.isChecked(),
            detail_scale=self.detail_scale_spin.value(),
            background_mode=BackgroundMode(str(self.background_combo.currentData())),
            confidence_cleanup=self.confidence_cleanup_check.isChecked(),
            alignment_mode=alignment,
            preview_scale=1.0,
            use_cuda=self.cuda_check.isChecked(),
            gpu_memory_limit_mb=self.gpu_limit_spin.value() * 1024,
        )

    def _restore_parameter_defaults(self) -> None:
        defaults = settings_json(STACK_DEFAULTS_KEY, {})
        if not isinstance(defaults, dict):
            return
        self._set_combo_value(self.method_combo, defaults.get("stacking_method"))
        self._set_combo_value(self.metric_combo, defaults.get("focus_metric"))
        patch_adjustment = defaults.get("patch_adjustment", defaults.get("region_bias", 0))
        self.patch_size_spin.setValue(int(patch_adjustment))
        self.smoothing_spin.setValue(
            float(defaults.get("smoothing_sigma", self.smoothing_spin.value()))
        )
        self.noise_suppression_spin.setValue(
            float(defaults.get("halo_suppression_sigma", self.noise_suppression_spin.value()))
        )
        self.score_threshold_spin.setValue(
            int(defaults.get("score_threshold", self.score_threshold_spin.value()))
        )
        self.scale_preset_spin.setValue(
            int(defaults.get("scale_preset", self.scale_preset_spin.value()))
        )
        self._set_combo_value(self.background_combo, defaults.get("background_mode"))
        self.confidence_cleanup_check.setChecked(
            bool(defaults.get("confidence_cleanup", self.confidence_cleanup_check.isChecked()))
        )
        self.adaptive_weighting_check.setChecked(
            bool(defaults.get("adaptive_weighting", self.adaptive_weighting_check.isChecked()))
        )
        self.detail_scale_spin.setValue(
            int(defaults.get("detail_scale", self.detail_scale_spin.value()))
        )
        alignment_mode = str(defaults.get("alignment_mode", AlignmentMode.TRANSLATION.value))
        self.align_check.setChecked(alignment_mode == AlignmentMode.TRANSLATION.value)
        self.cuda_check.setChecked(bool(defaults.get("use_cuda", self.cuda_check.isChecked())))
        self.gpu_limit_spin.setValue(
            max(2, int(defaults.get("gpu_memory_limit_mb", self.gpu_limit_spin.value() * 1024)) // 1024)
        )
        self._refresh_cuda_tooltip()

    def _refresh_cuda_tooltip(self) -> None:
        status = gpu_backend_status()
        if status.get("available"):
            assets = self._current_stack_assets() if hasattr(self, "thumbnails") else []
            memory_text = ""
            if assets:
                try:
                    shapes = [
                        (asset.height, asset.width, 3)
                        if asset.color_model in {"rgb", "rgba"}
                        else (asset.height, asset.width)
                        for asset in assets
                    ]
                    plan = plan_gpu_memory_from_shapes(
                        shapes,
                        multiplier=5.5,
                        memory_limit_mb=self.gpu_limit_spin.value() * 1024,
                    )
                    mode = "full-frame GPU" if plan.full_frame_possible else "CPU fallback likely"
                    memory_text = (
                        f" Estimated stack memory: {plan.required_memory_mb} MB; "
                        f"free GPU memory: {plan.free_memory_mb} MB; {mode}."
                    )
                except (ValueError, MemoryError):
                    memory_text = ""
            method_text = ""
            if str(self.method_combo.currentData()) == StackingMethod.CUSTOM.value:
                method_text = (
                    " Custom currently uses only partial CUDA acceleration; "
                    "Depth Map and Pyramid Max Contrast are the GPU-first methods."
                )
            elif str(self.method_combo.currentData()) == StackingMethod.CUSTOM2.value:
                method_text = (
                    " Custom2 uses the GPU-enabled PMax detail stage when available, "
                    "but its Custom base stage remains mostly CPU."
                )
            self.cuda_check.setToolTip(
                f"CUDA GPU backend available: {status.get('device_name', 'CUDA device')}."
                f"{memory_text}{method_text}"
            )
            return
        self.cuda_check.setToolTip(
            "CUDA GPU backend is not available in this Python environment. "
            f"Reason: {status.get('reason', 'unknown')}. CPU fallback will be used."
        )

    def _save_parameter_defaults(self, parameters: FocusStackParameters) -> None:
        data = parameters.to_dict()
        data["patch_adjustment"] = self.patch_size_spin.value()
        set_settings_json(STACK_DEFAULTS_KEY, data)

    def _set_combo_value(self, combo: QComboBox, value: object) -> None:
        if value is None:
            return
        index = combo.findData(str(value))
        if index >= 0:
            combo.setCurrentIndex(index)

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

    def _refresh_stack_entries(self) -> None:
        """Show source images plus comparison table/generated results when available."""
        assets = self._current_stack_assets()
        summary = (
            self._comparison_summaries.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        generated = (
            self._comparison_assets.get(self._current_stack_id, [])
            if self._current_stack_id is not None
            else []
        )
        if summary is None:
            self.thumbnails.set_assets(assets)
            return
        self.thumbnails.clear()
        table_item = QListWidgetItem("Comparison Results")
        table_item.setData(256, "__comparison_table__")
        table_item.setData(257, "comparison_table")
        self.thumbnails.addItem(table_item)
        for asset in assets:
            item = QListWidgetItem(asset.filename)
            item.setData(256, asset.id)
            item.setData(257, "source")
            item.setToolTip(f"{asset.filename}\n{asset.width} x {asset.height}, {asset.dtype}")
            self.thumbnails.addItem(item)
        for asset in sorted(
            generated,
            key=lambda item: int(item.metadata.get("sharpness_rank", 9999)),
        ):
            rank = int(asset.metadata.get("sharpness_rank", 0))
            prefix = f"[#{rank}] " if rank else ""
            item = QListWidgetItem(f"{prefix}Result - {asset.display_name}")
            item.setData(256, asset.id)
            item.setData(257, "generated_result")
            item.setToolTip(str(asset.path))
            self.thumbnails.addItem(item)

    def _select_stack_entry_item(self, current: QListWidgetItem | None) -> None:
        if current is None:
            return
        entry_type = str(current.data(257) or "")
        entry_id = str(current.data(256))
        if entry_type == "comparison_table":
            self._selected_result_pixels = None
            self._show_comparison_table()
            return
        asset = self.project.assets.get(entry_id)
        if asset is None:
            return
        if entry_type == "generated_result":
            loaded = read_image_asset(Path(asset.path), load_pixels=True)
            self._selected_result_pixels = loaded.pixels
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self.result_canvas.set_pixels(loaded.pixels, asset.display_name)
            return
        self._selected_result_pixels = None
        self.result_view_stack.setCurrentWidget(self.result_canvas)

    def _show_progress(self, message: str, fraction: float) -> None:
        self.progress.setValue(int(fraction * 100))
        self.progress.setFormat(f"{message} %p%")

    def _show_stack_preview(self, pixels: object, label: str) -> None:
        if not isinstance(pixels, np.ndarray):
            return
        if self._running_stack_id != self._current_stack_id:
            return
        self.result_canvas.set_pixels(pixels, label, fit=self.result_canvas.visible_image_rect() is None)

    def _stack_finished(self, result: object) -> None:
        stack_result = result
        if not isinstance(stack_result, FocusStackResult):
            self._stack_failed("Unexpected stack result type.")
            return
        stack_id = self._running_stack_id
        if stack_id is None or stack_id not in self.project.stacks:
            self._stack_failed("Stack no longer exists.")
            return
        if self._running_preview:
            if self._current_stack_id == stack_id:
                self.result_canvas.set_pixels(stack_result.image, "Low-resolution stack preview")
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

    def _comparison_finished(self, result: object) -> None:
        if not isinstance(result, SharpnessComparisonSummary):
            self._stack_failed("Unexpected sharpness comparison result type.")
            return
        stack_id = self._running_stack_id or self._current_stack_id
        if stack_id is None or stack_id not in self.project.stacks:
            self._stack_failed("Stack no longer exists.")
            return
        self._comparison_summaries[stack_id] = result
        generated: list[ImageAsset] = []
        for comparison_result in result.results:
            read_result = read_image_asset(comparison_result.temporary_path, load_pixels=False)
            asset = read_result.asset
            asset.kind = ImageAssetKind.STACK_RESULT
            asset.display_name = comparison_result.method_name
            asset.metadata.update(
                {
                    "source_stack_id": stack_id,
                    "sharpness_comparison": True,
                    "sharpness_result_id": comparison_result.result_id,
                    "sharpness_rank": comparison_result.rank,
                    "combined_score": comparison_result.combined_score,
                    "raw_scores": comparison_result.raw_scores,
                    "normalized_scores": comparison_result.normalized_scores,
                    "temporary": True,
                }
            )
            self.project.add_asset(asset)
            generated.append(asset)
        self._comparison_assets[stack_id] = generated
        self._refresh_stack_entries()
        self._populate_comparison_table(result)
        if generated:
            best = min(generated, key=lambda asset: int(asset.metadata.get("sharpness_rank", 9999)))
            self._select_asset_in_strip(best.id)
        self.project.touch()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _populate_comparison_table(self, summary: SharpnessComparisonSummary) -> None:
        metric_ids = sorted({metric for result in summary.results for metric in result.raw_scores})
        headers = ["Rank", "Method", "Preset"]
        headers.extend(sharpness_metric_display_name(metric) for metric in metric_ids)
        headers.extend(["Combined score", "Runtime", "Temporary filename"])
        self.result_table.setSortingEnabled(False)
        self.result_table.setColumnCount(len(headers))
        self.result_table.setHorizontalHeaderLabels(headers)
        self.result_table.setRowCount(len(summary.results))
        ordered_results = sorted(summary.results, key=lambda item: item.rank)
        best_combined_id = ordered_results[0].result_id if ordered_results else ""
        best_by_metric = {
            metric: max(
                ordered_results,
                key=lambda item, metric_id=metric: item.raw_scores.get(metric_id, float("-inf")),
            ).result_id
            for metric in metric_ids
            if ordered_results
        }
        for row, comparison_result in enumerate(ordered_results):
            values: list[object] = [
                comparison_result.rank,
                comparison_result.method_name,
                summary.preset_name,
            ]
            values.extend(comparison_result.raw_scores.get(metric, 0.0) for metric in metric_ids)
            values.extend(
                [
                    comparison_result.combined_score,
                    comparison_result.runtime_seconds,
                    comparison_result.temporary_path.name,
                ]
            )
            for column, value in enumerate(values):
                text = f"{value:.6g}" if isinstance(value, float) else str(value)
                item = QTableWidgetItem(text)
                item.setData(256, comparison_result.result_id)
                if isinstance(value, (int, float)):
                    item.setData(Qt.ItemDataRole.EditRole, value)
                if comparison_result.result_id == best_combined_id:
                    item.setBackground(QBrush(QColor("#e7f4ff")))
                if 3 <= column < 3 + len(metric_ids):
                    metric_id = metric_ids[column - 3]
                    if best_by_metric.get(metric_id) == comparison_result.result_id:
                        item.setBackground(QBrush(QColor("#edf8e9")))
                self.result_table.setItem(row, column, item)
        self.result_table.setSortingEnabled(True)
        if "Combined score" in headers:
            self.result_table.sortItems(
                headers.index("Combined score"),
                Qt.SortOrder.DescendingOrder,
            )
        self.result_summary_label.setText(self._comparison_summary_text(summary))

    def _show_comparison_table(self) -> None:
        summary = (
            self._comparison_summaries.get(self._current_stack_id)
            if self._current_stack_id is not None
            else None
        )
        if summary is not None:
            self._populate_comparison_table(summary)
        self.result_view_stack.setCurrentWidget(self.result_table_panel)

    def _select_comparison_result_row(self, row: int, _column: int) -> None:
        item = self.result_table.item(row, 0)
        if item is None or self._current_stack_id is None:
            return
        result_id = str(item.data(256))
        for asset in self._comparison_assets.get(self._current_stack_id, []):
            if asset.metadata.get("sharpness_result_id") == result_id:
                self._select_asset_in_strip(asset.id)
                self.result_table.selectRow(row)
                return

    def _comparison_summary_text(self, summary: SharpnessComparisonSummary) -> str:
        best = min(summary.results, key=lambda item: item.rank) if summary.results else None
        best_text = best.method_name if best is not None else "None"
        shape = " x ".join(str(part) for part in summary.image_shape)
        return (
            f"Source stack: {summary.stack_name} | "
            f"Frames: {summary.source_count} | "
            f"Shape: {shape} | "
            f"Bit depth: {summary.dtype} | "
            f"Analysis region: {summary.analysis_region} | "
            f"Preset: {summary.preset_name} | "
            f"Generated methods: {len(summary.results)} | "
            f"Best combined result: {best_text} | "
            f"Temporary result directory: {summary.temporary_dir}"
        )

    def _select_asset_in_strip(self, asset_id: str) -> None:
        for row in range(self.thumbnails.count()):
            item = self.thumbnails.item(row)
            if str(item.data(256)) == asset_id:
                self.thumbnails.setCurrentRow(row)
                return

    def _stack_failed(self, message: str) -> None:
        self.progress.setFormat(message)

    def _worker_finished(self) -> None:
        self.run_button.setEnabled(True)
        self.preview_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        self._worker = None
        self._comparison_worker = None
        self._running_stack_id = None
        self._running_preview = False
        self._update_comparison_button_enabled()

    def save_last_result(self, path: str) -> bool:
        """Save the most recent focus-stacked result."""
        result = (
            self._stack_results.get(self._current_stack_id)
            if self._current_stack_id is not None
            else self._last_stack_result
        )
        if result is None:
            if self._selected_result_pixels is None:
                return False
            export_image(self._selected_result_pixels, Path(path))
            return True
        if self.result_view_stack.currentWidget() is self.result_table_panel:
            return False
        if self._selected_result_pixels is not None:
            export_image(self._selected_result_pixels, Path(path))
            return True
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
        self._invalidate_stack_result(stack.id)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def add_images_to_current_stack(self) -> None:
        """Import additional images and append them to the selected stack."""
        stack = self._current_stack()
        if stack is None:
            return
        filters = "Images (" + " ".join(f"*{ext}" for ext in sorted(SUPPORTED_EXTENSIONS)) + ")"
        filenames = remembered_open_files(self, "Add Images to Stack", "stack_append", filters)
        if not filenames:
            return
        paths = resolve_stack_import_paths(self, [Path(filename) for filename in filenames])
        if not paths:
            return
        assets = import_images(
            self.project,
            paths,
            kind=ImageAssetKind.STACK_SOURCE,
        )
        new_asset_ids = [asset.id for asset in assets]
        stack.asset_ids.extend(new_asset_ids)
        if stack.enabled_asset_ids is None:
            stack.enabled_asset_ids = list(stack.asset_ids)
        else:
            stack.enabled_asset_ids.extend(new_asset_ids)
        self._invalidate_stack_result(stack.id)
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
        if str(current.data(257) or "source") != "source":
            return
        asset_id = str(current.data(256))
        stack.asset_ids = [item for item in stack.asset_ids if item != asset_id]
        stack.enabled_asset_ids = [
            item for item in (stack.enabled_asset_ids or []) if item != asset_id
        ]
        self._invalidate_stack_result(stack.id)
        if not stack.asset_ids:
            self._delete_stack(stack.id)
        self.project.touch()
        self.refresh()
        if self.stackCompleted is not None:
            self.stackCompleted()

    def _select_stack_item(self, current: QListWidgetItem | None) -> None:
        self._current_stack_id = None if current is None else str(current.data(256))
        assets = self._current_stack_assets()
        self._refresh_stack_entries()
        self._update_comparison_button_enabled()
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
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = None
            self.result_canvas.set_asset(None)
            return
        result = self._stack_results.get(self._current_stack_id)
        if result is not None:
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = result
            self.result_canvas.set_pixels(result, "Focus-stacked result")
            return
        asset = self._stack_result_asset(self._current_stack_id)
        if asset is not None:
            self.result_view_stack.setCurrentWidget(self.result_canvas)
            self._selected_result_pixels = None
            self.result_canvas.set_asset(asset)
            return
        self.result_view_stack.setCurrentWidget(self.result_canvas)
        self._selected_result_pixels = None
        self.result_canvas.set_asset(None)

    def _stack_result_asset(self, stack_id: str) -> ImageAsset | None:
        return next(
            (
                asset
                for asset in self.project.assets.values()
                if asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
                and not asset.metadata.get("stale")
            ),
            None,
        )

    def _invalidate_stack_result(self, stack_id: str) -> None:
        self._stack_results.pop(stack_id, None)
        self._remove_comparison_outputs(stack_id)
        for asset in self.project.assets.values():
            if (
                asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
            ):
                asset.metadata["stale"] = True
        if self._current_stack_id == stack_id:
            self.result_canvas.set_asset(None)

    def _remove_empty_stacks(self) -> None:
        """Drop stale empty stack records before drawing the stack list."""
        empty_stack_ids = [
            stack_id
            for stack_id, stack in self.project.stacks.items()
            if not stack.asset_ids
        ]
        for stack_id in empty_stack_ids:
            self._delete_stack(stack_id)

    def _delete_stack(self, stack_id: str) -> None:
        """Delete an empty stack record and any derived cached result records."""
        self._stack_results.pop(stack_id, None)
        self._remove_comparison_outputs(stack_id)
        self.project.stacks.pop(stack_id, None)
        stale_result_ids = [
            asset.id
            for asset in self.project.assets.values()
            if (
                asset.kind is ImageAssetKind.STACK_RESULT
                and asset.metadata.get("source_stack_id") == stack_id
            )
        ]
        for asset_id in stale_result_ids:
            self.project.assets.pop(asset_id, None)
        if self._current_stack_id == stack_id:
            self._current_stack_id = None
            self.source_canvas.set_asset(None)
            self.result_canvas.set_asset(None)

    def _remove_comparison_outputs(self, stack_id: str) -> None:
        self._comparison_summaries.pop(stack_id, None)
        for asset in self._comparison_assets.pop(stack_id, []):
            try:
                Path(asset.path).unlink(missing_ok=True)
            except OSError:
                pass
            self.project.assets.pop(asset.id, None)

    def _update_comparison_button_enabled(self) -> None:
        idle = self._worker is None and self._comparison_worker is None
        self.comparison_button.setEnabled(idle and len(self._current_stack_assets()) >= 2)

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
            asset.metadata.pop("stale", None)
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
        existing.metadata.pop("stale", None)
