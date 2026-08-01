"""GIMP-like edit workspace."""

from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from time import perf_counter

import numpy as np
from PySide6.QtCore import (
    QSize,
    Qt,
    QTimer,
)
from PySide6.QtGui import (
    QColor,
    QIcon,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.engine import ImageEditingEngine
from biopic.imaging.io import load_asset_pixels
from biopic.imaging.layer_buffers import (
    set_layer_buffers,
)
from biopic.imaging.paint_engine import (
    GimpPaintCore,
    PaintWorkQueue,
)
from biopic.imaging.project_render import (
    editable_assets,
)
from biopic.imaging.regions import DirtyRegion
from biopic.imaging.selection import (
    SelectionCombineMode,
    SelectionOptions,
)
from biopic.imaging.tiles import TilePaintSession
from biopic.models.editing import (
    AdjustmentLayer,
    EditLayer,
    LayerContentKind,
    LayerLock,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.ui.workspace_helpers.common import (
    editable_asset_label as _editable_asset_label,
)
from biopic.ui.workspace_helpers.icons import (
    set_button_icon as _set_button_icon,
)
from biopic.ui.workspace_helpers.icons import (
    tool_icon as _tool_icon,
)
from biopic.ui.workspace_helpers.layers import (
    layer_icon as _layer_icon,
)
from biopic.ui.workspace_helpers.layers import (
    layer_label as _layer_label,
)
from biopic.ui.workspace_helpers.operations import (
    is_adjustment_operation as _is_adjustment_operation,
)
from biopic.ui.workspace_helpers.operations import (
    is_filter_result_layer_operation as _is_filter_result_layer_operation,
)
from biopic.ui.workspace_helpers.operations import (
    operation_layer_name as _operation_layer_name,
)
from biopic.ui.workspaces.edit_background import EditBackgroundMixin
from biopic.ui.workspaces.edit_constants import (
    GIMP_TOOL_HELP as _GIMP_TOOL_HELP,
)
from biopic.ui.workspaces.edit_constants import (
    GIMP_TOOLBOX_TOOLS as _GIMP_TOOLBOX_TOOLS,
)
from biopic.ui.workspaces.edit_filter_dialogs import EditFilterDialogsMixin
from biopic.ui.workspaces.edit_history import EditHistoryMixin
from biopic.ui.workspaces.edit_layer_commands import EditLayerCommandsMixin
from biopic.ui.workspaces.edit_paint import EditPaintMixin
from biopic.ui.workspaces.edit_paint_preview import EditPaintPreviewMixin
from biopic.ui.workspaces.edit_rendering import EditRenderingMixin
from biopic.ui.workspaces.edit_selection import EditSelectionMixin

LOGGER = logging.getLogger(__name__)


class EditWorkspace(
    EditBackgroundMixin,
    EditFilterDialogsMixin,
    EditHistoryMixin,
    EditLayerCommandsMixin,
    EditPaintMixin,
    EditPaintPreviewMixin,
    EditRenderingMixin,
    EditSelectionMixin,
    QWidget,
):
    """GIMP-like non-destructive image-editing workspace."""

    def minimumSizeHint(self) -> QSize:
        """Allow the main window to shrink below the editor's preferred layout width."""
        return QSize(320, 220)

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self._edit_engine = ImageEditingEngine(project)
        self.editApplied: Callable[[], None] | None = None
        self._current_asset_id: str | None = None
        self._current_source_node_id: str | None = None
        self._current_layer_id: str | None = None
        self._asset_filter_ids: set[str] | None = None
        self._base_pixels: np.ndarray | None = None
        self._current_pixels: np.ndarray | None = None
        self._edit_composite_cache: np.ndarray | None = None
        self._edit_composite_cache_key: tuple[object, ...] | None = None
        self._clipboard_pixels: np.ndarray | None = None
        self._clipboard_alpha: np.ndarray | None = None
        self._foreground_value = 255.0
        self._editable_assets: list[ImageAsset] = []
        self._selected_tool = "pan"
        self._selection_rect: tuple[int, int, int, int] | None = None
        self._selection_shape = "rectangle"
        self._selection_polygon: list[tuple[float, float]] = []
        self._selection_coverage: np.ndarray | None = None
        self._selection_revision = 0
        self._selection_options = SelectionOptions()
        self._selection_persist_pending = False
        self._pending_white_balance_spot_sample_size: int | None = None
        self._last_tool_point: tuple[float, float] | None = None
        self._move_before: dict[str, object] | None = None
        self._move_layer_id: str | None = None
        self._move_start_offset: tuple[int, int] | None = None
        self._paint_stroke_before: dict[str, object] | None = None
        self._paint_stroke_layer_id: str | None = None
        self._paint_stroke_content: np.ndarray | None = None
        self._paint_stroke_alpha: np.ndarray | None = None
        self._paint_stroke_preview: np.ndarray | None = None
        self._paint_tile_session: TilePaintSession | None = None
        self._paint_stroke_operation: str | None = None
        self._paint_preview_layer_id: str | None = None
        self._paint_preview_regions_published = False
        self._paint_stroke_points: list[tuple[float, float]] = []
        self._paint_live_points: list[tuple[float, float]] = []
        self._gimp_paint_core = GimpPaintCore()
        self._retouch_stroke_points: list[tuple[float, float]] = []
        self._retouch_stroke_radius = 1.0
        self._retouch_stroke_parameters: dict[str, object] = {}
        self._retouch_record_spacing_px = 2.0
        self._queued_paint_points: list[tuple[int, int]] = []
        self._paint_work_queue = PaintWorkQueue(coalesce_after=1_000_000)
        self._paint_sequence = 0
        self._paint_stroke_id: str | None = None
        self._paint_finish_barrier_seen = False
        self._pending_paint_display_region = DirtyRegion()
        self._flushing_paint_queue = False
        self._paint_flush_budget_points = 1024
        self._paint_flush_budget_seconds = 0.014
        self._paint_corruption_event_count = 0
        self._last_live_preview_at = 0.0
        self._pending_external_edit_path: Path | None = None
        self._paint_flush_timer = QTimer(self)
        self._paint_flush_timer.setInterval(4)
        self._paint_flush_timer.timeout.connect(self._paint_timer_tick)
        self._move_commit_render_timer = QTimer(self)
        self._move_commit_render_timer.setSingleShot(True)
        self._move_commit_render_timer.setInterval(90)
        self._move_commit_render_timer.timeout.connect(self._render_committed_layer_move)
        self._selection_persist_timer = QTimer(self)
        self._selection_persist_timer.setSingleShot(True)
        self._selection_persist_timer.setInterval(250)
        self._selection_persist_timer.timeout.connect(self._flush_pending_selection_persistence)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        main_splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(main_splitter)

        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(6, 6, 6, 6)
        left_layout.addWidget(QLabel("Tools"))
        tools_grid = QGridLayout()
        self.tool_buttons: dict[str, QPushButton] = {}
        for index, (tool_id, label) in enumerate(_GIMP_TOOLBOX_TOOLS):
            button = QPushButton("" if _tool_icon(tool_id) is not None else label)
            button.setCheckable(True)
            button.setFixedSize(QSize(34, 30))
            icon = _tool_icon(tool_id)
            if icon is not None:
                button.setIcon(icon)
                button.setIconSize(QSize(20, 20))
            button.setToolTip(_GIMP_TOOL_HELP.get(tool_id, label))
            button.clicked.connect(
                lambda _checked=False, selected=tool_id: self.select_tool(selected)
            )
            self.tool_buttons[tool_id] = button
            tools_grid.addWidget(button, index // 2, index % 2)
        self.tool_buttons["pan"].setChecked(True)
        left_layout.addLayout(tools_grid)
        self.tool_options_label = QLabel("Tool options")
        left_layout.addWidget(self.tool_options_label)
        self.primary_spin = QDoubleSpinBox()
        self.primary_spin.setRange(0.01, 100.0)
        self.primary_spin.setValue(1.0)
        self.primary_spin.setSingleStep(0.1)
        self.secondary_spin = QDoubleSpinBox()
        self.secondary_spin.setRange(0.0, 255.0)
        self.secondary_spin.setValue(255.0)
        self.secondary_spin.valueChanged.connect(self._foreground_value_changed)
        self.foreground_swatch = QPushButton()
        self.foreground_swatch.setFixedSize(QSize(28, 22))
        self.foreground_swatch.clicked.connect(self._open_foreground_color_dialog)
        self._update_foreground_swatch()
        self.tool_text = QLineEdit()
        self.tool_text.setPlaceholderText("Text")
        self.size_value_label = QLabel("Size / value")
        self.intensity_label = QLabel("Intensity")
        left_layout.addWidget(self.size_value_label)
        left_layout.addWidget(self.primary_spin)
        left_layout.addWidget(self.intensity_label)
        left_layout.addWidget(self.secondary_spin)
        left_layout.addWidget(self.foreground_swatch)
        left_layout.addWidget(self.tool_text)
        for widget in (
            self.tool_options_label,
            self.size_value_label,
            self.primary_spin,
            self.intensity_label,
            self.secondary_spin,
            self.foreground_swatch,
            self.tool_text,
        ):
            widget.setVisible(False)
        self.selection_options_box = QGroupBox("Selection Options")
        selection_options_layout = QFormLayout(self.selection_options_box)
        self.selection_mode_combo = QComboBox()
        for label, mode in [
            ("Replace", SelectionCombineMode.REPLACE.value),
            ("Add", SelectionCombineMode.ADD.value),
            ("Subtract", SelectionCombineMode.SUBTRACT.value),
            ("Intersect", SelectionCombineMode.INTERSECT.value),
        ]:
            self.selection_mode_combo.addItem(label, mode)
        self.selection_antialias_check = QCheckBox("Antialiasing")
        self.selection_antialias_check.setChecked(True)
        self.selection_feather_check = QCheckBox("Feather edges")
        self.selection_feather_radius = QDoubleSpinBox()
        self.selection_feather_radius.setRange(0.0, 256.0)
        self.selection_feather_radius.setSingleStep(1.0)
        self.selection_feather_radius.setSuffix(" px")
        selection_options_layout.addRow("Mode", self.selection_mode_combo)
        selection_options_layout.addRow(self.selection_antialias_check)
        selection_options_layout.addRow(self.selection_feather_check)
        selection_options_layout.addRow("Feather radius", self.selection_feather_radius)
        left_layout.addWidget(self.selection_options_box)
        left_layout.addWidget(QLabel("Images"))
        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(170, 120))
        self.asset_list.setUniformItemSizes(True)
        left_layout.addWidget(self.asset_list, 1)

        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(6, 6, 6, 6)
        center_controls = QHBoxLayout()
        self.operation_combo = QComboBox()
        for label, operation in [
            ("Gamma", "gamma"),
            ("White Balance", "white_balance"),
            ("Levels", "levels"),
            ("Curves", "curve"),
            ("Auto Levels", "auto_levels"),
            ("Color / Saturation", "color_saturation"),
            ("High Pass", "high_pass"),
            ("Gaussian Smooth", "gaussian"),
            ("Median Filter", "median"),
            ("Invert", "invert"),
            ("Threshold", "threshold"),
            ("Sharpen", "sharpen"),
            ("Denoise", "denoise"),
            ("TV Denoise", "total_variation"),
            ("Wavelet Sharpen", "wavelet_sharpen"),
            ("Local Contrast", "local_contrast"),
            ("Deconvolution", "deconvolution"),
            ("Rotate 90", "rotate_90"),
            ("Flip Horizontal", "flip_horizontal"),
            ("Flip Vertical", "flip_vertical"),
            ("Crop Selection", "crop"),
            ("Flat-Field Correction", "flat_field_correction_estimated"),
            ("Uniform Background Outside Selection", "uniform_background_outside_selection"),
        ]:
            self.operation_combo.addItem(label, operation)
        self.apply_button = QPushButton("Apply")
        self.fit_button = QPushButton("Fit")
        self.actual_button = QPushButton("100%")
        self.external_editor_button = QPushButton("Open in GIMP/Krita")
        self.import_external_button = QPushButton("Import External Edit")
        center_controls.addWidget(QLabel("Operation"))
        center_controls.addWidget(self.operation_combo)
        center_controls.addWidget(self.apply_button)
        center_controls.addWidget(self.fit_button)
        center_controls.addWidget(self.actual_button)
        center_controls.addWidget(self.external_editor_button)
        center_controls.addWidget(self.import_external_button)
        center_controls.addStretch(1)
        center_layout.addLayout(center_controls)
        for control_index in range(center_controls.count()):
            item = center_controls.itemAt(control_index)
            widget = item.widget() if item is not None else None
            if widget is not None:
                widget.setVisible(False)
        self.high_pass_options = QGroupBox("High Pass Options")
        high_pass_layout = QFormLayout(self.high_pass_options)
        self.high_pass_radius_spin = QDoubleSpinBox()
        self.high_pass_radius_spin.setRange(0.1, 30.0)
        self.high_pass_radius_spin.setSingleStep(0.1)
        self.high_pass_radius_spin.setValue(1.2)
        self.high_pass_radius_spin.setSuffix(" px")
        self.high_pass_amount_spin = QDoubleSpinBox()
        self.high_pass_amount_spin.setRange(0.0, 8.0)
        self.high_pass_amount_spin.setSingleStep(0.1)
        self.high_pass_amount_spin.setValue(2.0)
        self.high_pass_threshold_spin = QDoubleSpinBox()
        self.high_pass_threshold_spin.setRange(0.0, 0.25)
        self.high_pass_threshold_spin.setSingleStep(0.0025)
        self.high_pass_threshold_spin.setDecimals(4)
        self.high_pass_threshold_spin.setValue(0.0)
        self.high_pass_halo_spin = QDoubleSpinBox()
        self.high_pass_halo_spin.setRange(0.0, 5.0)
        self.high_pass_halo_spin.setSingleStep(0.1)
        self.high_pass_halo_spin.setValue(0.0)
        self.high_pass_luminance_check = QCheckBox("Luminance only")
        self.high_pass_luminance_check.setChecked(True)
        high_pass_layout.addRow("Radius", self.high_pass_radius_spin)
        high_pass_layout.addRow("Amount", self.high_pass_amount_spin)
        high_pass_layout.addRow("Threshold", self.high_pass_threshold_spin)
        high_pass_layout.addRow("Halo control", self.high_pass_halo_spin)
        high_pass_layout.addRow(self.high_pass_luminance_check)
        center_layout.addWidget(self.high_pass_options)
        self.high_pass_options.setVisible(False)
        self.canvas = ImageCanvas()
        center_layout.addWidget(self.canvas, 1)

        right_tabs = QTabWidget()
        layers_page = QWidget()
        layers_layout = QVBoxLayout(layers_page)
        layers_layout.setContentsMargins(6, 6, 6, 6)
        layers_layout.addWidget(QLabel("Layers"))
        self.layers_list = QListWidget()
        self.layers_list.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.layers_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        layers_layout.addWidget(self.layers_list, 1)
        layer_controls = QHBoxLayout()
        self.add_layer_button = QPushButton()
        self.remove_layer_button = QPushButton()
        self.duplicate_layer_button = QPushButton()
        self.raise_layer_button = QPushButton("Up")
        self.lower_layer_button = QPushButton("Down")
        _set_button_icon(self.add_layer_button, "new_layer_icon.png", "New Layer")
        _set_button_icon(self.remove_layer_button, "delete_icon.png", "Delete Layer")
        _set_button_icon(self.duplicate_layer_button, "duplicate_layer_icon.png", "Duplicate Layer")
        layer_controls.addWidget(self.add_layer_button)
        layer_controls.addWidget(self.remove_layer_button)
        layer_controls.addWidget(self.duplicate_layer_button)
        layer_controls.addWidget(self.raise_layer_button)
        layer_controls.addWidget(self.lower_layer_button)
        layer_controls.addStretch(1)
        layers_layout.addLayout(layer_controls)
        layer_options = QHBoxLayout()
        self.layer_opacity_spin = QDoubleSpinBox()
        self.layer_opacity_spin.setRange(0.0, 100.0)
        self.layer_opacity_spin.setValue(100.0)
        self.layer_blend_combo = QComboBox()
        self.layer_blend_combo.addItems(["normal", "add", "multiply", "screen"])
        self.layer_visible_check = QCheckBox("Visible")
        self.layer_visible_check.setChecked(True)
        self.layer_lock_check = QCheckBox("Lock Pixels")
        self.layer_position_lock_check = QCheckBox("Lock Position")
        self.layer_visibility_lock_check = QCheckBox("Lock Visibility")
        layer_options.addWidget(QLabel("Opacity"))
        layer_options.addWidget(self.layer_opacity_spin)
        layer_options.addWidget(QLabel("Mode"))
        layer_options.addWidget(self.layer_blend_combo)
        layer_options.addWidget(self.layer_visible_check)
        layer_options.addWidget(self.layer_lock_check)
        layer_options.addWidget(self.layer_position_lock_check)
        layer_options.addWidget(self.layer_visibility_lock_check)
        layers_layout.addLayout(layer_options)

        history_page = QWidget()
        history_layout = QVBoxLayout(history_page)
        history_layout.setContentsMargins(6, 6, 6, 6)
        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        history_layout.addWidget(self.history)
        right_tabs.addTab(layers_page, "Layers")
        adjustments_page = QWidget()
        adjustments_layout = QVBoxLayout(adjustments_page)
        adjustments_layout.setContentsMargins(6, 6, 6, 6)
        self.adjustment_list = QListWidget()
        adjustments_layout.addWidget(QLabel("Adjustment Layers"))
        adjustments_layout.addWidget(self.adjustment_list)
        adjustment_controls = QHBoxLayout()
        self.disable_adjustment_button = QPushButton("Enable/Disable")
        self.delete_adjustment_button = QPushButton("Delete")
        adjustment_controls.addWidget(self.disable_adjustment_button)
        adjustment_controls.addWidget(self.delete_adjustment_button)
        adjustment_controls.addStretch(1)
        adjustments_layout.addLayout(adjustment_controls)
        right_tabs.addTab(adjustments_page, "Adjustments")
        right_tabs.addTab(history_page, "History")

        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(center_panel)
        main_splitter.addWidget(right_tabs)
        main_splitter.setStretchFactor(0, 0)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setStretchFactor(2, 0)
        main_splitter.setSizes([220, 820, 260])

        self.asset_list.currentRowChanged.connect(self._select_asset_row)
        self.operation_combo.currentIndexChanged.connect(self._operation_changed)
        self.apply_button.clicked.connect(self.apply_current_operation)
        self.selection_mode_combo.currentIndexChanged.connect(self._selection_options_changed)
        self.selection_antialias_check.toggled.connect(self._selection_options_changed)
        self.selection_feather_check.toggled.connect(self._selection_options_changed)
        self.selection_feather_radius.valueChanged.connect(self._selection_options_changed)
        self.fit_button.clicked.connect(self.canvas.fit_to_window)
        self.actual_button.clicked.connect(self.canvas.actual_size)
        self.external_editor_button.clicked.connect(self.open_external_editor)
        self.import_external_button.clicked.connect(self.import_external_editor_result)
        self.canvas.pointClicked.connect(self._tool_point_clicked)
        self.canvas.paintPointMoved.connect(self._paint_point_moved)
        self.canvas.paintStrokeStarted.connect(self._begin_paint_stroke)
        self.canvas.paintStrokeFinished.connect(self._finish_paint_stroke)
        self.canvas.viewZoomAboutToChange.connect(self._flush_all_queued_paint_points)
        self.canvas.layerDragStarted.connect(self._begin_layer_move)
        self.canvas.layerDragMoved.connect(self._preview_layer_move)
        self.canvas.layerDragFinished.connect(self._finish_layer_move)
        self.canvas.rectangleSelected.connect(self._tool_rectangle_selected)
        self.canvas.selectionCompleted.connect(self._tool_selection_completed)
        self.add_layer_button.clicked.connect(lambda _checked=False: self.add_empty_layer())
        self.remove_layer_button.clicked.connect(self.remove_selected_layer)
        self.duplicate_layer_button.clicked.connect(self.duplicate_selected_layer)
        self.raise_layer_button.clicked.connect(self.raise_selected_layer)
        self.lower_layer_button.clicked.connect(self.lower_selected_layer)
        self.layers_list.currentItemChanged.connect(self._selected_layer_changed)
        self.layers_list.model().rowsMoved.connect(self._layers_rows_moved)
        self.layer_opacity_spin.valueChanged.connect(self._apply_layer_controls)
        self.layer_blend_combo.currentTextChanged.connect(self._apply_layer_controls)
        self.layer_visible_check.toggled.connect(self._apply_layer_controls)
        self.layer_lock_check.toggled.connect(self._apply_layer_controls)
        self.layer_position_lock_check.toggled.connect(self._apply_layer_controls)
        self.layer_visibility_lock_check.toggled.connect(self._apply_layer_controls)
        self.disable_adjustment_button.clicked.connect(self.toggle_selected_adjustment)
        self.delete_adjustment_button.clicked.connect(self.delete_selected_adjustment)
        self.select_tool("pan")
        self._selection_options_changed()
        self._operation_changed()

    def refresh(self) -> None:
        """Refresh asset choices, layers, and history."""
        current = self._current_asset_id
        self.asset_list.blockSignals(True)
        self.asset_list.clear()
        assets = editable_assets(self.project)
        if self._asset_filter_ids is not None:
            assets = [asset for asset in assets if asset.id in self._asset_filter_ids]
        self._editable_assets = assets
        for asset in self._editable_assets:
            item = QListWidgetItem(
                QIcon(asset_thumbnail(asset, QSize(170, 120))),
                _editable_asset_label(asset),
            )
            item.setData(256, asset.id)
            self.asset_list.addItem(item)
        self.asset_list.blockSignals(False)
        if current:
            index = next(
                (i for i, asset in enumerate(self._editable_assets) if asset.id == current),
                -1,
            )
            if index >= 0:
                self.asset_list.setCurrentRow(index)
        if self.asset_list.count() and self.asset_list.currentRow() < 0:
            self.asset_list.setCurrentRow(0)
        self._select_asset_row(self.asset_list.currentRow())
        self._refresh_layers()
        self._refresh_adjustments()
        self._refresh_history()

    def set_asset_filter(self, asset_ids: list[str] | None) -> None:
        """Restrict Edit Image to a temporary workflow-specific asset context."""
        self._asset_filter_ids = None if asset_ids is None else set(asset_ids)
        self._current_asset_id = None
        self.refresh()

    def apply_current_operation(self) -> None:
        """Apply an edit operation, display it, and record a processing node."""
        if self._current_pixels is None or self._current_asset_id is None:
            return
        operation = str(self.operation_combo.currentData())
        parameters = self._parameters(operation)
        if _is_filter_result_layer_operation(operation):
            start = perf_counter()
            result = apply_edit_operation(self._current_pixels, operation, parameters)
            LOGGER.debug(
                "edit filter %s computed in %.3fs for shape=%s dtype=%s",
                operation,
                perf_counter() - start,
                getattr(result, "shape", None),
                getattr(result, "dtype", None),
            )
            self._commit_filter_result_layer(result, operation, parameters)
            return
        if _is_adjustment_operation(operation):
            self._upsert_adjustment_layer_from_operation(operation, parameters)
            self._render_current_adjustment_preview()
            self._refresh_adjustments()
            return
        result = apply_edit_operation(self._current_pixels, operation, parameters)
        self._commit_edit_result(
            result,
            operation,
            parameters,
            adjustment_operation=_is_adjustment_operation(operation),
        )

    def select_tool(self, tool_id: str) -> None:
        """Select a GIMP-like editing tool."""
        self._selected_tool = tool_id
        if tool_id == "rectangle_select":
            self._selection_shape = "rectangle"
            self._selection_polygon = []
        elif tool_id == "ellipse_select":
            self._selection_shape = "ellipse"
            self._selection_polygon = []
        elif tool_id == "free_select":
            self._selection_shape = "free"
            self._selection_polygon = []
        for current_tool, button in self.tool_buttons.items():
            button.setChecked(current_tool == tool_id)
        canvas_mode = {
            "move": "move",
            "pan": "pan",
            "rectangle_select": "select",
            "ellipse_select": "ellipse_select",
            "free_select": "free_select",
            "fuzzy_select": "fuzzy_select",
            "select_by_color": "select",
            "foreground_select": "select",
            "paths": "select",
            "pen": "select",
            "crop": "crop",
            "zoom": "zoom",
            "brush": "brush",
            "pencil": "pencil",
            "erase": "erase",
            "clone": "clone",
            "heal": "heal",
            "smudge": "smudge",
            "dodge_burn": "dodge_burn",
            "bucket_fill": "bucket_fill",
            "gradient": "bucket_fill",
            "color_picker": "color_picker",
            "text": "text",
            "measure": "measure",
            "align": "pan",
            "rotate": "rotate",
            "scale": "scale",
            "shear": "pan",
            "perspective": "pan",
            "flip": "pan",
            "cage_transform": "select",
            "unified_transform": "pan",
        }.get(tool_id, "pan")
        self.canvas.set_tool_mode(canvas_mode)
        self._configure_tool_options(tool_id)
        self._refresh_selection_options_visibility()

    def add_empty_layer(self, name: str | None = None) -> None:
        """Add a visible non-destructive layer record."""
        if self._current_asset_id is None:
            return
        before = self._snapshot_edit_state()
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        order = self._next_layer_order(source_node)
        layer = EditLayer(
            name=name or f"Layer {len(self.project.edit_layers) + 1}",
            source_node_id=source_node,
            content_kind=LayerContentKind.RASTER,
            order=order,
        )
        if self._base_pixels is not None:
            layer.set_content_pixels(np.zeros_like(self._base_pixels))
            layer.set_alpha_pixels(np.zeros(self._base_pixels.shape[:2], dtype=np.float32))
        self.project.edit_layers[layer.id] = layer
        if source_node is not None:
            self.project.active_edit_layers[source_node] = layer.id
            self._current_layer_id = layer.id
        self.project.touch()
        self._finish_command("add layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()

    def _select_asset_row(self, row: int) -> None:
        if row < 0 or row >= len(self._editable_assets):
            return
        self._flush_pending_selection_persistence()
        asset = self._editable_assets[row]
        self._current_asset_id = asset.id
        self._current_source_node_id = self.project.source_node_id_for_asset(asset.id)
        self._base_pixels = load_asset_pixels(asset)
        self._current_pixels = self._base_pixels.copy()
        self._selection_rect = None
        self._selection_coverage = None
        self._selection_polygon = []
        self._invalidate_layer_array_cache()
        self._ensure_default_layer()
        self._load_active_selection()
        self._current_layer_id = (
            self.project.active_edit_layers.get(self._current_source_node_id)
            if self._current_source_node_id is not None
            else None
        )
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_adjustments()

    def _operation_changed(self) -> None:
        operation = str(self.operation_combo.currentData())
        self.high_pass_options.setVisible(False)
        if operation == "gamma":
            self.primary_spin.setRange(0.05, 5.0)
            self.primary_spin.setValue(1.0)
        elif operation == "white_balance":
            self.primary_spin.setRange(0.1, 4.0)
            self.primary_spin.setSingleStep(0.05)
            self.primary_spin.setValue(1.0)
            self.secondary_spin.setRange(0.1, 4.0)
            self.secondary_spin.setSingleStep(0.05)
            self.secondary_spin.setValue(1.0)
        elif operation == "color_saturation":
            self.primary_spin.setRange(-100.0, 100.0)
            self.primary_spin.setSingleStep(1.0)
            self.primary_spin.setValue(0.0)
            self.secondary_spin.setRange(-100.0, 100.0)
            self.secondary_spin.setSingleStep(1.0)
            self.secondary_spin.setValue(0.0)
        elif operation == "high_pass":
            self.primary_spin.setRange(0.1, 30.0)
            self.primary_spin.setSingleStep(0.1)
            self.primary_spin.setValue(self.high_pass_radius_spin.value())
            self.secondary_spin.setRange(0.0, 8.0)
            self.secondary_spin.setSingleStep(0.1)
            self.secondary_spin.setValue(self.high_pass_amount_spin.value())
        elif operation == "gaussian":
            self.primary_spin.setRange(0.1, 30.0)
            self.primary_spin.setValue(2.0)
        elif operation == "median":
            self.primary_spin.setRange(1.0, 10.0)
            self.primary_spin.setValue(1.0)
        elif operation == "threshold":
            self.primary_spin.setRange(0.0, 1.0)
            self.primary_spin.setSingleStep(0.05)
            self.primary_spin.setValue(0.5)
        elif operation == "denoise":
            self.primary_spin.setRange(3.0, 15.0)
            self.primary_spin.setSingleStep(2.0)
            self.primary_spin.setValue(5.0)
        elif operation == "total_variation":
            self.primary_spin.setRange(0.01, 0.5)
            self.primary_spin.setSingleStep(0.01)
            self.primary_spin.setValue(0.08)
        elif operation == "wavelet_sharpen":
            self.primary_spin.setRange(0.0, 2.0)
            self.primary_spin.setSingleStep(0.05)
            self.primary_spin.setValue(0.35)
        elif operation == "local_contrast":
            self.primary_spin.setRange(1.0, 40.0)
            self.primary_spin.setSingleStep(1.0)
            self.primary_spin.setValue(8.0)
        elif operation == "deconvolution":
            self.primary_spin.setRange(0.5, 5.0)
            self.primary_spin.setSingleStep(0.1)
            self.primary_spin.setValue(1.5)
        elif operation in {"subtract_background_estimated", "flat_field_correction_estimated"}:
            self.primary_spin.setRange(2.0, 120.0)
            self.primary_spin.setSingleStep(2.0)
            self.primary_spin.setValue(24.0)
        elif operation == "uniform_background_outside_selection":
            self.primary_spin.setRange(0.0, 1.0)
            self.primary_spin.setValue(1.0)
        elif operation in {"rotate_90", "flip_horizontal", "flip_vertical"}:
            self.primary_spin.setRange(1.0, 4.0)
            self.primary_spin.setValue(1.0)
        else:
            self.primary_spin.setRange(0.0, 10.0)
            self.primary_spin.setValue(0.5)

    def _parameters(self, operation: str) -> dict[str, object]:
        value = self.primary_spin.value()
        secondary = self.secondary_spin.value()
        if operation == "gamma":
            return {"gamma": value}
        if operation == "white_balance":
            return {"red": value, "green": 1.0, "blue": secondary, "normalize": True}
        if operation == "color_saturation":
            return {
                "range": "all",
                "hue": 0.0,
                "saturation": value,
                "lightness": secondary,
                "overlap": 0.0,
            }
        if operation == "levels":
            return {
                "black_point": 0.0,
                "white_point": 1.0,
                "midtone": max(value, 0.01),
                "output_black": 0.0,
                "output_white": 1.0,
                "channel": "rgb",
            }
        if operation == "curve":
            return {"points": [(0.0, 0.0), (0.5, value / 2.0), (1.0, 1.0)], "channel": "rgb"}
        if operation == "auto_levels":
            return {"percentile": value}
        if operation == "high_pass":
            return {
                "sigma": self.high_pass_radius_spin.value(),
                "amount": self.high_pass_amount_spin.value(),
                "threshold": self.high_pass_threshold_spin.value(),
                "halo_suppression": self.high_pass_halo_spin.value(),
                "luminance_only": self.high_pass_luminance_check.isChecked(),
            }
        if operation == "gaussian":
            return {"sigma": value}
        if operation == "median":
            return {"radius": int(round(value))}
        if operation == "threshold":
            return {"threshold": value}
        if operation == "sharpen":
            return {"sigma": max(value, 0.01), "amount": 1.0}
        if operation == "denoise":
            return {
                "method": "microscopy",
                "luminance_strength": 0.16,
                "chroma_strength": 0.10,
                "impulse_radius": 1,
                "preserve_edges": True,
            }
        if operation == "total_variation":
            return {"weight": value}
        if operation == "wavelet_sharpen":
            return {
                "levels": 4,
                "amount": value,
                "threshold": 0.01,
                "luminance_only": False,
            }
        if operation == "local_contrast":
            return {
                "radius": value,
                "amount": 0.25,
                "threshold": 0.01,
                "shadow_protection": 0.25,
                "highlight_protection": 0.05,
                "halo_suppression": 0.25,
                "luminance_only": True,
            }
        if operation == "deconvolution":
            return {"radius": value, "iterations": 8, "amount": 0.5, "damping": 0.001}
        if operation == "rotate_90":
            return {"turns": int(round(value))}
        if operation == "scale_uniform":
            return {"scale": max(0.05, value / 100.0)}
        if operation == "crop" and self._selection_rect is not None:
            x, y, width, height = self._selection_rect
            return {"x": x, "y": y, "width": width, "height": height}
        if operation == "flat_field_correction_estimated":
            return {"sigma": value, "strength": 1.0, "preserve_mean": True}
        if operation == "subtract_background_estimated":
            return {"sigma": value, "amount": 1.0}
        if operation == "uniform_background_outside_selection":
            return {"selection_mask": self._selection_mask()}
        return {}

    def apply_named_operation(
        self, operation: str, parameters_override: dict[str, object] | None = None
    ) -> None:
        """Apply an operation directly from a context-toolbar menu."""
        if self._current_pixels is None:
            return
        index = self.operation_combo.findData(operation)
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        parameters = self._parameters(operation)
        if parameters_override:
            parameters.update(parameters_override)
        if _is_adjustment_operation(operation):
            self._upsert_adjustment_layer_from_operation(operation, parameters)
            self._render_current_adjustment_preview()
            self._refresh_adjustments()
            return
        result = apply_edit_operation(self._current_pixels, operation, parameters)
        if _is_filter_result_layer_operation(operation):
            self._commit_filter_result_layer(result, operation, parameters)
        else:
            self._commit_edit_result(result, operation, parameters)

    def _configure_tool_options(self, tool_id: str) -> None:
        if tool_id in {
            "brush",
            "pencil",
            "erase",
            "clone",
            "heal",
            "smudge",
            "dodge_burn",
            "bucket_fill",
            "gradient",
        }:
            self.primary_spin.setRange(1.0, 100.0)
            self.primary_spin.setValue(1.0 if tool_id == "pencil" else 12.0)
            self.secondary_spin.setEnabled(tool_id in {"brush", "pencil", "bucket_fill"})
        elif tool_id in {
            "rectangle_select",
            "ellipse_select",
            "free_select",
            "fuzzy_select",
            "select_by_color",
            "crop",
            "measure",
            "paths",
            "pen",
            "foreground_select",
        }:
            self.primary_spin.setRange(1.0, 100.0)
            self.primary_spin.setValue(1.0)
            self.secondary_spin.setEnabled(False)
        elif tool_id == "scale":
            self.primary_spin.setRange(5.0, 400.0)
            self.primary_spin.setSingleStep(5.0)
            self.primary_spin.setValue(100.0)
            self.secondary_spin.setEnabled(False)
        elif tool_id == "rotate":
            self.primary_spin.setRange(1.0, 4.0)
            self.primary_spin.setSingleStep(1.0)
            self.primary_spin.setValue(1.0)
            self.secondary_spin.setEnabled(False)
        else:
            self.secondary_spin.setEnabled(True)

    def _commit_edit_result(
        self,
        result: np.ndarray,
        operation: str,
        parameters: dict[str, object],
        *,
        adjustment_operation: bool = False,
    ) -> None:
        self._current_pixels = result
        self.canvas.set_pixels(result, f"{operation} preview")
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        inputs = () if source_node is None else (source_node,)
        node = ProcessingNode(
            operation=f"edit.{operation}",
            inputs=inputs,
            parameters=parameters,
            provenance={"non_destructive": True, "tool": self._selected_tool},
        )
        self.project.graph.add_node(node)
        if adjustment_operation:
            self._add_adjustment_layer(operation, parameters, node)
        self.project.touch()
        self._refresh_history()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

    def _commit_filter_result_layer(
        self, result: np.ndarray, operation: str, parameters: dict[str, object]
    ) -> None:
        """Store an applied correction/filter as a separate raster result layer."""
        commit_start = perf_counter()
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        before = self._snapshot_edit_state()
        node = ProcessingNode(
            operation=f"filter-layer.{operation}",
            inputs=(source_node,),
            parameters=dict(parameters),
            provenance={
                "non_destructive": True,
                "layer_result": True,
                "source": "current rendered edit image",
            },
        )
        self.project.graph.add_node(node)
        layer = EditLayer(
            name=_operation_layer_name(operation),
            source_node_id=source_node,
            content_kind=LayerContentKind.RASTER,
            order=self._next_layer_order(source_node),
        )
        alpha = np.ones(result.shape[:2], dtype=np.float32)
        layer.bump_generation()
        self.project.edit_layers[layer.id] = layer
        set_layer_buffers(layer.id, result, alpha)
        self.project.active_edit_layers[source_node] = layer.id
        self._current_layer_id = layer.id
        self._current_pixels = result
        self._edit_composite_cache = result
        self._edit_composite_cache_key = self._edit_composite_key(source_node)
        self._finish_command(f"add {layer.name} layer", before)
        after_history = perf_counter()
        self._refresh_layers()
        after_layers = perf_counter()
        self._render_current_adjustment_preview()
        after_render = perf_counter()
        LOGGER.debug(
            "edit filter %s committed in %.3fs (history %.3fs, layers %.3fs, render %.3fs)",
            operation,
            after_render - commit_start,
            after_history - commit_start,
            after_layers - after_history,
            after_render - after_layers,
        )
        if self.editApplied is not None:
            self.editApplied()

    def _add_adjustment_layer(
        self, operation: str, parameters: dict[str, object], node: ProcessingNode
    ) -> None:
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        image_node_id = source_node or node.id
        order = sum(
            1
            for layer in self.project.adjustment_layers.values()
            if layer.image_node_id == image_node_id
        )
        layer = AdjustmentLayer(
            name=operation.replace("_", " ").title(),
            image_node_id=image_node_id,
            operation=operation,
            parameters=dict(parameters),
            order=order,
        )
        self.project.add_adjustment_layer(layer)

    def _add_adjustment_layer_from_operation(
        self, operation: str, parameters: dict[str, object]
    ) -> None:
        self._upsert_adjustment_layer_from_operation(operation, parameters, replace_existing=False)

    def _upsert_adjustment_layer_from_operation(
        self,
        operation: str,
        parameters: dict[str, object],
        *,
        replace_existing: bool = True,
    ) -> None:
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        if replace_existing:
            existing = next(
                (
                    layer
                    for layer in self.project.adjustment_layers_for_image(source_node)
                    if layer.operation == operation
                ),
                None,
            )
            if existing is not None:
                self.project.update_adjustment_layer(existing.id, dict(parameters), enabled=True)
                if self.editApplied is not None:
                    self.editApplied()
                return
        node = ProcessingNode(
            operation=f"adjustment.{operation}",
            inputs=(source_node,),
            parameters=dict(parameters),
            provenance={"non_destructive": True, "renderer": "BioPic LM adjustment pipeline"},
        )
        self.project.graph.add_node(node)
        order = len(self.project.adjustment_layers_for_image(source_node))
        layer = AdjustmentLayer(
            name=operation.replace("_", " ").title(),
            image_node_id=source_node,
            operation=operation,
            parameters=dict(parameters),
            order=order,
            cache_key=None,
        )
        self.project.add_adjustment_layer(layer)
        if self.editApplied is not None:
            self.editApplied()

    def _start_white_balance_spot_pick(self, sample_size: int) -> None:
        self._pending_white_balance_spot_sample_size = max(3, int(sample_size))
        self.select_tool("color_picker")
        self._status("Click a neutral white/gray spot to set white balance.")

    def _apply_white_balance_spot_from_point(self, x: int, y: int) -> None:
        if self._current_pixels is None:
            return
        sample_size = max(3, int(self._pending_white_balance_spot_sample_size or 24))
        self._pending_white_balance_spot_sample_size = None
        image_height, image_width = self._current_pixels.shape[:2]
        half = sample_size // 2
        left = max(0, min(image_width - 1, int(x) - half))
        top = max(0, min(image_height - 1, int(y) - half))
        width = max(1, min(sample_size, image_width - left))
        height = max(1, min(sample_size, image_height - top))
        self.apply_named_operation(
            "white_balance",
            {
                "method": "spot",
                "sample_rect": (left, top, width, height),
                "sample_size": sample_size,
                "normalize": True,
            },
        )
        self.select_tool("pan")
        self._status(f"White balance sampled from {width} x {height}px spot.")

    def _foreground_value_changed(self, value: float) -> None:
        self._foreground_value = value
        self._update_foreground_swatch()

    def _update_foreground_swatch(self) -> None:
        value = int(max(0, min(255, round(self._foreground_value))))
        self.foreground_swatch.setStyleSheet(
            f"background-color: rgb({value}, {value}, {value}); border: 1px solid #777;"
        )

    def _open_foreground_color_dialog(self) -> None:
        value = int(max(0, min(255, round(self._foreground_value))))
        dialog = QColorDialog(QColor(value, value, value), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle("Change Foreground Color")
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        picked = float(round((color.redF() + color.greenF() + color.blueF()) / 3.0 * 255.0))
        self._foreground_value = picked
        self.secondary_spin.blockSignals(True)
        self.secondary_spin.setValue(picked)
        self.secondary_spin.blockSignals(False)
        self._update_foreground_swatch()

    def _layers_rows_moved(self, *_args: object) -> None:
        if self.layers_list.count() <= 1:
            return
        before = self._snapshot_edit_state()
        for order in range(self.layers_list.count()):
            layer_id = str(self.layers_list.item(order).data(256))
            layer = self.project.edit_layers.get(layer_id)
            if layer is not None:
                layer.order = order
        ordered = sorted(self.project.edit_layers.values(), key=lambda layer: layer.order)
        self.project.edit_layers = {layer.id: layer for layer in ordered}
        self.project.touch()
        self._finish_command("drag reorder layer", before)
        self._render_current_adjustment_preview()
        self._refresh_layers()

    def _status(self, message: str) -> None:
        self.history.appendPlainText(message)

    def _refresh_history(self) -> None:
        lines = [
            f"{node.operation}: {node.parameters}"
            for node in self.project.graph.nodes.values()
            if node.operation.startswith("edit.")
        ]
        lines.extend(
            str(item.get("operation", "edit command"))
            for item in self.project.history
            if isinstance(item, dict)
        )
        self.history.setPlainText("\n".join(lines))

    def _refresh_layers(self) -> None:
        active_layer_id = self._current_layer_id
        self.layers_list.clear()
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        selected_row = -1
        for layer in sorted(self.project.edit_layers.values(), key=lambda item: item.order):
            if source_node is None or layer.source_node_id in {None, source_node}:
                item = QListWidgetItem(_layer_label(layer))
                icon = _layer_icon(layer)
                if icon is not None:
                    item.setIcon(icon)
                item.setData(256, layer.id)
                self.layers_list.addItem(item)
                if layer.id == active_layer_id:
                    selected_row = self.layers_list.count() - 1
        if selected_row >= 0:
            self.layers_list.setCurrentRow(selected_row)
        if self.layers_list.count() and self.layers_list.currentRow() < 0:
            self.layers_list.setCurrentRow(0)

    def _update_current_layer_item(self, layer: EditLayer) -> None:
        for index in range(self.layers_list.count()):
            item = self.layers_list.item(index)
            if str(item.data(256)) == layer.id:
                item.setText(_layer_label(layer))
                icon = _layer_icon(layer)
                item.setIcon(icon if icon is not None else QIcon())
                break
        self.layer_opacity_spin.blockSignals(True)
        self.layer_blend_combo.blockSignals(True)
        self.layer_visible_check.blockSignals(True)
        self.layer_lock_check.blockSignals(True)
        self.layer_position_lock_check.blockSignals(True)
        self.layer_visibility_lock_check.blockSignals(True)
        self.layer_opacity_spin.setValue(layer.opacity * 100.0)
        self.layer_blend_combo.setCurrentText(layer.blend_mode.value)
        self.layer_visible_check.setChecked(layer.visible)
        self.layer_lock_check.setChecked(layer.locked or LayerLock.PIXELS in layer.lock_flags)
        self.layer_position_lock_check.setChecked(LayerLock.POSITION in layer.lock_flags)
        self.layer_visibility_lock_check.setChecked(LayerLock.VISIBILITY in layer.lock_flags)
        self.layer_opacity_spin.blockSignals(False)
        self.layer_blend_combo.blockSignals(False)
        self.layer_visible_check.blockSignals(False)
        self.layer_lock_check.blockSignals(False)
        self.layer_position_lock_check.blockSignals(False)
        self.layer_visibility_lock_check.blockSignals(False)

    def _refresh_adjustments(self) -> None:
        self.adjustment_list.clear()
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        layers = sorted(self.project.adjustment_layers.values(), key=lambda layer: layer.order)
        for layer in layers:
            if source_node is None or layer.image_node_id == source_node:
                state = "on" if layer.enabled else "off"
                item = QListWidgetItem(f"{state} | {layer.name}")
                item.setData(256, layer.id)
                self.adjustment_list.addItem(item)

    def _ensure_default_layer(self) -> None:
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        if any(layer.source_node_id == source_node for layer in self.project.edit_layers.values()):
            return
        layer = EditLayer(
            name="Background",
            source_node_id=source_node,
            content_kind=LayerContentKind.SOURCE,
            order=self._next_layer_order(source_node),
        )
        self.project.edit_layers[layer.id] = layer
        self.project.active_edit_layers[source_node] = layer.id
        self._current_layer_id = layer.id
        self.project.touch()
