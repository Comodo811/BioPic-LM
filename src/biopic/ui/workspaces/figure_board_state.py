"""Record refresh, current-board lookup, and undo/redo for figure boards."""

from __future__ import annotations

from typing import Any

from biopic.imaging.project_render import asset_for_source_node
from biopic.models.figure_board import FigureBoard
from biopic.ui.workspace_helpers.common import page_dimension_mm as _page_dimension_mm


class FigureBoardStateMixin:
    def _refresh_records(self) -> None:
        lines: list[str] = []
        first_board: FigureBoard | None = None
        for board in self.project.figure_boards.values():
            if first_board is None:
                first_board = board
            width, height = board.page.pixel_dimensions()
            page_width_mm = _page_dimension_mm(board.page.width, board.page.unit)
            page_height_mm = _page_dimension_mm(board.page.height, board.page.unit)
            self._update_caption(board)
            lines.append(
                f"{board.name}"
            )
            lines.append(
                f"Panels: {len(board.panels)} | Page: {page_width_mm:g} x "
                f"{page_height_mm:g} mm ({width} x {height} px)"
            )
            lines.append(f"Journal preset: {board.journal_preset or 'No journal preset'}")
            lines.append(
                f"Spacing: horizontal {board.horizontal_gutter:g} mm, "
                f"vertical {board.vertical_gutter:g} mm"
            )
            lines.append(
                f"Margins: left {board.margin_left:g} mm, right {board.margin_right:g} mm, "
                f"top {board.margin_top:g} mm, bottom {board.margin_bottom:g} mm"
            )
            lines.append("Panel assignments:")
            for panel in board.panels:
                asset = (
                    asset_for_source_node(self.project, panel.source_node_id)
                    if panel.source_node_id is not None
                    else None
                )
                image_label = asset.filename if asset is not None else "empty"
                lines.append(
                    f"  {panel.label}: {image_label}, zoom {panel.crop[2] * 100:g}%, "
                    f"rotation {panel.rotation:g}°"
                )
            lines.append("")
            lines.append("Caption")
            lines.append(board.caption.visible_text())
        self.records.setPlainText("\n".join(lines))
        current_board = self._current_board()
        if current_board is None:
            current_board = first_board
            self._current_board_id = None if first_board is None else first_board.id
        self.preview.set_board(current_board)
        self.board_list.set_project_boards(self.project, self._current_board_id)
        if current_board is not None:
            self._sync_spacing_controls_from_board(current_board)
            self._show_caption(current_board)

    def _current_board(self) -> FigureBoard | None:
        if self._current_board_id in self.project.figure_boards:
            return self.project.figure_boards[self._current_board_id]
        board = next(iter(self.project.figure_boards.values()), None)
        self._current_board_id = None if board is None else board.id
        return board

    def _preview_board_edit_started(self, snapshot: object) -> None:
        if isinstance(snapshot, dict):
            self._pending_preview_undo = dict(snapshot)

    def undo(self) -> None:
        """Undo the last figure-board edit."""
        board = self._current_board()
        if board is None or not self._undo_stack:
            return
        self._redo_stack.append(board.to_dict())
        self._restore_board_snapshot(self._undo_stack.pop())

    def redo(self) -> None:
        """Redo the last undone figure-board edit."""
        board = self._current_board()
        if board is None or not self._redo_stack:
            return
        self._undo_stack.append(board.to_dict())
        self._restore_board_snapshot(self._redo_stack.pop())

    def _push_board_undo(self, board: FigureBoard) -> None:
        snapshot = board.to_dict()
        if self._undo_stack and self._undo_stack[-1] == snapshot:
            return
        self._undo_stack.append(snapshot)
        self._redo_stack.clear()

    def _restore_board_snapshot(self, snapshot: dict[str, Any]) -> None:
        restored = FigureBoard.from_dict(snapshot)
        self.project.figure_boards[restored.id] = restored
        self._current_board_id = restored.id
        self._selected_panel_id = None
        self._pending_preview_undo = None
        self.preview.set_board(restored)
        self.preview.invalidate_render_cache()
        self._register_board_node(restored)
        self._update_caption(restored)
        self._show_caption(restored)
        self.project.touch()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()









