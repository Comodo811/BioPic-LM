"""Focus stacking workspace."""

from __future__ import annotations

from collections.abc import Callable
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import Any

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QBrush, QColor, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QProgressDialog,
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
from biopic.ui.previews import asset_preview_pixels
from biopic.ui.settings import (
    DEBUG_OPTIONS_SETTING_KEY,
    remembered_open_files,
    set_settings_json,
    settings_json,
)
from biopic.ui.stack_import_resolution import resolve_stack_import_paths
from biopic.ui.thumbnail_strip import ThumbnailStrip
from biopic.ui.workspace_helpers.common import stack_thumbnail
from biopic.ui.workspaces.stack_execution import StackExecutionMixin
from biopic.ui.workspaces.stack_management import StackManagementMixin
from biopic.workers.focus_stack_worker import FocusStackJob, FocusStackWorker

STACK_THUMBNAIL_SIZE = QSize(120, 88)
STACK_DEFAULTS_KEY = "stack/default_parameters"


class StackWorkspace(StackExecutionMixin, StackManagementMixin, QWidget):
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
        self._last_stack_progress_preview: tuple[str, np.ndarray, str] | None = None
        self._stack_results: dict[str, np.ndarray] = {}
        self._stack_display_overrides: dict[str, tuple[np.ndarray, str]] = {}
        self._comparison_summaries: dict[str, SharpnessComparisonSummary] = {}
        self._comparison_assets: dict[str, list[ImageAsset]] = {}
        self._selected_result_pixels: np.ndarray | None = None
        self._last_stack_selection_target = "stack"
        self._debug_options_enabled = bool(settings_json(DEBUG_OPTIONS_SETTING_KEY, False))
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
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
        self.thumbnails.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)

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
        self.skip_final_depth_buffer_check = QCheckBox("Skip final depth buffer")
        self.skip_final_depth_buffer_check.setChecked(False)
        self.debug_save_stages_check = QCheckBox("Save debug stages")
        self.debug_save_stages_check.setChecked(False)
        self.align_check = QCheckBox("Align")
        self.align_check.setChecked(True)
        self.cuda_check = QCheckBox("Use CUDA")
        self.cuda_check.setChecked(False)
        self.gpu_limit_spin = QSpinBox()
        self.gpu_limit_spin.setRange(2, 24)
        self.gpu_limit_spin.setValue(4)
        self.gpu_limit_spin.setSuffix(" GB")
        self.gpu_limit_label = QLabel("GPU limit")
        self._refresh_cuda_tooltip()
        self.run_button = QPushButton("Stack")
        self.comparison_button = QPushButton("Sharpness Comparison")
        self.preview_button = QPushButton("Low-Res Preview")
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.reverse_button = QPushButton("Reverse order")
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
        controls.addWidget(self.skip_final_depth_buffer_check)
        controls.addWidget(self.debug_save_stages_check)
        controls.addWidget(self.align_check)
        controls.addWidget(self.cuda_check)
        controls.addWidget(self.gpu_limit_label)
        controls.addWidget(self.gpu_limit_spin)
        controls.addWidget(self.add_images_button)
        controls.addWidget(self.remove_button)
        controls.addWidget(self.reverse_button)
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
            stack_shortcut = QShortcut(QKeySequence(key), self.stack_list)
            stack_shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            stack_shortcut.activated.connect(self.delete_selected_stack)
            shortcut = QShortcut(QKeySequence(key), self.thumbnails)
            shortcut.setContext(Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(self.remove_selected_image)
        self.run_button.clicked.connect(self.run_stacking)
        self.comparison_button.clicked.connect(self.open_sharpness_comparison)
        self.preview_button.clicked.connect(self.run_low_res_preview)
        self.cancel_button.clicked.connect(self.cancel_stacking)
        self.add_images_button.clicked.connect(self.add_images_to_current_stack)
        self.remove_button.clicked.connect(self.remove_selected_image)
        self.reverse_button.clicked.connect(self.reverse_current_stack)
        self.thumbnails.currentItemChanged.connect(self._select_stack_entry_item)
        self.result_table.cellClicked.connect(self._select_comparison_result_row)
        self.result_table.cellDoubleClicked.connect(self._select_comparison_result_row)
        self.method_combo.currentIndexChanged.connect(self._method_changed)
        self.gpu_limit_spin.valueChanged.connect(lambda _value: self._refresh_cuda_tooltip())
        self._update_comparison_button_enabled()

    def _method_changed(self, _index: int) -> None:
        is_custom = str(self.method_combo.currentData()) == StackingMethod.CUSTOM.value
        self.skip_final_depth_buffer_check.setVisible(self._debug_options_enabled and is_custom)
        self.debug_save_stages_check.setVisible(self._debug_options_enabled and is_custom)
        self.cuda_check.setVisible(False)
        self.gpu_limit_label.setVisible(False)
        self.gpu_limit_spin.setVisible(False)
        self._refresh_cuda_tooltip()

    def set_debug_options_enabled(self, enabled: bool) -> None:
        """Show or hide advanced debugging/runtime controls."""
        self._debug_options_enabled = bool(enabled)
        self._method_changed(self.method_combo.currentIndex())

    def set_cuda_enabled(self, enabled: bool) -> None:
        """Set CUDA preference from the Options menu."""
        self.cuda_check.setChecked(bool(enabled))
        self._refresh_cuda_tooltip()

    def set_gpu_memory_limit_gb(self, value: int) -> None:
        """Set the GPU memory limit preference from the Options menu."""
        self.gpu_limit_spin.setValue(int(value))
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
            self._set_source_preview_asset(assets[0])
        else:
            self.source_canvas.set_asset(None)
        self._refresh_result_canvas()

    def select_asset(self, asset_id: str) -> None:
        """Show the selected source asset."""
        asset = self.project.assets.get(asset_id)
        if asset is not None:
            self._set_source_preview_asset(asset)

    def select_stack(self, stack_id: str) -> None:
        """Select a stack by id after external creation."""
        self._current_stack_id = stack_id
        self.refresh()

