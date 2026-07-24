"""Measurement, calibration, presets, and scale-bar workspace."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
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
    asset_for_source_node,
    editable_assets,
    project_image_cache_key,
    render_project_image,
)
from biopic.models.calibration import (
    Calibration,
    ScalePreset,
    normalize_unit,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.measurement import Measurement, MeasurementKind, Point, ScaleBar
from biopic.models.project import Project
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.ui.settings import (
    remembered_save_file,
    restore_dialog_size,
    scrollable_dialog_body,
)
from biopic.ui.workspace_helpers.common import scale_preset_table_headers as _scale_preset_table_headers
from biopic.ui.workspace_helpers.common import project_asset_display_name as _project_asset_display_name
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.measure_scale_bars import MeasureScaleBarsMixin
from biopic.ui.workspaces.measure_scale_presets import MeasureScalePresetsMixin


class MeasureScaleWorkspace(MeasureScaleBarsMixin, MeasureScalePresetsMixin, QWidget):
    """Measurement, calibration, presets, and vector scale-bar workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.measurementChanged: Callable[[], None] | None = None
        self._last_measurement_line_pixels = 100.0
        self._editable_assets: list[ImageAsset] = []
        self._asset_list_signature: tuple[tuple[str, str, str], ...] | None = None
        self._display_signature: tuple[object, ...] | None = None
        self._rendered_image_cache: dict[str, tuple[tuple[object, ...], object]] = {}
        self._persistent_scale_presets_loaded = False
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)

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
        self.measurement_length_px = QDoubleSpinBox()
        self.measurement_length_px.setRange(0.001, 1_000_000.0)
        self.measurement_length_px.setValue(100.0)
        self.measurement_kind_combo = QComboBox()
        self.measurement_kind_combo.addItems(
            [
                "Line",
                "Segmented Line",
                "Polyline",
                "Angle",
                "Rectangle",
                "Ellipse",
                "Polygon",
                "Area",
                "Perimeter",
                "Feret Diameter",
            ]
        )
        self.add_line_measurement_button = QPushButton("Add Measurement")
        measurement_controls.addWidget(QLabel("Tool"))
        measurement_controls.addWidget(self.measurement_kind_combo)
        measurement_controls.addWidget(QLabel("Line length px"))
        measurement_controls.addWidget(self.measurement_length_px)
        measurement_controls.addWidget(self.add_line_measurement_button)
        measurement_controls.addStretch(1)

        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(170, 120))
        self.asset_list.setUniformItemSizes(True)
        self.asset_list.setFlow(QListWidget.Flow.LeftToRight)
        self.asset_list.setWrapping(False)
        self.asset_list.setFixedHeight(150)
        layout.addWidget(self.asset_list)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.canvas = ImageCanvas()
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        self.measurement_table = QTableWidget(0, 7)
        self.measurement_table.setHorizontalHeaderLabels(
            ["Label", "Kind", "Length px", "Length", "Area px", "Area", "Unit"]
        )
        self.measurement_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
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
        self.export_measurements_button.clicked.connect(self.export_measurements_csv)
        self._load_persistent_scale_presets()
        self._rebuild_scale_menu()

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

    def add_permanent_preset(self) -> None:
        """Open the permanent camera/microscope preset dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Permanent Scale")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "add_permanent_scale", QSize(1200, 760))
        body = scrollable_dialog_body(dialog)
        layout = QVBoxLayout(body)
        form = QFormLayout()
        name = QLineEdit(f"Preset {len(self.project.scale_presets) + 1}")
        camera = QLineEdit("Camera")
        microscope = QLineEdit("Microscope")
        imaging_method = QLineEdit()
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
            pixels_per_unit = self.pixel_distance.value() / self.known_distance.value()
            known_distance = self._preset_known_distance_for_magnification(10.0)
            values = [
                "10x",
                "Water",
                f"{pixels_per_unit * known_distance:g}",
                f"{known_distance:g}",
                normalize_unit(self.unit_combo.currentText()),
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
            return
        scales = self._scale_rows_from_table(table)
        if not scales:
            QMessageBox.warning(self, "Add Permanent Scale", "Add at least one valid scale row.")
            return
        preset = ScalePreset(
            name=name.text().strip() or f"Preset {len(self.project.scale_presets) + 1}",
            camera_name=camera.text().strip(),
            microscope_name=microscope.text().strip(),
            imaging_method=imaging_method.text().strip(),
            notes=notes.toPlainText().strip(),
            scales=scales,
        )
        self.project.scale_presets[preset.id] = preset
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()

    def add_scale_bar(self) -> None:
        """Open a dialog to create vector scale bars linked to current calibration."""
        self._add_scale_bar_from_dialog()

    def add_measurement_scale_bar(self) -> None:
        """Add a movable measurement scale-bar object linked to current calibration."""
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

    def add_line_measurement(self) -> None:
        """Add a measurement row using the selected calibrated tool."""
        node_id = self._current_source_node_id()
        if node_id is None or node_id not in self.project.calibrations:
            QMessageBox.warning(
                self,
                "Add Measurement",
                "Set a scale for the selected image first.",
            )
            return
        calibration = self.project.calibrations[node_id]
        kind_label = self.measurement_kind_combo.currentText()
        kind = {
            "Line": MeasurementKind.LINE,
            "Segmented Line": MeasurementKind.POLYLINE,
            "Polyline": MeasurementKind.POLYLINE,
            "Angle": MeasurementKind.ANGLE,
            "Rectangle": MeasurementKind.RECTANGLE,
            "Ellipse": MeasurementKind.ELLIPSE,
            "Polygon": MeasurementKind.POLYGON,
            "Area": MeasurementKind.POLYGON,
            "Perimeter": MeasurementKind.POLYLINE,
            "Feret Diameter": MeasurementKind.LINE,
        }[kind_label]
        length = self.measurement_length_px.value()
        measurement = Measurement(
            kind=kind,
            image_node_id=node_id,
            points=self._default_measurement_points(kind, length),
            calibration=calibration,
            label=f"{kind_label} {len(self.project.measurements) + 1}",
        )
        self.project.measurements[measurement.id] = measurement
        self.project.touch()
        self._changed()

    def determine_scale_from_image(self) -> None:
        """Open the determine-scale dialog and apply its calibration scope."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Determine Scale from Image")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "determine_scale_from_image", QSize(520, 320))
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        pixel_distance = QDoubleSpinBox()
        pixel_distance.setRange(0.001, 1_000_000.0)
        pixel_distance.setValue(self._last_measurement_line_pixels)
        known_distance = QDoubleSpinBox()
        known_distance.setRange(0.001, 1_000_000.0)
        known_distance.setValue(self.known_distance.value())
        unit = QComboBox()
        unit.addItems(["μm", "mm", "cm", "inch", "pt", "px"])
        unit.setCurrentText(self.unit_combo.currentText())
        pixel_aspect = QDoubleSpinBox()
        pixel_aspect.setRange(0.001, 1000.0)
        pixel_aspect.setValue(1.0)
        scope = QComboBox()
        scope.addItems(["Current image", "Selected images", "Entire project"])
        result = QLabel()
        form.addRow("Distance in pixels", pixel_distance)
        form.addRow("Known physical distance", known_distance)
        form.addRow("Unit", unit)
        form.addRow("Pixel aspect ratio", pixel_aspect)
        form.addRow("Apply calibration to", scope)
        form.addRow("Calculated calibration", result)
        layout.addLayout(form)

        def refresh_formula() -> None:
            selected_unit = normalize_unit(unit.currentText())
            s_value = known_distance.value() / pixel_distance.value()
            rho_value = pixel_distance.value() / known_distance.value()
            result.setText(
                f"s = d_known / d_pixels = {s_value:.6g} {selected_unit}/pixel\n"
                f"rho = d_pixels / d_known = {rho_value:.6g} pixels/{selected_unit}"
            )

        pixel_distance.valueChanged.connect(refresh_formula)
        known_distance.valueChanged.connect(refresh_formula)
        unit.currentTextChanged.connect(refresh_formula)
        refresh_formula()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        calibration = Calibration(
            unit_per_pixel=known_distance.value() / pixel_distance.value(),
            unit=normalize_unit(unit.currentText()),
            pixel_aspect_ratio=pixel_aspect.value(),
            source="determine_scale_from_image",
        )
        for node_id in self._node_ids_for_scope(scope.currentText()):
            self.project.calibrations[node_id] = calibration
        self.pixel_distance.setValue(pixel_distance.value())
        self.known_distance.setValue(known_distance.value())
        self.unit_combo.setCurrentText(normalize_unit(unit.currentText()))
        self.project.touch()
        self._changed()

    def export_measurements_csv(self) -> None:
        """Export measurement results to CSV."""
        from biopic.imaging.measurement import export_measurements_csv

        filename = remembered_save_file(
            self,
            "Export Measurements CSV",
            "measurements_csv",
            "CSV (*.csv)",
        )
        if not filename:
            return
        export_measurements_csv(list(self.project.measurements.values()), Path(filename))

    def _select_asset(self) -> None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return
        row = self.asset_combo.currentIndex()
        if row >= 0 and self.asset_list.currentRow() != row:
            self.asset_list.blockSignals(True)
            self.asset_list.setCurrentRow(row)
            self.asset_list.blockSignals(False)
        asset = self.project.assets.get(str(asset_id))
        if asset is not None:
            node_id = self.project.source_node_id_for_asset(asset.id)
            rendered = self._rendered_project_image(node_id)
            if rendered is not None:
                signature = (
                    asset.id,
                    node_id,
                    project_image_cache_key(self.project, node_id),
                    rendered.shape,
                    str(rendered.dtype),
                )
                if signature != self._display_signature:
                    self.canvas.set_pixels(rendered, asset.filename, fit=True)
                    self._display_signature = signature
            else:
                self.canvas.set_asset(asset)
                self._display_signature = (asset.id, "asset", asset.checksum or asset.path)
            self._refresh_scale_bar_overlay()

    def _select_asset_row(self, row: int) -> None:
        if row < 0 or row >= len(self._editable_assets):
            return
        if self.asset_combo.currentIndex() != row:
            self.asset_combo.blockSignals(True)
            self.asset_combo.setCurrentIndex(row)
            self.asset_combo.blockSignals(False)
        self._select_asset()

    def current_asset_id(self) -> str | None:
        """Return the currently selected editable image asset id."""
        asset_id = self.asset_combo.currentData()
        return None if asset_id is None else str(asset_id)

    def select_asset_id(self, asset_id: str | None) -> None:
        """Select an editable image asset by id and redraw linked overlays."""
        if asset_id is None:
            self._select_asset()
            return
        index = self.asset_combo.findData(asset_id)
        if index >= 0:
            self.asset_combo.setCurrentIndex(index)
        self._select_asset()

    def _current_source_node_id(self) -> str | None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return None
        return self.project.source_node_id_for_asset(str(asset_id))

    def _changed(self, *, notify: bool = True) -> None:
        self._refresh_records()
        self._rebuild_scale_menu()
        self._refresh_scale_bar_overlay()
        if notify and self.measurementChanged is not None:
            self.measurementChanged()

    def _refresh_scale_bar_overlay(self) -> None:
        node_id = self._current_source_node_id()
        scale_bars = [
            scale_bar
            for scale_bar in self.project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ]
        if node_id is not None and node_id in self.project.calibrations:
            calibration = self.project.calibrations[node_id]
            for scale_bar in scale_bars:
                scale_bar.calibration = calibration
        self.canvas.set_scale_bars(scale_bars)

    def _refresh_records(self) -> None:
        self._refresh_measurement_table()
        lines: list[str] = []
        lines.append("Calibrations")
        for node_id, calibration in self.project.calibrations.items():
            label = self._source_node_label(node_id)
            lines.append(
                f"{label}: Scale {calibration.unit_per_pixel:.6g} "
                f"{calibration.unit}/pixel; Density {calibration.pixels_per_unit:.6g} "
                f"pixels/{calibration.unit}"
            )
        lines.append("")
        lines.append("Scale Presets")
        for preset in self.project.scale_presets.values():
            labels = ", ".join(scale.menu_label() for scale in preset.scales)
            lines.append(f"{preset.name}: {labels}")
        lines.append("")
        lines.append("Measurements")
        for measurement in self.project.measurements.values():
            lines.append(
                f"{measurement.label}: {measurement.length_physical():.6g} "
                f"{measurement.calibration.unit}"
            )
        lines.append("")
        lines.append("Scale Bars")
        for scale_bar in self.project.scale_bars.values():
            label = self._source_node_label(scale_bar.image_node_id)
            lines.append(
                f"{label}: {scale_bar.physical_length:g} {scale_bar.unit} scale bar, "
                f"{scale_bar.pixel_length:.2f} pixels at {scale_bar.location}"
            )
        self.records.setPlainText("\n".join(lines))

    def _source_node_label(self, node_id: str) -> str:
        asset = asset_for_source_node(self.project, node_id)
        if asset is not None:
            return asset.filename
        return "Current image"

    def _refresh_measurement_table(self) -> None:
        measurements = list(self.project.measurements.values())
        self.measurement_table.setRowCount(len(measurements))
        for row, measurement in enumerate(measurements):
            values = [
                measurement.label,
                measurement.kind.value,
                f"{measurement.length_pixels():.6g}",
                f"{measurement.length_physical():.6g}",
                f"{measurement.area_pixels():.6g}",
                f"{measurement.area_physical():.6g}",
                measurement.calibration.unit,
            ]
            for column, value in enumerate(values):
                self.measurement_table.setItem(row, column, QTableWidgetItem(value))

    def _default_measurement_points(
        self, kind: MeasurementKind, length: float
    ) -> list[Point]:
        if kind is MeasurementKind.RECTANGLE:
            return [Point(0.0, 0.0), Point(length, max(1.0, length / 2.0))]
        if kind is MeasurementKind.ELLIPSE:
            return [Point(0.0, 0.0), Point(length, max(1.0, length / 2.0))]
        if kind is MeasurementKind.POLYGON:
            return [Point(0.0, 0.0), Point(length, 0.0), Point(length, length)]
        if kind is MeasurementKind.ANGLE:
            return [Point(0.0, 0.0), Point(length / 2.0, 0.0), Point(length / 2.0, length / 2.0)]
        return [Point(0.0, 0.0), Point(length, 0.0)]
