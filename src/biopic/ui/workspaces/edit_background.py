"""Uniform-background workflow for the edit workspace."""

from __future__ import annotations

import numpy as np
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QVBoxLayout

from biopic.imaging.layer_buffers import set_layer_buffers
from biopic.models.editing import EditLayer, LayerContentKind
from biopic.native.adjustments_backend import (
    uniform_background_outside_selection as native_uniform_background,
)
from biopic.ui.workspace_helpers.background import (
    background_pixels_from_selection,
    mean_background_color,
)


class EditBackgroundMixin:
    """Uniform-background layer creation helpers."""

    def create_uniform_background_outside_selection_layer(self) -> None:
        """Create a solid background layer outside the active selection."""
        if (
            self._current_pixels is None
            or self._base_pixels is None
            or self._current_asset_id is None
            or self._current_source_node_id is None
        ):
            return
        options = self._uniform_background_options()
        if options is None:
            return
        commit_pending = getattr(self.canvas, "commit_pending_free_selection", None)
        if callable(commit_pending):
            commit_pending()
        if self._selection_rect is None:
            self._status("Create a selection around the organism first.")
            return
        smooth_transition, transition_px = options
        mask = self._selection_mask()
        if mask is None or not np.any(mask):
            self._status("Create a selection around the organism first.")
            return
        outside = ~mask
        if not np.any(outside):
            self._status("Selection covers the whole image; no outside background was found.")
            return
        before = self._snapshot_edit_state()
        source_node = self._current_source_node_id
        base = self._base_pixels
        native_background = native_uniform_background(
            base,
            mask,
            transition_px if smooth_transition else 0,
        )
        if native_background is not None:
            background_pixels, background_alpha, _bg_color = native_background
        else:
            bg_color = mean_background_color(base, outside)
            background_pixels = background_pixels_from_selection(
                base,
                bg_color,
                mask,
                transition_px if smooth_transition else 0,
            )
            background_alpha = (~mask).astype(np.float32)
        organism_layer = self._ensure_active_source_as_organism_layer(mask)
        background_layer = self._uniform_background_layer(source_node)
        if background_layer is None:
            for layer in self.project.edit_layers.values():
                if layer.source_node_id in {None, source_node}:
                    layer.order += 1
            background_layer = EditLayer(
                name="Uniform Background",
                source_node_id=source_node,
                content_kind=LayerContentKind.RASTER,
                order=0,
            )
            self.project.edit_layers[background_layer.id] = background_layer
        background_layer.name = "Uniform Background"
        background_layer.content_kind = LayerContentKind.RASTER
        background_layer.order = 0
        background_layer.set_content_pixels(background_pixels)
        background_layer.set_alpha_pixels(background_alpha)
        if organism_layer is not None:
            organism_layer.order = 1
        original_layer = self._hidden_original_layer(source_node)
        if original_layer is not None:
            original_layer.visible = False
            original_layer.order = 2
        self._current_layer_id = background_layer.id
        self.project.active_edit_layers[source_node] = background_layer.id
        set_layer_buffers(background_layer.id, background_pixels, background_alpha)
        self._finish_command("uniform background outside selection", before)
        self._invalidate_edit_composite_cache()
        self._refresh_layers()
        self._render_current_adjustment_preview()
        if self.editApplied is not None:
            self.editApplied()

    def _uniform_background_options(self) -> tuple[bool, int] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Uniform Background Outside Selection")
        layout = QVBoxLayout(dialog)
        smooth_check = QCheckBox("Smooth transition")
        transition_spin = QSpinBox()
        transition_spin.setRange(1, 512)
        transition_spin.setValue(12)
        smooth_check.setChecked(True)
        transition_spin.setEnabled(True)
        smooth_check.toggled.connect(transition_spin.setEnabled)
        form = QFormLayout()
        form.addRow(smooth_check)
        form.addRow("Transition width (px)", transition_spin)
        layout.addLayout(form)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return smooth_check.isChecked(), int(transition_spin.value())

    def _ensure_active_source_as_organism_layer(self, mask: np.ndarray) -> EditLayer | None:
        if self._base_pixels is None or self._current_source_node_id is None:
            return None
        source_node = self._current_source_node_id
        self._ensure_hidden_original_layer(source_node)
        organism_layers = [
            layer
            for layer in self.project.edit_layers.values()
            if layer.source_node_id == source_node and layer.name == "Selected Organism"
        ]
        if organism_layers:
            layer = organism_layers[0]
        else:
            for item in self.project.edit_layers.values():
                if item.source_node_id in {None, source_node} and item.name != "Uniform Background":
                    item.order += 1
            layer = EditLayer(
                name="Selected Organism",
                source_node_id=source_node,
                content_kind=LayerContentKind.RASTER,
                order=1,
            )
            self.project.edit_layers[layer.id] = layer
        layer.name = "Selected Organism"
        layer.content_kind = LayerContentKind.RASTER
        layer.set_alpha_pixels(mask.astype(np.float32))
        layer.set_content_pixels(self._base_pixels.copy())
        set_layer_buffers(layer.id, self._base_pixels.copy(), mask.astype(np.float32))
        return layer

    def _ensure_hidden_original_layer(self, source_node: str) -> EditLayer:
        original_layers = [
            layer
            for layer in self.project.edit_layers.values()
            if layer.source_node_id == source_node and layer.name == "Original Image"
        ]
        if original_layers:
            layer = original_layers[0]
        else:
            source_layers = [
                item
                for item in self.project.edit_layers.values()
                if item.source_node_id == source_node and item.content_kind is LayerContentKind.SOURCE
            ]
            layer = source_layers[0] if source_layers else EditLayer(
                name="Original Image",
                source_node_id=source_node,
                content_kind=LayerContentKind.SOURCE,
                order=2,
            )
            self.project.edit_layers[layer.id] = layer
        layer.name = "Original Image"
        layer.content_kind = LayerContentKind.SOURCE
        layer.visible = False
        layer.order = max(layer.order, 2)
        return layer

    def _uniform_background_layer(self, source_node: str) -> EditLayer | None:
        for layer in self.project.edit_layers.values():
            if layer.source_node_id == source_node and layer.name == "Uniform Background":
                return layer
        return None

    def _hidden_original_layer(self, source_node: str) -> EditLayer | None:
        for layer in self.project.edit_layers.values():
            if layer.source_node_id == source_node and layer.name == "Original Image":
                return layer
        return None
