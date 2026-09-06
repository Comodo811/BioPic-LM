"""Asset selection, measurement records, and measurement table helpers."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

from biopic.imaging.project_render import asset_for_source_node, project_image_cache_key
from biopic.models.measurement import (
    MeasurementKind,
    Point,
    normalize_area_unit,
    normalize_length_unit,
)
from biopic.ui.settings import remembered_save_file


class MeasureScaleRecordsMixin:
    """Selection and record-refresh helpers for the measure/scale workspace."""

    def export_measurements_csv(self) -> None:
        """Export measurement results to CSV."""
        from biopic.imaging.measurement import export_measurements_csv

        filename = remembered_save_file(
            self,
            "Export Measurements CSV",
            "measurements_csv",
            "CSV (*.csv)",
        )
        if not filename:
            return
        export_measurements_csv(list(self.project.measurements.values()), Path(filename))

    def _select_asset(self) -> None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return
        row = self.asset_combo.currentIndex()
        if row >= 0 and self.asset_list.currentRow() != row:
            self.asset_list.blockSignals(True)
            self.asset_list.setCurrentRow(row)
            self.asset_list.blockSignals(False)
        asset = self.project.assets.get(str(asset_id))
        if asset is not None:
            node_id = self.project.source_node_id_for_asset(asset.id)
            rendered = self._rendered_project_image(node_id)
            if rendered is not None:
                signature = (
                    asset.id,
                    node_id,
                    project_image_cache_key(self.project, node_id),
                    rendered.shape,
                    str(rendered.dtype),
                )
                if signature != self._display_signature:
                    self.canvas.set_pixels(rendered, asset.filename, fit=True)
                    self._display_signature = signature
            else:
                self.canvas.set_asset(asset)
                self._display_signature = (asset.id, "asset", asset.checksum or asset.path)
            self._refresh_scale_bar_overlay()

    def _select_asset_row(self, row: int) -> None:
        if row < 0 or row >= len(self._editable_assets):
            return
        if self.asset_combo.currentIndex() != row:
            self.asset_combo.blockSignals(True)
            self.asset_combo.setCurrentIndex(row)
            self.asset_combo.blockSignals(False)
        self._select_asset()

    def current_asset_id(self) -> str | None:
        """Return the currently selected editable image asset id."""
        asset_id = self.asset_combo.currentData()
        return None if asset_id is None else str(asset_id)

    def select_asset_id(self, asset_id: str | None) -> None:
        """Select an editable image asset by id and redraw linked overlays."""
        if asset_id is None:
            self._select_asset()
            return
        index = self.asset_combo.findData(asset_id)
        if index >= 0:
            self.asset_combo.setCurrentIndex(index)
        self._select_asset()

    def _current_source_node_id(self) -> str | None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return None
        return self.project.source_node_id_for_asset(str(asset_id))

    def _changed(self, *, notify: bool = True) -> None:
        self._refresh_records()
        self._rebuild_scale_menu()
        self._refresh_scale_bar_overlay()
        if notify and self.measurementChanged is not None:
            self.measurementChanged()

    def _refresh_scale_bar_overlay(self) -> None:
        node_id = self._current_source_node_id()
        scale_bars = [
            scale_bar
            for scale_bar in self.project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ]
        if node_id is not None and node_id in self.project.calibrations:
            calibration = self.project.calibrations[node_id]
            for scale_bar in scale_bars:
                scale_bar.calibration = calibration
        self.canvas.set_scale_bars(scale_bars)
        self._refresh_measurement_overlay()

    def _refresh_records(self) -> None:
        self._refresh_measurement_table()
        lines: list[str] = []
        lines.append("Calibrations")
        for node_id, calibration in self.project.calibrations.items():
            label = self._source_node_label(node_id)
            lines.append(
                f"{label}: Scale {calibration.unit_per_pixel:.6g} "
                f"{calibration.unit}/pixel; Density {calibration.pixels_per_unit:.6g} "
                f"pixels/{calibration.unit}"
            )
        lines.append("")
        lines.append("Scale Presets")
        for preset in self.project.scale_presets.values():
            labels = ", ".join(scale.menu_label() for scale in preset.scales)
            lines.append(f"{preset.name}: {labels}")
        lines.append("")
        lines.append("Measurements")
        for measurement in self.project.measurements.values():
            lines.append(
                f"{measurement.label}: {measurement.length_physical():.6g} "
                f"{measurement.calibration.unit}"
            )
        lines.append("")
        lines.append("Scale Bars")
        for scale_bar in self.project.scale_bars.values():
            label = self._source_node_label(scale_bar.image_node_id)
            lines.append(
                f"{label}: {scale_bar.physical_length:g} {scale_bar.unit} scale bar, "
                f"{scale_bar.pixel_length:.2f} pixels at {scale_bar.location}"
            )
        self.records.setPlainText("\n".join(lines))

    def _source_node_label(self, node_id: str) -> str:
        asset = asset_for_source_node(self.project, node_id)
        if asset is not None:
            return asset.filename
        return "Current image"

    def _refresh_measurement_table(self) -> None:
        measurements = list(self.project.measurements.values())
        self.measurement_table.blockSignals(True)
        self.measurement_table.setRowCount(len(measurements))
        for row, measurement in enumerate(measurements):
            length_text = "—"
            area_text = "—"
            if measurement.kind in {MeasurementKind.LINE, MeasurementKind.POLYLINE, MeasurementKind.ANGLE}:
                unit = normalize_length_unit(measurement.display_unit)
                length_text = f"{measurement.length_display(unit):.6g} {unit}"
            if measurement.kind in {MeasurementKind.RECTANGLE, MeasurementKind.ELLIPSE, MeasurementKind.POLYGON}:
                unit = normalize_area_unit(measurement.area_display_unit)
                area_text = f"{measurement.area_display(unit):.6g} {unit}"
            values = [
                measurement.label,
                self._measurement_kind_label(measurement.kind),
                length_text,
                area_text,
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, measurement.id)
                if column != 0:
                    item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                self.measurement_table.setItem(row, column, item)
        self.measurement_table.blockSignals(False)

    def _measurement_table_item_changed(self, item: QTableWidgetItem) -> None:
        """Persist user edits to measurement labels from the measurement table."""
        if item.column() != 0:
            return
        measurement_id = item.data(256)
        if measurement_id is None:
            return
        measurement = self.project.measurements.get(str(measurement_id))
        if measurement is None:
            return
        label = item.text().strip()
        if measurement.label == label:
            return
        self._push_measurement_undo()
        measurement.label = label
        self.project.touch()
        self._refresh_measurement_overlay()
        self._refresh_records()
        if self.measurementChanged is not None:
            self.measurementChanged()

    def _refresh_measurement_overlay(self) -> None:
        node_id = self._current_source_node_id()
        if node_id is None:
            self.canvas.set_measurements([])
            return
        self.canvas.set_measurements(
            [
                measurement
                for measurement in self.project.measurements.values()
                if measurement.image_node_id == node_id
            ]
        )

    def _default_measurement_points(
        self, kind: MeasurementKind, length: float
    ) -> list[Point]:
        if kind is MeasurementKind.RECTANGLE:
            return [Point(0.0, 0.0), Point(length, max(1.0, length / 2.0))]
        if kind is MeasurementKind.ELLIPSE:
            return [Point(0.0, 0.0), Point(length, max(1.0, length / 2.0))]
        if kind is MeasurementKind.POLYGON:
            return [Point(0.0, 0.0), Point(length, 0.0), Point(length, length)]
        if kind is MeasurementKind.ANGLE:
            return [Point(0.0, 0.0), Point(length / 2.0, 0.0), Point(length / 2.0, length / 2.0)]
        return [Point(0.0, 0.0), Point(length, 0.0)]

