"""Layer and adjustment panel refresh helpers for the edit workspace."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QHBoxLayout, QLabel, QListWidgetItem, QToolButton, QWidget

from biopic.models.editing import AdjustmentLayer, EditLayer, LayerLock
from biopic.ui.workspace_helpers.layers import (
    layer_icon as _layer_icon,
    layer_label as _layer_label,
)
from biopic.ui.workspace_helpers.operations import operation_layer_name as _operation_layer_name


class EditLayerPanelsMixin:
    """Refresh and edit helpers for the layer and adjustment side panels."""

    def _status(self, message: str) -> None:
        self.history.appendPlainText(message)

    def _refresh_history(self) -> None:
        lines = [
            f"{node.operation}: {node.parameters}"
            for node in self.project.graph.nodes.values()
            if node.operation.startswith("edit.")
        ]
        lines.extend(
            str(item.get("operation", "edit command"))
            for item in self.project.history
            if isinstance(item, dict)
        )
        self.history.setPlainText("\n".join(lines))

    def _refresh_layers(self) -> None:
        active_layer_id = self._current_layer_id
        self.layers_list.clear()
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        selected_row = -1
        for layer in sorted(self.project.edit_layers.values(), key=lambda item: item.order):
            if source_node is None or layer.source_node_id in {None, source_node}:
                item = QListWidgetItem("" if layer.filter_operation else _layer_label(layer))
                item.setData(256, layer.id)
                self.layers_list.addItem(item)
                if layer.filter_operation:
                    row = self._filter_row_widget(layer)
                    item.setSizeHint(row.sizeHint())
                    self.layers_list.setItemWidget(item, row)
                else:
                    icon = _layer_icon(layer)
                    if icon is not None:
                        item.setIcon(icon)
                if layer.id == active_layer_id:
                    selected_row = self.layers_list.count() - 1
        if source_node is not None:
            for layer in self.project.adjustment_layers_for_image(source_node):
                item = QListWidgetItem()
                item.setData(256, layer.id)
                item.setData(257, "adjustment")
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsDragEnabled)
                self.layers_list.addItem(item)
                row = self._adjustment_row_widget(layer)
                item.setSizeHint(row.sizeHint())
                self.layers_list.setItemWidget(item, row)
        if selected_row >= 0:
            self.layers_list.setCurrentRow(selected_row)
        if self.layers_list.count() and self.layers_list.currentRow() < 0:
            self.layers_list.setCurrentRow(0)

    def _update_current_layer_item(self, layer: EditLayer) -> None:
        for index in range(self.layers_list.count()):
            item = self.layers_list.item(index)
            if str(item.data(256)) == layer.id:
                if self.layers_list.itemWidget(item) is None:
                    item.setText(_layer_label(layer))
                    icon = _layer_icon(layer)
                    item.setIcon(icon if icon is not None else QIcon())
                else:
                    item.setText("")
                break
        self.layer_opacity_spin.blockSignals(True)
        self.layer_opacity_slider.blockSignals(True)
        self.layer_blend_combo.blockSignals(True)
        self.layer_visible_check.blockSignals(True)
        self.layer_lock_check.blockSignals(True)
        self.layer_position_lock_check.blockSignals(True)
        self.layer_visibility_lock_check.blockSignals(True)
        self.layer_opacity_spin.setValue(layer.opacity * 100.0)
        self.layer_opacity_slider.setValue(round(layer.opacity * 100.0))
        self.layer_blend_combo.setCurrentText(layer.blend_mode.value)
        self.layer_visible_check.setChecked(layer.visible)
        self.layer_lock_check.setChecked(layer.locked or LayerLock.PIXELS in layer.lock_flags)
        self.layer_position_lock_check.setChecked(LayerLock.POSITION in layer.lock_flags)
        self.layer_visibility_lock_check.setChecked(LayerLock.VISIBILITY in layer.lock_flags)
        self.layer_opacity_spin.blockSignals(False)
        self.layer_opacity_slider.blockSignals(False)
        self.layer_blend_combo.blockSignals(False)
        self.layer_visible_check.blockSignals(False)
        self.layer_lock_check.blockSignals(False)
        self.layer_position_lock_check.blockSignals(False)
        self.layer_visibility_lock_check.blockSignals(False)

    def _refresh_adjustments(self) -> None:
        self.adjustment_list.clear()
        source_node = (
            self.project.source_node_id_for_asset(self._current_asset_id)
            if self._current_asset_id is not None
            else None
        )
        layers = sorted(self.project.adjustment_layers.values(), key=lambda layer: layer.order)
        for layer in layers:
            if source_node is None or layer.image_node_id == source_node:
                state = "on" if layer.enabled else "off"
                text = f"{state} | {layer.name}"
                item = QListWidgetItem()
                item.setData(256, layer.id)
                self.adjustment_list.addItem(item)
                row = self._adjustment_row_widget(layer, text=text)
                item.setSizeHint(row.sizeHint())
                self.adjustment_list.setItemWidget(item, row)

    def _settings_row_widget(
        self,
        layer_id: str,
        label_text: str,
        *,
        enabled: bool = True,
        tooltip: str = "Edit layer settings",
        edit_callback: Callable[[str], None],
    ) -> QWidget:
        row = QWidget()
        row_layout = QHBoxLayout(row)
        row_layout.setContentsMargins(6, 2, 4, 2)
        row_layout.setSpacing(6)
        label = QLabel(label_text, row)
        label.setEnabled(enabled)
        row_layout.addWidget(label, 1)
        settings_button = QToolButton(row)
        settings_button.setToolTip(tooltip)
        settings_button.setIcon(QIcon(str(Path(__file__).resolve().parents[4] / "icons/settings_icon.png")))
        settings_button.setIconSize(QSize(18, 18))
        settings_button.setAutoRaise(True)
        settings_button.clicked.connect(
            lambda _checked=False, item_id=layer_id: QTimer.singleShot(
                0,
                lambda: edit_callback(item_id),
            )
        )
        row_layout.addWidget(settings_button, 0, Qt.AlignmentFlag.AlignRight)
        return row

    def _adjustment_row_widget(
        self,
        layer: AdjustmentLayer,
        *,
        text: str | None = None,
    ) -> QWidget:
        state = "on" if layer.enabled else "off"
        return self._settings_row_widget(
            layer.id,
            text or f"{state} | {layer.name}",
            enabled=layer.enabled,
            tooltip="Edit adjustment settings",
            edit_callback=self.edit_adjustment_layer,
        )

    def _filter_row_widget(self, layer: EditLayer) -> QWidget:
        operation = layer.filter_operation or ""
        return self._settings_row_widget(
            layer.id,
            _operation_layer_name(operation) if operation else _layer_label(layer),
            enabled=layer.visible,
            tooltip="Edit filter settings",
            edit_callback=self.edit_filter_layer,
        )

    def edit_adjustment_layer(self, layer_id: str) -> None:
        """Open the matching settings dialog for an existing adjustment layer."""
        layer = self.project.adjustment_layers.get(layer_id)
        if layer is None:
            return
        parameters = dict(layer.parameters)
        if layer.operation == "levels":
            self.open_levels_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.operation == "gamma":
            self.open_gamma_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.operation == "curve":
            self.open_curves_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.operation == "white_balance":
            self.open_white_balance_dialog(layer_id=layer.id, initial_parameters=parameters)
        elif layer.operation == "color_saturation":
            self.open_color_saturation_dialog(layer_id=layer.id, initial_parameters=parameters)
        else:
            self._status(f"{layer.name} has no editable settings dialog.")

    def edit_filter_layer(self, layer_id: str) -> None:
        """Open the matching settings dialog for an existing raster filter layer."""
        layer = self.project.edit_layers.get(layer_id)
        if layer is None or layer.filter_operation is None:
            return
        self.open_filter_layer_dialog(layer.id)

    def _update_adjustment_layer_parameters(
        self,
        layer_id: str,
        parameters: dict[str, object],
    ) -> None:
        """Update one adjustment layer and record it as an undoable command."""
        layer = self.project.adjustment_layers.get(layer_id)
        if layer is None:
            return
        before = self._snapshot_edit_state()
        self.project.update_adjustment_layer(layer.id, dict(parameters), enabled=True)
        self._finish_command(f"update {layer.operation.replace('_', ' ')} adjustment", before)
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

