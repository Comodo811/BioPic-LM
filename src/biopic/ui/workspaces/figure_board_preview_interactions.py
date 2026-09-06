"""Mouse, keyboard, drag/drop, and overlay editing for figure-board preview."""

from __future__ import annotations

from math import atan2, degrees

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QDragEnterEvent,
    QDragLeaveEvent,
    QDragMoveEvent,
    QDropEvent,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QWheelEvent,
)
from PySide6.QtWidgets import QMenu

from biopic.ui.workspace_helpers.common import point_distance as _point_distance


class FigureBoardPreviewInteractionMixin:
    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasFormat("application/x-biopic-asset-id"):
            event.acceptProposedAction()
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event: QDragMoveEvent) -> None:
        panel = self._panel_at(event.position())
        self._highlight_panel_id = None if panel is None else panel.id
        self.update()
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent) -> None:
        self._highlight_panel_id = None
        self.update()
        super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent) -> None:
        if self._board is None:
            super().dropEvent(event)
            return
        mime = event.mimeData()
        if not mime.hasFormat("application/x-biopic-asset-id"):
            super().dropEvent(event)
            return
        panel = self._panel_at(event.position())
        if panel is None:
            return
        asset_id = bytes(mime.data("application/x-biopic-asset-id").data()).decode("utf-8")
        self._highlight_panel_id = None
        self.imageDropped.emit(panel.id, asset_id)
        event.acceptProposedAction()
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            delta = 10 if event.angleDelta().y() > 0 else -10
            self.set_zoom_percent(self._zoom_percent + delta)
            event.accept()
            return
        super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent) -> None:
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if (
            self._annotation_edit_enabled
            and event.button() == Qt.MouseButton.LeftButton
            and self._board is not None
        ):
            overlay = self._overlay_at(event.position())
            if overlay is not None:
                self._selected_overlay = {
                    key: overlay.get(key)
                    for key in ("kind", "id", "target", "panel_id")
                }
                self.overlaySelected.emit(dict(self._selected_overlay))
                self._overlay_drag = overlay
                self._overlay_drag["start_position"] = event.position()
                self._drag_mode = "overlay"
                self._is_interacting = True
                self.update()
                event.accept()
                return
            panel = self._panel_at(event.position())
            if panel is not None:
                self._selected_overlay = None
                self.overlaySelected.emit(None)
                self._selected_panel_ids = {panel.id}
                self._selected_panel_id = panel.id
                self.panelSelected.emit(panel.id)
                self.update()
                event.accept()
                return
            printable = self._printable_rect(self._page_rect())
            if self._content_rect(printable).contains(event.position()):
                self._selected_overlay = None
                self.overlaySelected.emit(None)
                self._selected_panel_id = None
                self._selected_panel_ids.clear()
                self.update()
                event.accept()
                return
        if event.button() == Qt.MouseButton.RightButton and self._board is not None:
            printable = self._printable_rect(self._page_rect())
            panel = self._panel_at(event.position())
            if panel is not None:
                self._selected_panel_id = panel.id
                if panel.id not in self._selected_panel_ids:
                    self._selected_panel_ids = {panel.id}
                self.panelSelected.emit(panel.id)
                menu = QMenu(self)
                clear_image = None
                if panel.source_node_id is not None:
                    clear_image = menu.addAction("Remove Image")
                delete_outline = menu.addAction("Delete Outline")
                merge_selected = None
                if len(self._selected_panel_ids) == 2:
                    merge_selected = menu.addAction("Merge Selected Outlines")
                divide_horizontal = menu.addAction("Divide Horizontally")
                divide_vertical = menu.addAction("Divide Vertically")
                change_label_color = menu.addAction("Change Letter Color")
                selected = menu.exec(event.globalPosition().toPoint())
                if selected == clear_image:
                    self.panelImageClearRequested.emit(panel.id)
                elif selected == delete_outline:
                    self.panelDeleteRequested.emit(panel.id)
                elif selected == merge_selected:
                    self.panelsMergeRequested.emit(list(self._selected_panel_ids))
                elif selected == divide_horizontal:
                    self.panelDivideRequested.emit(panel.id, "horizontal")
                elif selected == divide_vertical:
                    self.panelDivideRequested.emit(panel.id, "vertical")
                elif selected == change_label_color:
                    self.panelLabelColorRequested.emit(panel.id)
                self.update(
                    self._content_rect(printable).adjusted(-48, -48, 48, 48).toAlignedRect()
                )
                event.accept()
                return
        if self._board is not None and self._caption_rect(self._page_rect()).contains(
            event.position()
        ):
            self.captionClicked.emit()
            event.accept()
            return
        printable = self._printable_rect(self._page_rect())
        content_rect = self._content_rect(printable)
        selected_panel = (
            self._panel_by_id(self._selected_panel_id)
            if self._selected_panel_id not in {None, "__board__"}
            else None
        )
        if selected_panel is not None:
            selected_panel_rect = self._panel_rect(selected_panel, content_rect)
            panel_handle = self._panel_resize_handle_at(event.position(), selected_panel_rect)
            if panel_handle is not None:
                self._drag_mode = panel_handle
                self._drag_start = event.position()
                self._drag_start_panel_rect = selected_panel.rect
                self._is_interacting = True
                self._drag_panel_changed = False
                self._emit_board_edit_started()
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            selected_handle = self._image_handle_at(
                event.position(),
                selected_panel,
                selected_panel_rect,
            )
            if selected_handle is not None:
                self._drag_mode = selected_handle
                self._drag_start = event.position()
                self._drag_start_crop = selected_panel.crop
                self._drag_start_panel_rect = selected_panel.rect
                self._drag_start_rotation = selected_panel.rotation
                self._is_interacting = True
                self._drag_panel_changed = False
                self._emit_board_edit_started()
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
        divider = self._divider_at(event.position(), content_rect)
        if divider is not None:
            self._selected_panel_id = "__board__"
            self._selected_panel_ids.clear()
            self._highlight_divider = divider
            self._drag_mode = divider
            self._drag_start = event.position()
            self._drag_start_panel_rects = {
                panel.id: panel.rect for panel in self._board.panels
            }
            self._is_interacting = True
            self._drag_panel_changed = False
            self._emit_board_edit_started()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        if content_rect.contains(event.position()) and self._board_handle_at(
            event.position(), content_rect
        ) is not None:
            self._selected_panel_id = "__board__"
            self._selected_panel_ids.clear()
            self.panelSelected.emit("__board__")
            self._drag_mode = "board_" + (
                self._board_handle_at(event.position(), content_rect) or "move"
            )
            self._drag_start = event.position()
            self._drag_start_content_rect = self._board.content_rect
            self._is_interacting = True
            self._drag_panel_changed = False
            self._emit_board_edit_started()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        if content_rect.contains(event.position()) and self._panel_at(event.position()) is None:
            self._selected_panel_id = None
            self._selected_panel_ids.clear()
            self._drag_mode = None
            self._drag_start = None
            self._drag_start_content_rect = None
            self._is_interacting = False
            self.unsetCursor()
            self.update(content_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        panel = self._panel_at(event.position())
        if panel is not None:
            if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
                if panel.id in self._selected_panel_ids:
                    self._selected_panel_ids.remove(panel.id)
                else:
                    self._selected_panel_ids.add(panel.id)
                if len(self._selected_panel_ids) > 2:
                    self._selected_panel_ids = {panel.id}
                self._selected_panel_id = panel.id
            else:
                self._selected_panel_ids = {panel.id}
                self._selected_panel_id = panel.id
            self.panelSelected.emit(panel.id)
            panel_rect = self._panel_rect(panel, content_rect)
            image_handle = self._image_handle_at(event.position(), panel, panel_rect)
            self._drag_mode = image_handle or "move"
            self._drag_start = event.position()
            self._drag_start_crop = panel.crop
            self._drag_start_panel_rect = panel.rect
            self._drag_start_rotation = panel.rotation
            self._is_interacting = True
            self._drag_panel_changed = False
            self._emit_board_edit_started()
            self.update(panel_rect.adjusted(-48, -48, 48, 48).toAlignedRect())
            return
        self._selected_panel_id = None
        self._selected_panel_ids.clear()
        self._drag_mode = None
        self._drag_start = None
        self._drag_start_content_rect = None
        self._is_interacting = False
        self.unsetCursor()
        self.update()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        if (
            self._annotation_edit_enabled
            and self._drag_mode == "overlay"
            and self._overlay_drag is not None
        ):
            self._move_overlay_drag(event.position())
            self.update()
            event.accept()
            return
        if (
            self._board is not None
            and self._selected_panel_id is not None
            and self._drag_mode is not None
            and self._drag_start is not None
        ):
            printable = self._printable_rect(self._page_rect())
            content_rect = self._content_rect(printable)
            if self._drag_mode.startswith("divider_"):
                self._move_divider(event.position(), content_rect)
                self._drag_panel_changed = True
                self.update(content_rect.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            if self._drag_mode.startswith("board_"):
                self._move_or_resize_board(event.position(), printable)
                self._drag_panel_changed = True
                self.update(printable.adjusted(-64, -64, 64, 64).toAlignedRect())
                return
            if self._drag_mode.startswith("panel_resize_"):
                panel = self._panel_by_id(self._selected_panel_id)
                if panel is not None:
                    self._resize_panel_outline(panel, event.position(), content_rect)
                    self._drag_panel_changed = True
                    self.update(content_rect.adjusted(-96, -96, 96, 96).toAlignedRect())
                return
            if self._drag_start_crop is None:
                return
            panel = self._panel_by_id(self._selected_panel_id)
            if panel is None:
                return
            panel_rect = self._panel_rect(panel, content_rect)
            if self._drag_mode == "move":
                delta = event.position() - self._drag_start
                next_x = self._drag_start_crop[0] + delta.x() / panel_rect.width()
                next_y = self._drag_start_crop[1] + delta.y() / panel_rect.height()
                next_x, next_y = self._bounded_image_center(panel, panel_rect, next_x, next_y)
                panel.crop = (
                    next_x,
                    next_y,
                    self._drag_start_crop[2],
                )
                self._drag_panel_changed = True
            elif self._drag_mode == "rotate":
                center = self._image_center(panel, panel_rect)
                start_angle = degrees(
                    atan2(self._drag_start.y() - center.y(), self._drag_start.x() - center.x())
                )
                current_angle = degrees(
                    atan2(event.position().y() - center.y(), event.position().x() - center.x())
                )
                rotation = self._drag_start_rotation + current_angle - start_angle
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    rotation = round(rotation / 15.0) * 15.0
                panel.rotation = rotation
                self._drag_panel_changed = True
            elif self._drag_mode.startswith("scale"):
                center = self._image_center(panel, panel_rect)
                start_distance = max(1.0, _point_distance(self._drag_start, center))
                current_distance = max(1.0, _point_distance(event.position(), center))
                zoom = self._drag_start_crop[2] * current_distance / start_distance
                panel.crop = (
                    self._drag_start_crop[0],
                    self._drag_start_crop[1],
                    max(0.1, min(10.0, zoom)),
                )
                self.imageScaleChanged.emit(panel.crop[2] * 100.0)
                self._drag_panel_changed = True
            self.update(content_rect.adjusted(-96, -96, 96, 96).toAlignedRect())
            return
        if self._board is not None:
            printable = self._printable_rect(self._page_rect())
            content_rect = self._content_rect(printable)
            if self._annotation_edit_enabled:
                overlay = self._overlay_at(event.position())
                if overlay is not None:
                    self.setCursor(Qt.CursorShape.SizeAllCursor)
                else:
                    self.unsetCursor()
                return
            divider = self._divider_at(event.position(), content_rect)
            if divider != self._highlight_divider:
                self._highlight_divider = divider
                self.update(content_rect.adjusted(-16, -16, 16, 16).toAlignedRect())
            if divider is not None:
                self.setCursor(
                    Qt.CursorShape.SizeHorCursor
                    if divider.startswith("divider_v")
                    else Qt.CursorShape.SizeVerCursor
                )
                return
            selected_panel = (
                self._panel_by_id(self._selected_panel_id)
                if self._selected_panel_id not in {None, "__board__"}
                else None
            )
            if selected_panel is not None:
                panel_handle = self._panel_resize_handle_at(
                    event.position(),
                    self._panel_rect(selected_panel, content_rect),
                )
                if panel_handle is not None:
                    self.setCursor(
                        Qt.CursorShape.SizeHorCursor
                        if panel_handle.endswith(("_l", "_r"))
                        else Qt.CursorShape.SizeVerCursor
                    )
                    return
                handle = self._image_handle_at(
                    event.position(),
                    selected_panel,
                    self._panel_rect(selected_panel, content_rect),
                )
                if handle == "rotate":
                    self.setCursor(Qt.CursorShape.CrossCursor)
                    return
                if handle is not None:
                    self.setCursor(Qt.CursorShape.SizeFDiagCursor)
                    return
            self.unsetCursor()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if self._drag_mode == "overlay":
            self._drag_mode = None
            self._drag_start = None
            self._overlay_drag = None
            self._is_interacting = False
            self.annotationEdited.emit()
            self.update()
            event.accept()
            return
        if self._drag_mode is not None:
            panel_id = self._selected_panel_id
            changed = self._drag_panel_changed
            self._drag_mode = None
            self._drag_start = None
            self._drag_start_crop = None
            self._drag_start_panel_rect = None
            self._drag_start_content_rect = None
            self._drag_start_panel_rects = {}
            self._drag_panel_changed = False
            self._highlight_divider = None
            self._interaction_quality_timer.stop()
            self._is_interacting = False
            self.update()
            if panel_id is not None and changed:
                self.panelTransformed.emit(panel_id)
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in {Qt.Key.Key_Delete, Qt.Key.Key_Backspace}:
            if self._annotation_edit_enabled and self._delete_selected_overlay():
                event.accept()
                return
            panel = (
                self._panel_by_id(self._selected_panel_id)
                if self._selected_panel_id not in {None, "__board__"}
                else None
            )
            if panel is not None and panel.source_node_id is not None:
                self.panelImageClearRequested.emit(panel.id)
                event.accept()
                return
        if event.matches(QKeySequence.StandardKey.Undo):
            self.undoRequested.emit()
            event.accept()
            return
        if event.matches(QKeySequence.StandardKey.Redo):
            self.redoRequested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

    def _delete_selected_overlay(self) -> bool:
        overlay = self._selected_overlay
        if not isinstance(overlay, dict):
            return False
        overlay_kind = overlay.get("kind")
        overlay_id = str(overlay.get("id") or "")
        deleted = False
        if overlay_kind == "annotation" and overlay_id in self.project.annotations:
            del self.project.annotations[overlay_id]
            deleted = True
        elif overlay_kind == "measurement" and overlay_id in self.project.measurements:
            del self.project.measurements[overlay_id]
            deleted = True
        if not deleted:
            return False
        self._selected_overlay = None
        self._overlay_drag = None
        self.overlaySelected.emit(None)
        self.annotationEdited.emit()
        self.update()
        return True

    def _emit_board_edit_started(self) -> None:
        if self._board is not None:
            self.boardEditStarted.emit(self._board.to_dict())

    def _move_or_resize_board(self, position: QPointF, printable: QRectF) -> None:
        if self._board is None or self._drag_start is None or self._drag_start_content_rect is None:
            return
        x, y, width, height = self._drag_start_content_rect
        dx = (position.x() - self._drag_start.x()) / max(1.0, printable.width())
        dy = (position.y() - self._drag_start.y()) / max(1.0, printable.height())
        mode = self._drag_mode or ""
        min_size = 0.12
        if mode == "board_move":
            x = max(0.0, min(1.0 - width, x + dx))
            y = max(0.0, min(1.0 - height, y + dy))
        elif mode.startswith("board_scale_"):
            handle = mode.removeprefix("board_scale_")
            horizontal = "l" in handle or "r" in handle
            vertical = "t" in handle or "b" in handle
            if horizontal and "l" in handle:
                next_x = max(0.0, min(x + width - min_size, x + dx))
                width = width + x - next_x
                x = next_x
            if horizontal and "r" in handle:
                width = max(min_size, min(1.0 - x, width + dx))
            if vertical and "t" in handle:
                next_y = max(0.0, min(y + height - min_size, y + dy))
                height = height + y - next_y
                y = next_y
            if vertical and "b" in handle:
                height = max(min_size, min(1.0 - y, height + dy))
        self._board.content_rect = (x, y, width, height)

    def _resize_panel_outline(
        self,
        panel: FigurePanel,
        position: QPointF,
        content: QRectF,
    ) -> None:
        if self._drag_start is None or self._drag_start_panel_rect is None:
            return
        x, y, width, height = self._drag_start_panel_rect
        dx = (position.x() - self._drag_start.x()) / max(1.0, content.width())
        dy = (position.y() - self._drag_start.y()) / max(1.0, content.height())
        min_size = 0.04
        mode = self._drag_mode or ""
        if mode.endswith("_l"):
            next_x = max(0.0, min(x + width - min_size, x + dx))
            width = width + x - next_x
            x = next_x
        elif mode.endswith("_r"):
            width = max(min_size, min(1.0 - x, width + dx))
        elif mode.endswith("_t"):
            next_y = max(0.0, min(y + height - min_size, y + dy))
            height = height + y - next_y
            y = next_y
        elif mode.endswith("_b"):
            height = max(min_size, min(1.0 - y, height + dy))
        panel.rect = (x, y, width, height)


