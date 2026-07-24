"""Undo, redo, and edit-command restoration helpers."""

from __future__ import annotations

import numpy as np

from biopic.imaging.layer_buffers import layer_alpha_buffer, layer_content_buffer, set_layer_buffers
from biopic.models.editing import EditLayer, LayerContentKind, payload_to_pixels
from biopic.ui.workspace_helpers.layers import (
    apply_layer_metadata as _apply_layer_metadata,
    layer_metadata as _layer_metadata,
    layer_visual_metadata_changed as _layer_visual_metadata_changed,
    metadata_int as _metadata_int,
)


class EditHistoryMixin:
    """Undo/redo and command snapshot support for edit workspaces."""

    def undo(self) -> None:
        """Restore the previous edit-layer command snapshot."""
        if not self.project.undo_stack:
            return
        entry = self.project.undo_stack.pop()
        if entry.get("kind") == "layer_metadata":
            redo_entry = self._inverse_layer_metadata_entry(entry)
            if redo_entry is not None:
                self.project.redo_stack.append(redo_entry)
            self._restore_layer_metadata_entry(entry)
            return
        if entry.get("kind") == "tile_paint":
            self.project.redo_stack.append(entry)
            self._restore_tile_paint_entry(entry, use_after=False)
            return
        self.project.redo_stack.append(
            {
                "description": entry.get("description", "redo"),
                "state": self._snapshot_edit_state(),
            }
        )
        state = entry.get("state")
        if isinstance(state, dict):
            self._restore_edit_state(state)

    def redo(self) -> None:
        """Restore the next edit-layer command snapshot."""
        if not self.project.redo_stack:
            return
        entry = self.project.redo_stack.pop()
        if entry.get("kind") == "layer_metadata":
            undo_entry = self._inverse_layer_metadata_entry(entry)
            if undo_entry is not None:
                self.project.undo_stack.append(undo_entry)
            self._restore_layer_metadata_entry(entry)
            return
        if entry.get("kind") == "tile_paint":
            self.project.undo_stack.append(entry)
            self._restore_tile_paint_entry(entry, use_after=True)
            return
        self.project.undo_stack.append(
            {
                "description": entry.get("description", "undo"),
                "state": self._snapshot_edit_state(),
            }
        )
        state = entry.get("state")
        if isinstance(state, dict):
            self._restore_edit_state(state)

    def _snapshot_edit_state(self) -> dict[str, object]:
        return {
            "edit_layers": [layer.to_dict() for layer in self.project.edit_layers.values()],
            "active_edit_layers": dict(self.project.active_edit_layers),
        }

    def _restore_edit_state(self, state: dict[str, object]) -> None:
        layers_data = state.get("edit_layers", [])
        if isinstance(layers_data, list):
            layers = [EditLayer.from_dict(item) for item in layers_data if isinstance(item, dict)]
            self.project.edit_layers = {layer.id: layer for layer in layers}
        active_data = state.get("active_edit_layers", {})
        if isinstance(active_data, dict):
            self.project.active_edit_layers = {
                str(key): str(value) for key, value in active_data.items()
            }
        self._current_layer_id = (
            self.project.active_edit_layers.get(self._current_source_node_id)
            if self._current_source_node_id is not None
            else None
        )
        self.project.touch()
        self._invalidate_layer_array_cache()
        self._invalidate_edit_composite_cache()
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_history()

    def _finish_command(self, description: str, before: dict[str, object]) -> None:
        after = self._snapshot_edit_state()
        if before == after:
            return
        self.project.touch()
        self.project.undo_stack.append({"description": description, "state": before})
        self.project.redo_stack.clear()
        self.project.history.append({"operation": description})

    def _finish_layer_metadata_command(
        self,
        description: str,
        layer: EditLayer,
        before: dict[str, object],
    ) -> None:
        after = _layer_metadata(layer)
        if before == after:
            return
        self.project.undo_stack.append(
            {
                "kind": "layer_metadata",
                "description": description,
                "layer_id": layer.id,
                "before": before,
                "after": after,
            }
        )
        self.project.redo_stack.clear()
        self.project.history.append({"operation": description})

    def _restore_layer_metadata_entry(self, entry: dict[str, object]) -> None:
        layer = self.project.edit_layers.get(str(entry.get("layer_id")))
        metadata = entry.get("before")
        if layer is None or not isinstance(metadata, dict):
            return
        before = _layer_metadata(layer)
        _apply_layer_metadata(layer, metadata)
        self.project.touch()
        self._update_current_layer_item(layer)
        if _layer_visual_metadata_changed(before, _layer_metadata(layer)):
            self._invalidate_edit_composite_cache()
            self._render_current_adjustment_preview()

    def _restore_tile_paint_entry(self, entry: dict[str, object], *, use_after: bool) -> None:
        layer = self.project.edit_layers.get(str(entry.get("layer_id")))
        if layer is None:
            return
        content = layer_content_buffer(layer.id)
        if content is None:
            content = layer.content_pixels()
        alpha = layer_alpha_buffer(layer.id)
        if alpha is None:
            alpha = layer.alpha_pixels()
        if content is None or alpha is None:
            if self._base_pixels is None:
                return
            content = np.zeros_like(self._base_pixels)
            alpha = np.zeros(self._base_pixels.shape[:2], dtype=np.float32)
        patches = entry.get("patches", [])
        if not isinstance(patches, list):
            return
        content_key = "content_after" if use_after else "content_before"
        alpha_key = "alpha_after" if use_after else "alpha_before"
        for patch in patches:
            if not isinstance(patch, dict):
                continue
            x = _metadata_int(patch, "x", 0)
            y = _metadata_int(patch, "y", 0)
            content_patch = payload_to_pixels(patch.get(content_key))
            alpha_patch = payload_to_pixels(patch.get(alpha_key))
            if content_patch is not None:
                height, width = content_patch.shape[:2]
                content[y : y + height, x : x + width] = content_patch
            if alpha_patch is not None:
                height, width = alpha_patch.shape[:2]
                alpha[y : y + height, x : x + width] = alpha_patch
        layer.content_kind = LayerContentKind(
            str(
                entry.get(
                    "after_content_kind" if use_after else "before_content_kind",
                    LayerContentKind.RASTER.value,
                )
            )
        )
        set_layer_buffers(layer.id, content, alpha.astype(np.float32, copy=False))
        self.project.touch()
        self._invalidate_edit_composite_cache()
        self._render_current_adjustment_preview()
        self._refresh_layers()
        self._refresh_history()

    def _inverse_layer_metadata_entry(self, entry: dict[str, object]) -> dict[str, object] | None:
        layer = self.project.edit_layers.get(str(entry.get("layer_id")))
        if layer is None:
            return None
        return {
            "kind": "layer_metadata",
            "description": entry.get("description", "layer metadata"),
            "layer_id": layer.id,
            "before": _layer_metadata(layer),
            "after": entry.get("before", {}),
        }

    def _next_layer_order(self, source_node_id: str | None) -> int:
        matching = [
            layer.order
            for layer in self.project.edit_layers.values()
            if layer.source_node_id in {None, source_node_id}
        ]
        return (max(matching) + 1) if matching else 0
