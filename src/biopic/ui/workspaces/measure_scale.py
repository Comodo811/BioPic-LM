"""Measurement, calibration, presets, and scale-bar workspace."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon, QKeyEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.project_render import (
    editable_assets,
    project_image_cache_key,
    render_project_image,
)
from biopic.models.calibration import (
    Calibration,
    ScalePreset,
    normalize_unit,
    parse_magnification,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import (
    Point,
    ScaleBar,
)
from biopic.models.project import Project
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.ui.settings import (
    restore_dialog_size,
    scrollable_dialog_body,
    settings_json,
)
from biopic.ui.workspace_helpers.common import (
    project_asset_display_name as _project_asset_display_name,
)
from biopic.ui.workspace_helpers.common import (
    scale_preset_table_headers as _scale_preset_table_headers,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.measure_scale_bars import MeasureScaleBarsMixin
from biopic.ui.workspaces.measure_scale_detection import MeasureScaleDetectionMixin
from biopic.ui.workspaces.measure_scale_measurements import MeasureScaleMeasurementsMixin
from biopic.ui.workspaces.measure_scale_presets import MeasureScalePresetsMixin
from biopic.ui.workspaces.measure_scale_records import MeasureScaleRecordsMixin


class MeasureScaleWorkspace(
    MeasureScaleMeasurementsMixin,
    MeasureScaleDetectionMixin,
    MeasureScaleRecordsMixin,
    MeasureScaleBarsMixin,
    MeasureScalePresetsMixin,
    QWidget,
):
    """Measurement, calibration, presets, and vector scale-bar workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.measurementChanged: Callable[[], None] | None = None
        self._last_measurement_line_pixels = 100.0
        self._editable_assets: list[ImageAsset] = []
        self._asset_list_signature: tuple[tuple[str, str, str], ...] | None = None
        self._display_signature: tuple[object, ...] | None = None
        self._rendered_image_cache: dict[str, tuple[tuple[object, ...], object]] = {}
        self._persistent_scale_presets_loaded = False
        self._last_determined_scale: dict[str, object] | None = None
        self._measurement_undo_stack: list[dict[str, object]] = []
        self._measurement_redo_stack: list[dict[str, object]] = []
        self._moving_measurement_id: str | None = None
        self._measurement_move_mode = "geometry"
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)
        measurement_defaults = settings_json(
            "measure/measurement_defaults",
            {
                "color": "#ffffff",
                "line_width": 2.0,
                "font_size": 13.0,
                "bold": False,
                "italic": False,
                "show_label": True,
                "decimal_places": 2,
            },
        )

        controls = QHBoxLayout()
        self.asset_combo = QComboBox()
        self.pixel_distance = QDoubleSpinBox()
        self.pixel_distance.setRange(0.001, 1_000_000.0)
        self.pixel_distance.setValue(100.0)
        self.known_distance = QDoubleSpinBox()
        self.known_distance.setRange(0.001, 1_000_000.0)
        self.known_distance.setValue(10.0)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(["μm", "mm", "cm", "inch", "pt", "px"])
        self.set_scale_button = QToolButton()
        self.set_scale_button.setText("Set Scale")
        self.set_scale_button.setMinimumWidth(96)
        self.set_scale_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.set_scale_menu = QMenu(self.set_scale_button)
        self.set_scale_menu.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        self.set_scale_button.setMenu(self.set_scale_menu)
        controls.addWidget(QLabel("Image"))
        controls.addWidget(self.asset_combo)
        controls.addWidget(QLabel("Pixels"))
        controls.addWidget(self.pixel_distance)
        controls.addWidget(QLabel("Known"))
        controls.addWidget(self.known_distance)
        controls.addWidget(self.unit_combo)
        controls.addWidget(self.set_scale_button)

        scale_bar_controls = QHBoxLayout()
        self.add_scale_bar_button = QPushButton("Add Scale Bar")
        scale_bar_controls.addWidget(self.add_scale_bar_button)
        self.export_measurements_button = QPushButton("Export Measurements CSV")
        scale_bar_controls.addWidget(self.export_measurements_button)
        scale_bar_controls.addStretch(1)

        measurement_controls = QHBoxLayout()
        self.measurement_type_label = QLabel("Measurement")
        self.measurement_type_combo = QComboBox()
        self.measurement_type_combo.addItems(["Line", "Area"])
        self.measurement_kind_combo = self.measurement_type_combo
        self.area_geometry_label = QLabel("Area geometry")
        self.area_geometry_combo = QComboBox()
        self.area_geometry_combo.addItems(["Rectangle", "Ellipse", "Freehand"])
        self.length_unit_label = QLabel("Length unit")
        self.length_unit_combo = QComboBox()
        self.length_unit_combo.addItems(["px", "\u03bcm", "mm"])
        self.length_unit_combo.setCurrentIndex(1)
        self.area_unit_label = QLabel("Area unit")
        self.area_unit_combo = QComboBox()
        self.area_unit_combo.addItems(["px\u00b2", "\u03bcm\u00b2", "mm\u00b2"])
        self.area_unit_combo.setCurrentIndex(1)
        self.label_alignment_combo = QComboBox()
        self.label_alignment_combo.addItems(["Keep label horizontal", "Align label to measurement"])
        self.measurement_color_button = self._color_button(
            str(measurement_defaults.get("color", "#ffffff"))
        )
        self.measurement_line_width = QDoubleSpinBox()
        self.measurement_line_width.setRange(0.5, 30.0)
        self.measurement_line_width.setValue(float(measurement_defaults.get("line_width", 2.0)))
        self.measurement_line_width.setSuffix(" px")
        self.measurement_font_size = QDoubleSpinBox()
        self.measurement_font_size.setRange(4.0, 144.0)
        self.measurement_font_size.setValue(float(measurement_defaults.get("font_size", 13.0)))
        self.measurement_font_size.setSuffix(" pt")
        self.measurement_bold = QCheckBox("B")
        self.measurement_bold.setToolTip("Bold measurement label")
        self.measurement_bold.setChecked(bool(measurement_defaults.get("bold", False)))
        self.measurement_italic = QCheckBox("I")
        self.measurement_italic.setToolTip("Italic measurement label")
        self.measurement_italic.setChecked(bool(measurement_defaults.get("italic", False)))
        self.measurement_show_label = QCheckBox("Show label")
        self.measurement_show_label.setChecked(bool(measurement_defaults.get("show_label", True)))
        self.measurement_digits = QDoubleSpinBox()
        self.measurement_digits.setRange(0, 6)
        self.measurement_digits.setDecimals(0)
        self.measurement_digits.setValue(float(measurement_defaults.get("decimal_places", 2)))
        self.measurement_show_sides = QCheckBox("Sides")
        self.measurement_show_sides.setToolTip("Display rectangle side lengths")
        self.measurement_move_button = QPushButton("Move")
        self.measurement_move_label_button = QPushButton("Move Label")
        self.measurement_move_value_button = QPushButton("Move Value")
        self.add_line_measurement_button = QPushButton("Add Measurement")
        self.add_to_preset_button = QPushButton("Add to Preset")
        self.add_to_preset_button.setVisible(False)
        measurement_controls.addWidget(self.measurement_type_label)
        measurement_controls.addWidget(self.measurement_type_combo)
        measurement_controls.addWidget(self.area_geometry_label)
        measurement_controls.addWidget(self.area_geometry_combo)
        measurement_controls.addWidget(self.length_unit_label)
        measurement_controls.addWidget(self.length_unit_combo)
        measurement_controls.addWidget(self.area_unit_label)
        measurement_controls.addWidget(self.area_unit_combo)
        measurement_controls.addWidget(QLabel("Label"))
        measurement_controls.addWidget(self.measurement_show_label)
        measurement_controls.addWidget(self.label_alignment_combo)
        measurement_controls.addWidget(QLabel("Color"))
        measurement_controls.addWidget(self.measurement_color_button)
        measurement_controls.addWidget(QLabel("Line"))
        measurement_controls.addWidget(self.measurement_line_width)
        measurement_controls.addWidget(QLabel("Font"))
        measurement_controls.addWidget(self.measurement_font_size)
        measurement_controls.addWidget(self.measurement_bold)
        measurement_controls.addWidget(self.measurement_italic)
        measurement_controls.addWidget(QLabel("Digits"))
        measurement_controls.addWidget(self.measurement_digits)
        measurement_controls.addWidget(self.measurement_show_sides)
        measurement_controls.addWidget(self.measurement_move_button)
        measurement_controls.addWidget(self.measurement_move_label_button)
        measurement_controls.addWidget(self.measurement_move_value_button)
        measurement_controls.addWidget(self.add_to_preset_button)
        measurement_controls.addStretch(1)

        layout.addLayout(measurement_controls)

        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(170, 120))
        self.asset_list.setUniformItemSizes(True)
        self.asset_list.setFlow(QListWidget.Flow.LeftToRight)
        self.asset_list.setWrapping(False)
        self.asset_list.setFixedHeight(150)
        layout.addWidget(self.asset_list)
        figure_board_note = QLabel(
            "Note: Figure-board scale bars and measurement text use their printed "
            "paper size. Positions are preserved; final styling can be adjusted in "
            "the figure board."
        )
        figure_board_note.setWordWrap(True)
        figure_board_note.setMaximumHeight(36)
        figure_board_note.setStyleSheet(
            "color: #b9c0c6; padding-left: 4px; padding-right: 4px;"
        )
        layout.addWidget(figure_board_note)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = ImageCanvas()
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        self.measurement_table = QTableWidget(0, 4)
        self.measurement_table.setHorizontalHeaderLabels(
            ["Label", "Kind", "Length", "Area"]
        )
        self.measurement_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.measurement_table.itemChanged.connect(self._measurement_table_item_changed)
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.addWidget(self.measurement_table)
        right_layout.addWidget(self.records)
        splitter.addWidget(self.canvas)
        splitter.addWidget(right_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)
        layout.addWidget(splitter)

        self.asset_combo.currentIndexChanged.connect(self._select_asset)
        self.asset_list.currentRowChanged.connect(self._select_asset_row)
        self.set_scale_menu.aboutToShow.connect(self._rebuild_scale_menu)
        self.add_scale_bar_button.clicked.connect(self.add_scale_bar)
        self.add_line_measurement_button.clicked.connect(self.add_line_measurement)
        self.add_to_preset_button.clicked.connect(self.add_determined_scale_to_preset)
        self.export_measurements_button.clicked.connect(self.export_measurements_csv)
        self.length_unit_combo.currentTextChanged.connect(self._measurement_display_options_changed)
        self.area_unit_combo.currentTextChanged.connect(self._measurement_display_options_changed)
        self.label_alignment_combo.currentTextChanged.connect(self._measurement_display_options_changed)
        self.measurement_line_width.valueChanged.connect(self._measurement_display_options_changed)
        self.measurement_font_size.valueChanged.connect(self._measurement_display_options_changed)
        self.measurement_bold.toggled.connect(self._measurement_display_options_changed)
        self.measurement_italic.toggled.connect(self._measurement_display_options_changed)
        self.measurement_show_label.toggled.connect(self._measurement_display_options_changed)
        self.measurement_digits.valueChanged.connect(self._measurement_display_options_changed)
        self.measurement_show_sides.toggled.connect(self._measurement_display_options_changed)
        self.measurement_move_button.clicked.connect(
            lambda: self._activate_measurement_move("geometry")
        )
        self.measurement_move_label_button.clicked.connect(
            lambda: self._activate_measurement_move("label")
        )
        self.measurement_move_value_button.clicked.connect(
            lambda: self._activate_measurement_move("value")
        )
        self.measurement_type_combo.currentTextChanged.connect(self._measurement_type_changed)
        self.area_geometry_combo.currentTextChanged.connect(
            lambda _value: self._measurement_type_changed(self.measurement_type_combo.currentText())
        )
        self.canvas.pointClicked.connect(self._measurement_point_clicked)
        self.canvas.lineSelected.connect(self._measurement_line_selected)
        self.canvas.rectangleSelected.connect(self._measurement_rectangle_selected)
        self.canvas.selectionCompleted.connect(self._measurement_selection_completed)
        self.canvas.layerDragStarted.connect(self._measurement_move_started)
        self.canvas.layerDragFinished.connect(self._measurement_move_finished)
        self._load_persistent_scale_presets()
        self._rebuild_scale_menu()
        self._measurement_pending_start: Point | None = None
        self._measurement_type_changed(self.measurement_type_combo.currentText())

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Measurement tool shortcuts."""
        key = event.key()
        if key == Qt.Key.Key_L:
            self.select_measurement_tool("line")
            return
        if key == Qt.Key.Key_R:
            self.select_measurement_tool("rectangle")
            return
        if key in {Qt.Key.Key_E, Qt.Key.Key_U}:
            self.select_measurement_tool("ellipse")
            return
        if key == Qt.Key.Key_F:
            self.select_measurement_tool("freehand")
            return
        if key == Qt.Key.Key_M:
            self._activate_measurement_move("geometry")
            return
        super().keyPressEvent(event)

    def select_measurement_tool(self, tool: str) -> None:
        """Select and activate a measurement tool."""
        if tool == "line":
            self.measurement_type_combo.setCurrentText("Line")
        else:
            self.measurement_type_combo.setCurrentText("Area")
            self.area_geometry_combo.setCurrentText(
                {
                    "rectangle": "Rectangle",
                    "ellipse": "Ellipse",
                    "freehand": "Freehand",
                }.get(tool, "Rectangle")
            )
        self.add_line_measurement()

    def _activate_measurement_move(self, mode: str) -> None:
        self._measurement_move_mode = mode
        self.canvas.set_tool_mode("move")
        self.records.setPlainText(
            {
                "label": "Move label: drag near a measurement label.",
                "value": "Move value: drag near a measurement value.",
            }.get(mode, "Move measurement: drag an existing measurement.")
        )

    def refresh(self) -> None:
        """Refresh image choices and record list."""
        self._load_persistent_scale_presets()
        current = self.asset_combo.currentData()
        assets = editable_assets(self.project)
        signature = tuple(
            (
                asset.id,
                _project_asset_display_name(asset, self.project.stacks),
                asset.checksum or asset.path,
            )
            for asset in assets
        )
        if signature != self._asset_list_signature:
            self.asset_combo.blockSignals(True)
            self.asset_list.blockSignals(True)
            self.asset_combo.clear()
            self.asset_list.clear()
            self._editable_assets = assets
            for asset in self._editable_assets:
                label = _project_asset_display_name(asset, self.project.stacks)
                self.asset_combo.addItem(label, asset.id)
                item = QListWidgetItem(
                    QIcon(asset_thumbnail(asset, QSize(170, 120))),
                    label,
                )
                item.setData(256, asset.id)
                self.asset_list.addItem(item)
            self.asset_combo.blockSignals(False)
            self.asset_list.blockSignals(False)
            self._asset_list_signature = signature
        else:
            self._editable_assets = assets
        if current is not None:
            index = self.asset_combo.findData(current)
            if index >= 0:
                self.asset_combo.setCurrentIndex(index)
                self.asset_list.setCurrentRow(index)
        if self.asset_combo.count() and self.asset_combo.currentIndex() < 0:
            self.asset_combo.setCurrentIndex(0)
        if self.asset_list.count() and self.asset_list.currentRow() < 0:
            self.asset_list.setCurrentRow(self.asset_combo.currentIndex())
        self._select_asset()
        self._refresh_records()

    def _rendered_project_image(self, node_id: str | None):
        if node_id is None:
            return None
        key = project_image_cache_key(self.project, node_id)
        if key is None:
            return None
        cached = self._rendered_image_cache.get(node_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        rendered = render_project_image(self.project, node_id)
        if rendered is not None:
            self._rendered_image_cache[node_id] = (key, rendered)
        return rendered

    def set_scale_from_inputs(self) -> None:
        """Calculate and store calibration for the selected image."""
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        calibration = Calibration.from_known_distance(
            self.pixel_distance.value(),
            self.known_distance.value(),
            normalize_unit(self.unit_combo.currentText()),
        )
        self.project.calibrations[node_id] = calibration
        self.project.touch()
        self._changed(notify=False)

    def add_permanent_preset(
        self,
        *,
        preset_name: str | None = None,
        camera_name: str | None = None,
        microscope_name: str | None = None,
        imaging_method_name: str | None = None,
        magnification_text: str | None = None,
        fluid_text: str | None = None,
        distance_pixels: float | None = None,
        known_distance_value: float | None = None,
        unit_text: str | None = None,
    ) -> bool:
        """Open the permanent camera/microscope preset dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Permanent Scale")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "add_permanent_scale", QSize(1200, 760))
        body = scrollable_dialog_body(dialog)
        layout = QVBoxLayout(body)
        form = QFormLayout()
        name = QLineEdit(preset_name or f"Preset {len(self.project.scale_presets) + 1}")
        camera = QLineEdit(camera_name or "Camera")
        microscope = QLineEdit(microscope_name or "Microscope")
        imaging_method = QLineEdit(imaging_method_name or "")
        notes = QPlainTextEdit()
        notes.setMaximumHeight(72)
        form.addRow("Preset Name", name)
        form.addRow("Camera Name", camera)
        form.addRow("Microscope Name", microscope)
        form.addRow("Imaging Method", imaging_method)
        form.addRow("Notes", notes)
        layout.addLayout(form)

        table = QTableWidget(0, 7)
        table.setHorizontalHeaderLabels(_scale_preset_table_headers())
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)

        row_controls = QHBoxLayout()
        add_row_button = QPushButton("+")
        remove_row_button = QPushButton("-")
        row_controls.addWidget(add_row_button)
        row_controls.addWidget(remove_row_button)
        row_controls.addStretch(1)
        layout.addLayout(row_controls)

        def add_row() -> None:
            row = table.rowCount()
            table.insertRow(row)
            base_pixels = float(distance_pixels or self.pixel_distance.value())
            base_known = float(known_distance_value or self.known_distance.value())
            pixels_per_unit = base_pixels / base_known
            magnification_value = magnification_text or "10x"
            try:
                known_distance = self._preset_known_distance_for_magnification(
                    parse_magnification(magnification_value)
                )
            except ValueError:
                known_distance = base_known
            values = [
                magnification_value,
                fluid_text or "Air",
                f"{pixels_per_unit * known_distance:g}",
                f"{known_distance:g}",
                normalize_unit(unit_text or self.unit_combo.currentText()),
                f"{pixels_per_unit:.6g}",
                "",
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))
            self._update_preset_table_row(table, row)

        def remove_row() -> None:
            row = table.currentRow()
            if row >= 0:
                table.removeRow(row)

        def update_row(row: int, _column: int) -> None:
            self._update_preset_table_row(table, row)

        add_row_button.clicked.connect(add_row)
        remove_row_button.clicked.connect(remove_row)
        table.cellChanged.connect(update_row)
        add_row()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        scales = self._scale_rows_from_table(table)
        if not scales:
            QMessageBox.warning(self, "Add Permanent Scale", "Add at least one valid scale row.")
            return False
        preset = ScalePreset(
            name=name.text().strip() or f"Preset {len(self.project.scale_presets) + 1}",
            camera_name=camera.text().strip(),
            microscope_name=microscope.text().strip(),
            imaging_method=imaging_method.text().strip(),
            notes=notes.toPlainText().strip(),
            scales=scales,
        )
        preset.scales = self._sorted_scale_rows(preset.scales)
        self.project.scale_presets[preset.id] = preset
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()
        return True

    def add_scale_bar(self) -> None:
        """Open a dialog to create vector scale bars linked to current calibration."""
        self._add_scale_bar_from_dialog()

    def _add_scale_bar_from_dialog(self) -> None:
        node_id = self._current_source_node_id()
        if node_id is None or node_id not in self.project.calibrations:
            QMessageBox.warning(self, "Add Scale Bar", "Set a scale for the selected image first.")
            return
        calibration = self.project.calibrations[node_id]
        existing_scale_bar = next(
            (
                scale_bar
                for scale_bar in self.project.scale_bars.values()
                if scale_bar.image_node_id == node_id
            ),
            None,
        )
        dialog = self._scale_bar_dialog(calibration, existing_scale_bar)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        new_scale_bar: ScaleBar | None = None
        image_width, image_height = self._scale_bar_offset_basis()
        for controls in dialog.property("scale_bar_controls"):
            enabled = controls["enabled"].isChecked()
            if not enabled:
                continue
            self._save_scale_bar_defaults(controls)
            new_scale_bar = ScaleBar(
                image_node_id=node_id,
                physical_length=controls["length"].value(),
                unit=controls["unit"].currentText(),
                calibration=calibration,
                orientation=controls["orientation"],
                width_px=controls["width"].value(),
                location=controls["location"].currentText(),
                offset_x=controls["offset_x"].value() / 100.0 * image_width,
                offset_y=controls["offset_y"].value() / 100.0 * image_height,
                foreground=self._color_button_value(controls["foreground"]),
                background=self._color_button_value(controls["background"]),
                display_length=controls["display_length"].isChecked(),
                font_family=controls["font_family"].currentText(),
                font_size=controls["font_size"].value(),
                bold=controls["bold"].isChecked(),
                italic=controls["italic"].isChecked(),
                opacity=controls["opacity"].value() / 100.0,
            )
            break
        if new_scale_bar is None:
            return
        for scale_bar_id, scale_bar in list(self.project.scale_bars.items()):
            if scale_bar.image_node_id == node_id:
                self.project.scale_bars.pop(scale_bar_id, None)
        self.project.scale_bars[new_scale_bar.id] = new_scale_bar
        self.project.touch()
        self._changed(notify=False)

