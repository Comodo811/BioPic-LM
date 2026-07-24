"""Abbreviation-table management for annotation workspaces."""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from PySide6.QtCore import QSize
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from biopic.models.annotations import (
    AbbreviationEntry,
    AbbreviationTablePreset,
    AnnotationDefinition,
)
from biopic.ui.settings import (
    remembered_open_file,
    remembered_save_file,
    restore_dialog_size,
    set_settings_json,
    settings_json,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET

COMMON_ABBREVIATION_LANGUAGES = [
    "English",
    "German",
    "Chinese",
    "Japanese",
    "Italian",
    "French",
    "Spanish",
    "Portuguese",
    "Dutch",
    "Polish",
    "Russian",
    "Korean",
]


class AnnotationAbbreviationsMixin:
    """Persistent abbreviation-table actions and dialogs."""

    def _load_persistent_abbreviation_tables(self) -> None:
        data = settings_json(
            "presets/abbreviation_tables",
            {"schema_version": 1, "active_table_id": None, "tables": []},
        )
        self._abbreviation_presets.clear()
        for item in data.get("tables", []):
            try:
                preset = AbbreviationTablePreset.from_dict(item)
            except (KeyError, TypeError, ValueError):
                continue
            self._abbreviation_presets[preset.id] = preset
        active = data.get("active_table_id")
        self._active_abbreviation_table_id = (
            str(active) if active in self._abbreviation_presets else None
        )

    def _save_persistent_abbreviation_tables(self) -> None:
        set_settings_json(
            "presets/abbreviation_tables",
            {
                "schema_version": 1,
                "active_table_id": self._active_abbreviation_table_id,
                "tables": [
                    preset.to_dict() for preset in self._abbreviation_presets.values()
                ],
            },
        )

    def _rebuild_abbreviation_table_menu(self) -> None:
        self.abbreviation_table_menu.clear()
        if self._abbreviation_presets:
            for preset in self._abbreviation_presets.values():
                preset_menu = self.abbreviation_table_menu.addMenu(preset.name)
                preset_menu.menuAction().setCheckable(True)
                preset_menu.menuAction().setChecked(
                    preset.id == self._active_abbreviation_table_id
                )
                language_menu = preset_menu.addMenu("Language")
                translated_languages = preset.translated_languages()
                if not translated_languages:
                    action = QAction("No translated entries", language_menu)
                    action.setEnabled(False)
                    language_menu.addAction(action)
                for language in translated_languages:
                    action = language_menu.addAction(
                        language,
                        lambda _checked=False, preset=preset, language=language: (
                            self._select_abbreviation_table_language(preset, language)
                        ),
                    )
                    action.setCheckable(True)
                    action.setChecked(
                        preset.id == self._active_abbreviation_table_id
                        and language == preset.active_language
                    )
                preset_menu.addSeparator()
                preset_menu.addAction(
                    "Set Active",
                    lambda _checked=False, preset=preset: self._set_active_abbreviation_table(
                        preset
                    ),
                )
                preset_menu.addAction(
                    "Edit",
                    lambda _checked=False, preset=preset: self._edit_abbreviation_table(
                        preset
                    ),
                )
                preset_menu.addAction(
                    "Duplicate",
                    lambda _checked=False, preset=preset: self._duplicate_abbreviation_table(
                        preset
                    ),
                )
                preset_menu.addAction(
                    "Export",
                    lambda _checked=False, preset=preset: self._export_abbreviation_table(
                        preset
                    ),
                )
                preset_menu.addAction(
                    "Delete",
                    lambda _checked=False, preset=preset: self._delete_abbreviation_table(
                        preset
                    ),
                )
        else:
            action = QAction("No abbreviation tables saved", self.abbreviation_table_menu)
            action.setEnabled(False)
            self.abbreviation_table_menu.addAction(action)
        self.abbreviation_table_menu.addSeparator()
        self.abbreviation_table_menu.addAction(
            "Add Abbreviation Table", self._add_abbreviation_table
        )
        self.abbreviation_table_menu.addAction("Import Table", self._import_abbreviation_table)

    def _add_abbreviation_table(self) -> None:
        preset = self._abbreviation_table_dialog()
        if preset is None:
            return
        self._abbreviation_presets[preset.id] = preset
        self._active_abbreviation_table_id = preset.id
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _edit_abbreviation_table(self, preset: AbbreviationTablePreset) -> None:
        updated = self._abbreviation_table_dialog(preset)
        if updated is None:
            return
        self._abbreviation_presets[preset.id] = updated
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _abbreviation_table_dialog(
        self, preset: AbbreviationTablePreset | None = None
    ) -> AbbreviationTablePreset | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(
            "Edit Abbreviation Table" if preset is not None else "Add Abbreviation Table"
        )
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "abbreviation_table", QSize(760, 520))
        layout = QVBoxLayout(dialog)
        name = QLineEdit(preset.name if preset is not None else "Abbreviation Table")
        language = QComboBox()
        language.setEditable(True)
        languages = list(dict.fromkeys(COMMON_ABBREVIATION_LANGUAGES + (
            preset.languages() if preset is not None else []
        )))
        language.addItems(languages)
        if preset is not None:
            language.setCurrentText(preset.active_language)
        form = QFormLayout()
        form.addRow("Table Name", name)
        form.addRow("Language", language)
        layout.addLayout(form)
        table = QTableWidget(0, 2)
        table.setHorizontalHeaderLabels(["Abbreviation", "Complete word"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(table)

        def populate(current_language: str) -> None:
            table.blockSignals(True)
            table.setRowCount(0)
            entries = preset.entries if preset is not None else [AbbreviationEntry("MX", {})]
            for entry in entries:
                row = table.rowCount()
                table.insertRow(row)
                table.setItem(row, 0, QTableWidgetItem(entry.abbreviation))
                table.setItem(row, 1, QTableWidgetItem(entry.text_for_language(current_language)))
            table.blockSignals(False)

        populate(language.currentText())
        row_controls = QHBoxLayout()
        add_row = QPushButton("+")
        remove_row = QPushButton("-")
        row_controls.addWidget(add_row)
        row_controls.addWidget(remove_row)
        row_controls.addStretch(1)
        layout.addLayout(row_controls)
        add_row.clicked.connect(lambda: self._insert_abbreviation_table_row(table))
        remove_row.clicked.connect(lambda: self._remove_dialog_abbreviation_row(table))
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        selected_language = language.currentText().strip() or "English"
        existing = {
            entry.abbreviation: entry
            for entry in (preset.entries if preset is not None else [])
        }
        entries: list[AbbreviationEntry] = []
        for row in range(table.rowCount()):
            abbreviation = self._table_text(table, row, 0)
            complete_word = self._table_text(table, row, 1)
            if not abbreviation:
                continue
            entry = existing.get(abbreviation, AbbreviationEntry(abbreviation, {}))
            entry.translations[selected_language] = complete_word
            entries.append(entry)
        return AbbreviationTablePreset(
            id=preset.id if preset is not None else str(uuid4()),
            name=name.text().strip() or "Abbreviation Table",
            active_language=selected_language,
            entries=entries,
        )

    def _insert_abbreviation_table_row(self, table: QTableWidget) -> None:
        row = table.rowCount()
        table.insertRow(row)
        table.setItem(row, 0, QTableWidgetItem(""))
        table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_dialog_abbreviation_row(self, table: QTableWidget) -> None:
        row = table.currentRow()
        if row >= 0:
            table.removeRow(row)

    def _set_active_abbreviation_table(self, preset: AbbreviationTablePreset) -> None:
        self._active_abbreviation_table_id = preset.id
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _select_abbreviation_table_language(
        self, preset: AbbreviationTablePreset, language: str
    ) -> None:
        preset.active_language = language
        self._active_abbreviation_table_id = preset.id
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _duplicate_abbreviation_table(self, preset: AbbreviationTablePreset) -> None:
        duplicate = AbbreviationTablePreset.from_dict(preset.to_dict())
        duplicate.id = str(uuid4())
        duplicate.name = f"{preset.name} copy"
        self._abbreviation_presets[duplicate.id] = duplicate
        self._save_persistent_abbreviation_tables()
        self._rebuild_abbreviation_table_menu()

    def _delete_abbreviation_table(self, preset: AbbreviationTablePreset) -> None:
        self._abbreviation_presets.pop(preset.id, None)
        if self._active_abbreviation_table_id == preset.id:
            self._active_abbreviation_table_id = None
        self._save_persistent_abbreviation_tables()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _export_abbreviation_table(self, preset: AbbreviationTablePreset) -> None:
        filename = remembered_save_file(
            self,
            "Export Abbreviation Table",
            "abbreviation_table_export",
            "JSON (*.json)",
            f"{preset.name}.biopic-abbreviations.json",
        )
        if not filename:
            return
        Path(filename).write_text(json.dumps(preset.to_dict(), indent=2), encoding="utf-8")

    def _import_abbreviation_table(self) -> None:
        filename = remembered_open_file(
            self,
            "Import Abbreviation Table",
            "abbreviation_table_import",
            "JSON (*.json)",
        )
        if not filename:
            return
        data = json.loads(Path(filename).read_text(encoding="utf-8"))
        preset = AbbreviationTablePreset.from_dict(data)
        self._abbreviation_presets[preset.id] = preset
        self._active_abbreviation_table_id = preset.id
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()

    def _apply_active_abbreviation_table(self) -> None:
        preset = self._active_abbreviation_table()
        if preset is None:
            return
        active_entries: dict[str, tuple[str, str]] = {}
        for entry in preset.entries:
            abbreviation = entry.abbreviation.strip()
            full_definition = entry.text_for_language(preset.active_language).strip()
            if abbreviation and full_definition:
                active_entries[abbreviation.casefold()] = (abbreviation, full_definition)
        canonical_ids: dict[str, str] = {}
        duplicate_ids: dict[str, list[str]] = {}
        for definition in self.project.annotation_definitions.values():
            key = definition.abbreviation.casefold()
            if key not in active_entries:
                continue
            if key not in canonical_ids:
                canonical_ids[key] = definition.id
                definition.abbreviation = active_entries[key][0]
                definition.full_definition = active_entries[key][1]
                definition.include_in_legend = True
            else:
                duplicate_ids.setdefault(key, []).append(definition.id)
        for key, (abbreviation, full_definition) in active_entries.items():
            if key in canonical_ids:
                continue
            definition = AnnotationDefinition(
                abbreviation=abbreviation,
                full_definition=full_definition,
            )
            self.project.annotation_definitions[definition.id] = definition
            canonical_ids[key] = definition.id
        duplicate_to_canonical = {
            duplicate_id: canonical_ids[key]
            for key, duplicates in duplicate_ids.items()
            for duplicate_id in duplicates
        }
        for annotation in self.project.annotations.values():
            if annotation.definition_id in duplicate_to_canonical:
                annotation.definition_id = duplicate_to_canonical[annotation.definition_id]
        for duplicate_id in duplicate_to_canonical:
            self.project.annotation_definitions.pop(duplicate_id, None)
        self.project.touch()
        self._records_signature = None
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _active_abbreviation_table(self) -> AbbreviationTablePreset | None:
        if self._active_abbreviation_table_id is None:
            return None
        return self._abbreviation_presets.get(self._active_abbreviation_table_id)

    def _refresh_abbreviation_table_view(self) -> None:
        preset = self._active_abbreviation_table()
        self.abbreviation_table.blockSignals(True)
        self.abbreviation_table.setRowCount(0)
        if preset is not None:
            self.abbreviation_language_combo.blockSignals(True)
            self.abbreviation_language_combo.clear()
            self.abbreviation_language_combo.addItems(
                list(dict.fromkeys(COMMON_ABBREVIATION_LANGUAGES + preset.languages()))
            )
            self.abbreviation_language_combo.setCurrentText(preset.active_language)
            self.abbreviation_language_combo.blockSignals(False)
            for entry in preset.entries:
                row = self.abbreviation_table.rowCount()
                self.abbreviation_table.insertRow(row)
                self.abbreviation_table.setItem(row, 0, QTableWidgetItem(entry.abbreviation))
                self.abbreviation_table.setItem(
                    row,
                    1,
                    QTableWidgetItem(entry.text_for_language(preset.active_language)),
                )
        self.abbreviation_table.blockSignals(False)

    def _add_abbreviation_row(self) -> None:
        self._insert_abbreviation_table_row(self.abbreviation_table)

    def _remove_abbreviation_row(self) -> None:
        row = self.abbreviation_table.currentRow()
        if row >= 0:
            self.abbreviation_table.removeRow(row)
            self._sync_visible_abbreviation_table()

    def _abbreviation_language_changed(self, language: str) -> None:
        preset = self._active_abbreviation_table()
        if preset is None:
            return
        preset.active_language = language.strip() or "English"
        self._save_persistent_abbreviation_tables()
        self._apply_active_abbreviation_table()
        self._refresh_abbreviation_table_view()

    def _abbreviation_table_cell_changed(self, _row: int, _column: int) -> None:
        self._sync_visible_abbreviation_table()

    def _sync_visible_abbreviation_table(self) -> None:
        preset = self._active_abbreviation_table()
        if preset is None:
            return
        language = self.abbreviation_language_combo.currentText().strip() or "English"
        entries: list[AbbreviationEntry] = []
        for row in range(self.abbreviation_table.rowCount()):
            abbreviation = self._table_text(self.abbreviation_table, row, 0)
            complete_word = self._table_text(self.abbreviation_table, row, 1)
            if not abbreviation:
                continue
            existing = next(
                (entry for entry in preset.entries if entry.abbreviation == abbreviation),
                AbbreviationEntry(abbreviation, {}),
            )
            existing.translations[language] = complete_word
            entries.append(existing)
        preset.entries = entries
        preset.active_language = language
        self._save_persistent_abbreviation_tables()

    def _table_text(self, table: QTableWidget, row: int, column: int) -> str:
        item = table.item(row, column)
        return "" if item is None else item.text().strip()
