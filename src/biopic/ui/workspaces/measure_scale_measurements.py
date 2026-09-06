"""Measurement creation, styling, movement, and undo helpers."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox, QPushButton

from biopic.models.calibration import Calibration, normalize_unit
from biopic.models.measurement import (
    Measurement,
    MeasurementKind,
    MeasurementLabelAlignment,
    Point,
    normalize_area_unit,
    normalize_length_unit,
    rotated_rectangle_points,
)
from biopic.ui.settings import set_settings_json


class MeasureScaleMeasurementsMixin:
    """Interactive measurement creation and editing behavior."""

    def add_line_measurement(self) -> None:
        """Activate the unified measurement tool for the selected mode."""
        node_id = self._current_source_node_id()
        if node_id is None:
            QMessageBox.warning(
                self,
                "Add Measurement",
                "Select an image first.",
            )
            return
        measurement_type = self.measurement_type_combo.currentText()
        if measurement_type == "Line":
            self._measurement_pending_start = None
            self.canvas.set_tool_mode("measure_line")
            self.records.setPlainText(
                "Line measurement: drag a line, or click start point and then click end point."
            )
            return
        geometry = self.area_geometry_combo.currentText()
        if geometry == "Ellipse":
            self.canvas.set_tool_mode("ellipse_select")
            self.records.setPlainText("Ellipse measurement: drag an ellipse bounding box.")
        elif geometry == "Freehand":
            self.canvas.set_tool_mode("free_select")
            self.records.setPlainText("Freehand measurement: draw a closed freehand region.")
        else:
            self.canvas.set_tool_mode("select")
            self.records.setPlainText("Rectangle measurement: drag a rectangle.")

    def _create_default_measurement(self) -> None:
        """Create a default measurement without mouse interaction."""
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        kind = self._current_measurement_kind()
        measurement = Measurement(
            kind=kind,
            image_node_id=node_id,
            points=self._default_measurement_points(kind, 100.0),
            calibration=self._measurement_calibration(node_id),
            label=f"{self._measurement_kind_label(kind)} {len(self.project.measurements) + 1}",
            display_unit=normalize_length_unit(self.length_unit_combo.currentText()),
            area_display_unit=normalize_area_unit(self.area_unit_combo.currentText()),
            label_alignment=self._current_label_alignment(),
            **self._measurement_style_kwargs(),
        )
        self._store_measurement(measurement)

    def _measurement_point_clicked(self, x: int, y: int) -> None:
        if self.measurement_type_combo.currentText() != "Line":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        point = Point(float(x), float(y))
        if self._measurement_pending_start is None:
            self._measurement_pending_start = point
            return
        measurement = Measurement(
            kind=MeasurementKind.LINE,
            image_node_id=node_id,
            points=[self._measurement_pending_start, point],
            calibration=self._measurement_calibration(node_id),
            label=f"Line {len(self.project.measurements) + 1}",
            display_unit=normalize_length_unit(self.length_unit_combo.currentText()),
            area_display_unit=normalize_area_unit(self.area_unit_combo.currentText()),
            label_alignment=self._current_label_alignment(),
            **self._measurement_style_kwargs(),
        )
        self._measurement_pending_start = None
        self._store_measurement(measurement)

    def _measurement_line_selected(self, x1: int, y1: int, x2: int, y2: int) -> None:
        if self.measurement_type_combo.currentText() != "Line":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        measurement = Measurement(
            kind=MeasurementKind.LINE,
            image_node_id=node_id,
            points=[Point(float(x1), float(y1)), Point(float(x2), float(y2))],
            calibration=self._measurement_calibration(node_id),
            label=f"Line {len(self.project.measurements) + 1}",
            display_unit=normalize_length_unit(self.length_unit_combo.currentText()),
            area_display_unit=normalize_area_unit(self.area_unit_combo.currentText()),
            label_alignment=self._current_label_alignment(),
            **self._measurement_style_kwargs(),
        )
        self._measurement_pending_start = None
        self._store_measurement(measurement)

    def _measurement_rectangle_selected(self, x: int, y: int, width: int, height: int) -> None:
        if self.measurement_type_combo.currentText() != "Area":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        geometry = self.area_geometry_combo.currentText()
        if geometry == "Ellipse":
            center = Point(x + width / 2.0, y + height / 2.0)
            points = [center, Point(center.x + width / 2.0, center.y), Point(center.x, center.y + height / 2.0)]
            kind = MeasurementKind.ELLIPSE
        elif geometry == "Freehand":
            return
        else:
            center = Point(x + width / 2.0, y + height / 2.0)
            points = rotated_rectangle_points(center, float(width), float(height), 0.0)
            kind = MeasurementKind.RECTANGLE
        measurement = Measurement(
            kind=kind,
            image_node_id=node_id,
            points=points,
            calibration=self._measurement_calibration(node_id),
            label=f"{self._measurement_kind_label(kind)} {len(self.project.measurements) + 1}",
            display_unit=normalize_length_unit(self.length_unit_combo.currentText()),
            area_display_unit=normalize_area_unit(self.area_unit_combo.currentText()),
            label_alignment=self._current_label_alignment(),
            **self._measurement_style_kwargs(),
        )
        self._store_measurement(measurement)

    def _measurement_selection_completed(
        self,
        shape: str,
        _x: int,
        _y: int,
        _width: int,
        _height: int,
        polygon: object,
    ) -> None:
        if self.measurement_type_combo.currentText() != "Area":
            return
        if self.area_geometry_combo.currentText() != "Freehand":
            return
        if shape != "free":
            return
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        points: list[Point] = []
        if isinstance(polygon, list):
            for item in polygon:
                if isinstance(item, (tuple, list)) and len(item) >= 2:
                    points.append(Point(float(item[0]), float(item[1])))
        if len(points) < 3:
            return
        measurement = Measurement(
            kind=MeasurementKind.POLYGON,
            image_node_id=node_id,
            points=points,
            calibration=self._measurement_calibration(node_id),
            label=f"Freehand {len(self.project.measurements) + 1}",
            display_unit=normalize_length_unit(self.length_unit_combo.currentText()),
            area_display_unit=normalize_area_unit(self.area_unit_combo.currentText()),
            label_alignment=self._current_label_alignment(),
            **self._measurement_style_kwargs(),
        )
        self._store_measurement(measurement)

    def _measurement_move_started(self, x: int, y: int) -> None:
        if self.canvas._tool_mode != "move":
            return
        self._moving_measurement_id = self._nearest_measurement_id(
            float(x),
            float(y),
            target=self._measurement_move_mode,
        )

    def _measurement_move_finished(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        if self.canvas._tool_mode != "move" or self._moving_measurement_id is None:
            return
        measurement = self.project.measurements.get(self._moving_measurement_id)
        self._moving_measurement_id = None
        if measurement is None:
            return
        dx = float(end_x - start_x)
        dy = float(end_y - start_y)
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return
        self._push_measurement_undo()
        if self._measurement_move_mode == "label":
            measurement.label_offset = (
                measurement.label_offset[0] + dx,
                measurement.label_offset[1] + dy,
            )
        elif self._measurement_move_mode == "value":
            measurement.value_offset = (
                measurement.value_offset[0] + dx,
                measurement.value_offset[1] + dy,
            )
        else:
            measurement.points = [Point(point.x + dx, point.y + dy) for point in measurement.points]
        self.project.touch()
        self._changed()

    def _nearest_measurement_id(self, x: float, y: float, *, target: str = "geometry") -> str | None:
        node_id = self._current_source_node_id()
        best_id: str | None = None
        best_distance = 80.0 if target in {"label", "value"} else 25.0
        for measurement in self.project.measurements.values():
            if measurement.image_node_id != node_id:
                continue
            if target in {"label", "value"}:
                point = self._measurement_text_anchor(measurement, target)
                distance = ((point.x - x) ** 2 + (point.y - y) ** 2) ** 0.5
                if distance < best_distance:
                    best_distance = distance
                    best_id = measurement.id
                continue
            for point in measurement.points:
                distance = ((point.x - x) ** 2 + (point.y - y) ** 2) ** 0.5
                if distance < best_distance:
                    best_distance = distance
                    best_id = measurement.id
        return best_id

    def _measurement_text_anchor(self, measurement: Measurement, target: str) -> Point:
        base = self._measurement_base_label_point(measurement)
        offset = measurement.label_offset if target == "label" else measurement.value_offset
        value_shift = 18.0 if target == "value" and measurement.show_label and measurement.label else 0.0
        return Point(base.x + offset[0], base.y + offset[1] + value_shift)

    def _measurement_base_label_point(self, measurement: Measurement) -> Point:
        if not measurement.points:
            return Point(0.0, 0.0)
        if measurement.kind is MeasurementKind.LINE and len(measurement.points) >= 2:
            a, b = measurement.points[0], measurement.points[1]
            return Point((a.x + b.x) / 2.0 + 6.0, (a.y + b.y) / 2.0 + 6.0)
        xs = [point.x for point in measurement.points]
        ys = [point.y for point in measurement.points]
        return Point(sum(xs) / len(xs) + 6.0, min(ys) - 18.0)

    def _store_measurement(self, measurement: Measurement) -> None:
        self._push_measurement_undo()
        if normalize_unit(measurement.calibration.unit) == "px":
            measurement.display_unit = "px"
            measurement.area_display_unit = "px\u00b2"
        self.project.measurements[measurement.id] = measurement
        self.project.touch()
        self._changed()
        self.canvas.set_tool_mode("pan")

    def _measurement_display_options_changed(self, _value: str | None = None) -> None:
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        self._push_measurement_undo()
        self._save_measurement_defaults()
        for measurement in self.project.measurements.values():
            if measurement.image_node_id != node_id:
                continue
            if normalize_unit(measurement.calibration.unit) == "px":
                measurement.display_unit = "px"
                measurement.area_display_unit = "px\u00b2"
            else:
                measurement.display_unit = normalize_length_unit(self.length_unit_combo.currentText())
                measurement.area_display_unit = normalize_area_unit(self.area_unit_combo.currentText())
            measurement.label_alignment = self._current_label_alignment()
            self._apply_measurement_style(measurement)
        self._refresh_measurement_overlay()
        self._refresh_measurement_table()

    def _measurement_type_changed(self, value: str) -> None:
        is_area = value == "Area"
        self.area_geometry_label.setVisible(is_area)
        self.area_geometry_combo.setVisible(is_area)
        self.area_unit_label.setVisible(is_area)
        self.area_unit_combo.setVisible(is_area)
        self.length_unit_label.setVisible(not is_area)
        self.length_unit_combo.setVisible(not is_area)
        self.measurement_show_sides.setVisible(
            is_area and self.area_geometry_combo.currentText() == "Rectangle"
        )

    def _current_label_alignment(self) -> MeasurementLabelAlignment:
        if self.label_alignment_combo.currentText().startswith("Align"):
            return MeasurementLabelAlignment.ALIGNED
        return MeasurementLabelAlignment.HORIZONTAL

    def _measurement_style_kwargs(self) -> dict[str, object]:
        return {
            "color": self._color_button_value(self.measurement_color_button),
            "line_width": float(self.measurement_line_width.value()),
            "font_size": float(self.measurement_font_size.value()),
            "bold": bool(self.measurement_bold.isChecked()),
            "italic": bool(self.measurement_italic.isChecked()),
            "show_label": bool(self.measurement_show_label.isChecked()),
            "show_side_lengths": bool(self.measurement_show_sides.isChecked()),
            "decimal_places": int(self.measurement_digits.value()),
        }

    def _apply_measurement_style(self, measurement: Measurement) -> None:
        style = self._measurement_style_kwargs()
        measurement.color = str(style["color"])
        measurement.line_width = float(style["line_width"])
        measurement.font_size = float(style["font_size"])
        measurement.bold = bool(style["bold"])
        measurement.italic = bool(style["italic"])
        measurement.show_label = bool(style["show_label"])
        measurement.show_side_lengths = bool(style["show_side_lengths"])
        measurement.decimal_places = int(style["decimal_places"])

    def _choose_button_color(self, button: QPushButton) -> None:
        super()._choose_button_color(button)
        if button is self.measurement_color_button:
            self._measurement_display_options_changed()

    def _save_measurement_defaults(self) -> None:
        set_settings_json("measure/measurement_defaults", self._measurement_style_kwargs())

    def _measurement_snapshot(self) -> dict[str, object]:
        return {
            measurement_id: measurement.to_dict()
            for measurement_id, measurement in self.project.measurements.items()
        }

    def _restore_measurement_snapshot(self, snapshot: dict[str, object]) -> None:
        self.project.measurements = {
            str(measurement_id): Measurement.from_dict(dict(data))
            for measurement_id, data in snapshot.items()
            if isinstance(data, dict)
        }
        self.project.touch()
        self._changed()

    def _push_measurement_undo(self) -> None:
        snapshot = self._measurement_snapshot()
        if self._measurement_undo_stack and self._measurement_undo_stack[-1] == snapshot:
            return
        self._measurement_undo_stack.append(snapshot)
        self._measurement_redo_stack.clear()

    def undo(self) -> None:
        if not self._measurement_undo_stack:
            return
        self._measurement_redo_stack.append(self._measurement_snapshot())
        self._restore_measurement_snapshot(self._measurement_undo_stack.pop())

    def redo(self) -> None:
        if not self._measurement_redo_stack:
            return
        self._measurement_undo_stack.append(self._measurement_snapshot())
        self._restore_measurement_snapshot(self._measurement_redo_stack.pop())

    def _current_measurement_kind(self) -> MeasurementKind:
        if self.measurement_type_combo.currentText() == "Line":
            return MeasurementKind.LINE
        return {
            "Rectangle": MeasurementKind.RECTANGLE,
            "Ellipse": MeasurementKind.ELLIPSE,
            "Freehand": MeasurementKind.POLYGON,
        }.get(self.area_geometry_combo.currentText(), MeasurementKind.RECTANGLE)

    def _measurement_calibration(self, node_id: str) -> Calibration:
        return self.project.calibrations.get(
            node_id,
            Calibration(unit_per_pixel=1.0, unit="px", source="uncalibrated"),
        )

    def _measurement_kind_label(self, kind: MeasurementKind) -> str:
        return {
            MeasurementKind.LINE: "Line",
            MeasurementKind.RECTANGLE: "Rectangle",
            MeasurementKind.ELLIPSE: "Ellipse",
            MeasurementKind.POLYGON: "Freehand",
        }.get(kind, kind.value.title())

