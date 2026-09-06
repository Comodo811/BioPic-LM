"""Scale-bar dialog helpers for the measure/scale workspace."""

from __future__ import annotations

from PySide6.QtCore import QSize
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from biopic.models.calibration import Calibration
from biopic.models.measurement import ScaleBar
from biopic.ui.settings import restore_dialog_size, set_settings_json, settings_json
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET


class MeasureScaleBarsMixin:
    """Scale-bar creation dialog and color helpers."""

    def _scale_bar_dialog(
        self, calibration: Calibration, existing_scale_bar: ScaleBar | None = None
    ) -> QDialog:
        dialog = QDialog(self)
        dialog.setWindowTitle("Add Scale Bar")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        restore_dialog_size(dialog, "add_scale_bar", QSize(520, 420))
        layout = QVBoxLayout(dialog)
        controls: list[dict[str, object]] = []
        controls.append(
            self._add_scale_bar_section(
                layout, "Horizontal Scale", "horizontal", True, calibration, existing_scale_bar
            )
        )
        controls.append(
            self._add_scale_bar_section(
                layout, "Vertical Scale", "vertical", False, calibration, existing_scale_bar
            )
        )
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        dialog.setProperty("scale_bar_controls", controls)
        return dialog

    def _add_scale_bar_section(
        self,
        parent_layout: QVBoxLayout,
        title: str,
        orientation: str,
        enabled_by_default: bool,
        calibration: Calibration,
        existing_scale_bar: ScaleBar | None = None,
    ) -> dict[str, object]:
        is_existing_orientation = (
            existing_scale_bar is not None and existing_scale_bar.orientation == orientation
        )
        existing = existing_scale_bar if is_existing_orientation else None
        defaults = settings_json("measure/scale_bar_defaults", {})
        group = QGroupBox(title)
        group.setCheckable(True)
        group.setChecked(
            is_existing_orientation or (existing_scale_bar is None and enabled_by_default)
        )
        group_layout = QVBoxLayout(group)
        main_panel = QWidget()
        main_form = QFormLayout(main_panel)
        main_panel.setVisible(group.isChecked())
        group.toggled.connect(main_panel.setVisible)
        length = QDoubleSpinBox()
        length.setRange(0.001, 1_000_000.0)
        length.setValue(
            existing.physical_length
            if existing is not None
            else float(defaults.get("length", 10.0))
        )
        unit = QComboBox()
        unit.addItems(["μm", "mm", "cm", "inch", "pt", "px"])
        unit.setCurrentText(calibration.unit)
        width = QDoubleSpinBox()
        width.setRange(1.0, 100.0)
        width.setValue(
            existing.width_px if existing is not None else float(defaults.get("width", 4.0))
        )
        line_style = QComboBox()
        line_style.addItems(["Solid", "Dash", "Dot"])
        foreground = self._color_button(
            existing.foreground if existing is not None else "#ffffff"
        )
        background = self._color_button(
            existing.background
            if existing is not None and existing.background is not None
            else "#00000080"
        )
        font_family = QComboBox()
        font_family.addItems(["Arial", "Helvetica", "Times New Roman", "Calibri"])
        if existing is not None:
            font_family.setCurrentText(existing.font_family)
        font_size = QDoubleSpinBox()
        font_size.setRange(1.0, 200.0)
        font_size.setValue(
            existing.font_size
            if existing is not None
            else float(defaults.get("font_size", 12.0))
        )
        bold = QCheckBox()
        bold.setChecked(existing.bold if existing is not None else False)
        italic = QCheckBox()
        italic.setChecked(existing.italic if existing is not None else False)
        display_length = QCheckBox()
        display_length.setChecked(
            existing.display_length
            if existing is not None
            else bool(defaults.get("display_length", True))
        )
        text_position = QComboBox()
        text_position.addItems(["Above", "Below", "Left", "Right"])
        location = QComboBox()
        location.addItems(["Upper Left", "Upper Right", "Lower Left", "Lower Right"])
        location.setCurrentText(
            existing.location if existing is not None else str(defaults.get("location", "Lower Right"))
        )
        offset_x = QDoubleSpinBox()
        offset_x.setRange(-100.0, 100.0)
        offset_y = QDoubleSpinBox()
        offset_y.setRange(-100.0, 100.0)
        margin_x, margin_y = self._scale_bar_default_offsets()
        image_width, image_height = self._scale_bar_offset_basis()
        offset_x.setValue(
            (existing.offset_x if existing is not None else margin_x)
            / max(1.0, image_width)
            * 100.0
        )
        offset_y.setValue(
            (existing.offset_y if existing is not None else margin_y)
            / max(1.0, image_height)
            * 100.0
        )
        for spin in (offset_x, offset_y):
            spin.setMinimumWidth(72)
            spin.setMaximumWidth(120)
            spin.setSuffix("%")
        opacity = QDoubleSpinBox()
        opacity.setRange(0.0, 100.0)
        opacity.setValue(existing.opacity * 100.0 if existing is not None else 100.0)
        for label, widget in [
            ("Scale Length", length),
            ("Unit", unit),
            ("Scale Width in pixels", width),
            ("Font family", font_family),
            ("Font size", font_size),
            ("Display Length", display_length),
        ]:
            main_form.addRow(label, widget)
        advanced = QGroupBox("Advanced")
        advanced.setCheckable(True)
        advanced.setChecked(False)
        advanced_panel = QWidget()
        advanced_form = QFormLayout(advanced_panel)
        advanced_panel.setVisible(False)
        advanced.toggled.connect(advanced_panel.setVisible)
        advanced_layout = QVBoxLayout(advanced)
        advanced_layout.addWidget(advanced_panel)
        offset_widget = QWidget()
        offset_layout = QGridLayout(offset_widget)
        offset_layout.setContentsMargins(0, 0, 0, 0)
        offset_layout.setColumnStretch(1, 1)
        offset_layout.setColumnStretch(3, 1)
        for column, (label, widget) in enumerate([("X:", offset_x), ("Y:", offset_y)]):
            offset_layout.addWidget(QLabel(label), 0, column * 2)
            offset_layout.addWidget(widget, 0, column * 2 + 1)
        for label, widget in [
            ("Line style", line_style),
            ("Foreground color", foreground),
            ("Optional background or contrast box", background),
            ("Bold", bold),
            ("Italic", italic),
            ("Text position relative to bar", text_position),
            ("Location", location),
            ("Offset (% image)", offset_widget),
            ("Opacity", opacity),
        ]:
            advanced_form.addRow(label, widget)
        for label in [
            "Rotation",
            "Text Rotation",
            "Padding",
            "Keep inside visible image bounds",
            "Snap to image edge",
            "Use publication-safe contrast",
        ]:
            is_checkbox = "Use" in label or "Keep" in label or "Snap" in label
            advanced_form.addRow(label, QCheckBox() if is_checkbox else QDoubleSpinBox())
        group_layout.addWidget(main_panel)
        group_layout.addWidget(advanced)
        parent_layout.addWidget(group)
        return {
            "enabled": group,
            "orientation": orientation,
            "length": length,
            "unit": unit,
            "width": width,
            "location": location,
            "offset_x": offset_x,
            "offset_y": offset_y,
            "foreground": foreground,
            "background": background,
            "display_length": display_length,
            "font_family": font_family,
            "font_size": font_size,
            "bold": bold,
            "italic": italic,
            "opacity": opacity,
        }

    def _save_scale_bar_defaults(self, controls: dict[str, object]) -> None:
        set_settings_json(
            "measure/scale_bar_defaults",
            {
                "length": controls["length"].value(),
                "width": controls["width"].value(),
                "font_size": controls["font_size"].value(),
                "display_length": controls["display_length"].isChecked(),
                "location": controls["location"].currentText(),
            },
        )

    def _scale_bar_default_offsets(self) -> tuple[float, float]:
        pixels = self.canvas._pixels
        if pixels is None:
            return (24.0, 24.0)
        return (max(1.0, pixels.shape[1] * 0.02), max(1.0, pixels.shape[0] * 0.02))

    def _scale_bar_offset_basis(self) -> tuple[float, float]:
        pixels = self.canvas._pixels
        if pixels is not None:
            return (max(1.0, float(pixels.shape[1])), max(1.0, float(pixels.shape[0])))
        return (1.0, 1.0)

    def _color_button(self, color: str) -> QPushButton:
        button = QPushButton()
        button.setProperty("color", color)
        button.setToolTip("Choose color")
        button.setFixedSize(QSize(28, 24))
        self._style_color_button(button)
        button.clicked.connect(lambda: self._choose_button_color(button))
        return button

    def _choose_button_color(self, button: QPushButton) -> None:
        current = QColor(self._color_button_value(button) or "#ffffff")
        selected = QColorDialog.getColor(
            current,
            self,
            "Choose Color",
            QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not selected.isValid():
            return
        alpha = selected.alpha()
        value = selected.name(QColor.NameFormat.HexRgb)
        if alpha < 255:
            value = f"{value}{alpha:02x}"
        button.setProperty("color", value)
        self._style_color_button(button)

    def _style_color_button(self, button: QPushButton) -> None:
        color = self._color_button_value(button) or "#ffffff"
        button.setText("")
        button.setStyleSheet(
            f"background-color: {color[:7]}; border: 1px solid #1f1f1f;"
        )

    def _color_button_value(self, button: object) -> str:
        if isinstance(button, QPushButton):
            value = button.property("color")
            return "" if value is None else str(value)
        return ""
