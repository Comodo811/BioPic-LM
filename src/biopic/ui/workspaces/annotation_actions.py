"""Annotation workspace asset, table, overlay, and edit actions."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QKeyEvent
from PySide6.QtWidgets import QColorDialog, QInputDialog, QPushButton, QTableWidgetItem

from biopic.imaging.project_render import project_image_cache_key, render_project_image
from biopic.models.annotations import (
    AnnotationDefinition,
    AnnotationKind,
    AnnotationObject,
    consolidate_legend,
    normalize_wedge_points,
)
from biopic.ui.fonts import safe_font_family
from biopic.ui.settings import set_settings_json


class AnnotationActionsMixin:
    """Asset selection, annotation table sync, overlays, and edit tools."""

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
            rendered = self._rendered_project_image(node_id) if node_id is not None else None
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
            self._refresh_annotation_overlay()

    def _select_asset_row(self, row: int) -> None:
        if row < 0 or row >= len(self._editable_assets):
            return
        if self.asset_combo.currentIndex() != row:
            self.asset_combo.blockSignals(True)
            self.asset_combo.setCurrentIndex(row)
            self.asset_combo.blockSignals(False)
        self._select_asset()

    def _rendered_project_image(self, node_id: str | None) -> np.ndarray | None:
        if node_id is None:
            return None
        key = project_image_cache_key(self.project, node_id)
        if key is None:
            return None
        cached = self._rendered_image_cache.get(node_id)
        if cached is not None and cached[0] == key:
            return cached[1]
        rendered = render_project_image(self.project, node_id)
        if rendered is not None:
            self._rendered_image_cache[node_id] = (key, rendered)
        return rendered

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
            if self.asset_combo.currentIndex() != index:
                self.asset_combo.setCurrentIndex(index)
            elif self.asset_list.currentRow() != index:
                self.asset_list.setCurrentRow(index)
        self._select_asset()

    def _current_source_node_id(self) -> str | None:
        asset_id = self.asset_combo.currentData()
        if asset_id is None:
            return None
        return self.project.source_node_id_for_asset(str(asset_id))

    def _refresh_records(self) -> None:
        signature = (
            tuple(
                sorted(
                    (
                        definition.id,
                        definition.abbreviation,
                        definition.full_definition,
                        definition.include_in_legend,
                    )
                    for definition in self.project.annotation_definitions.values()
                )
            ),
            tuple(
                sorted(
                    (
                        annotation.id,
                        annotation.text,
                        annotation.definition_id,
                        annotation.visible,
                        annotation.include_in_legend,
                    )
                    for annotation in self.project.annotations.values()
                )
            ),
        )
        if signature == self._records_signature:
            return
        self._records_signature = signature
        entries = consolidate_legend(
            self.project.annotation_definitions,
            list(self.project.annotations.values()),
            include_panels=False,
        )
        lines = ["Legend"]
        lines.extend(entries)
        self.records.setPlainText("\n".join(lines))

    def _refresh_annotation_table(self) -> None:
        node_id = self._current_source_node_id()
        annotations = [
            annotation
            for annotation in self.project.annotations.values()
            if annotation.image_node_id == node_id
        ]
        measurements = [
            measurement
            for measurement in self.project.measurements.values()
            if measurement.image_node_id == node_id
        ]
        signature = (
            node_id,
            self._selected_annotation_id,
            tuple(
                (
                    annotation.id,
                    annotation.text,
                    annotation.kind.value,
                    annotation.font,
                    annotation.size,
                    annotation.color,
                    annotation.line_width,
                    annotation.visible,
                )
                for annotation in annotations
            ),
            tuple(
                (
                    measurement.id,
                    measurement.kind.value,
                    tuple((point.x, point.y) for point in measurement.points),
                    measurement.label,
                    measurement.display_unit,
                    measurement.area_display_unit,
                    measurement.label_alignment.value,
                    measurement.rotation,
                )
                for measurement in measurements
            ),
        )
        if signature == self._annotation_table_signature:
            return
        self._annotation_table_signature = signature
        self.annotation_table.blockSignals(True)
        self.annotation_table.setRowCount(len(annotations))
        selected_row = -1
        for row, annotation in enumerate(annotations):
            values = [
                annotation.text or annotation.kind.value,
                self._annotation_kind_label(annotation.kind),
                safe_font_family(annotation.font),
                f"{annotation.size:g}",
                "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(256, annotation.id)
                self.annotation_table.setItem(row, column, item)
            color_button = QPushButton()
            color_button.setFixedSize(QSize(28, 20))
            color_button.setToolTip("Change annotation color")
            color_button.setStyleSheet(
                f"background-color: {annotation.color}; border: 1px solid #151515;"
            )
            color_button.clicked.connect(
                lambda _checked=False, annotation_id=annotation.id: (
                    self._select_annotation_by_id(annotation_id),
                    self._open_annotation_color_dialog(),
                )
            )
            self.annotation_table.setCellWidget(row, 4, color_button)
            if annotation.id == self._selected_annotation_id:
                selected_row = row
        self.annotation_table.blockSignals(False)
        if selected_row >= 0:
            self.annotation_table.setCurrentCell(selected_row, 0)

    def _annotation_table_selection_changed(
        self,
        current_row: int,
        _current_column: int,
        _previous_row: int,
        _previous_column: int,
    ) -> None:
        if current_row < 0:
            self._selected_annotation_id = None
            self.canvas.set_selected_annotation_id(None)
            return
        item = self.annotation_table.item(current_row, 0)
        if item is None:
            self._selected_annotation_id = None
            self.canvas.set_selected_annotation_id(None)
            return
        self._selected_annotation_id = str(item.data(256))
        self._sync_selected_annotation_controls()

    def _annotation_table_cell_changed(self, row: int, column: int) -> None:
        item = self.annotation_table.item(row, column)
        id_item = self.annotation_table.item(row, 0)
        if item is None or id_item is None:
            return
        annotation = self.project.annotations.get(str(id_item.data(256)))
        if annotation is None:
            return
        value = item.text().strip()
        updates: dict[str, object] = {}
        if column == 0 and annotation.text != value:
            updates["text"] = value
        elif column == 2:
            font = safe_font_family(value)
            if annotation.font != font:
                updates["font"] = font
        elif column == 3:
            try:
                size = max(4.0, min(144.0, float(value.replace(",", "."))))
            except ValueError:
                self._annotation_table_signature = None
                self._refresh_annotation_table()
                return
            if abs(annotation.size - size) > 1e-6:
                updates["size"] = size
        if not updates:
            return
        self._push_annotation_undo()
        for field_name, next_value in updates.items():
            setattr(annotation, field_name, next_value)
        self._selected_annotation_id = annotation.id
        self._sync_selected_annotation_controls()
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_table_signature = None
        self._annotation_overlay_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _select_annotation_by_id(self, annotation_id: str) -> None:
        self._selected_annotation_id = annotation_id
        self.canvas.set_selected_annotation_id(annotation_id)
        for row in range(self.annotation_table.rowCount()):
            item = self.annotation_table.item(row, 0)
            if item is not None and str(item.data(256)) == annotation_id:
                self.annotation_table.setCurrentCell(row, 0)
                break
        self._sync_selected_annotation_controls()

    def _annotation_transformed_on_canvas(
        self,
        annotation_id: str,
        points: object,
    ) -> None:
        annotation = self.project.annotations.get(annotation_id)
        if annotation is None:
            return
        if not self._annotation_transform_undo_open:
            self._push_annotation_undo()
            self._annotation_transform_undo_open = True
        annotation.points = [
            (float(x), float(y))
            for x, y in points
        ]
        self._selected_annotation_id = annotation_id
        self.project.touch()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._refresh_annotation_table()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _delete_annotation_by_id(self, annotation_id: str) -> bool:
        if annotation_id not in self.project.annotations:
            return False
        self._push_annotation_undo()
        del self.project.annotations[annotation_id]
        if self._selected_annotation_id == annotation_id:
            self._selected_annotation_id = None
        self.canvas.set_selected_annotation_id(None)
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()
        return True

    def _delete_selected_annotation(self) -> bool:
        if self._selected_annotation_id is None:
            return False
        return self._delete_annotation_by_id(self._selected_annotation_id)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace} and self._delete_selected_annotation():
            event.accept()
            return
        super().keyPressEvent(event)

    def _sync_selected_annotation_controls(self) -> None:
        annotation = self.project.annotations.get(self._selected_annotation_id)
        if annotation is None:
            return
        self.annotation_font_family.blockSignals(True)
        self.annotation_font_size.blockSignals(True)
        self.annotation_width.blockSignals(True)
        self.annotation_font_family.setCurrentFont(QFont(safe_font_family(annotation.font)))
        self.annotation_font_size.setValue(float(annotation.size))
        self.annotation_width.setValue(float(annotation.line_width))
        self.annotation_font_family.blockSignals(False)
        self.annotation_font_size.blockSignals(False)
        self.annotation_width.blockSignals(False)
        self._annotation_color = annotation.color
        self._update_annotation_color_button()

    def _apply_selected_annotation_style(self, *_args: object) -> None:
        self._save_persistent_annotation_style()
        if hasattr(self, "_configure_annotation_shape_preview"):
            self._configure_annotation_shape_preview()
        targets: list[AnnotationObject]
        if self._selected_annotation_id is None:
            node_id = self._current_source_node_id()
            targets = [
                annotation
                for annotation in self.project.annotations.values()
                if annotation.image_node_id == node_id
            ]
        else:
            annotation = self.project.annotations.get(self._selected_annotation_id)
            targets = [] if annotation is None else [annotation]
        if not targets:
            return
        self._push_annotation_undo()
        font = self._safe_annotation_font_family()
        size = float(self.annotation_font_size.value())
        line_width = float(self.annotation_width.value())
        for annotation in targets:
            annotation.font = font
            annotation.size = size
            annotation.color = self._annotation_color
            annotation.line_width = line_width
            if annotation.kind is AnnotationKind.WEDGE:
                annotation.fill = self._annotation_color
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_table_signature = None
        self._annotation_overlay_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _save_persistent_annotation_style(self) -> None:
        set_settings_json(
            "annotation/default_style",
            {
                "font_family": self._safe_annotation_font_family(),
                "font_size": float(self.annotation_font_size.value()),
                "color": self._annotation_color,
                "line_width": float(self.annotation_width.value()),
            },
        )

    def _refresh_scale_bar_overlay(self) -> None:
        node_id = self._current_source_node_id()
        scale_bars = [
            scale_bar
            for scale_bar in self.project.scale_bars.values()
            if scale_bar.image_node_id == node_id
        ]
        signature = (
            node_id,
            tuple(
                (
                    scale_bar.id,
                    scale_bar.pixel_length,
                    scale_bar.physical_length,
                    scale_bar.unit,
                    scale_bar.location,
                    scale_bar.offset_x,
                    scale_bar.offset_y,
                    scale_bar.foreground,
                    scale_bar.background,
                    scale_bar.font_family,
                    scale_bar.font_size,
                    scale_bar.display_length,
                    scale_bar.opacity,
                )
                for scale_bar in scale_bars
            ),
        )
        if signature == self._scale_bar_overlay_signature:
            return
        self._scale_bar_overlay_signature = signature
        if node_id is not None and node_id in self.project.calibrations:
            calibration = self.project.calibrations[node_id]
            for scale_bar in scale_bars:
                scale_bar.calibration = calibration
        self.canvas.set_scale_bars(scale_bars)

    def _refresh_annotation_overlay(self) -> None:
        node_id = self._current_source_node_id()
        annotations = [
            annotation
            for annotation in self.project.annotations.values()
            if annotation.image_node_id == node_id
        ]
        measurements = [
            measurement
            for measurement in self.project.measurements.values()
            if measurement.image_node_id == node_id
        ]
        signature = (
            node_id,
            tuple(
                (
                    annotation.id,
                    annotation.kind.value,
                    tuple(annotation.points),
                    annotation.text,
                    annotation.font,
                    annotation.size,
                    annotation.color,
                    annotation.line_width,
                    annotation.fill,
                    annotation.opacity,
                    annotation.visible,
                )
                for annotation in annotations
            ),
            tuple(
                (
                    measurement.id,
                    measurement.kind.value,
                    tuple((point.x, point.y) for point in measurement.points),
                    measurement.label,
                    measurement.display_unit,
                    measurement.area_display_unit,
                    measurement.label_alignment.value,
                    measurement.rotation,
                    measurement.color,
                    measurement.line_width,
                )
                for measurement in measurements
            ),
        )
        if signature == self._annotation_overlay_signature:
            return
        self._annotation_overlay_signature = signature
        self.canvas.set_annotations(annotations)
        self.canvas.set_selected_annotation_id(self._selected_annotation_id)
        self.canvas.set_measurements(measurements)

    def _add_text_annotation(
        self,
        node_id: str,
        point: tuple[float, float],
        abbreviation: str,
        full_definition: str,
    ) -> None:
        definition = self._definition_for_label(abbreviation, full_definition)
        annotation = AnnotationObject(
            image_node_id=node_id,
            kind=AnnotationKind.TEXT,
            points=[point],
            text=abbreviation,
            definition_id=definition.id,
            category=definition.category,
            color=self._annotation_color,
            font=self._safe_annotation_font_family(),
            size=self.annotation_font_size.value(),
        )
        self._push_annotation_undo()
        self.project.annotation_definitions[definition.id] = definition
        self._store_annotation(annotation, push_undo=False)

    def _annotation_label_point_clicked(self, x: int, y: int) -> None:
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        abbreviation = self._label_text_from_user()
        if not abbreviation:
            return
        full_definition = self.definition_text.toPlainText().strip() or abbreviation
        self._add_text_annotation(
            node_id,
            self._normalized_annotation_point(x, y),
            abbreviation,
            full_definition,
        )

    def _annotation_font_changed(self, font: QFont) -> None:
        safe_family = safe_font_family(font.family())
        if safe_family == font.family():
            return
        self.annotation_font_family.blockSignals(True)
        self.annotation_font_family.setCurrentFont(QFont(safe_family))
        self.annotation_font_family.blockSignals(False)

    def _safe_annotation_font_family(self) -> str:
        return safe_font_family(self.annotation_font_family.currentFont().family())

    def _annotation_kind_label(self, kind: AnnotationKind) -> str:
        return kind.value.replace("_", " ").title()

    def _label_text_from_user(self) -> str:
        text, accepted = QInputDialog.getText(
            self,
            "Add Label",
            "Label text:",
            text=self.abbreviation_text.toPlainText().strip(),
        )
        if not accepted:
            return ""
        return text.strip()

    def _store_annotation(self, annotation: AnnotationObject, *, push_undo: bool = True) -> None:
        if push_undo:
            self._push_annotation_undo()
        self.project.annotations[annotation.id] = annotation
        self._selected_annotation_id = annotation.id
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _normalized_annotation_point(self, x: int, y: int) -> tuple[float, float]:
        size = self.canvas.image_size()
        if size is None:
            return (0.0, 0.0)
        width, height = size
        normalized_x = max(0.0, min(1.0, float(x) / max(1.0, float(width))))
        normalized_y = max(0.0, min(1.0, float(y) / max(1.0, float(height))))
        return (normalized_x, normalized_y)

    def _annotation_move_started(self, x: int, y: int) -> None:
        if self._annotation_tool != "move":
            return
        self._moving_annotation_id = self._nearest_annotation_id(
            self._normalized_annotation_point(x, y)
        )

    def _annotation_move_finished(
        self, start_x: int, start_y: int, end_x: int, end_y: int
    ) -> None:
        if self._annotation_tool != "move" or self._moving_annotation_id is None:
            return
        annotation = self.project.annotations.get(self._moving_annotation_id)
        self._moving_annotation_id = None
        if annotation is None:
            return
        start = self._normalized_annotation_point(start_x, start_y)
        end = self._normalized_annotation_point(end_x, end_y)
        delta_x = end[0] - start[0]
        delta_y = end[1] - start[1]
        if abs(delta_x) < 1e-12 and abs(delta_y) < 1e-12:
            return
        self._push_annotation_undo()
        if annotation.kind is AnnotationKind.WEDGE:
            annotation.points = [
                (round(point_x + delta_x, 10), round(point_y + delta_y, 10))
                for point_x, point_y in annotation.points
            ]
            annotation.points = normalize_wedge_points(annotation.points)
        else:
            annotation.points = [
                (
                    round(max(0.0, min(1.0, point_x + delta_x)), 10),
                    round(max(0.0, min(1.0, point_y + delta_y)), 10),
                )
                for point_x, point_y in annotation.points
            ]
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _nearest_annotation_id(
        self, point: tuple[float, float], *, max_distance: float = 0.08
    ) -> str | None:
        node_id = self._current_source_node_id()
        if node_id is None:
            return None
        best_id: str | None = None
        best_distance = max_distance
        for annotation in self.project.annotations.values():
            if annotation.image_node_id != node_id or not annotation.visible:
                continue
            for item_point in annotation.points:
                distance = (
                    (item_point[0] - point[0]) ** 2 + (item_point[1] - point[1]) ** 2
                ) ** 0.5
                if distance <= best_distance:
                    best_distance = distance
                    best_id = annotation.id
        return best_id

    def _annotation_snapshot(self) -> dict[str, object]:
        return {
            "annotations": {
                annotation_id: annotation.to_dict()
                for annotation_id, annotation in self.project.annotations.items()
            },
            "definitions": {
                definition_id: definition.to_dict()
                for definition_id, definition in self.project.annotation_definitions.items()
            },
            "selected_annotation_id": self._selected_annotation_id,
        }

    def _restore_annotation_snapshot(self, snapshot: dict[str, object]) -> None:
        annotation_data = snapshot.get("annotations")
        definition_data = snapshot.get("definitions")
        self.project.annotations = {
            str(annotation_id): AnnotationObject.from_dict(dict(data))
            for annotation_id, data in dict(annotation_data or {}).items()
            if isinstance(data, dict)
        }
        self.project.annotation_definitions = {
            str(definition_id): AnnotationDefinition.from_dict(dict(data))
            for definition_id, data in dict(definition_data or {}).items()
            if isinstance(data, dict)
        }
        selected = snapshot.get("selected_annotation_id")
        self._selected_annotation_id = (
            str(selected)
            if selected is not None and str(selected) in self.project.annotations
            else None
        )
        self.canvas.set_selected_annotation_id(self._selected_annotation_id)
        self.project.touch()
        self._rendered_image_cache.clear()
        self._annotation_overlay_signature = None
        self._annotation_table_signature = None
        self._records_signature = None
        self._refresh_annotation_overlay()
        self._refresh_annotation_table()
        self._refresh_records()
        if self.annotationChanged is not None:
            self.annotationChanged()

    def _push_annotation_undo(self) -> None:
        snapshot = self._annotation_snapshot()
        if self._annotation_undo_stack and self._annotation_undo_stack[-1] == snapshot:
            return
        self._annotation_undo_stack.append(snapshot)
        self._annotation_redo_stack.clear()

    def undo(self) -> None:
        if not self._annotation_undo_stack:
            return
        self._annotation_redo_stack.append(self._annotation_snapshot())
        self._restore_annotation_snapshot(self._annotation_undo_stack.pop())

    def redo(self) -> None:
        if not self._annotation_redo_stack:
            return
        self._annotation_undo_stack.append(self._annotation_snapshot())
        self._restore_annotation_snapshot(self._annotation_redo_stack.pop())

    def _annotation_transform_finished(self) -> None:
        self._annotation_transform_undo_open = False

    def _open_annotation_color_dialog(self) -> None:
        dialog = QColorDialog(QColor(self._annotation_color), self)
        dialog.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dialog.setWindowTitle("Change Annotation Color")
        if dialog.exec() != QColorDialog.DialogCode.Accepted:
            return
        color = dialog.selectedColor()
        if color.isValid():
            self._annotation_color = color.name(QColor.NameFormat.HexRgb)
            self._update_annotation_color_button()
            self._apply_selected_annotation_style()

    def _update_annotation_color_button(self) -> None:
        self.annotation_color_button.setText("")
        self.annotation_color_button.setStyleSheet(
            "QPushButton {"
            "border: 1px solid #151515;"
            f"background-color: {self._annotation_color};"
            "}"
        )

