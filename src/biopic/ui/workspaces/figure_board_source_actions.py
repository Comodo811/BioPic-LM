"""Source-image deletion and cleanup actions for figure boards."""

from __future__ import annotations

from PySide6.QtWidgets import QMessageBox


class FigureBoardSourceActionsMixin:
    def _delete_source_asset(self, asset_id: str) -> None:
        asset = self.project.assets.get(asset_id)
        if asset is None:
            return
        node_id = self.project.source_node_id_for_asset(asset.id)
        if node_id is None:
            return
        if self._source_asset_needs_delete_confirmation(asset_id, node_id):
            response = QMessageBox.question(
                self,
                "Delete Source Image",
                (
                    f"Delete '{asset.filename}' from the project?\n\n"
                    "This image has edits, metadata, measurements, annotations, scale bars, "
                    "or figure-board placements. Those project records will also be removed."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        self._remove_source_asset(asset_id)
        self.project.touch()
        self.image_strip.set_project_assets(self.project)
        self.preview.invalidate_render_cache()
        self._update_panel_label_color_button(None)
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _source_asset_needs_delete_confirmation(self, asset_id: str, node_id: str) -> bool:
        asset = self.project.assets.get(asset_id)
        if asset is None:
            return False
        if asset.metadata:
            return True
        if any(layer.source_node_id == node_id for layer in self.project.edit_layers.values()):
            return True
        if any(layer.image_node_id == node_id for layer in self.project.adjustment_layers.values()):
            return True
        if node_id in self.project.calibrations:
            return True
        if any(item.image_node_id == node_id for item in self.project.measurements.values()):
            return True
        if any(item.image_node_id == node_id for item in self.project.scale_bars.values()):
            return True
        if any(item.image_node_id == node_id for item in self.project.annotations.values()):
            return True
        return any(
            panel.source_node_id == node_id
            for board in self.project.figure_boards.values()
            for panel in board.panels
        )

    def _remove_source_asset(self, asset_id: str) -> None:
        asset = self.project.assets.get(asset_id)
        if asset is None:
            return
        node_id = self.project.source_node_id_for_asset(asset.id)
        if node_id is None:
            self.project.assets.pop(asset_id, None)
            return
        asset_ids = {asset_id}
        node_ids = {node_id}
        for candidate_id, candidate in self.project.assets.items():
            if candidate.metadata.get("internal_figure_board_asset") is not True:
                continue
            if (
                candidate.origin_node_id == node_id
                or candidate.metadata.get("source_node_id") == node_id
                or candidate.metadata.get("source_asset_id") == asset_id
            ):
                asset_ids.add(candidate_id)
        for candidate_id in list(asset_ids):
            candidate_node_id = self.project.source_node_id_for_asset(candidate_id)
            if candidate_node_id is not None:
                node_ids.add(candidate_node_id)
        for board in self.project.figure_boards.values():
            changed = False
            for panel in board.panels:
                if panel.source_node_id in node_ids:
                    self._clear_panel_empty_background(panel)
                    panel.source_node_id = None
                    panel.crop = (0.5, 0.5, 1.0)
                    panel.rotation = 0.0
                    panel.fill_empty_background = False
                    changed = True
            if changed:
                self._register_board_node(board)
                self._update_caption(board)
        self.project.edit_layers = {
            key: layer
            for key, layer in self.project.edit_layers.items()
            if layer.source_node_id not in node_ids
        }
        self.project.adjustment_layers = {
            key: layer
            for key, layer in self.project.adjustment_layers.items()
            if layer.image_node_id not in node_ids
        }
        self.project.retouch_strokes = {
            key: stroke
            for key, stroke in self.project.retouch_strokes.items()
            if stroke.image_node_id not in node_ids
        }
        self.project.selections = {
            key: selection
            for key, selection in self.project.selections.items()
            if selection.source_node_id not in node_ids
        }
        self.project.calibrations = {
            key: calibration
            for key, calibration in self.project.calibrations.items()
            if key not in node_ids
        }
        self.project.measurements = {
            key: measurement
            for key, measurement in self.project.measurements.items()
            if measurement.image_node_id not in node_ids
        }
        self.project.scale_bars = {
            key: scale_bar
            for key, scale_bar in self.project.scale_bars.items()
            if scale_bar.image_node_id not in node_ids
        }
        self.project.annotations = {
            key: annotation
            for key, annotation in self.project.annotations.items()
            if annotation.image_node_id not in node_ids
        }
        self.project.active_edit_layers = {
            key: value
            for key, value in self.project.active_edit_layers.items()
            if key not in node_ids
        }
        for graph_node_id, graph_node in list(self.project.graph.nodes.items()):
            source_asset_id = graph_node.parameters.get("asset_id")
            if (
                graph_node_id in node_ids
                or source_asset_id in asset_ids
                or any(input_id in node_ids for input_id in graph_node.inputs)
            ):
                del self.project.graph.nodes[graph_node_id]
        for remove_asset_id in asset_ids:
            self.project.assets.pop(remove_asset_id, None)
        if self._selected_panel_id not in {
            panel.id
            for board in self.project.figure_boards.values()
            for panel in board.panels
            if panel.source_node_id is not None
        }:
            self._selected_panel_id = None


