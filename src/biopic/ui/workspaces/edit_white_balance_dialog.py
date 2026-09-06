"""White-balance dialog for the edit workspace."""

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


class EditWhiteBalanceDialogMixin:
    """RawTherapee-style white-balance adjustment dialog."""

    def open_white_balance_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a RawTherapee-style rendered-image white-balance dialog."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        dialog = QDialog(self)
        dialog.setWindowTitle("White Balance")
        dialog.setMinimumWidth(420)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        mode_combo = QComboBox(dialog)
        for label, value in [
            ("Camera / As Shot", "camera"),
            ("RAW Daylight Metadata", "raw_daylight"),
            ("Automatic - Temperature Correlation", "auto_temperature"),
            ("Automatic - RGB Grey", "auto"),
            ("Spot From Current Selection", "spot"),
            ("Custom Temperature + Tint", "temperature"),
            ("Light Source Preset", "preset"),
            ("Manual RGB Multipliers", "manual"),
        ]:
            mode_combo.addItem(label, value)
        preset_combo = QComboBox(dialog)
        for key in WHITE_BALANCE_PRESETS:
            preset_combo.addItem(key.replace("_", " ").title(), key)
        temperature_spin = QDoubleSpinBox(dialog)
        temperature_spin.setRange(1500.0, 15000.0)
        temperature_spin.setSingleStep(100.0)
        temperature_spin.setValue(6500.0)
        temperature_spin.setSuffix(" K")
        tint_spin = QDoubleSpinBox(dialog)
        tint_spin.setRange(0.25, 4.0)
        tint_spin.setSingleStep(0.05)
        tint_spin.setValue(1.0)
        blue_red_spin = QDoubleSpinBox(dialog)
        blue_red_spin.setRange(0.25, 4.0)
        blue_red_spin.setDecimals(3)
        blue_red_spin.setSingleStep(0.05)
        blue_red_spin.setValue(1.0)
        awb_bias_spin = QDoubleSpinBox(dialog)
        awb_bias_spin.setRange(-3000.0, 3000.0)
        awb_bias_spin.setSingleStep(50.0)
        awb_bias_spin.setValue(0.0)
        awb_bias_spin.setSuffix(" K")
        matrix_strength_spin = QDoubleSpinBox(dialog)
        matrix_strength_spin.setRange(0.0, 1.0)
        matrix_strength_spin.setDecimals(3)
        matrix_strength_spin.setSingleStep(0.05)
        matrix_strength_spin.setValue(0.0)
        red_spin = QDoubleSpinBox(dialog)
        green_spin = QDoubleSpinBox(dialog)
        blue_spin = QDoubleSpinBox(dialog)
        for spin in (red_spin, green_spin, blue_spin):
            spin.setRange(0.05, 8.0)
            spin.setDecimals(4)
            spin.setSingleStep(0.05)
            spin.setValue(1.0)
        sample_spin = QSpinBox(dialog)
        sample_spin.setRange(3, 128)
        sample_spin.setValue(24)
        histogram_low_spin = QDoubleSpinBox(dialog)
        histogram_low_spin.setRange(0.0, 25.0)
        histogram_low_spin.setSingleStep(0.1)
        histogram_low_spin.setValue(0.2)
        histogram_low_spin.setSuffix(" %")
        histogram_high_spin = QDoubleSpinBox(dialog)
        histogram_high_spin.setRange(0.0, 25.0)
        histogram_high_spin.setSingleStep(0.1)
        histogram_high_spin.setValue(0.2)
        histogram_high_spin.setSuffix(" %")
        histogram_bins_spin = QSpinBox(dialog)
        histogram_bins_spin.setRange(12, 96)
        histogram_bins_spin.setValue(32)
        mode_index = mode_combo.findData(str(initial_parameters.get("method", "auto_temperature")))
        if mode_index >= 0:
            mode_combo.setCurrentIndex(mode_index)
        preset_index = preset_combo.findData(str(initial_parameters.get("preset", "daylight")))
        if preset_index >= 0:
            preset_combo.setCurrentIndex(preset_index)
        temperature_spin.setValue(float(initial_parameters.get("temperature", 6500.0)))
        tint_spin.setValue(float(initial_parameters.get("tint", 1.0)))
        blue_red_spin.setValue(float(initial_parameters.get("blue_red_equalizer", 1.0)))
        awb_bias_spin.setValue(float(initial_parameters.get("awb_temperature_bias", 0.0)))
        matrix_strength_spin.setValue(float(initial_parameters.get("camera_matrix_strength", 0.0)))
        red_spin.setValue(float(initial_parameters.get("red", 1.0)))
        green_spin.setValue(float(initial_parameters.get("green", 1.0)))
        blue_spin.setValue(float(initial_parameters.get("blue", 1.0)))
        sample_spin.setValue(int(initial_parameters.get("sample_size", 24)))
        histogram_low_spin.setValue(float(initial_parameters.get("histogram_low_clip", 0.2)))
        histogram_high_spin.setValue(float(initial_parameters.get("histogram_high_clip", 0.2)))
        histogram_bins_spin.setValue(int(initial_parameters.get("histogram_bins", 32)))
        diagnostics = QLabel(
            "Automatic Temperature Correlation uses chromaticity histogram sampling.",
            dialog,
        )
        diagnostics.setWordWrap(True)
        estimate_button = QPushButton("Estimate From Current Selection", dialog)
        temperature_estimate_button = QPushButton("Estimate Auto Temperature", dialog)
        pipette_button = QPushButton("Pick Spot With Pipette", dialog)
        form.addRow("Mode", mode_combo)
        form.addRow("Preset", preset_combo)
        form.addRow("Temperature", temperature_spin)
        form.addRow("Tint", tint_spin)
        form.addRow("Blue/Red Equalizer", blue_red_spin)
        form.addRow("AWB Temperature Bias", awb_bias_spin)
        form.addRow("Camera Matrix Strength", matrix_strength_spin)
        form.addRow("Red Gain", red_spin)
        form.addRow("Green Gain", green_spin)
        form.addRow("Blue Gain", blue_spin)
        form.addRow("Sample Size", sample_spin)
        form.addRow("Histogram Black Clip", histogram_low_spin)
        form.addRow("Histogram White Clip", histogram_high_spin)
        form.addRow("Histogram Bins", histogram_bins_spin)
        layout.addLayout(form)
        pick_buttons = QHBoxLayout()
        pick_buttons.addWidget(estimate_button)
        pick_buttons.addWidget(temperature_estimate_button)
        pick_buttons.addWidget(pipette_button)
        layout.addLayout(pick_buttons)
        layout.addWidget(diagnostics)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset,
            dialog,
        )
        layout.addWidget(buttons)

        def estimate_from_selection() -> None:
            rect = self._selection_rect
            try:
                estimate = estimate_white_balance_from_region(
                    self._current_pixels,
                    rect,
                    sample_size=sample_spin.value(),
                    reject_unsuitable=True,
                )
            except ValueError as exc:
                diagnostics.setText(str(exc))
                return
            red_spin.setValue(estimate.red)
            green_spin.setValue(estimate.green)
            blue_spin.setValue(estimate.blue)
            mode_combo.setCurrentIndex(mode_combo.findData("manual"))
            warning = f"; warning: {estimate.warning}" if estimate.warning else ""
            diagnostics.setText(
                "Gains R/G/B: "
                f"{estimate.red:.4f}, {estimate.green:.4f}, {estimate.blue:.4f}; "
                f"usable pixels: {estimate.sample_count} "
                f"({estimate.valid_fraction:.0%}){warning}"
            )

        def estimate_auto_temperature() -> None:
            try:
                estimate = estimate_white_balance_temperature_correlation(
                    self._current_pixels,
                    temperature_bias=awb_bias_spin.value(),
                    histogram_low_clip=histogram_low_spin.value(),
                    histogram_high_clip=histogram_high_spin.value(),
                    histogram_bins=histogram_bins_spin.value(),
                )
            except ValueError as exc:
                diagnostics.setText(str(exc))
                return
            red_spin.setValue(estimate.red)
            green_spin.setValue(estimate.green)
            blue_spin.setValue(estimate.blue)
            if estimate.temperature is not None:
                temperature_spin.setValue(estimate.temperature)
            if estimate.tint is not None:
                tint_spin.setValue(estimate.tint)
            mode_combo.setCurrentIndex(mode_combo.findData("temperature"))
            warning = f"; warning: {estimate.warning}" if estimate.warning else ""
            correlation = (
                f"; correlation error: {estimate.correlation:.4f}"
                if estimate.correlation is not None
                else ""
            )
            diagnostics.setText(
                "Auto temperature: "
                f"{temperature_spin.value():.0f} K, tint {tint_spin.value():.3f}; "
                f"usable pixels: {estimate.sample_count} "
                f"({estimate.valid_fraction:.0%}); "
                f"histogram bins: {estimate.histogram_bins}{correlation}{warning}"
            )

        def reset_values() -> None:
            mode_combo.setCurrentIndex(mode_combo.findData("auto_temperature"))
            preset_combo.setCurrentIndex(preset_combo.findData("daylight"))
            temperature_spin.setValue(6500.0)
            tint_spin.setValue(1.0)
            blue_red_spin.setValue(1.0)
            awb_bias_spin.setValue(0.0)
            matrix_strength_spin.setValue(0.0)
            red_spin.setValue(1.0)
            green_spin.setValue(1.0)
            blue_spin.setValue(1.0)
            histogram_low_spin.setValue(0.2)
            histogram_high_spin.setValue(0.2)
            histogram_bins_spin.setValue(32)
            diagnostics.setText("Reset to neutral white balance.")

        estimate_button.clicked.connect(estimate_from_selection)
        temperature_estimate_button.clicked.connect(estimate_auto_temperature)
        pipette_button.clicked.connect(
            lambda _checked=False: (
                self._start_white_balance_spot_pick(sample_spin.value()),
                dialog.reject(),
            )
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(reset_values)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        method = str(mode_combo.currentData())
        sample_rect = self._selection_rect if method == "spot" else None
        raw_metadata = self._white_balance_raw_metadata()
        parameters: dict[str, object] = {
            "method": method,
            "red": red_spin.value(),
            "green": green_spin.value(),
            "blue": blue_spin.value(),
            "temperature": temperature_spin.value(),
            "tint": tint_spin.value(),
            "preset": str(preset_combo.currentData()),
            "blue_red_equalizer": blue_red_spin.value(),
            "awb_temperature_bias": awb_bias_spin.value(),
            "histogram_low_clip": histogram_low_spin.value(),
            "histogram_high_clip": histogram_high_spin.value(),
            "histogram_bins": histogram_bins_spin.value(),
            "camera_matrix_strength": matrix_strength_spin.value(),
            "normalize": True,
            "sample_size": sample_spin.value(),
        }
        if raw_metadata:
            parameters["raw_metadata"] = raw_metadata
        if sample_rect is not None:
            parameters["sample_rect"] = sample_rect
        if layer_id is not None:
            self._update_adjustment_layer_parameters(layer_id, parameters)
        else:
            self.apply_named_operation("white_balance", parameters)

