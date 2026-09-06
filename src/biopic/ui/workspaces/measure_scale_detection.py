"""Image-based scale detection dialog for the measure/scale workspace."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from biopic.imaging.io import read_image_asset
from biopic.imaging.scale_detection import (
    align_image_to_axes,
    confidence_label,
    detect_scale_stripe_pattern,
    infer_scale_metadata_from_filename,
)
from biopic.models.calibration import (
    Calibration,
    MagnificationScale,
    ScalePreset,
    normalize_unit,
    parse_magnification,
)
from biopic.ui.scale_detection_canvas import ScaleDetectionCanvas
from biopic.ui.settings import restore_dialog_size
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET


class MeasureScaleDetectionMixin:
    """Scale detection and preset capture actions."""

    def determine_scale_from_image(self) -> None:
        """Open the determine-scale dialog and apply its calibration scope."""
        dialog = QDialog(self)
        dialog.setWindowTitle("Determine Scale from Image")
        dialog.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        dialog.setWindowFlag(Qt.WindowType.WindowMaximizeButtonHint, True)
        restore_dialog_size(dialog, "determine_scale_from_image", QSize(980, 720))
        layout = QVBoxLayout(dialog)
        state: dict[str, object] = {
            "pixels": None,
            "path": "",
            "roi": None,
            "source_label": "Current image",
            "stripe_axis": "",
            "stripe_positions": (),
        }

        source_controls = QHBoxLayout()
        use_current = QPushButton("Use Current Image")
        load_other = QPushButton("Load Other Image")
        measure_distance = QPushButton("Measure Distance")
        accept_detected = QPushButton("Accept Detected Scale")
        reject_detected = QPushButton("Reject Detected Scale")
        clear_measurement = QPushButton("Clear Measurement")
        auto_detect = QPushButton("Auto-detect Stripes")
        align_button = QPushButton("Align Image")
        full_screen_button = QPushButton("Full Screen")
        source_controls.addWidget(use_current)
        source_controls.addWidget(load_other)
        source_controls.addWidget(measure_distance)
        source_controls.addWidget(auto_detect)
        source_controls.addWidget(align_button)
        source_controls.addWidget(accept_detected)
        source_controls.addWidget(reject_detected)
        source_controls.addWidget(clear_measurement)
        source_controls.addWidget(full_screen_button)
        source_controls.addStretch(1)
        layout.addLayout(source_controls)

        detection_canvas = ScaleDetectionCanvas()
        detection_canvas.setMinimumHeight(360)
        layout.addWidget(detection_canvas, 1)
        form = QFormLayout()
        pixel_distance = QDoubleSpinBox()
        pixel_distance.setRange(0.001, 1_000_000.0)
        pixel_distance.setValue(self._last_measurement_line_pixels)
        known_distance = QDoubleSpinBox()
        known_distance.setRange(0.001, 1_000_000.0)
        known_distance.setValue(10.0)
        unit = QComboBox()
        unit.addItem("µm")
        unit.addItems(["μm", "mm", "cm", "inch", "pt", "px"])
        unit.clear()
        unit.addItems(["µm", "mm", "cm", "inch", "pt", "px"])
        unit.setCurrentText(normalize_unit(self.unit_combo.currentText()))
        pixel_aspect = QDoubleSpinBox()
        pixel_aspect.setRange(0.001, 1000.0)
        pixel_aspect.setValue(1.0)
        rotation = QDoubleSpinBox()
        rotation.setRange(-45.0, 45.0)
        rotation.setDecimals(3)
        rotation.setSuffix(" deg")
        magnification = QLineEdit()
        fluid = QComboBox()
        fluid.addItems(["Air", "Water", "Oil", "Glycerol", "Silicone oil"])
        microscope = QLineEdit()
        camera = QLineEdit()
        preset_action = QComboBox()
        preset_action.addItem("Do not add to preset", "")
        preset_action.addItem("Create new preset", "__new__")
        for preset in self.project.scale_presets.values():
            preset_action.addItem(preset.name, preset.id)
        scope = QComboBox()
        scope.addItems(["Current image", "Selected images", "Entire project"])
        roi_label = QLabel("No selection")
        result = QLabel()
        result.setWordWrap(True)
        form.addRow("Image selection", roi_label)
        form.addRow("Distance in pixels", pixel_distance)
        form.addRow("Known physical distance", known_distance)
        form.addRow("Unit", unit)
        form.addRow("Pixel aspect ratio", pixel_aspect)
        form.addRow("Rotation-only alignment", rotation)
        form.addRow("Magnification", magnification)
        form.addRow("Immersion fluid", fluid)
        form.addRow("Microscope", microscope)
        form.addRow("Camera", camera)
        form.addRow("Preset", preset_action)
        form.addRow("Apply calibration to", scope)
        form.addRow("Calculated calibration", result)
        layout.addLayout(form)

        def positive_distances() -> tuple[float, float] | None:
            pixels = float(pixel_distance.value())
            known = float(known_distance.value())
            if pixels <= 0.0 or known <= 0.0:
                return None
            return pixels, known

        def refresh_formula() -> None:
            selected_unit = normalize_unit(unit.currentText())
            distances = positive_distances()
            if distances is None:
                result.setText("Enter positive pixel and known distances to calculate calibration.")
                return
            pixels, known = distances
            s_value = known / pixels
            rho_value = pixels / known
            result.setText(
                f"s = d_known / d_pixels = {s_value:.6g} {selected_unit}/pixel\n"
                f"rho = d_pixels / d_known = {rho_value:.6g} pixels/{selected_unit}"
            )

        def current_pixels() -> tuple[np.ndarray | None, str]:
            asset_id = self.asset_combo.currentData()
            if asset_id is None:
                return None, ""
            asset = self.project.assets.get(str(asset_id))
            if asset is None:
                return None, ""
            node_id = self.project.source_node_id_for_asset(asset.id)
            rendered = self._rendered_project_image(node_id)
            if rendered is not None:
                return np.asarray(rendered), asset.path
            try:
                return read_image_asset(Path(asset.path), load_pixels=True).pixels, asset.path
            except (OSError, ValueError):
                return None, asset.path

        def set_detection_pixels(pixels: np.ndarray | None, path: str, label: str) -> None:
            if pixels is None:
                QMessageBox.warning(dialog, "Determine Scale from Image", "No image could be loaded.")
                return
            state["pixels"] = np.asarray(pixels)
            state["path"] = path
            state["roi"] = None
            state["source_label"] = label
            detection_canvas.set_pixels(np.asarray(pixels), Path(path).name or label, fit=True)
            detection_canvas.set_tool_mode("pan")
            roi_label.setText(f"{label}: full image")
            guessed = infer_scale_metadata_from_filename(path)
            if guessed.get("magnification"):
                magnification.setText(guessed["magnification"])
            fluid.setCurrentText(guessed.get("fluid", "Air"))
            if guessed.get("microscope"):
                microscope.setText(guessed["microscope"])
            if guessed.get("camera"):
                camera.setText(guessed["camera"])

        def load_current_image() -> None:
            pixels, path = current_pixels()
            set_detection_pixels(pixels, path, "Current image")

        def load_other_image() -> None:
            filename, _selected_filter = QFileDialog.getOpenFileName(
                dialog,
                "Load Scale Image",
                "",
                "Images (*.tif *.tiff *.png *.jpg *.jpeg *.bmp *.cr2 *.cr3 *.dng *.raw);;All Files (*)",
            )
            if not filename:
                return
            try:
                result_asset = read_image_asset(Path(filename), load_pixels=True)
            except (OSError, ValueError) as exc:
                QMessageBox.warning(dialog, "Load Scale Image", str(exc))
                return
            set_detection_pixels(result_asset.pixels, filename, "Loaded image")

        def start_measurement() -> None:
            detection_canvas.begin_measure_distance()
            roi_label.setText("Click start, move, then click endpoint. Shift/Ctrl enables free angle.")

        def accept_measured_distance(distance: float) -> None:
            if distance <= 0:
                return
            pixel_distance.setValue(distance)
            distances = positive_distances()
            if distances is not None:
                pixels, known = distances
                detection_canvas.set_calibration_preview(
                    pixels / known,
                    normalize_unit(unit.currentText()),
                )
            roi_label.setText(f"Measured distance: {distance:.3f}px")
            refresh_formula()

        def auto_detect_spacing() -> None:
            pixels = state.get("pixels")
            if pixels is None:
                QMessageBox.warning(dialog, "Auto-detect Scale", "Load or select an image first.")
                return
            try:
                detection = detect_scale_stripe_pattern(
                    np.asarray(pixels),
                    state.get("roi") if isinstance(state.get("roi"), tuple) else None,
                )
            except ValueError as exc:
                QMessageBox.warning(dialog, "Auto-detect Scale", str(exc))
                return
            spacing = detection.spacing_pixels
            axis = detection.axis
            confidence = detection.confidence
            state["stripe_axis"] = axis
            state["stripe_positions"] = detection.stripe_positions
            pixel_distance.setValue(spacing)
            known_distance.setValue(10.0)
            unit.setCurrentText("Î¼m")
            detection_canvas.set_calibration_preview(
                spacing / 10.0,
                normalize_unit(unit.currentText()),
                stripe_axis=axis,
                stripe_positions=detection.stripe_positions,
                tick_marks=detection.tick_marks,
            )
            roi_label.setText(
                f"Detected {axis}: {spacing:.3f} px per 10 µm; "
                f"confidence {confidence_label(confidence)} ({confidence:.2f})"
            )
            refresh_formula()

        def accept_detected_scale() -> None:
            distances = positive_distances()
            if distances is None:
                QMessageBox.warning(
                    dialog,
                    "Determine Scale from Image",
                    "Distance in pixels and known physical distance must be greater than zero.",
                )
                return
            pixels, known = distances
            detection_canvas.set_calibration_preview(
                pixels / known,
                normalize_unit(unit.currentText()),
            )
            roi_label.setText("Detected scale accepted for this dialog")
            refresh_formula()

        def reject_detected_scale() -> None:
            detection_canvas.clear_calibration_preview()
            roi_label.setText("Detected scale rejected; measure or enter distance manually")

        def toggle_full_screen() -> None:
            if dialog.isFullScreen():
                dialog.showNormal()
                full_screen_button.setText("Full Screen")
            else:
                dialog.showFullScreen()
                full_screen_button.setText("Exit Full Screen")

        def align_stripes() -> None:
            pixels = state.get("pixels")
            if pixels is None:
                QMessageBox.warning(dialog, "Align Image", "Load or select an image first.")
                return
            try:
                rotated, angle = align_image_to_axes(np.asarray(pixels))
            except ValueError as exc:
                QMessageBox.warning(dialog, "Align Image", str(exc))
                return
            state["pixels"] = rotated
            state["roi"] = None
            rotation.setValue(angle)
            detection_canvas.set_pixels(
                rotated,
                str(state.get("source_label", "Aligned image")),
                fit=True,
            )
            detection_canvas.set_tool_mode("pan")
            roi_label.setText(f"Aligned by {angle:.3f} deg; select area again if needed")

        use_current.clicked.connect(load_current_image)
        load_other.clicked.connect(load_other_image)
        measure_distance.clicked.connect(start_measurement)
        auto_detect.clicked.connect(auto_detect_spacing)
        align_button.clicked.connect(align_stripes)
        accept_detected.clicked.connect(accept_detected_scale)
        reject_detected.clicked.connect(reject_detected_scale)
        clear_measurement.clicked.connect(detection_canvas.clear_measurement)
        full_screen_button.clicked.connect(toggle_full_screen)
        detection_canvas.measurementAccepted.connect(accept_measured_distance)
        pixel_distance.valueChanged.connect(refresh_formula)
        known_distance.valueChanged.connect(refresh_formula)
        unit.currentTextChanged.connect(refresh_formula)
        refresh_formula()
        load_current_image()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        while True:
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            if positive_distances() is None:
                QMessageBox.warning(
                    dialog,
                    "Determine Scale from Image",
                    "Distance in pixels and known physical distance must be greater than zero.",
                )
                continue
            preset_choice = str(preset_action.currentData() or "")
            if preset_choice != "__new__":
                break
            created = self.add_permanent_preset(
                preset_name=f"Preset {len(self.project.scale_presets) + 1}",
                camera_name=camera.text().strip() or None,
                microscope_name=microscope.text().strip() or None,
                magnification_text=magnification.text().strip() or None,
                fluid_text=fluid.currentText(),
                distance_pixels=pixel_distance.value(),
                known_distance_value=known_distance.value(),
                unit_text=normalize_unit(unit.currentText()),
            )
            if created:
                preset_choice = ""
                break
        calibration = Calibration(
            unit_per_pixel=known_distance.value() / pixel_distance.value(),
            unit=normalize_unit(unit.currentText()),
            pixel_aspect_ratio=pixel_aspect.value(),
            source="determine_scale_from_image",
        )
        for node_id in self._node_ids_for_scope(scope.currentText()):
            self.project.calibrations[node_id] = calibration
        if preset_choice:
            magnification_text = magnification.text().strip() or "10x"
            try:
                parsed_magnification = parse_magnification(magnification_text)
            except ValueError as exc:
                QMessageBox.warning(dialog, "Scale Preset", str(exc))
                return
            preset = self.project.scale_presets.get(preset_choice)
            if preset is None:
                QMessageBox.warning(dialog, "Scale Preset", "Selected preset no longer exists.")
                return
            preset.scales.append(
                MagnificationScale(
                    magnification=parsed_magnification,
                    distance_pixels=pixel_distance.value(),
                    known_distance=known_distance.value(),
                    unit=normalize_unit(unit.currentText()),
                    fluid=fluid.currentText(),
                    objective=magnification_text,
                )
            )
            preset.scales = self._sorted_scale_rows(preset.scales)
            self._save_persistent_scale_presets()
        self.pixel_distance.setValue(pixel_distance.value())
        self.known_distance.setValue(known_distance.value())
        self.unit_combo.setCurrentText(normalize_unit(unit.currentText()))
        self._last_measurement_line_pixels = pixel_distance.value()
        self._last_determined_scale = {
            "distance_pixels": pixel_distance.value(),
            "known_distance": known_distance.value(),
            "unit": normalize_unit(unit.currentText()),
            "magnification": magnification.text().strip(),
            "fluid": fluid.currentText(),
            "microscope": microscope.text().strip(),
            "camera": camera.text().strip(),
            "source_path": str(state.get("path", "")),
        }
        self.add_to_preset_button.setVisible(False)
        self.project.touch()
        self._changed()

    def add_determined_scale_to_preset(self) -> None:
        """Add the last image-derived scale to a new or existing permanent preset."""
        data = self._last_determined_scale
        if not data:
            QMessageBox.warning(
                self,
                "Add to Preset",
                "Determine a scale from an image before adding it to a preset.",
            )
            return
        magnification_text = str(data.get("magnification", "")).strip()
        if not magnification_text:
            magnification_text, ok = QInputDialog.getText(
                self,
                "Add to Preset",
                "Magnification",
                text="10x",
            )
            if not ok:
                return
        try:
            parsed_magnification = parse_magnification(magnification_text)
        except ValueError as exc:
            QMessageBox.warning(self, "Add to Preset", str(exc))
            return
        existing_names = [preset.name for preset in self.project.scale_presets.values()]
        choices = ["Create new preset", *existing_names]
        choice, ok = QInputDialog.getItem(
            self,
            "Add to Preset",
            "Preset",
            choices,
            0,
            False,
        )
        if not ok:
            return
        if choice == "Create new preset":
            default_name = str(data.get("microscope", "")).strip() or "Scale Preset"
            name, ok = QInputDialog.getText(
                self,
                "Create Scale Preset",
                "Preset name",
                text=default_name,
            )
            if not ok:
                return
            preset = ScalePreset(
                name=name.strip() or default_name,
                camera_name=str(data.get("camera", "")).strip(),
                microscope_name=str(data.get("microscope", "")).strip(),
            )
            self.project.scale_presets[preset.id] = preset
        else:
            preset = next(
                preset for preset in self.project.scale_presets.values() if preset.name == choice
            )
        scale = MagnificationScale(
            magnification=parsed_magnification,
            distance_pixels=float(data["distance_pixels"]),
            known_distance=float(data["known_distance"]),
            unit=str(data["unit"]),
            fluid=str(data.get("fluid", "Air") or "Air"),
            objective=magnification_text,
        )
        preset.scales.append(scale)
        preset.scales = self._sorted_scale_rows(preset.scales)
        self._save_persistent_scale_presets()
        self.project.touch()
        self._changed()
        return True

