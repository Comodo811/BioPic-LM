"""Raster filter result dialogs for the edit workspace."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from scipy.interpolate import PchipInterpolator
from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QThread, QTimer
from PySide6.QtGui import QColor, QMouseEvent, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QRadioButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.corrections import (
    WHITE_BALANCE_PRESETS,
    estimate_white_balance_from_region,
    estimate_white_balance_temperature_correlation,
)
from biopic.imaging.editing import apply_edit_operation
from biopic.imaging.io import SUPPORTED_EXTENSIONS, read_image_asset
from biopic.ui.settings import remembered_open_file, set_settings_json, settings_json
from biopic.workers.edit_operation_worker import EditOperationWorker

def _image_file_filter() -> str:
    extensions = sorted(f"*{extension}" for extension in SUPPORTED_EXTENSIONS)
    return f"Images ({' '.join(extensions)});;All Files (*)"



class EditFilterResultDialogsMixin:
    """Dialogs that create raster filter-result layers."""

    def open_flat_field_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Ask for a reference/background image and apply classic flat-field correction."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        reference_path = (
            Path(str(initial_parameters["flat_path"]))
            if initial_parameters.get("flat_path")
            else self._classic_flat_field_reference_path()
        )
        if reference_path is None:
            return
        parameters = {"flat_path": str(reference_path)}
        if layer_id is not None:
            try:
                self._update_filter_layer_parameters(layer_id, parameters)
            except Exception as exc:
                self._status(f"Flat-field correction failed: {exc}")
            return
        try:
            result = self._run_computation_with_progress(
                "Applying flat-field correction...",
                lambda progress: self._classic_flat_field_with_progress(
                    reference_path,
                    progress,
                ),
                accepts_progress=True,
            )
        except Exception as exc:
            self._status(f"Flat-field correction failed: {exc}")
            return
        if not isinstance(result, np.ndarray):
            self._status("Flat-field correction failed.")
            return
        self._commit_filter_result_layer(
            result,
            "flat_field",
            parameters,
        )

    def _classic_flat_field_with_progress(self, reference_path: Path, progress: object) -> np.ndarray:
        if self._current_pixels is None:
            raise ValueError("No image is loaded")
        if callable(progress):
            progress("Loading flat-field background image", 0.08)
        reference = read_image_asset(reference_path, load_pixels=True).pixels
        if callable(progress):
            progress("Applying classic flat-field correction", 0.40)
        result = apply_edit_operation(
            self._filter_operation_source_pixels(),
            "flat_field",
            {"flat": reference},
        )
        if callable(progress):
            progress("Flat-field correction complete", 1.0)
        return result

    def _classic_flat_field_reference_path(self) -> Path | None:
        filters = _image_file_filter()
        filename = remembered_open_file(
            self,
            "Select Flat-Field Background Image",
            "flat_field_reference",
            filters,
        )
        return Path(filename) if filename else None


    def open_high_pass_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a GIMP-style high-pass sharpening options dialog."""
        if self._current_pixels is None:
            return
        index = self.operation_combo.findData("high_pass")
        if index >= 0:
            self.operation_combo.setCurrentIndex(index)
        dialog = QDialog(self)
        dialog.setWindowTitle("High-Pass Filter")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        defaults = settings_json("edit/high_pass_defaults", {})
        initial_parameters = dict(initial_parameters or {})
        radius_spin = QDoubleSpinBox(dialog)
        radius_spin.setRange(0.1, 30.0)
        radius_spin.setSingleStep(0.1)
        radius_spin.setSuffix(" px")
        radius_spin.setValue(
            float(
                initial_parameters.get(
                    "sigma",
                    defaults.get("radius", self.high_pass_radius_spin.value()),
                )
            )
        )
        amount_spin = QDoubleSpinBox(dialog)
        amount_spin.setRange(0.0, 5.0)
        amount_spin.setSingleStep(0.1)
        amount_spin.setValue(
            float(
                initial_parameters.get(
                    "amount",
                    defaults.get("amount", self.high_pass_amount_spin.value()),
                )
            )
        )
        form.addRow("Radius", radius_spin)
        form.addRow("Contrast", amount_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.high_pass_radius_spin.setValue(radius_spin.value())
        self.high_pass_amount_spin.setValue(amount_spin.value())
        set_settings_json(
            "edit/high_pass_defaults",
            {
                "radius": radius_spin.value(),
                "amount": amount_spin.value(),
            },
        )
        parameters = {
            "sigma": radius_spin.value(),
            "amount": amount_spin.value(),
        }
        if layer_id is not None:
            try:
                self._update_filter_layer_parameters(layer_id, parameters)
            except Exception as exc:
                self._status(f"High-pass filter update failed: {exc}")
        else:
            self.apply_named_operation("high_pass", parameters)

    def open_noise_reduction_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open GIMP-style noise-reduction options."""
        if self._current_pixels is None:
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Noise Reduction")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        defaults = settings_json("edit/noise_reduction_defaults", {})
        initial_parameters = dict(initial_parameters or {})
        strength_spin = QSpinBox(dialog)
        strength_spin.setRange(0, 8)
        strength_spin.setSingleStep(1)
        strength_spin.setValue(int(initial_parameters.get("strength", defaults.get("strength", 4))))
        form.addRow("Strength", strength_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        set_settings_json(
            "edit/noise_reduction_defaults",
            {"strength": strength_spin.value()},
        )
        parameters = {"method": "gimp", "strength": strength_spin.value()}
        if layer_id is not None:
            self._update_filter_layer_parameters(layer_id, parameters)
        else:
            self.apply_named_operation("denoise", parameters)

    def open_filter_layer_dialog(self, layer_id: str) -> None:
        """Open an editor for an existing raster filter layer."""
        layer = self.project.edit_layers.get(layer_id)
        if layer is None or layer.filter_operation is None:
            return
        parameters = dict(layer.filter_parameters)
        if layer.filter_operation == "high_pass":
            self.open_high_pass_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.filter_operation == "denoise":
            self.open_noise_reduction_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.filter_operation == "flat_field":
            self.open_flat_field_dialog(layer_id=layer.id, initial_parameters=parameters)
        else:
            self._open_generic_filter_layer_dialog(layer.id, layer.filter_operation, parameters)

    def _open_generic_filter_layer_dialog(
        self,
        layer_id: str,
        operation: str,
        initial_parameters: dict[str, object],
    ) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Edit {operation.replace('_', ' ').title()}")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        editors: dict[str, object] = {}
        for key, value in initial_parameters.items():
            if isinstance(value, bool):
                editor = QCheckBox(dialog)
                editor.setChecked(value)
            elif isinstance(value, int) and not isinstance(value, bool):
                editor = QSpinBox(dialog)
                editor.setRange(-10000, 10000)
                editor.setValue(value)
            elif isinstance(value, float):
                editor = QDoubleSpinBox(dialog)
                editor.setRange(-10000.0, 10000.0)
                editor.setDecimals(4)
                editor.setSingleStep(0.1)
                editor.setValue(value)
            elif isinstance(value, str):
                editor = QLineEdit(value, dialog)
            else:
                continue
            editors[key] = editor
            form.addRow(key.replace("_", " ").title(), editor)
        if not editors:
            self._status(f"{operation.replace('_', ' ').title()} has no editable parameters.")
            return
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        parameters = dict(initial_parameters)
        for key, editor in editors.items():
            if isinstance(editor, QCheckBox):
                parameters[key] = editor.isChecked()
            elif isinstance(editor, QSpinBox):
                parameters[key] = editor.value()
            elif isinstance(editor, QDoubleSpinBox):
                parameters[key] = editor.value()
            elif isinstance(editor, QLineEdit):
                parameters[key] = editor.text()
        self._update_filter_layer_parameters(layer_id, parameters)

