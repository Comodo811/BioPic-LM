"""Clipboard, layer, and external-editor commands for the edit workspace."""

from __future__ import annotations

import numpy as np
from PySide6.QtCore import QProcess
from PySide6.QtWidgets import QListWidgetItem

from biopic.imaging.layer_buffers import set_layer_buffers, share_layer_buffers
from biopic.integrations.gpl_editors import (
    external_edit_cache_path,
    find_external_editor,
    read_external_edit_image,
    write_external_edit_image,
)
from biopic.models.editing import BlendMode, EditLayer, LayerContentKind, LayerLock
from biopic.ui.workspace_helpers.layers import layer_metadata as _layer_metadata


class EditLayerCommandsMixin:
    """Layer, clipboard, and external-editor actions."""

    def copy_selection(self) -> None:
        """Copy the current selection, or the full rendered image if no selection exists."""
        if self._current_pixels is None:
            return
        if self._selection_rect is None:
            self._clipboard_pixels = self._current_pixels.copy()
            self._clipboard_alpha = np.ones(self._current_pixels.shape[:2], dtype=np.float32)
            self.history.appendPlainText("copy: full image")
            return
        x, y, width, height = self._selection_rect
        coverage = self._selection_coverage_mask()
        self._clipboard_pixels = self._current_pixels[y : y + height, x : x + width].copy()
        if coverage is None:
            self._clipboard_alpha = np.ones((height, width), dtype=np.float32)
        else:
            self._clipboard_alpha = coverage[y : y + height, x : x + width].astype(np.float32)
        self.history.appendPlainText(f"copy: {width} x {height}px")

    def paste_as_layer(self) -> None:
        """Paste copied pixels into a new layer and preview the pasted raster."""
        if self._clipboard_pixels is None or self._current_pixels is None:
            return
        if self._current_asset_id is None:
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            return
        before = self._snapshot_edit_state()
        height = min(self._current_pixels.shape[0], self._clipboard_pixels.shape[0])
        width = min(self._current_pixels.shape[1], self._clipboard_pixels.shape[1])
        content = np.zeros_like(self._current_pixels)
        content[:height, :width] = self._clipboard_pixels[:height, :width]
        alpha = np.zeros(self._current_pixels.shape[:2], dtype=np.float32)
        if self._clipboard_alpha is None:
            alpha[:height, :width] = 1.0
        else:
            alpha[:height, :width] = self._clipboard_alpha[:height, :width]
        layer = EditLayer(
            name=f"Pasted Layer {len(self.project.edit_layers) + 1}",
            source_node_id=source_node,
            content_kind=LayerContentKind.RASTER,
            order=self._next_layer_order(source_node),
        )
        layer.set_content_pixels(content)
        layer.set_alpha_pixels(alpha)
        self.project.edit_layers[layer.id] = layer
        self.project.active_edit_layers[source_node] = layer.id
        self._current_layer_id = layer.id
        set_layer_buffers(layer.id, content, alpha)
        self.project.touch()
        self._finish_command("paste selection as layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()

    def open_external_editor(self) -> None:
        """Launch the active image in a real GPL editor for a lossless round trip."""
        if self._current_asset_id is None or self._base_pixels is None:
            self._status("Select an image before opening an external editor.")
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            self._status("The selected image has no source node.")
            return
        editor = find_external_editor()
        if editor is None:
            self._status("GIMP or Krita was not found. Install one or add it to PATH.")
            return
        handoff_path = external_edit_cache_path(self.project.id, self._current_asset_id)
        write_external_edit_image(handoff_path, self._render_external_edit_source(source_node))
        launched = QProcess.startDetached(str(editor.path), [str(handoff_path)])
        if not launched:
            self._status(f"Could not launch {editor.name}: {editor.path}")
            return
        self._pending_external_edit_path = handoff_path
        self._status(f"Opened {handoff_path.name} in {editor.name}. Save it there, then import.")

    def import_external_editor_result(self) -> None:
        """Import the saved GIMP/Krita handoff image as a new unlocked raster layer."""
        if self._current_asset_id is None or self._base_pixels is None:
            self._status("Select an image before importing an external edit.")
            return
        source_node = self.project.source_node_id_for_asset(self._current_asset_id)
        if source_node is None:
            self._status("The selected image has no source node.")
            return
        handoff_path = self._pending_external_edit_path or external_edit_cache_path(
            self.project.id, self._current_asset_id
        )
        if not handoff_path.exists():
            self._status("No saved external edit file was found.")
            return
        before = self._snapshot_edit_state()
        pixels, alpha = read_external_edit_image(handoff_path, self._base_pixels)
        layer = EditLayer(
            name=f"External Edit {len(self.project.edit_layers) + 1}",
            source_node_id=source_node,
            content_kind=LayerContentKind.RASTER,
            order=self._next_layer_order(source_node),
        )
        layer.set_content_pixels(pixels)
        if alpha is not None:
            layer.set_alpha_pixels(alpha)
        self.project.edit_layers[layer.id] = layer
        self.project.active_edit_layers[source_node] = layer.id
        self._current_layer_id = layer.id
        self.project.touch()
        self._finish_command("import external GPL editor layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        self._status(f"Imported {handoff_path.name} as an unlocked layer.")
        if self.editApplied is not None:
            self.editApplied()

    def toggle_selected_adjustment(self) -> None:
        """Enable or disable the selected adjustment layer."""
        current = self.adjustment_list.currentItem()
        if current is None:
            return
        adjustment = self.project.adjustment_layers.get(str(current.data(256)))
        if adjustment is None:
            return
        self.project.update_adjustment_layer(adjustment.id, enabled=not adjustment.enabled)
        self._render_current_adjustment_preview()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

    def delete_selected_adjustment(self) -> None:
        """Delete the selected adjustment layer record."""
        current = self.adjustment_list.currentItem()
        if current is None:
            return
        self.project.adjustment_layers.pop(str(current.data(256)), None)
        self.project.touch()
        self._refresh_adjustments()
        if self.editApplied is not None:
            self.editApplied()

    def remove_selected_layer(self) -> None:
        """Remove the selected layer record."""
        current = self.layers_list.currentItem()
        if current is None:
            return
        layer = self.project.edit_layers.get(str(current.data(256)))
        if layer is None or layer.locked:
            self._status("Cannot delete a locked layer.")
            return
        before = self._snapshot_edit_state()
        self.project.edit_layers.pop(layer.id, None)
        self.project.touch()
        self._finish_command("delete layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()

    def duplicate_selected_layer(self) -> None:
        """Duplicate the selected layer record."""
        current = self.layers_list.currentItem()
        if current is None:
            return
        layer = self.project.edit_layers.get(str(current.data(256)))
        if layer is None:
            return
        before = self._snapshot_edit_state()
        duplicate = EditLayer(
            name=f"{layer.name} copy",
            source_node_id=layer.source_node_id,
            layer_type=layer.layer_type,
            content_kind=layer.content_kind,
            visible=layer.visible,
            opacity=layer.opacity,
            blend_mode=layer.blend_mode,
            mask_node_id=layer.mask_node_id,
            mask_content=layer.mask_content,
            mask_enabled=layer.mask_enabled,
            mask_edit_state=layer.mask_edit_state,
            group_composite_mode=layer.group_composite_mode,
            parent_id=layer.parent_id,
            offset_x=layer.offset_x,
            offset_y=layer.offset_y,
            order=self._next_layer_order(layer.source_node_id),
            content=layer.content,
            alpha=layer.alpha,
        )
        share_layer_buffers(layer.id, duplicate.id)
        self.project.edit_layers[duplicate.id] = duplicate
        if layer.source_node_id is not None:
            self.project.active_edit_layers[layer.source_node_id] = duplicate.id
            self._current_layer_id = duplicate.id
        self.project.touch()
        self._finish_command("duplicate layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()

    def raise_selected_layer(self) -> None:
        """Move selected layer up in the layer stack."""
        self._move_selected_layer(-1)

    def lower_selected_layer(self) -> None:
        """Move selected layer down in the layer stack."""
        self._move_selected_layer(1)

    def _move_selected_layer(self, direction: int) -> None:
        current = self.layers_list.currentItem()
        if current is None:
            return
        layer_ids = list(self.project.edit_layers)
        index = layer_ids.index(str(current.data(256)))
        target = max(0, min(len(layer_ids) - 1, index + direction))
        if index == target:
            return
        layer = self.project.edit_layers[layer_ids[index]]
        if layer.locked:
            self._status("Cannot move a locked layer.")
            return
        before = self._snapshot_edit_state()
        layer_ids[index], layer_ids[target] = layer_ids[target], layer_ids[index]
        for order, layer_id in enumerate(layer_ids):
            self.project.edit_layers[layer_id].order = order
        self.project.edit_layers = {
            layer_id: self.project.edit_layers[layer_id] for layer_id in layer_ids
        }
        self.project.touch()
        self._finish_command("reorder layer", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()

    def _selected_layer_changed(
        self,
        current: QListWidgetItem | None,
        _previous: QListWidgetItem | None = None,
    ) -> None:
        if current is None:
            return
        layer = self.project.edit_layers.get(str(current.data(256)))
        if layer is None:
            return
        self._current_layer_id = layer.id
        if layer.source_node_id is not None:
            self.project.active_edit_layers[layer.source_node_id] = layer.id
        self.layer_opacity_spin.blockSignals(True)
        self.layer_blend_combo.blockSignals(True)
        self.layer_visible_check.blockSignals(True)
        self.layer_lock_check.blockSignals(True)
        self.layer_position_lock_check.blockSignals(True)
        self.layer_visibility_lock_check.blockSignals(True)
        self.layer_opacity_spin.setValue(layer.opacity * 100.0)
        self.layer_blend_combo.setCurrentText(layer.blend_mode.value)
        self.layer_visible_check.setChecked(layer.visible)
        self.layer_lock_check.setChecked(layer.locked or LayerLock.PIXELS in layer.lock_flags)
        self.layer_position_lock_check.setChecked(LayerLock.POSITION in layer.lock_flags)
        self.layer_visibility_lock_check.setChecked(LayerLock.VISIBILITY in layer.lock_flags)
        self.layer_opacity_spin.blockSignals(False)
        self.layer_blend_combo.blockSignals(False)
        self.layer_visible_check.blockSignals(False)
        self.layer_lock_check.blockSignals(False)
        self.layer_position_lock_check.blockSignals(False)
        self.layer_visibility_lock_check.blockSignals(False)

    def _apply_layer_controls(self, _value: object = None) -> None:
        current = self.layers_list.currentItem()
        if current is None:
            return
        layer = self.project.edit_layers.get(str(current.data(256)))
        if layer is None:
            return
        before = _layer_metadata(layer)
        previous_visible = layer.visible
        previous_opacity = layer.opacity
        previous_blend = layer.blend_mode
        layer.opacity = self.layer_opacity_spin.value() / 100.0
        requested_visible = self.layer_visible_check.isChecked()
        if requested_visible != layer.visible and LayerLock.VISIBILITY in layer.lock_flags:
            self.layer_visible_check.blockSignals(True)
            self.layer_visible_check.setChecked(layer.visible)
            self.layer_visible_check.blockSignals(False)
            self._status("Cannot change visibility on a visibility-locked layer.")
            return
        layer.visible = requested_visible
        if self.layer_lock_check.isChecked():
            layer.lock_flags.discard(LayerLock.ALL)
            layer.lock_flags.add(LayerLock.PIXELS)
        else:
            layer.lock_flags.discard(LayerLock.ALL)
            layer.lock_flags.discard(LayerLock.PIXELS)
        if self.layer_position_lock_check.isChecked():
            layer.lock_flags.add(LayerLock.POSITION)
        else:
            layer.lock_flags.discard(LayerLock.POSITION)
        if self.layer_visibility_lock_check.isChecked():
            layer.lock_flags.add(LayerLock.VISIBILITY)
        else:
            layer.lock_flags.discard(LayerLock.VISIBILITY)
        layer.blend_mode = BlendMode(self.layer_blend_combo.currentText())
        layer.bump_generation()
        self.project.touch()
        self._finish_layer_metadata_command("change layer properties", layer, before)
        self._update_current_layer_item(layer)
        needs_render = (
            previous_visible != layer.visible
            or previous_opacity != layer.opacity
            or previous_blend != layer.blend_mode
        )
        if needs_render:
            self._invalidate_edit_composite_cache()
            self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()
