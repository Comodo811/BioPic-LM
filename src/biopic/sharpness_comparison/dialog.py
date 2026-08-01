"""Sharpness comparison settings dialog."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QHeaderView,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from biopic.sharpness_comparison.config_models import SharpnessComparisonConfig
from biopic.sharpness_comparison.presets import config_for_preset, preset_names


class SharpnessComparisonDialog(QDialog):
    """Modal settings dialog for sharpness comparison."""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Sharpness Comparison Settings")
        self._config = config_for_preset("Standard microscopy comparison")
        self._loading = False
        layout = QVBoxLayout(self)
        self.preset_combo = QComboBox()
        self.preset_combo.addItems(preset_names())
        self.preset_combo.setCurrentText(self._config.preset_name)
        layout.addWidget(self.preset_combo)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Enabled", "Method", "Metric or parameter", "Value", "Unit", "Description"]
        )
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.table)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Run")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.preset_combo.currentTextChanged.connect(self._preset_changed)
        self._populate_table()

    def config(self) -> SharpnessComparisonConfig:
        """Return current config."""
        return self._config

    def _preset_changed(self, name: str) -> None:
        if self._loading:
            return
        self._config = config_for_preset(name)
        self._populate_table()

    def _mark_custom(self) -> None:
        if self._loading:
            return
        self._config.preset_name = "Custom"
        self._loading = True
        self.preset_combo.setCurrentText("Custom")
        self._loading = False

    def _populate_table(self) -> None:
        self._loading = True
        self.table.setRowCount(0)
        self._add_general_rows()
        for method in self._config.methods:
            self._add_method_enabled_row(method)
            self._add_method_weight_row(method)
            for key, value in method.parameters.items():
                self._add_method_parameter_row(method, key, value)
        self._loading = False

    def _add_general_rows(self) -> None:
        rows = [
            ("General", "Analysis region", self._config.analysis_region, "-", "Region used for scoring"),
            ("General", "Intensity normalization", self._config.normalization, "-", "Normalizes comparison scores"),
            ("General", "Noise reduction", self._config.noise_reduction, "-", "Optional preprocessing before scoring"),
        ]
        for method, parameter, value, unit, description in rows:
            row = self.table.rowCount()
            self.table.insertRow(row)
            item = QTableWidgetItem("Yes")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.table.setItem(row, 0, item)
            self.table.setItem(row, 1, QTableWidgetItem(method))
            self.table.setItem(row, 2, QTableWidgetItem(parameter))
            self.table.setItem(row, 3, QTableWidgetItem(value))
            self.table.setItem(row, 4, QTableWidgetItem(unit))
            self.table.setItem(row, 5, QTableWidgetItem(description))

    def _add_method_enabled_row(self, method) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        enabled = QCheckBox()
        enabled.setChecked(method.enabled)
        enabled.stateChanged.connect(
            lambda state, current=method: self._enabled_changed(current, state)
        )
        self.table.setCellWidget(row, 0, enabled)
        self.table.setItem(row, 1, QTableWidgetItem(method.display_name))
        self.table.setItem(row, 2, QTableWidgetItem("Enabled"))
        self.table.setItem(row, 3, QTableWidgetItem("Yes" if method.enabled else "No"))
        self.table.setItem(row, 4, QTableWidgetItem("-"))
        self.table.setItem(row, 5, QTableWidgetItem("Generate and evaluate this stack result."))

    def _add_method_weight_row(self, method) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(method.display_name))
        self.table.setItem(row, 2, QTableWidgetItem("Combined-score metric weight"))
        weight = QDoubleSpinBox()
        weight.setRange(0.0, 10.0)
        weight.setDecimals(2)
        weight.setSingleStep(0.25)
        weight.setValue(method.evaluation_weight)
        weight.valueChanged.connect(
            lambda value, current=method: self._weight_changed(current, value)
        )
        self.table.setCellWidget(row, 3, weight)
        self.table.setItem(row, 4, QTableWidgetItem("relative"))
        self.table.setItem(row, 5, QTableWidgetItem("Weight used when this metric is scored."))

    def _add_method_parameter_row(self, method, key: str, value: object) -> None:
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(""))
        self.table.setItem(row, 1, QTableWidgetItem(method.display_name))
        self.table.setItem(row, 2, QTableWidgetItem(key.replace("_", " ").title()))
        if isinstance(value, int):
            spin = QSpinBox()
            spin.setRange(0, 99)
            spin.setValue(value)
            spin.valueChanged.connect(
                lambda next_value, current=method, parameter=key: self._parameter_changed(
                    current, parameter, next_value
                )
            )
            self.table.setCellWidget(row, 3, spin)
        elif isinstance(value, float):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 99.0)
            spin.setDecimals(2)
            spin.setSingleStep(0.25)
            spin.setValue(value)
            spin.valueChanged.connect(
                lambda next_value, current=method, parameter=key: self._parameter_changed(
                    current, parameter, next_value
                )
            )
            self.table.setCellWidget(row, 3, spin)
        else:
            self.table.setItem(row, 3, QTableWidgetItem(str(value)))
        unit = "px" if key in {"kernel_size", "window_size", "offset"} else "-"
        self.table.setItem(row, 4, QTableWidgetItem(unit))
        self.table.setItem(row, 5, QTableWidgetItem(_parameter_description(key)))

    def _enabled_changed(self, method, state: int) -> None:
        method.enabled = state == Qt.CheckState.Checked.value
        self._mark_custom()

    def _weight_changed(self, method, value: float) -> None:
        method.evaluation_weight = float(value)
        self._mark_custom()

    def _parameter_changed(self, method, key: str, value: int | float) -> None:
        method.parameters[key] = value
        self._mark_custom()


def _parameter_description(key: str) -> str:
    descriptions = {
        "kernel_size": "Neighborhood size for the focus filter.",
        "gradient_threshold": "Ignores weak gradient responses.",
        "offset": "Pixel spacing used by the Brenner difference metric.",
        "window_size": "Local texture window size.",
        "wavelet": "Wavelet family used for high-frequency energy.",
        "levels": "Wavelet decomposition depth.",
    }
    return descriptions.get(key, "Method-specific comparison parameter.")
