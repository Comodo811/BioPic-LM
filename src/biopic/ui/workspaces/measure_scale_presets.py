"""Scale-preset menus, import/export, and table parsing."""

from __future__ import annotations

import json
from pathlib import Path

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from biopic.imaging.project_render import editable_assets
from biopic.models.calibration import MagnificationScale, ScalePreset, normalize_unit, parse_magnification
from biopic.ui.settings import (
    remembered_open_file,
    remembered_save_file,
    restore_dialog_size,
    scrollable_dialog_body,
    set_settings_json,
    settings_json,
)
from biopic.ui.workspace_helpers.common import scale_preset_table_headers as _scale_preset_table_headers
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET


class MeasureScalePresetsMixin:
    """Scale-preset menu and persistence helpers."""

    def _rebuild_scale_menu(self) -> None:
        self.set_scale_menu.clear()
        self.set_scale_menu.addAction("Set Scale", self.set_scale_from_inputs)
        self.set_scale_menu.addAction("Determine Scale from Image", self.determine_scale_from_image)
        self.set_scale_menu.addSeparator()
        if self.project.scale_presets:
            for preset in self.project.scale_presets.values():
                preset_menu = self.set_scale_menu.addMenu(preset.name)
                preset_menu.menuAction().setCheckable(True)
                preset_menu.menuAction().setChecked(self._preset_is_active(preset))
                for scale in preset.scales:
                    label = scale.menu_label().replace("x", "x")
                    action = preset_menu.addAction(
                        label,
                        lambda _checked=False, preset=preset, scale=scale: self._apply_preset_scale(
                            preset, scale
                        ),
                    )
                    action.setCheckable(True)
                    action.setChecked(self._scale_is_active(preset, scale))
                preset_menu.addSeparator()
                preset_menu.addAction(
                    "Edit Preset",
                    lambda _checked=False, preset=preset: self._edit_preset(preset),
                )
                preset_menu.addAction(
                    "Duplicate Preset",
                    lambda _checked=False, preset=preset: self._duplicate_preset(preset),
                )
                preset_menu.addAction(
                    "Export Preset",
                    lambda _checked=False, preset=preset: self._export_preset(preset),
                )
                preset_menu.addAction(
                    "Delete Preset",
                    lambda _checked=False, preset=preset: self._delete_preset(preset),
                )
        else:
            action = QAction("Saved Camera + Microscope Presets", self.set_scale_menu)
            action.setEnabled(False)
            self.set_scale_menu.addAction(action)
        self.set_scale_menu.addSeparator()
        self.set_scale_menu.addAction("Add Permanent Scale", self.add_permanent_preset)
        self.set_scale_menu.addAction("Import Preset", self._import_preset)

    def _apply_preset_scale(self, preset: ScalePreset, scale: MagnificationScale) -> None:
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        self.project.calibrations[node_id] = scale.to_calibration(source=preset.name)
        self.project.touch()
        self._changed(notify=False)

    def _preset_is_active(self, preset: ScalePreset) -> bool:
        return any(self._scale_is_active(preset, scale) for scale in preset.scales)

    def _scale_is_active(self, preset: ScalePreset, scale: MagnificationScale) -> bool:
        node_id = self._current_source_node_id()
        if node_id is None:
            return False
        active = self.project.calibrations.get(node_id)
        if active is None or active.source != preset.name:
            return False
        calibration = scale.to_calibration(source=preset.name)
        return (
            normalize_unit(active.unit) == normalize_unit(calibration.unit)
            and abs(active.unit_per_pixel - calibration.unit_per_pixel) < 1e-9
        )

    def _edit_preset(self, preset: ScalePreset) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Edit Preset")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "edit_scale_preset", QSize(1200, 760))
        body = scrollable_dialog_body(dialog)
        layout = QVBoxLayout(body)
        form = QFormLayout()
        name = QLineEdit(preset.name)
        camera = QLineEdit(preset.camera_name)
        microscope = QLineEdit(preset.microscope_name)
        imaging_method = QLineEdit(preset.imaging_method)
        notes = QPlainTextEdit(preset.notes)
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

        for scale in preset.scales:
            row = table.rowCount()
            table.insertRow(row)
            values = [
                f"{scale.magnification:g}x",
                scale.fluid,
                f"{scale.distance_pixels:g}",
                f"{scale.known_distance:g}",
                scale.unit,
                f"{scale.pixels_per_unit:.6g}",
                scale.objective,
            ]
            for column, value in enumerate(values):
                table.setItem(row, column, QTableWidgetItem(value))

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
            for column, value in enumerate(["10x", "Water", "100", "10", "μm", "10"]):
                table.setItem(row, column, QTableWidgetItem(value))

        def remove_row() -> None:
            row = table.currentRow()
            if row >= 0:
                table.removeRow(row)

        add_row_button.clicked.connect(add_row)
        remove_row_button.clicked.connect(remove_row)
        table.cellChanged.connect(lambda row, _column: self._update_preset_table_row(table, row))

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
            QMessageBox.warning(self, "Edit Preset", "Add at least one valid scale row.")
            return
        preset.name = name.text().strip() or preset.name
        preset.camera_name = camera.text().strip()
        preset.microscope_name = microscope.text().strip()
        preset.imaging_method = imaging_method.text().strip()
        preset.notes = notes.toPlainText().strip()
        preset.scales = scales
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()

    def _duplicate_preset(self, preset: ScalePreset) -> None:
        duplicate = ScalePreset(
            name=f"{preset.name} copy",
            camera_name=preset.camera_name,
            microscope_name=preset.microscope_name,
            imaging_method=preset.imaging_method,
            notes=preset.notes,
            scales=list(preset.scales),
        )
        self.project.scale_presets[duplicate.id] = duplicate
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()

    def _delete_preset(self, preset: ScalePreset) -> None:
        self.project.scale_presets.pop(preset.id, None)
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()

    def _export_preset(self, preset: ScalePreset) -> None:
        filename = remembered_save_file(
            self,
            "Export Scale Preset",
            "scale_preset_export",
            "JSON (*.json)",
            f"{preset.name}.biopic-scale.json",
        )
        if not filename:
            return
        Path(filename).write_text(json.dumps(preset.to_dict(), indent=2), encoding="utf-8")

    def _import_preset(self) -> None:
        filename = remembered_open_file(
            self,
            "Import Scale Preset",
            "scale_preset_import",
            "JSON (*.json)",
        )
        if not filename:
            return
        data = json.loads(Path(filename).read_text(encoding="utf-8"))
        preset = ScalePreset.from_dict(data)
        self.project.scale_presets[preset.id] = preset
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()

    def _load_persistent_scale_presets(self) -> None:
        if bool(getattr(self, "_persistent_scale_presets_loaded", False)):
            return
        data = settings_json("presets/scale", {"schema_version": 1, "scale_presets": []})
        for item in data.get("scale_presets", []):
            try:
                preset = ScalePreset.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            self.project.scale_presets.setdefault(preset.id, preset)
        self._persistent_scale_presets_loaded = True

    def _save_persistent_scale_presets(self) -> None:
        set_settings_json(
            "presets/scale",
            {
                "schema_version": 1,
                "scale_presets": [
                    preset.to_dict() for preset in self.project.scale_presets.values()
                ],
            },
        )
        self._persistent_scale_presets_loaded = True

    def _scale_rows_from_table(self, table: QTableWidget) -> list[MagnificationScale]:
        scales: list[MagnificationScale] = []
        for row in range(table.rowCount()):
            try:
                magnification = parse_magnification(self._table_text(table, row, 0))
                fluid = self._table_text(table, row, 1) or "Water"
                distance_pixels = float(self._table_text(table, row, 2))
                known_distance = float(self._table_text(table, row, 3))
                unit = normalize_unit(self._table_text(table, row, 4) or "μm")
                pixels_per_unit = self._optional_positive_float(self._table_text(table, row, 5))
                unit_per_pixel = None if pixels_per_unit is None else 1.0 / pixels_per_unit
                objective = self._table_text(table, row, 6)
                scales.append(
                    MagnificationScale(
                        magnification=magnification,
                        fluid=fluid,
                        distance_pixels=distance_pixels,
                        known_distance=known_distance,
                        unit=unit,
                        unit_per_pixel=unit_per_pixel,
                        objective=objective,
                    )
                )
            except ValueError:
                continue
        return scales

    def _update_preset_table_row(self, table: QTableWidget, row: int) -> None:
        if row < 0 or row >= table.rowCount():
            return
        try:
            magnification = parse_magnification(self._table_text(table, row, 0))
        except ValueError:
            return
        known_distance = self._preset_known_distance_for_magnification(magnification)
        pixels_per_unit = self._optional_positive_float(self._table_text(table, row, 5))
        if pixels_per_unit is None:
            try:
                distance_pixels = float(self._table_text(table, row, 2))
                manual_known_distance = float(self._table_text(table, row, 3))
                if distance_pixels <= 0 or manual_known_distance <= 0:
                    return
                known_distance = manual_known_distance
                pixels_per_unit = distance_pixels / known_distance
            except ValueError:
                table.blockSignals(True)
                table.setItem(row, 3, QTableWidgetItem(f"{known_distance:g}"))
                table.blockSignals(False)
                return
        else:
            distance_pixels = pixels_per_unit * known_distance
        table.blockSignals(True)
        table.setItem(row, 2, QTableWidgetItem(f"{distance_pixels:g}"))
        table.setItem(row, 3, QTableWidgetItem(f"{known_distance:g}"))
        table.setItem(
            row,
            4,
            QTableWidgetItem(normalize_unit(self._table_text(table, row, 4) or "Î¼m")),
        )
        table.setItem(row, 5, QTableWidgetItem(f"{pixels_per_unit:.6g}"))
        table.blockSignals(False)

    def _preset_known_distance_for_magnification(self, magnification: float) -> float:
        anchors = {
            5.0: 1000.0,
            10.0: 800.0,
            20.0: 400.0,
            40.0: 200.0,
            100.0: 80.0,
        }
        if magnification in anchors:
            return anchors[magnification]
        sorted_items = sorted(anchors.items())
        for (left_mag, left_distance), (right_mag, right_distance) in zip(
            sorted_items[:-1],
            sorted_items[1:],
            strict=True,
        ):
            if left_mag <= magnification <= right_mag:
                ratio = (magnification - left_mag) / (right_mag - left_mag)
                return left_distance + ratio * (right_distance - left_distance)
        reference_magnification, reference_distance = (
            sorted_items[0] if magnification < sorted_items[0][0] else sorted_items[-1]
        )
        return reference_distance * reference_magnification / magnification

    def _table_text(self, table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()

    def _optional_positive_float(self, value: str) -> float | None:
        if not value:
            return None
        number = float(value)
        if number <= 0:
            raise ValueError("value must be greater than zero")
        return number

    def _node_ids_for_scope(self, scope: str) -> list[str]:
        if scope == "Entire project":
            return [
                node_id
                for asset in editable_assets(self.project)
                if (node_id := self.project.source_node_id_for_asset(asset.id)) is not None
            ]
        node_id = self._current_source_node_id()
        return [] if node_id is None else [node_id]
