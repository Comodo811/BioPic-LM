"""Figure-board panel behavior, caption generation, records, and undo helpers."""

from __future__ import annotations

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QMessageBox

from biopic.models.figure_board import (
    FigureBoard,
    FigurePanel,
    PageFormat,
    PageUnit,
    relabel_panels,
    visual_panel_order,
)
from biopic.pipeline.node import ProcessingNode
from biopic.ui.fonts import safe_font_family
from biopic.ui.workspace_helpers.common import page_dimension_mm as _page_dimension_mm
from biopic.ui.workspaces.figure_board_labels import _label_style_id


class FigureBoardActionsMixin:
    """Panel interaction, caption, records, and undo behavior."""

    def _select_board(self, board_id: str) -> None:
        board = self.project.figure_boards.get(board_id)
        if board is None or board.id == self._current_board_id:
            return
        self._current_board_id = board.id
        self._selected_panel_id = None
        self._pending_preview_undo = None
        self.preview.set_board(board)
        self._sync_spacing_controls_from_board(board)
        self._sync_board_size_controls()
        self._update_caption(board)
        self._show_caption(board)
        self._update_panel_label_color_button(None)
        self._refresh_records()

    def _delete_board(self, board_id: str | None = None) -> None:
        board = self.project.figure_boards.get(board_id or self._current_board_id or "")
        if board is None:
            return
        if self._board_has_assigned_images(board):
            response = QMessageBox.question(
                self,
                "Delete Figure Board",
                (
                    f"Delete figure board '{board.name}'?\n\n"
                    "This board contains assigned images. The source images remain in the project."
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if response != QMessageBox.StandardButton.Yes:
                return
        was_current = board.id == self._current_board_id
        del self.project.figure_boards[board.id]
        self._remove_board_node(board.id)
        if was_current:
            next_board = next(iter(self.project.figure_boards.values()), None)
            self._current_board_id = None if next_board is None else next_board.id
            self._selected_panel_id = None
            self._pending_preview_undo = None
        self.project.touch()
        current = self._current_board()
        self.preview.set_board(current)
        self.preview.invalidate_render_cache()
        if current is not None:
            self._sync_spacing_controls_from_board(current)
            self._sync_board_size_controls()
            self._update_caption(current)
            self._show_caption(current)
        else:
            self.caption.blockSignals(True)
            self.caption.clear()
            self.caption.blockSignals(False)
        self._update_panel_label_color_button(None)
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _board_has_assigned_images(self, board: FigureBoard) -> bool:
        return any(panel.source_node_id is not None for panel in board.panels)

    def _remove_board_node(self, board_id: str) -> None:
        for node_id, node in list(self.project.graph.nodes.items()):
            if node.operation == "figure_board" and node.parameters.get("board_id") == board_id:
                del self.project.graph.nodes[node_id]

    def _image_dropped_on_preview(self, panel_id: str, asset_id: str) -> None:
        board = self._current_board()
        if board is None:
            return
        source_node_id = self.project.source_node_id_for_asset(asset_id)
        if source_node_id is None:
            return
        self.assign_image_to_panel(board.id, panel_id, source_node_id)
        self._select_panel(panel_id)

    def _select_panel(self, panel_id: str) -> None:
        if panel_id == "__board__":
            self._selected_panel_id = panel_id
            self._sync_board_size_controls()
            self._update_panel_label_color_button(None)
            return
        panel = self._panel_by_id(panel_id)
        if panel is None:
            return
        self._selected_panel_id = panel_id
        center_x, center_y, zoom = panel.crop
        self.panel_image_scale.blockSignals(True)
        self.panel_offset_x.blockSignals(True)
        self.panel_offset_y.blockSignals(True)
        self.panel_rotation.blockSignals(True)
        self.panel_label_text.blockSignals(True)
        self.panel_label_font_family.blockSignals(True)
        self.panel_label_font_size.blockSignals(True)
        self.panel_label_font_style.blockSignals(True)
        self.panel_image_scale.setValue(zoom)
        self.panel_offset_x.setValue(center_x * 100.0)
        self.panel_offset_y.setValue(center_y * 100.0)
        self.panel_rotation.setValue(panel.rotation)
        self.panel_label_text.setText(panel.label)
        self.panel_label_font_family.setCurrentFont(QFont(safe_font_family(panel.label_font_family)))
        self.panel_label_font_size.setValue(panel.label_font_size_pt)
        self.panel_label_font_style.setCurrentIndex(
            max(0, self.panel_label_font_style.findData(_label_style_id(panel)))
        )
        self.panel_image_scale.blockSignals(False)
        self.panel_offset_x.blockSignals(False)
        self.panel_offset_y.blockSignals(False)
        self.panel_rotation.blockSignals(False)
        self.panel_label_text.blockSignals(False)
        self.panel_label_font_family.blockSignals(False)
        self.panel_label_font_size.blockSignals(False)
        self.panel_label_font_style.blockSignals(False)
        self._update_panel_label_color_button(panel)
        self._sync_figure_overlay_controls()

    def _focus_caption_editor(self) -> None:
        self.caption.setFocus()
        self.caption.selectAll()

    def _panel_transform_changed(self) -> None:
        if self._selected_panel_id is None:
            return
        panel = self._panel_by_id(self._selected_panel_id)
        if panel is None:
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        self._clear_panel_empty_background(panel)
        panel.crop = (
            self.panel_offset_x.value() / 100.0,
            self.panel_offset_y.value() / 100.0,
            self.panel_image_scale.value(),
        )
        panel.rotation = self.panel_rotation.value()
        self.project.touch()
        self.preview.update()

    def _clear_panel_image(self, panel_id: str) -> None:
        board = next(
            (
                board
                for board in self.project.figure_boards.values()
                if any(panel.id == panel_id for panel in board.panels)
            ),
            None,
        )
        if board is None:
            return
        panel = next((panel for panel in board.panels if panel.id == panel_id), None)
        if panel is None or panel.source_node_id is None:
            return
        self._push_board_undo(board)
        self._clear_panel_empty_background(panel)
        panel.source_node_id = None
        panel.crop = (0.5, 0.5, 1.0)
        panel.rotation = 0.0
        panel.fill_empty_background = False
        self._selected_panel_id = panel.id
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self._select_panel(panel.id)
        self.project.touch()
        self.preview.invalidate_render_cache()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _delete_panel(self, panel_id: str) -> None:
        board = self._board_containing_panel(panel_id)
        if board is None or len(board.panels) <= 1:
            return
        self._push_board_undo(board)
        before = len(board.panels)
        board.panels = [panel for panel in board.panels if panel.id != panel_id]
        if len(board.panels) == before:
            return
        relabel_panels(board)
        self._selected_panel_id = None
        self.preview.set_board(board)
        self.preview.invalidate_render_cache()
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _merge_panels(self, panel_ids: list[str]) -> None:
        board = self._current_board()
        if board is None:
            return
        selected = [panel for panel in board.panels if panel.id in set(panel_ids)]
        if len(selected) != 2:
            return
        merged_rect = _mergeable_union_rect(selected[0], selected[1])
        if merged_rect is None:
            return
        self._push_board_undo(board)
        keep, discard = visual_panel_order(selected)
        keep.rect = merged_rect
        if keep.source_node_id is None:
            keep.source_node_id = discard.source_node_id
            keep.crop = discard.crop
            keep.rotation = discard.rotation
            keep.fill_empty_background = discard.fill_empty_background
            keep.empty_background_path = discard.empty_background_path
            keep.empty_background_signature = discard.empty_background_signature
        else:
            self._clear_panel_empty_background(keep)
        board.panels = [panel for panel in board.panels if panel.id != discard.id]
        relabel_panels(board)
        self._selected_panel_id = keep.id
        self.preview.set_board(board)
        self.preview.invalidate_render_cache()
        self._select_panel(keep.id)
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _panel_transformed_on_canvas(self, panel_id: str) -> None:
        board = self._current_board()
        panel = self._panel_by_id(panel_id)
        if board is not None and self._pending_preview_undo is not None:
            if board.to_dict() != self._pending_preview_undo:
                self._undo_stack.append(self._pending_preview_undo)
                self._redo_stack.clear()
            self._pending_preview_undo = None
        if panel is not None:
            self._clear_panel_empty_background(panel)
        self._select_panel(panel_id)
        self.project.touch()
        self._sync_board_size_controls()

    def _figure_board_annotation_edited(self) -> None:
        """Refresh project state after moving annotations or measurement text on the board."""
        self.project.touch()
        self.preview.update()
        if self.annotationOverlayChanged is not None:
            self.annotationOverlayChanged()
        elif self.boardChanged is not None:
            self.boardChanged()

    def _sync_panel_scale_spin(self, value_percent: float) -> None:
        self.panel_image_scale.blockSignals(True)
        self.panel_image_scale.setValue(value_percent / 100.0)
        self.panel_image_scale.blockSignals(False)

    def _page_size_controls_changed(self) -> None:
        board = self._current_board()
        if board is None:
            return
        self.page_combo.blockSignals(True)
        self.page_combo.setCurrentText("Custom")
        self.page_combo.blockSignals(False)
        self._push_board_undo(board)
        board.page = PageFormat(
            "Custom",
            self.board_width.value(),
            self.board_height.value(),
            PageUnit.MM,
            board.page.dpi,
        )
        self.page_width.blockSignals(True)
        self.page_height.blockSignals(True)
        self.page_unit.blockSignals(True)
        self.page_width.setValue(self.board_width.value())
        self.page_height.setValue(self.board_height.value())
        self.page_unit.setCurrentText(PageUnit.MM.value)
        self.page_width.blockSignals(False)
        self.page_height.blockSignals(False)
        self.page_unit.blockSignals(False)
        self.project.touch()
        self.preview.set_board(board)

    def _board_size_controls_changed(self) -> None:
        board = self._current_board()
        if board is None:
            return
        page_width_mm = _page_dimension_mm(board.page.width, board.page.unit)
        page_height_mm = _page_dimension_mm(board.page.height, board.page.unit)
        printable_width = max(1.0, page_width_mm - board.margin_left - board.margin_right)
        printable_height = max(
            1.0,
            page_height_mm - board.margin_top - board.margin_bottom,
        )
        x, y, _width, _height = board.content_rect
        self._push_board_undo(board)
        width = min(1.0 - x, max(0.05, self.outline_width.value() / printable_width))
        height = min(1.0 - y, max(0.05, self.outline_height.value() / printable_height))
        board.content_rect = (x, y, width, height)
        self.project.touch()
        self.preview.update()

    def _sync_board_size_controls(self) -> None:
        board = self._current_board()
        if board is None:
            return
        page_width_mm = _page_dimension_mm(board.page.width, board.page.unit)
        page_height_mm = _page_dimension_mm(board.page.height, board.page.unit)
        printable_width = max(1.0, page_width_mm - board.margin_left - board.margin_right)
        printable_height = max(
            1.0,
            page_height_mm - board.margin_top - board.margin_bottom,
        )
        self.board_width.blockSignals(True)
        self.board_height.blockSignals(True)
        self.outline_width.blockSignals(True)
        self.outline_height.blockSignals(True)
        self.board_width.setValue(page_width_mm)
        self.board_height.setValue(page_height_mm)
        self.outline_width.setValue(board.content_rect[2] * printable_width)
        self.outline_height.setValue(board.content_rect[3] * printable_height)
        self.board_width.blockSignals(False)
        self.board_height.blockSignals(False)
        self.outline_width.blockSignals(False)
        self.outline_height.blockSignals(False)

    def _panel_by_id(self, panel_id: str) -> FigurePanel | None:
        boards = [self._current_board()] + [
            board for board in self.project.figure_boards.values()
            if board.id != self._current_board_id
        ]
        for board in boards:
            if board is None:
                continue
            for panel in board.panels:
                if panel.id == panel_id:
                    self._current_board_id = board.id
                    return panel
        return None

    def _board_containing_panel(self, panel_id: str) -> FigureBoard | None:
        return next(
            (
                board
                for board in self.project.figure_boards.values()
                if any(panel.id == panel_id for panel in board.panels)
            ),
            None,
        )

    def _sync_zoom_spin(self, value: int) -> None:
        if self.zoom_spin.value() == value:
            return
        self.zoom_spin.blockSignals(True)
        self.zoom_spin.setValue(value)
        self.zoom_spin.blockSignals(False)

    def assign_image_to_panel(self, board_id: str, panel_id: str, source_node_id: str) -> None:
        """Assign an editable source node to a panel without copying pixels."""
        board = self.project.figure_boards[board_id]
        panel = next(panel for panel in board.panels if panel.id == panel_id)
        self._push_board_undo(board)
        self._clear_panel_empty_background(panel)
        panel.source_node_id = source_node_id
        panel.fill_empty_background = False
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _divide_panel(self, panel_id: str, orientation: str) -> None:
        board = self._board_containing_panel(panel_id)
        if board is None:
            return
        self._push_board_undo(board)
        panel_index = next(
            index for index, panel in enumerate(board.panels) if panel.id == panel_id
        )
        panel = board.panels[panel_index]
        x, y, width, height = panel.rect
        if orientation == "horizontal":
            panel.rect = (x, y, width, height / 2.0)
            new_rect = (x, y + height / 2.0, width, height / 2.0)
        else:
            panel.rect = (x, y, width / 2.0, height)
            new_rect = (x + width / 2.0, y, width / 2.0, height)
        new_panel = FigurePanel(
            rect=new_rect,
            label="",
            label_color=panel.label_color,
            label_font_family=panel.label_font_family,
            label_font_size_pt=panel.label_font_size_pt,
            label_bold=panel.label_bold,
            label_italic=panel.label_italic,
            label_offset=panel.label_offset,
        )
        board.panels.insert(panel_index + 1, new_panel)
        board.panels = visual_panel_order(board.panels)
        relabel_panels(board)
        self._selected_panel_id = new_panel.id
        self.preview.set_board(board)
        self.preview.invalidate_render_cache()
        self._select_panel(new_panel.id)
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def move_vertical_divider(
        self, board_id: str, left_index: int, right_index: int, delta: float
    ) -> None:
        """Move a divider between adjacent panels."""
        from biopic.models.figure_board import move_vertical_divider

        board = self.project.figure_boards[board_id]
        left, right = move_vertical_divider(
            board.panels[left_index], board.panels[right_index], delta
        )
        board.panels[left_index] = left
        board.panels[right_index] = right
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _register_board_node(self, board: FigureBoard) -> None:
        source_nodes = tuple(
            panel.source_node_id for panel in board.panels if panel.source_node_id is not None
        )
        existing = next(
            (
                node
                for node in self.project.graph.nodes.values()
                if node.operation == "figure_board"
                and node.parameters.get("board_id") == board.id
            ),
            None,
        )
        if existing is not None:
            existing.inputs = source_nodes
            existing.parameters = {"board_id": board.id}
            return
        self.project.graph.add_node(
            ProcessingNode(
                operation="figure_board",
                inputs=source_nodes,
                parameters={"board_id": board.id},
            )
        )

def _mergeable_union_rect(
    first: FigurePanel,
    second: FigurePanel,
    *,
    tolerance: float = 1e-5,
) -> tuple[float, float, float, float] | None:
    ax, ay, aw, ah = first.rect
    bx, by, bw, bh = second.rect
    left = min(ax, bx)
    top = min(ay, by)
    right = max(ax + aw, bx + bw)
    bottom = max(ay + ah, by + bh)
    union_area = (right - left) * (bottom - top)
    panel_area = aw * ah + bw * bh
    if abs(union_area - panel_area) > tolerance:
        return None
    horizontal_neighbors = (
        abs(ay - by) <= tolerance
        and abs(ah - bh) <= tolerance
        and (abs(ax + aw - bx) <= tolerance or abs(bx + bw - ax) <= tolerance)
    )
    vertical_neighbors = (
        abs(ax - bx) <= tolerance
        and abs(aw - bw) <= tolerance
        and (abs(ay + ah - by) <= tolerance or abs(by + bh - ay) <= tolerance)
    )
    if not horizontal_neighbors and not vertical_neighbors:
        return None
    return (left, top, right - left, bottom - top)

