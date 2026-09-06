"""Uniform-background workflow for the edit workspace."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PySide6.QtWidgets import QCheckBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox, QVBoxLayout

from biopic.imaging.layer_buffers import set_layer_buffers
from biopic.models.editing import EditLayer, LayerContentKind
from biopic.native.adjustments_backend import (
    uniform_background_outside_selection as native_uniform_background,
)
from biopic.ui.workspace_helpers.background import (
    global_textured_background_from_selection,
    healed_textured_background_from_selection,
)


class EditBackgroundMixin:
    """Uniform-background layer creation helpers."""

    def create_uniform_background_outside_selection_layer(self) -> None:
        """Create a cloned-texture background layer outside the active selection."""
        self._create_uniform_background_outside_selection_layer(
            layer_name="Uniform Background Outside Selection (Stamp)",
            command_name="uniform background outside selection",
            progress_message="Creating uniform background...",
            options_title="Uniform Background Outside Selection (Stamp)",
            synthesizer=self._stamp_background_layer_pixels,
        )

    def create_healed_uniform_background_outside_selection_layer(self) -> None:
        """Create a healed-texture background layer outside the active selection."""
        self._create_uniform_background_outside_selection_layer(
            layer_name="Uniform Background Outside Selection (Heal)",
            command_name="healed uniform background outside selection",
            progress_message="Creating healed uniform background...",
            options_title="Uniform Background Outside Selection (Heal)",
            synthesizer=healed_textured_background_from_selection,
        )

    def _create_uniform_background_outside_selection_layer(
        self,
        *,
        layer_name: str,
        command_name: str,
        progress_message: str,
        options_title: str,
        synthesizer: Callable[..., np.ndarray | tuple[np.ndarray, np.ndarray]],
    ) -> None:
        """Create a background layer outside the active selection."""
        if (
            self._current_pixels is None
            or self._base_pixels is None
            or self._current_asset_id is None
            or self._current_source_node_id is None
        ):
            return
        options = self._uniform_background_options(options_title)
        if options is None:
            return
        commit_pending = getattr(self.canvas, "commit_pending_free_selection", None)
        if callable(commit_pending):
            commit_pending()
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
        try:
            background_result = self._run_computation_with_progress(
                progress_message,
                lambda progress: synthesizer(
                    base,
                    mask,
                    transition_px if smooth_transition else 0,
                    progress=progress,
                ),
                accepts_progress=True,
            )
        except Exception as exc:
            self._status(f"Uniform background creation failed: {exc}")
            return
        if isinstance(background_result, tuple) and len(background_result) == 2:
            background_pixels, background_alpha = background_result
        elif isinstance(background_result, np.ndarray):
            background_pixels = background_result
            background_alpha = (~mask).astype(np.float32)
        else:
            self._status("Uniform background creation failed.")
            return
        if not isinstance(background_pixels, np.ndarray) or not isinstance(background_alpha, np.ndarray):
            self._status("Uniform background creation failed.")
            return

        def create_layer() -> None:
            organism_layer = self._ensure_active_source_as_organism_layer(mask)
            background_layer = self._uniform_background_layer(source_node, layer_name)
            if background_layer is None:
                for layer in self.project.edit_layers.values():
                    if layer.source_node_id in {None, source_node}:
                        layer.order += 1
                background_layer = EditLayer(
                    name=layer_name,
                    source_node_id=source_node,
                    content_kind=LayerContentKind.RASTER,
                    order=0,
                )
                self.project.edit_layers[background_layer.id] = background_layer
            background_layer.name = layer_name
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
            self._finish_command(command_name, before)
            self._invalidate_edit_composite_cache()
            self._refresh_layers()
            self._render_current_adjustment_preview()
            if self.editApplied is not None:
                self.editApplied()

        create_layer()

    def _stamp_background_layer_pixels(
        self,
        image: np.ndarray,
        selection_mask: np.ndarray,
        transition_px: int,
        *,
        progress: Callable[[str, float], None] | None = None,
    ) -> tuple[np.ndarray, np.ndarray] | np.ndarray:
        if progress is not None:
            progress("Creating uniform background", 0.05)
        native_background = native_uniform_background(image, selection_mask, transition_px)
        if native_background is not None:
            background_pixels, background_alpha, _bg_color = native_background
            if progress is not None:
                progress("Background complete", 1.0)
            return background_pixels, background_alpha.astype(np.float32, copy=False)
        return global_textured_background_from_selection(
            image,
            selection_mask,
            transition_px,
            progress=progress,
        )

    def _uniform_background_options(
        self,
        title: str = "Uniform Background Outside Selection",
    ) -> tuple[bool, int] | None:
        dialog = QDialog(self)
        dialog.setWindowTitle(title)
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
                if item.source_node_id in {None, source_node} and item.name not in {
                    "Uniform Background",
                    "Healed Uniform Background",
                    "Uniform Background Outside Selection (Stamp)",
                    "Uniform Background Outside Selection (Heal)",
                }:
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

    def _uniform_background_layer(self, source_node: str, layer_name: str) -> EditLayer | None:
        for layer in self.project.edit_layers.values():
            if layer.source_node_id == source_node and layer.name == layer_name:
                return layer
        return None

    def _hidden_original_layer(self, source_node: str) -> EditLayer | None:
        for layer in self.project.edit_layers.values():
            if layer.source_node_id == source_node and layer.name == "Original Image":
                return layer
        return None
