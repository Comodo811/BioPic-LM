"""Levels, curves, and gamma dialogs for the edit workspace."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSlider,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.editing import apply_edit_operation
from biopic.ui.settings import set_settings_json, settings_json
from biopic.ui.workspaces.edit_tonal_widgets import (
    _CurveEditorWidget,
    _LevelsHistogramWidget,
    _LevelsInputWidget,
    _evaluate_curve,
    _levels_auto_input_bounds,
    _levels_channel_values,
    _sanitize_curve_points,
)


class EditTonalDialogsMixin:
    """Tonal adjustment dialogs."""

    def open_curves_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a GIMP-style Curves / Gradationskurve dialog."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        original = (
            self._adjustment_preview_base(exclude_layer_id=layer_id)
            if layer_id is not None
            else self._current_pixels
        )
        if original is None:
            original = self._current_pixels.copy()
        dialog = QDialog(self)
        dialog.setWindowTitle("Curves / Gradationskurve")
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        channel_combo = QComboBox(dialog)
        for label, value in [
            ("Value", "rgb"),
            ("Red", "red"),
            ("Green", "green"),
            ("Blue", "blue"),
        ]:
            channel_combo.addItem(label, value)
        if self._current_pixels.ndim == 3 and self._current_pixels.shape[-1] >= 4:
            channel_combo.addItem("Alpha", "alpha")
        curve_type_combo = QComboBox(dialog)
        curve_type_combo.addItem("Smooth", "smooth")
        curve_type_combo.addItem("Free / Linear", "free")
        logarithmic_check = QCheckBox("Logarithmic histogram", dialog)
        curve_editor = _CurveEditorWidget(dialog)
        channel_index = channel_combo.findData(str(initial_parameters.get("channel", "rgb")))
        if channel_index >= 0:
            channel_combo.setCurrentIndex(channel_index)
        curve_type_index = curve_type_combo.findData(
            str(initial_parameters.get("curve_type", "smooth"))
        )
        if curve_type_index >= 0:
            curve_type_combo.setCurrentIndex(curve_type_index)
        points = initial_parameters.get("points")
        if isinstance(points, list):
            curve_editor.set_points(points)
        curve_editor.set_curve_type(str(curve_type_combo.currentData()))
        curve_editor.set_pixels(original, str(channel_combo.currentData()))
        input_spin = QSpinBox(dialog)
        output_spin = QSpinBox(dialog)
        for spin in (input_spin, output_spin):
            spin.setRange(0, 255)
            spin.setFixedWidth(80)
        form.addRow("Channel", channel_combo)
        form.addRow("Curve Type", curve_type_combo)
        form.addRow("Selected Input", input_spin)
        form.addRow("Selected Output", output_spin)
        layout.addWidget(curve_editor)
        layout.addWidget(logarithmic_check)
        layout.addLayout(form)
        reset_button = QPushButton("Reset Channel", dialog)
        button_row = QHBoxLayout()
        button_row.addWidget(reset_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        layout.addWidget(buttons)
        updating = {"value": False}

        def selected_point_changed(point: tuple[float, float]) -> None:
            updating["value"] = True
            input_spin.setValue(int(round(point[0] * 255.0)))
            output_spin.setValue(int(round(point[1] * 255.0)))
            updating["value"] = False

        def numeric_point_changed() -> None:
            if updating["value"]:
                return
            curve_editor.set_selected_point(input_spin.value() / 255.0, output_spin.value() / 255.0)

        def refresh_curve_histogram() -> None:
            curve_editor.set_logarithmic(logarithmic_check.isChecked())
            curve_editor.set_pixels(original, str(channel_combo.currentData()))

        curve_editor.on_selected_point_changed = selected_point_changed
        input_spin.valueChanged.connect(lambda _value: numeric_point_changed())
        output_spin.valueChanged.connect(lambda _value: numeric_point_changed())
        channel_combo.currentIndexChanged.connect(lambda _index: refresh_curve_histogram())
        logarithmic_check.toggled.connect(lambda _checked: refresh_curve_histogram())
        curve_type_combo.currentIndexChanged.connect(
            lambda _index: curve_editor.set_curve_type(str(curve_type_combo.currentData()))
        )
        reset_button.clicked.connect(lambda _checked=False: curve_editor.reset())
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        selected_point_changed(curve_editor.selected_point())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        parameters = {
            "points": curve_editor.points(),
            "channel": str(channel_combo.currentData()),
            "curve_type": str(curve_type_combo.currentData()),
        }
        if layer_id is not None:
            self._update_adjustment_layer_parameters(layer_id, parameters)
        else:
            self.apply_named_operation("curve", parameters)

    def open_gamma_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a dedicated gamma-correction dialog."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        dialog = QDialog(self)
        dialog.setWindowTitle("Gamma Correction")
        dialog.setMinimumWidth(360)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        defaults = settings_json("edit/gamma_defaults", {})
        gamma_spin = QDoubleSpinBox(dialog)
        gamma_spin.setRange(0.05, 5.0)
        gamma_spin.setDecimals(3)
        gamma_spin.setSingleStep(0.05)
        gamma_spin.setValue(float(initial_parameters.get("gamma", defaults.get("gamma", 1.0))))
        gamma_slider = QSlider(Qt.Orientation.Horizontal, dialog)
        gamma_slider.setRange(5, 500)
        gamma_slider.setValue(int(round(gamma_spin.value() * 100.0)))

        def slider_changed(value: int) -> None:
            mapped = max(0.05, float(value) / 100.0)
            if abs(gamma_spin.value() - mapped) > 1e-6:
                gamma_spin.setValue(mapped)

        def spin_changed(value: float) -> None:
            mapped = int(round(value * 100.0))
            if gamma_slider.value() != mapped:
                gamma_slider.setValue(mapped)

        gamma_slider.valueChanged.connect(slider_changed)
        gamma_spin.valueChanged.connect(spin_changed)
        gamma_row = QWidget(dialog)
        gamma_layout = QHBoxLayout(gamma_row)
        gamma_layout.setContentsMargins(0, 0, 0, 0)
        gamma_layout.setSpacing(8)
        gamma_layout.addWidget(gamma_slider, 1)
        gamma_layout.addWidget(gamma_spin)
        form.addRow("Gamma", gamma_row)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Reset,
            dialog,
        )
        layout.addWidget(buttons)
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            lambda _checked=False: gamma_spin.setValue(1.0)
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        parameters = {"gamma": gamma_spin.value()}
        if layer_id is not None:
            self._update_adjustment_layer_parameters(layer_id, parameters)
        else:
            set_settings_json("edit/gamma_defaults", parameters)
            self.apply_named_operation("gamma", parameters)

    def open_levels_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a GIMP-style Levels / Tonwertkorrektur dialog."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        original = (
            self._adjustment_preview_base(exclude_layer_id=layer_id)
            if layer_id is not None
            else self._adjustment_preview_base("levels")
        )
        if original is None:
            original = self._current_pixels.copy()
        dialog = QDialog(self)
        dialog.setWindowTitle("Levels / Tonwertkorrektur")
        dialog.setMinimumWidth(540)
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        channel_combo = QComboBox(dialog)
        for label, value in [
            ("Value", "rgb"),
            ("Red", "red"),
            ("Green", "green"),
            ("Blue", "blue"),
        ]:
            channel_combo.addItem(label, value)
        if self._current_pixels.ndim == 3 and self._current_pixels.shape[-1] >= 4:
            channel_combo.addItem("Alpha", "alpha")
        channel_index = channel_combo.findData(str(initial_parameters.get("channel", "rgb")))
        if channel_index >= 0:
            channel_combo.setCurrentIndex(channel_index)
        input_widget = _LevelsInputWidget(dialog)
        input_widget.set_pixels(original, str(channel_combo.currentData()))
        log_histogram_check = QCheckBox("Logarithmic histogram", dialog)
        log_histogram_check.setChecked(False)
        preview_check = QCheckBox("Preview", dialog)
        preview_check.setChecked(True)

        def slider_spin_row(
            minimum: int,
            maximum: int,
            value: int,
        ) -> tuple[QSlider, QSpinBox, QWidget]:
            row = QWidget(dialog)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            slider = QSlider(Qt.Orientation.Horizontal, dialog)
            slider.setRange(minimum, maximum)
            slider.setValue(value)
            spin = QSpinBox(dialog)
            spin.setRange(minimum, maximum)
            spin.setValue(value)
            spin.setFixedWidth(80)
            slider.valueChanged.connect(spin.setValue)
            spin.valueChanged.connect(slider.setValue)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(spin)
            return slider, spin, row

        input_numeric_row = QWidget(dialog)
        input_numeric_layout = QHBoxLayout(input_numeric_row)
        input_numeric_layout.setContentsMargins(0, 0, 0, 0)
        input_numeric_layout.setSpacing(8)
        black_spin = QSpinBox(dialog)
        white_spin = QSpinBox(dialog)
        for spin in (black_spin, white_spin):
            spin.setRange(0, 255)
            spin.setFixedWidth(74)
        gamma_spin = QDoubleSpinBox(dialog)
        gamma_spin.setRange(0.1, 10.0)
        gamma_spin.setDecimals(3)
        gamma_spin.setSingleStep(0.05)
        gamma_spin.setValue(1.0)
        gamma_spin.setFixedWidth(86)
        initial_black = int(
            np.clip(round(float(initial_parameters.get("black_point", 0.0)) * 255.0), 0, 254)
        )
        initial_white = int(
            np.clip(round(float(initial_parameters.get("white_point", 1.0)) * 255.0), 1, 255)
        )
        if initial_black >= initial_white:
            initial_black, initial_white = 0, 255
        black_spin.setValue(initial_black)
        white_spin.setValue(initial_white)
        gamma_spin.setValue(float(initial_parameters.get("midtone", 1.0)))
        input_numeric_layout.addWidget(QLabel("Black", dialog))
        input_numeric_layout.addWidget(black_spin)
        input_numeric_layout.addWidget(QLabel("Gamma", dialog))
        input_numeric_layout.addWidget(gamma_spin)
        input_numeric_layout.addWidget(QLabel("White", dialog))
        input_numeric_layout.addWidget(white_spin)
        input_numeric_layout.addStretch(1)
        initial_output_black = int(
            np.clip(round(float(initial_parameters.get("output_black", 0.0)) * 255.0), 0, 254)
        )
        initial_output_white = int(
            np.clip(round(float(initial_parameters.get("output_white", 1.0)) * 255.0), 1, 255)
        )
        if initial_output_black >= initial_output_white:
            initial_output_black, initial_output_white = 0, 255
        output_black_slider, output_black_spin, output_black_row = slider_spin_row(
            0,
            254,
            initial_output_black,
        )
        output_white_slider, output_white_spin, output_white_row = slider_spin_row(
            1,
            255,
            initial_output_white,
        )
        form.addRow("Channel", channel_combo)
        form.addRow("Input Levels", input_numeric_row)
        form.addRow("Output Black", output_black_row)
        form.addRow("Output White", output_white_row)
        layout.addWidget(input_widget)
        toggle_row = QHBoxLayout()
        toggle_row.addWidget(log_histogram_check)
        toggle_row.addStretch(1)
        toggle_row.addWidget(preview_check)
        layout.addLayout(toggle_row)
        layout.addLayout(form)
        auto_button = QPushButton("Auto Input Levels", dialog)
        reset_button = QPushButton("Reset Channel", dialog)
        button_row = QHBoxLayout()
        button_row.addWidget(auto_button)
        button_row.addWidget(reset_button)
        button_row.addStretch(1)
        layout.addLayout(button_row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        layout.addWidget(buttons)
        preview_timer = QTimer(dialog)
        preview_timer.setSingleShot(True)
        preview_timer.setInterval(80)
        updating = {"value": False}

        def parameters() -> dict[str, object]:
            return {
                "black_point": black_spin.value() / 255.0,
                "white_point": white_spin.value() / 255.0,
                "midtone": gamma_spin.value(),
                "output_black": output_black_spin.value() / 255.0,
                "output_white": output_white_spin.value() / 255.0,
                "channel": str(channel_combo.currentData()),
            }

        def update_preview() -> None:
            if not preview_check.isChecked():
                self.canvas.set_pixels(original, "levels preview base", fit=False)
                return
            try:
                preview = apply_edit_operation(original, "levels", parameters())
            except ValueError as exc:
                self._status(str(exc))
                return
            self.canvas.set_pixels(preview, "levels preview", fit=False)

        def schedule_preview() -> None:
            preview_timer.start()

        def constrain_input_black(value: int) -> None:
            if value >= white_spin.value():
                white_spin.setValue(min(255, value + 1))
            sync_input_widget_from_spins()
            schedule_preview()

        def constrain_input_white(value: int) -> None:
            if value <= black_spin.value():
                black_spin.setValue(max(0, value - 1))
            sync_input_widget_from_spins()
            schedule_preview()

        def constrain_output_black(value: int) -> None:
            if value >= output_white_spin.value():
                output_white_spin.setValue(min(255, value + 1))
            schedule_preview()

        def constrain_output_white(value: int) -> None:
            if value <= output_black_spin.value():
                output_black_spin.setValue(max(0, value - 1))
            schedule_preview()

        def sync_input_spins_from_widget(black: int, gamma: float, white: int) -> None:
            updating["value"] = True
            black_spin.setValue(black)
            gamma_spin.setValue(gamma)
            white_spin.setValue(white)
            updating["value"] = False
            schedule_preview()

        def sync_input_widget_from_spins() -> None:
            if updating["value"]:
                return
            input_widget.set_values(
                black_spin.value(),
                gamma_spin.value(),
                white_spin.value(),
                emit=False,
            )

        black_spin.valueChanged.connect(constrain_input_black)
        gamma_spin.valueChanged.connect(lambda _value: (sync_input_widget_from_spins(), schedule_preview()))
        white_spin.valueChanged.connect(constrain_input_white)
        output_black_spin.valueChanged.connect(constrain_output_black)
        output_white_spin.valueChanged.connect(constrain_output_white)
        input_widget.on_values_changed = sync_input_spins_from_widget

        def refresh_histogram() -> None:
            input_widget.set_logarithmic(log_histogram_check.isChecked())
            input_widget.set_pixels(original, str(channel_combo.currentData()))
            schedule_preview()

        def reset_channel() -> None:
            black_spin.setValue(0)
            white_spin.setValue(255)
            gamma_spin.setValue(1.0)
            output_black_spin.setValue(0)
            output_white_spin.setValue(255)
            sync_input_widget_from_spins()
            schedule_preview()

        def auto_input_levels() -> None:
            low, high = _levels_auto_input_bounds(
                original,
                str(channel_combo.currentData()),
            )
            black_spin.setValue(low)
            white_spin.setValue(high)
            gamma_spin.setValue(1.0)
            sync_input_widget_from_spins()
            schedule_preview()

        channel_combo.currentIndexChanged.connect(lambda _index: refresh_histogram())
        log_histogram_check.toggled.connect(lambda _checked: refresh_histogram())
        preview_check.toggled.connect(lambda _checked: update_preview())
        preview_timer.timeout.connect(update_preview)
        reset_button.clicked.connect(lambda _checked=False: reset_channel())
        auto_button.clicked.connect(lambda _checked=False: auto_input_levels())
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        sync_input_widget_from_spins()
        update_preview()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            preview_timer.stop()
            self._render_current_adjustment_preview()
            return
        preview_timer.stop()
        self._current_pixels = original
        if layer_id is not None:
            self._update_adjustment_layer_parameters(layer_id, parameters())
        else:
            self.apply_named_operation("levels", parameters())

