"""Preset menu and dialog helpers for the main window."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QMessageBox,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QVBoxLayout,
)

from biopic.models.calibration import MagnificationScale, ScalePreset, parse_magnification
from biopic.ui.settings import set_settings_json, settings_json


class MainWindowPresetsMixin:
    """Preset menu and persistence helpers."""

    def _journal_preset_callback(self, name: str) -> Callable[[], None]:
        def callback() -> None:
            self.figure_board_workspace.set_journal_preset(name)

        return callback

    def _rebuild_metadata_preset_menus(self) -> None:
        self._load_persistent_metadata_presets()
        self.equipment_presets_menu.clear()
        self._add_action(
            self.equipment_presets_menu,
            "Add Equipment Preset...",
            None,
            self.measure_workspace.add_permanent_preset,
        )
        if self.project.scale_presets:
            self.equipment_presets_menu.addSeparator()
        for preset in self.project.scale_presets.values():
            preset_menu = self.equipment_presets_menu.addMenu(preset.name)
            preset_menu.addAction(
                "Use for Current Image Metadata",
                lambda _checked=False, preset_id=preset.id: (
                    self.metadata_workspace.apply_metadata_preset("equipment", preset_id)
                ),
            )
            preset_menu.addAction(
                "Edit Scale / Equipment Preset",
                lambda _checked=False, preset=preset: self.measure_workspace._edit_preset(preset),
            )
        for menu, category, label in (
            (self.location_presets_menu, "location", "Location Preset"),
            (self.collector_presets_menu, "collector", "Collector Preset"),
            (self.preparation_presets_menu, "preparation", "Preparation Preset"),
        ):
            menu.clear()
            self._add_action(
                menu,
                f"Add {label}...",
                None,
                lambda _checked=False, current=category: self._add_metadata_preset(current),
            )
            presets = self.project.metadata_presets.setdefault(category, [])
            if presets:
                menu.addSeparator()
            for preset in presets:
                name = preset.get("name", "").strip()
                if not name:
                    continue
                self._add_action(
                    menu,
                    name,
                    None,
                    lambda _checked=False, current=category, preset_name=name: (
                        self.metadata_workspace.apply_metadata_preset(current, preset_name)
                    ),
                )

    def _add_metadata_preset(self, category: str) -> None:
        if category == "equipment":
            self._add_equipment_preset()
            return
        fields_by_category = {
            "location": (
                ("name", "Preset name"),
                ("locality", "Location name"),
                ("latitude", "Latitude"),
                ("longitude", "Longitude"),
                ("habitat", "Habitat / Substrate"),
                ("institution", "Institution"),
            ),
            "collector": (
                ("name", "Preset name"),
                ("collector", "Collector"),
                ("institution", "Institution"),
            ),
            "preparation": (
                ("name", "Preset name"),
                ("preparation", "Preparation"),
                ("staining", "Staining / Contrast"),
            ),
        }
        field_specs = fields_by_category.get(category)
        if field_specs is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Add {category.title()} Preset")
        form = QFormLayout(dialog)
        editors: dict[str, QLineEdit] = {}
        for key, label in field_specs:
            editor = QLineEdit()
            editors[key] = editor
            form.addRow(label, editor)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preset = {
            key: editor.text().strip()
            for key, editor in editors.items()
            if editor.text().strip()
        }
        if not preset.get("name"):
            QMessageBox.warning(self, "Preset Name Required", "Enter a preset name.")
            return
        presets = self.project.metadata_presets.setdefault(category, [])
        presets[:] = [item for item in presets if item.get("name") != preset["name"]]
        presets.append(preset)
        self._save_persistent_metadata_presets()
        self.project.touch()
        self._has_unsaved_changes = True
        self.metadata_workspace.refresh_metadata_presets()
        self._rebuild_metadata_preset_menus()
        self.refresh_project_views()

    def _add_equipment_preset(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Equipment Preset")
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        editors: dict[str, QLineEdit] = {}
        for key, label in (
            ("name", "Preset name"),
            ("microscope", "Microscope"),
            ("camera", "Camera"),
            ("imaging_method", "Imaging method"),
        ):
            editor = QLineEdit()
            editors[key] = editor
            form.addRow(label, editor)
        layout.addLayout(form)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Objective", "Magnification"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)
        row_controls = QHBoxLayout()
        add_row = QToolButton()
        add_row.setText("+")
        remove_row = QToolButton()
        remove_row.setText("-")
        row_controls.addWidget(add_row)
        row_controls.addWidget(remove_row)
        row_controls.addStretch(1)
        layout.addLayout(row_controls)

        def append_row(objective: str = "", magnification: str = "") -> None:
            row = table.rowCount()
            table.insertRow(row)
            table.setItem(row, 0, QTableWidgetItem(objective))
            table.setItem(row, 1, QTableWidgetItem(magnification))

        def remove_current_row() -> None:
            row = table.currentRow()
            if row >= 0:
                table.removeRow(row)

        def update_objective_from_magnification(row: int, column: int) -> None:
            if column != 1 or row < 0:
                return
            objective_item = table.item(row, 0)
            magnification_item = table.item(row, 1)
            if magnification_item is None or magnification_item.text().strip() == "":
                return
            if objective_item is not None and objective_item.text().strip():
                return
            table.blockSignals(True)
            table.setItem(
                row,
                0,
                QTableWidgetItem(f"{magnification_item.text().strip()} objective"),
            )
            table.blockSignals(False)

        add_row.clicked.connect(lambda: append_row())
        remove_row.clicked.connect(remove_current_row)
        table.cellChanged.connect(update_objective_from_magnification)
        append_row("10x objective", "10x")
        append_row("40x objective", "40x")
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        preset: dict[str, object] = {
            key: editor.text().strip()
            for key, editor in editors.items()
            if editor.text().strip()
        }
        if not preset.get("name"):
            QMessageBox.warning(self, "Preset Name Required", "Enter a preset name.")
            return
        objectives: list[dict[str, str]] = []
        for row in range(table.rowCount()):
            objective_item = table.item(row, 0)
            magnification_item = table.item(row, 1)
            objective = "" if objective_item is None else objective_item.text().strip()
            magnification = "" if magnification_item is None else magnification_item.text().strip()
            if objective or magnification:
                objectives.append({"objective": objective, "magnification": magnification})
        preset["objectives"] = objectives
        presets = self.project.metadata_presets.setdefault("equipment", [])
        presets[:] = [item for item in presets if item.get("name") != preset["name"]]
        presets.append(preset)
        self._sync_equipment_scale_preset(preset)
        self.measure_workspace._save_persistent_scale_presets()
        self._save_persistent_metadata_presets()
        self.project.touch()
        self._has_unsaved_changes = True
        self.metadata_workspace.refresh_metadata_presets()
        self._rebuild_metadata_preset_menus()
        self.refresh_project_views()

    def _sync_equipment_scale_preset(self, preset: dict[str, object]) -> None:
        name = str(preset.get("name", "")).strip()
        if not name:
            return
        scales: list[MagnificationScale] = []
        imaging_method = str(preset.get("imaging_method", ""))
        for row in preset.get("objectives", []):
            if not isinstance(row, dict):
                continue
            try:
                magnification = parse_magnification(row.get("magnification", ""))
            except ValueError:
                continue
            known_distance = self._default_known_distance_for_magnification(magnification)
            pixels_per_unit = 10.0
            scales.append(
                MagnificationScale(
                    magnification=magnification,
                    fluid="Air",
                    distance_pixels=known_distance * pixels_per_unit,
                    known_distance=known_distance,
                    unit="ÃŽÂ¼m",
                    unit_per_pixel=1.0 / pixels_per_unit,
                    objective=str(row.get("objective", "")),
                )
            )
        if not scales:
            return
        existing = next(
            (
                scale_preset
                for scale_preset in self.project.scale_presets.values()
                if scale_preset.name == name
            ),
            None,
        )
        if existing is None:
            existing = ScalePreset(name=name)
            self.project.scale_presets[existing.id] = existing
        existing.camera_name = str(preset.get("camera", ""))
        existing.microscope_name = str(preset.get("microscope", ""))
        existing.imaging_method = imaging_method
        existing.notes = (
            "Seeded from equipment preset. Pixel per unit rows are editable calibration values."
        )
        existing.scales = scales

    def _default_known_distance_for_magnification(self, magnification: float) -> float:
        anchors = {5.0: 1000.0, 10.0: 800.0, 20.0: 400.0, 40.0: 200.0, 100.0: 80.0}
        if magnification in anchors:
            return anchors[magnification]
        nearest = min(anchors, key=lambda value: abs(value - magnification))
        return anchors[nearest] * nearest / magnification

    def _load_persistent_metadata_presets(self) -> None:
        if bool(getattr(self, "_persistent_metadata_presets_loaded", False)):
            return
        data = settings_json(
            "presets/metadata",
            {
                "schema_version": 1,
                "metadata_presets": {
                    "equipment": [],
                    "location": [],
                    "collector": [],
                    "preparation": [],
                },
            },
        )
        presets_by_category = data.get("metadata_presets", {}) if isinstance(data, dict) else {}
        if not isinstance(presets_by_category, dict):
            presets_by_category = {}
        for category in ("equipment", "location", "collector", "preparation"):
            project_presets = self.project.metadata_presets.setdefault(category, [])
            existing_names = {
                str(item.get("name", "")).casefold()
                for item in project_presets
                if isinstance(item, dict)
            }
            stored_presets = presets_by_category.get(category, [])
            if not isinstance(stored_presets, list):
                continue
            for stored in stored_presets:
                if not isinstance(stored, dict):
                    continue
                preset = {str(key): value for key, value in stored.items()}
                name = str(preset.get("name", "")).strip()
                if not name or name.casefold() in existing_names:
                    continue
                project_presets.append(preset)
                existing_names.add(name.casefold())
        self._persistent_metadata_presets_loaded = True

    def _save_persistent_metadata_presets(self) -> None:
        set_settings_json(
            "presets/metadata",
            {
                "schema_version": 1,
                "metadata_presets": {
                    category: [
                        dict(preset)
                        for preset in self.project.metadata_presets.get(category, [])
                        if isinstance(preset, dict) and str(preset.get("name", "")).strip()
                    ]
                    for category in ("equipment", "location", "collector", "preparation")
                },
            },
        )
        self._persistent_metadata_presets_loaded = True
