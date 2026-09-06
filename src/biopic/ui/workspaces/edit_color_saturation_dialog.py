"""Color/Saturation dialog for the edit workspace."""

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


class EditColorSaturationDialogMixin:
    """GIMP-style Hue-Saturation adjustment dialog."""

    def open_color_saturation_dialog(
        self,
        *,
        layer_id: str | None = None,
        initial_parameters: dict[str, object] | None = None,
    ) -> None:
        """Open a GIMP-style Hue-Saturation dialog."""
        if self._current_pixels is None:
            return
        initial_parameters = dict(initial_parameters or {})
        original = (
            self._adjustment_preview_base(exclude_layer_id=layer_id)
            if layer_id is not None
            else self._adjustment_preview_base("color_saturation")
        )
        if original is None:
            original = self._current_pixels.copy()
        dialog = QDialog(self)
        dialog.setWindowTitle("Color / Saturation")
        dialog.setMinimumWidth(560)
        layout = QVBoxLayout(dialog)
        title = QLabel("Select Primary Color to Adjust", dialog)
        title.setStyleSheet("font-weight: 700;")
        layout.addWidget(title)
        color_grid = QGridLayout()
        range_buttons: dict[str, QPushButton | QRadioButton] = {}
        swatches: dict[str, QLabel] = {}
        color_specs = {
            "red": ("R", "#ff1018", 0, 3),
            "yellow": ("Y", "#ffff00", 1, 1),
            "magenta": ("M", "#f000e8", 1, 5),
            "green": ("G", "#00ff20", 2, 1),
            "blue": ("B", "#1010ff", 2, 5),
            "cyan": ("C", "#20e8f0", 3, 3),
            "all": ("All", "#555555", 2, 3),
        }
        for name, (label, color, row, column) in color_specs.items():
            if name == "all":
                button = QPushButton(label, dialog)
                button.setCheckable(True)
                button.setMinimumSize(QSize(48, 30))
                button.setStyleSheet(
                    "QPushButton { padding: 3px; } "
                    "QPushButton:checked { background-color: #2f2f2f; color: #ffffff; font-weight: 700; }"
                )
                range_buttons[name] = button
                color_grid.addWidget(button, row, column)
                continue
            cell = QWidget(dialog)
            cell_layout = QHBoxLayout(cell)
            cell_layout.setContentsMargins(0, 0, 0, 0)
            cell_layout.setSpacing(4)
            swatch = QLabel(dialog)
            swatch.setFixedSize(QSize(42, 22))
            swatch.setStyleSheet(f"background-color: {color}; border: 1px solid #111;")
            button = QRadioButton(label, dialog)
            button.setStyleSheet("QRadioButton { spacing: 3px; }")
            swatches[name] = swatch
            range_buttons[name] = button
            cell_layout.addWidget(swatch)
            cell_layout.addWidget(button)
            color_grid.addWidget(cell, row, column)
        range_buttons["all"].setChecked(True)
        layout.addLayout(color_grid)
        form = QFormLayout()

        def slider_spin_row(
            minimum: int,
            maximum: int,
            *,
            suffix: str,
        ) -> tuple[QSlider, QDoubleSpinBox, QWidget]:
            row = QWidget(dialog)
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(8)
            slider = QSlider(Qt.Orientation.Horizontal, dialog)
            slider.setRange(minimum, maximum)
            slider.setSingleStep(1)
            slider.setPageStep(10)
            spin = QDoubleSpinBox(dialog)
            spin.setRange(float(minimum), float(maximum))
            spin.setDecimals(1)
            spin.setSingleStep(1.0)
            spin.setSuffix(suffix)
            spin.setFixedWidth(108)
            row_layout.addWidget(slider, 1)
            row_layout.addWidget(spin)
            return slider, spin, row

        overlap_slider, overlap_spin, overlap_row = slider_spin_row(0, 100, suffix=" %")
        hue_slider, hue_spin, hue_row = slider_spin_row(-180, 180, suffix=" deg")
        lightness_slider, lightness_spin, lightness_row = slider_spin_row(-100, 100, suffix=" %")
        saturation_slider, saturation_spin, saturation_row = slider_spin_row(-100, 100, suffix=" %")
        form.addRow("Overlap", overlap_row)
        section = QLabel("Edit Selected Color", dialog)
        section.setStyleSheet("font-weight: 700;")
        layout.addWidget(section)
        form.addRow("Hue", hue_row)
        form.addRow("Lightness", lightness_row)
        form.addRow("Saturation", saturation_row)
        layout.addLayout(form)
        reset_color_button = QPushButton("Reset Color", dialog)
        layout.addWidget(reset_color_button, alignment=Qt.AlignmentFlag.AlignRight)
        preview_check = QCheckBox("Preview", dialog)
        preview_check.setChecked(True)
        split_check = QCheckBox("Split View", dialog)
        toggles = QHBoxLayout()
        toggles.addWidget(preview_check)
        toggles.addStretch(1)
        toggles.addWidget(split_check)
        layout.addLayout(toggles)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Help
            | QDialogButtonBox.StandardButton.Reset
            | QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel,
            dialog,
        )
        layout.addWidget(buttons)

        state: dict[str, dict[str, float]] = {
            name: {"hue": 0.0, "lightness": 0.0, "saturation": 0.0}
            for name in color_specs
        }
        ranges = initial_parameters.get("ranges")
        if isinstance(ranges, dict):
            for name, values in ranges.items():
                if name in state and isinstance(values, dict):
                    state[str(name)] = {
                        "hue": float(values.get("hue", 0.0)),
                        "lightness": float(values.get("lightness", 0.0)),
                        "saturation": float(values.get("saturation", 0.0)),
                    }
        initial_range = str(initial_parameters.get("range", "all"))
        if initial_range not in state:
            initial_range = "all"
        if not isinstance(ranges, dict):
            state[initial_range] = {
                "hue": float(initial_parameters.get("hue", 0.0)),
                "lightness": float(initial_parameters.get("lightness", 0.0)),
                "saturation": float(initial_parameters.get("saturation", 0.0)),
            }
        active_range = {"name": initial_range}
        updating = {"value": False}
        preview_timer = QTimer(dialog)
        preview_timer.setSingleShot(True)
        preview_timer.setInterval(80)
        preview_state: dict[str, object] = {
            "token": 0,
            "running": False,
            "pending": False,
            "active": True,
            "thread": None,
            "worker": None,
            "latest_parameters": None,
            "running_rect": None,
            "display_rect": None,
        }
        base_swatch_rgb = {
            "red": (1.0, 0.0, 0.0),
            "yellow": (1.0, 1.0, 0.0),
            "green": (0.0, 1.0, 0.0),
            "cyan": (0.0, 1.0, 1.0),
            "blue": (0.0, 0.0, 1.0),
            "magenta": (1.0, 0.0, 1.0),
            }

        def bind_slider_spin(slider: QSlider, spin: QDoubleSpinBox) -> None:
            def slider_changed(value: int) -> None:
                if abs(spin.value() - float(value)) > 1e-6:
                    spin.setValue(float(value))

            def spin_changed(value: float) -> None:
                rounded = int(round(value))
                if slider.value() != rounded:
                    slider.setValue(rounded)

            slider.valueChanged.connect(slider_changed)
            spin.valueChanged.connect(spin_changed)

        for slider, spin in [
            (overlap_slider, overlap_spin),
            (hue_slider, hue_spin),
            (lightness_slider, lightness_spin),
            (saturation_slider, saturation_spin),
        ]:
            bind_slider_spin(slider, spin)
        overlap_spin.setValue(float(initial_parameters.get("overlap", 0.0)))

        def parameters() -> dict[str, object]:
            values = state[active_range["name"]]
            return {
                "range": active_range["name"],
                "hue": values["hue"],
                "lightness": values["lightness"],
                "saturation": values["saturation"],
                "overlap": overlap_spin.value(),
                "ranges": {
                    name: dict(values)
                    for name, values in state.items()
                    if any(abs(float(component)) > 1e-9 for component in values.values())
                },
            }

        def update_preview() -> None:
            if not preview_check.isChecked():
                self._show_color_saturation_preview(original)
                return
            preview_state["latest_parameters"] = parameters()
            preview_state["token"] = int(preview_state["token"]) + 1
            token = int(preview_state["token"])
            if bool(preview_state["running"]):
                preview_state["pending"] = True
                return
            start_preview_worker(token, dict(preview_state["latest_parameters"]))

        def start_preview_worker(token: int, worker_parameters: dict[str, object]) -> None:
            preview_state["running"] = True
            preview_state["pending"] = False
            rect = self._color_saturation_preview_rect(original)
            if rect is None:
                preview_state["running"] = False
                return
            x, y, width, height = rect
            preview_state["running_rect"] = rect
            preview_pixels = original[y : y + height, x : x + width].copy()
            thread = QThread(dialog)
            worker = EditOperationWorker(
                token,
                preview_pixels,
                "color_saturation",
                worker_parameters,
            )
            worker.moveToThread(thread)
            thread.started.connect(worker.run)
            worker.resultReady.connect(handle_preview_result)
            worker.finished.connect(thread.quit)
            worker.finished.connect(worker.deleteLater)
            thread.finished.connect(thread.deleteLater)
            thread.finished.connect(on_preview_finished)
            preview_state["thread"] = thread
            preview_state["worker"] = worker
            thread.start()

        def handle_preview_result(token: int, result: object) -> None:
            if not bool(preview_state["active"]) or token != int(preview_state["token"]):
                return
            if isinstance(result, Exception):
                self._status(f"Color / Saturation preview failed: {result}")
                return
            if preview_check.isChecked() and isinstance(result, np.ndarray):
                rect = preview_state.get("running_rect")
                if isinstance(rect, tuple):
                    self._show_color_saturation_preview_region(result, rect)

        def on_preview_finished() -> None:
            preview_state["running"] = False
            preview_state["thread"] = None
            preview_state["worker"] = None
            if (
                bool(preview_state["active"])
                and bool(preview_state["pending"])
                and preview_check.isChecked()
                and isinstance(preview_state["latest_parameters"], dict)
            ):
                start_preview_worker(
                    int(preview_state["token"]),
                    dict(preview_state["latest_parameters"]),
                )

        def stop_preview_worker() -> None:
            preview_state["active"] = False
            thread = preview_state.get("thread")
            preview_state["thread"] = None
            preview_state["worker"] = None
            if not isinstance(thread, QThread):
                return
            try:
                if thread.isRunning():
                    thread.quit()
                    thread.wait()
            except RuntimeError:
                pass

        def schedule_preview() -> None:
            if preview_check.isChecked():
                preview_timer.start()

        def update_swatches() -> None:
            for name, rgb in base_swatch_rgb.items():
                color = np.array([[rgb]], dtype=np.float32)
                mapped = apply_edit_operation(color, "color_saturation", parameters())[0, 0]
                red = int(np.clip(mapped[0], 0.0, 1.0) * 255.0)
                green = int(np.clip(mapped[1], 0.0, 1.0) * 255.0)
                blue = int(np.clip(mapped[2], 0.0, 1.0) * 255.0)
                border = "2px solid #ffffff" if active_range["name"] == name else "1px solid #111"
                swatches[name].setStyleSheet(
                    f"background-color: rgb({red}, {green}, {blue}); border: {border};"
                )

        def load_active_values() -> None:
            updating["value"] = True
            values = state[active_range["name"]]
            hue_spin.setValue(values["hue"])
            lightness_spin.setValue(values["lightness"])
            saturation_spin.setValue(values["saturation"])
            hue_slider.setValue(int(round(values["hue"])))
            lightness_slider.setValue(int(round(values["lightness"])))
            saturation_slider.setValue(int(round(values["saturation"])))
            updating["value"] = False

        def select_range(name: str) -> None:
            active_range["name"] = name
            for current, button in range_buttons.items():
                button.setChecked(current == name)
            load_active_values()
            update_swatches()

        def save_active_values() -> None:
            if updating["value"]:
                return
            values = state[active_range["name"]]
            values["hue"] = hue_spin.value()
            values["lightness"] = lightness_spin.value()
            values["saturation"] = saturation_spin.value()
            update_swatches()
            schedule_preview()

        def reset_current() -> None:
            state[active_range["name"]] = {"hue": 0.0, "lightness": 0.0, "saturation": 0.0}
            load_active_values()
            update_swatches()
            schedule_preview()

        def reset_all() -> None:
            for key in state:
                state[key] = {"hue": 0.0, "lightness": 0.0, "saturation": 0.0}
            overlap_spin.setValue(0.0)
            load_active_values()
            update_swatches()
            schedule_preview()

        for name, button in range_buttons.items():
            button.clicked.connect(lambda _checked=False, value=name: select_range(value))
        hue_spin.valueChanged.connect(save_active_values)
        lightness_spin.valueChanged.connect(save_active_values)
        saturation_spin.valueChanged.connect(save_active_values)
        overlap_spin.valueChanged.connect(lambda _value: (update_swatches(), schedule_preview()))
        preview_check.toggled.connect(lambda _checked: update_preview())
        preview_timer.timeout.connect(update_preview)
        reset_color_button.clicked.connect(lambda _checked=False: reset_current())
        buttons.button(QDialogButtonBox.StandardButton.Reset).clicked.connect(
            lambda _checked=False: reset_all()
        )
        buttons.button(QDialogButtonBox.StandardButton.Help).clicked.connect(
            lambda: self._status("GIMP-style Hue-Saturation uses color ranges, not RGB channels.")
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        select_range(active_range["name"])
        update_swatches()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            preview_timer.stop()
            stop_preview_worker()
            self._render_current_adjustment_preview()
            return
        preview_timer.stop()
        stop_preview_worker()
        self._current_pixels = original
        if layer_id is not None:
            self._update_adjustment_layer_parameters(layer_id, parameters())
        else:
            self.apply_named_operation("color_saturation", parameters())

    def _show_color_saturation_preview(self, pixels: np.ndarray) -> None:
        """Update the color preview without rebuilding canvas items on every slider tick."""
        self._show_color_saturation_preview_region(pixels, None)

    def _show_color_saturation_preview_region(
        self,
        pixels: np.ndarray,
        rect: tuple[int, int, int, int] | None,
    ) -> None:
        if self._current_pixels is not None and pixels.shape == self._current_pixels.shape:
            self.canvas.update_tile_regions(
                pixels,
                [(0, 0, int(pixels.shape[1]), int(pixels.shape[0]))],
            )
        elif rect is not None:
            self.canvas.update_tile_region_patch(pixels, rect)
        else:
            self.canvas.set_pixels(pixels, "color saturation preview", fit=False)

    def _color_saturation_preview_rect(
        self,
        pixels: np.ndarray,
        *,
        max_pixels: int = 500_000,
    ) -> tuple[int, int, int, int] | None:
        if pixels.ndim < 2 or pixels.shape[0] <= 0 or pixels.shape[1] <= 0:
            return None
        height, width = int(pixels.shape[0]), int(pixels.shape[1])
        if width * height <= max_pixels:
            return (0, 0, width, height)
        scale = (max_pixels / float(width * height)) ** 0.5
        preview_width = max(1, min(width, int(width * scale)))
        preview_height = max(1, min(height, max_pixels // preview_width))
        x = max(0, (width - preview_width) // 2)
        y = max(0, (height - preview_height) // 2)
        return (x, y, preview_width, preview_height)
