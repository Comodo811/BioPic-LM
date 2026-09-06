"""Panel label controls for the figure-board workspace."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import numpy as np
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QColorDialog
from PIL import Image

from biopic.export import export_image
from biopic.export.raster_figure_board import _display_compatible, _panel_image
from biopic.export.raster_figure_board_rendering import (
    _content_rect_px,
    _export_dimensions_px,
    _mm_to_px,
    _panel_rect_px,
)
from biopic.imaging.background import fill_transparent_regions_with_background
from biopic.imaging.io import load_asset_pixels
from biopic.imaging.project_render import asset_for_source_node, render_project_image
from biopic.models.figure_board import FigurePanel, panel_empty_background_signature
from biopic.ui.fonts import safe_font_family


class FigureBoardLabelsMixin:
    """Handle selected-panel label and background-fill controls."""

    def _panel_label_text_changed(self, text: str) -> None:
        if self._figure_edit_target() == "overlays":
            self._figure_overlay_text_changed(text)
            return
        if self._selected_panel_id is None:
            return
        panel = self._panel_by_id(self._selected_panel_id)
        if panel is None:
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        panel.label = text.strip()
        if board is not None:
            self._update_caption(board)
            self._show_caption(board)
        self.project.touch()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()

    def _add_background_to_selected_empty_region(self) -> None:
        if self._selected_panel_id is None:
            return
        panel = self._panel_by_id(self._selected_panel_id)
        if panel is None or panel.source_node_id is None:
            return
        board = self._current_board()
        if board is None:
            return
        self._push_board_undo(board)
        self._bake_panel_empty_background(panel)
        panel.fill_empty_background = False
        self._register_board_node(board)
        self._select_panel(panel.id)
        self.project.touch()
        self.preview.invalidate_render_cache()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()
        self._refresh_records()

    def _bake_panel_empty_background(self, panel: FigurePanel) -> None:
        """Create a one-time filled derivative image for the selected panel state."""
        board = self._current_board()
        if board is None or panel.source_node_id is None:
            raise ValueError("No figure-board panel image is selected")
        asset = asset_for_source_node(self.project, panel.source_node_id)
        if asset is None:
            raise ValueError("Selected panel image could not be found")
        rendered = render_project_image(self.project, panel.source_node_id)
        if rendered is None:
            rendered = load_asset_pixels(asset)
        image = Image.fromarray(_display_compatible(rendered)).convert("RGBA")
        board_width, board_height = _export_dimensions_px(board)
        content = _content_rect_px(board, board_width, board_height)
        gutter_x = _mm_to_px(board.horizontal_gutter, board.page.dpi)
        gutter_y = _mm_to_px(board.vertical_gutter, board.page.dpi)
        _panel_x, _panel_y, panel_width, panel_height = _panel_rect_px(
            panel,
            content,
            gutter_x,
            gutter_y,
        )
        source_panel = replace(
            panel,
            fill_empty_background=False,
            empty_background_path=None,
            empty_background_signature=None,
        )
        panel_image = _panel_image(
            image,
            source_panel,
            panel_width,
            panel_height,
            cover_rotation=False,
        )
        filled = fill_transparent_regions_with_background(np.asarray(panel_image))
        pixels = np.asarray(Image.fromarray(filled).convert("RGB"))
        output_dir = (Path.cwd() / ".biopic_cache" / self.project.id / "figure_background").resolve()
        output_path = output_dir / f"panel_background_{uuid4().hex[:10]}.png"
        self._clear_panel_empty_background(panel)
        export_image(
            pixels,
            output_path,
            dpi=board.page.dpi,
            metadata={
                "operation": "figure_board_add_background_to_empty_region",
                "created_at": datetime.now(UTC).isoformat(),
                "source_node_id": panel.source_node_id,
                "source_asset_id": asset.id,
                "panel_id": panel.id,
                "panel_crop": list(panel.crop),
                "panel_rotation": panel.rotation,
            },
        )
        panel.empty_background_path = str(output_path)
        panel.empty_background_signature = panel_empty_background_signature(
            panel,
            panel_width,
            panel_height,
        )

    def _clear_panel_empty_background(self, panel: FigurePanel) -> None:
        path = Path(panel.empty_background_path) if panel.empty_background_path else None
        panel.empty_background_path = None
        panel.empty_background_signature = None
        if path is None:
            return
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    def _panel_label_style_changed(self) -> None:
        if self._figure_edit_target() == "overlays":
            self._figure_overlay_style_changed()
            return
        board = self._current_board()
        if board is None:
            return
        panels = self._target_label_panels(board)
        if not panels:
            return
        self._push_board_undo(board)
        bold, italic = _label_style_flags(str(self.panel_label_font_style.currentData()))
        family = safe_font_family(
            self.panel_label_font_family.currentFont().family()
        )
        size = self.panel_label_font_size.value()
        for panel in panels:
            panel.label_font_family = family
            panel.label_font_size_pt = size
            panel.label_bold = bool(bold)
            panel.label_italic = bool(italic)
        self.project.touch()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()

    def _target_label_panels(self, board: object) -> list[FigurePanel]:
        selected_panel_ids = getattr(self, "_selected_panel_ids", set())
        if selected_panel_ids:
            selected_ids = set(selected_panel_ids)
            return [
                panel
                for panel in board.panels
                if panel.id in selected_ids
            ]
        if self._selected_panel_id:
            panel = self._panel_by_id(self._selected_panel_id)
            return [] if panel is None else [panel]
        return list(board.panels)

    def _update_panel_label_color_button(self, panel: FigurePanel | None = None) -> None:
        if panel is None and self._selected_panel_id is not None:
            panel = self._panel_by_id(self._selected_panel_id)
        enabled = panel is not None
        self.panel_label_text.setEnabled(enabled)
        self.panel_label_color_button.setEnabled(enabled)
        self.panel_fill_empty_background_button.setEnabled(
            panel is not None and panel.source_node_id is not None
        )
        self.panel_label_font_family.setEnabled(enabled)
        self.panel_label_font_size.setEnabled(enabled)
        self.panel_label_font_style.setEnabled(enabled)
        color = QColor(panel.label_color if panel is not None else "#111111")
        if not color.isValid():
            color = QColor("#111111")
        self.panel_label_color_button.setStyleSheet(
            f"background-color: {color.name()}; color: {_contrast_text_color(color)};"
        )
        self._sync_figure_overlay_controls()

    def _change_selected_panel_label_color(self) -> None:
        if self._figure_edit_target() == "overlays":
            self._change_selected_figure_overlay_color()
            return
        if self._selected_panel_id is None:
            return
        self._change_panel_label_color(self._selected_panel_id)

    def _change_panel_label_color(self, panel_id: str) -> None:
        panel = self._panel_by_id(panel_id)
        if panel is None:
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        current = QColor(panel.label_color)
        if not current.isValid():
            current = QColor("#111111")
        color = QColorDialog.getColor(current, self, "Change Panel Letter Color")
        if not color.isValid():
            return
        panel.label_color = color.name(QColor.NameFormat.HexRgb)
        self._selected_panel_id = panel.id
        self._update_panel_label_color_button(panel)
        self.project.touch()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()

    def _figure_edit_target(self) -> str:
        return str(self.figure_edit_target_combo.currentData() or "letters")

    def _figure_edit_target_changed(self) -> None:
        target = self._figure_edit_target()
        is_scale = target == "scale_bars"
        self.panel_label_caption.setText("Label / value" if target == "overlays" else "Letter")
        self.panel_label_color_button.setText(
            "Overlay Color" if target == "overlays" else "Letter Color"
        )
        self.panel_label_font_caption.setVisible(not is_scale)
        self.panel_label_font_family.setVisible(not is_scale)
        self.panel_label_size_caption.setVisible(not is_scale)
        self.panel_label_font_size.setVisible(not is_scale)
        self.panel_label_style_caption.setVisible(not is_scale)
        self.panel_label_font_style.setVisible(not is_scale)
        self.panel_label_caption.setVisible(not is_scale)
        self.panel_label_text.setVisible(not is_scale)
        self.panel_label_color_button.setVisible(not is_scale)
        self.scale_bar_length.setVisible(is_scale)
        self.scale_bar_height.setVisible(is_scale)
        self.scale_bar_hide_common_value.setVisible(is_scale)
        self._sync_figure_overlay_controls()

    def _figure_board_overlay_selected(self, overlay: object) -> None:
        self._selected_figure_overlay = dict(overlay) if isinstance(overlay, dict) else None
        if self._figure_edit_target() != "overlays":
            index = self.figure_edit_target_combo.findData("overlays")
            if index >= 0:
                self.figure_edit_target_combo.setCurrentIndex(index)
        self._sync_figure_overlay_controls()

    def _sync_figure_overlay_controls(self) -> None:
        target = self._figure_edit_target()
        if target == "scale_bars":
            self._sync_scale_bar_controls()
            return
        if target != "overlays":
            return
        overlay = self._selected_figure_overlay
        self.panel_label_text.blockSignals(True)
        self.panel_label_font_family.blockSignals(True)
        self.panel_label_font_size.blockSignals(True)
        self.panel_label_font_style.blockSignals(True)
        item = self._figure_overlay_item(overlay)
        has_board_overlays = self._has_current_board_overlays()
        controls_enabled = item is not None or has_board_overlays
        self.panel_label_text.setEnabled(item is not None)
        self.panel_label_color_button.setEnabled(controls_enabled)
        self.panel_label_font_family.setEnabled(controls_enabled)
        self.panel_label_font_size.setEnabled(controls_enabled)
        self.panel_label_font_style.setEnabled(controls_enabled)
        if item is None:
            self.panel_label_text.clear()
            style_item = self._first_current_board_overlay()
            if style_item is not None:
                if hasattr(style_item, "font_family"):
                    self.panel_label_font_family.setCurrentFont(
                        QFont(safe_font_family(style_item.font_family))
                    )
                    self.panel_label_font_size.setValue(float(style_item.font_size))
                    self.panel_label_font_style.setCurrentIndex(
                        max(0, self.panel_label_font_style.findData(_style_id(style_item.bold, style_item.italic)))
                    )
                    self._set_color_button(style_item.color)
                else:
                    self.panel_label_font_family.setCurrentFont(
                        QFont(safe_font_family(style_item.font))
                    )
                    self.panel_label_font_size.setValue(float(style_item.size))
                    self.panel_label_font_style.setCurrentIndex(1)
                    self._set_color_button(style_item.color)
        elif overlay and overlay.get("kind") == "measurement":
            self.panel_label_text.setText(
                item.label if overlay.get("target") == "label" else item.value_text()
            )
            self.panel_label_font_family.setCurrentFont(QFont(safe_font_family(item.font_family)))
            self.panel_label_font_size.setValue(float(item.font_size))
            self.panel_label_font_style.setCurrentIndex(
                max(0, self.panel_label_font_style.findData(_style_id(item.bold, item.italic)))
            )
            self._set_color_button(item.color)
        else:
            self.panel_label_text.setText(getattr(item, "text", ""))
            self.panel_label_font_family.setCurrentFont(QFont(safe_font_family(item.font)))
            self.panel_label_font_size.setValue(float(item.size))
            self.panel_label_font_style.setCurrentIndex(1)
            self._set_color_button(item.color)
        self.panel_label_text.blockSignals(False)
        self.panel_label_font_family.blockSignals(False)
        self.panel_label_font_size.blockSignals(False)
        self.panel_label_font_style.blockSignals(False)

    def _sync_scale_bar_controls(self) -> None:
        board = self._current_board()
        panel = self._panel_by_id(self._selected_panel_id) if self._selected_panel_id else None
        scale_bars = []
        if panel is not None and panel.source_node_id is not None:
            scale_bars = [
                scale_bar
                for scale_bar in self.project.scale_bars.values()
                if scale_bar.image_node_id == panel.source_node_id
            ]
        first = scale_bars[0] if scale_bars else None
        for widget in (self.scale_bar_length, self.scale_bar_height, self.scale_bar_hide_common_value):
            widget.blockSignals(True)
        self.scale_bar_length.setEnabled(first is not None)
        self.scale_bar_height.setEnabled(first is not None)
        if first is not None:
            self.scale_bar_length.setValue(float(first.physical_length))
            self.scale_bar_height.setValue(float(first.width_px))
        self.scale_bar_hide_common_value.setEnabled(board is not None)
        self.scale_bar_hide_common_value.setChecked(
            bool(board.hide_common_scale_bar_value) if board is not None else False
        )
        for widget in (self.scale_bar_length, self.scale_bar_height, self.scale_bar_hide_common_value):
            widget.blockSignals(False)

    def _figure_overlay_item(self, overlay: dict[str, object] | None) -> object | None:
        if not overlay:
            return None
        item_id = str(overlay.get("id", ""))
        if overlay.get("kind") == "measurement":
            return self.project.measurements.get(item_id)
        if overlay.get("kind") == "annotation":
            return self.project.annotations.get(item_id)
        return None

    def _figure_overlay_text_changed(self, text: str) -> None:
        overlay = self._selected_figure_overlay
        item = self._figure_overlay_item(overlay)
        if item is None or not overlay:
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        if overlay.get("kind") == "measurement":
            if overlay.get("target") == "label":
                item.label = text.strip()
                item.show_label = bool(item.label)
        elif getattr(item, "kind", None) is not None:
            item.text = text
        self._figure_overlay_changed()

    def _figure_overlay_style_changed(self) -> None:
        overlay = self._selected_figure_overlay
        item = self._figure_overlay_item(overlay)
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        bold, italic = _label_style_flags(str(self.panel_label_font_style.currentData()))
        family = safe_font_family(self.panel_label_font_family.currentFont().family())
        if item is None:
            self._apply_figure_overlay_style_globally(family, float(self.panel_label_font_size.value()), bold, italic)
            self._figure_overlay_changed()
            return
        if overlay and overlay.get("kind") == "measurement":
            item.font_family = family
            item.font_size = float(self.panel_label_font_size.value())
            item.bold = bool(bold)
            item.italic = bool(italic)
        else:
            item.font = family
            item.size = float(self.panel_label_font_size.value())
        self._figure_overlay_changed()

    def _change_selected_figure_overlay_color(self) -> None:
        overlay = self._selected_figure_overlay
        item = self._figure_overlay_item(overlay)
        current = QColor(getattr(item, "color", "#ffffff") if item is not None else "#ffffff")
        if not current.isValid():
            current = QColor("#ffffff")
        color = QColorDialog.getColor(current, self, "Change Figure Board Overlay Color")
        if not color.isValid():
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        color_name = color.name(QColor.NameFormat.HexRgb)
        if item is None and not self.panel_label_text.text().strip():
            self._apply_figure_overlay_color_globally(color_name)
            self._set_color_button(color_name)
            self._figure_overlay_changed()
            return
        if item is None:
            return
        item.color = color_name
        if getattr(item, "fill", None) is not None:
            item.fill = item.color
        self._set_color_button(item.color)
        self._figure_overlay_changed()

    def _apply_figure_overlay_color_globally(self, color_name: str) -> None:
        board = self._current_board()
        if board is None:
            return
        node_ids = {
            panel.source_node_id
            for panel in board.panels
            if panel.source_node_id is not None
        }
        for annotation in self.project.annotations.values():
            if annotation.image_node_id in node_ids:
                annotation.color = color_name
                if annotation.fill is not None:
                    annotation.fill = color_name
        for measurement in self.project.measurements.values():
            if measurement.image_node_id in node_ids:
                measurement.color = color_name

    def _apply_figure_overlay_style_globally(
        self,
        family: str,
        size: float,
        bold: bool,
        italic: bool,
    ) -> None:
        node_ids = self._current_board_source_node_ids()
        for annotation in self.project.annotations.values():
            if annotation.image_node_id in node_ids:
                annotation.font = family
                annotation.size = size
        for measurement in self.project.measurements.values():
            if measurement.image_node_id in node_ids:
                measurement.font_family = family
                measurement.font_size = size
                measurement.bold = bool(bold)
                measurement.italic = bool(italic)

    def _current_board_source_node_ids(self) -> set[str]:
        board = self._current_board()
        if board is None:
            return set()
        return {
            panel.source_node_id
            for panel in board.panels
            if panel.source_node_id is not None
        }

    def _has_current_board_overlays(self) -> bool:
        node_ids = self._current_board_source_node_ids()
        return any(
            annotation.image_node_id in node_ids and annotation.visible
            for annotation in self.project.annotations.values()
        ) or any(
            measurement.image_node_id in node_ids
            for measurement in self.project.measurements.values()
        )

    def _first_current_board_overlay(self) -> object | None:
        node_ids = self._current_board_source_node_ids()
        return next(
            (
                annotation
                for annotation in self.project.annotations.values()
                if annotation.image_node_id in node_ids and annotation.visible
            ),
            next(
                (
                    measurement
                    for measurement in self.project.measurements.values()
                    if measurement.image_node_id in node_ids
                ),
                None,
            ),
        )

    def _figure_scale_bar_controls_changed(self) -> None:
        board = self._current_board()
        if board is None:
            return
        self._push_board_undo(board)
        board.hide_common_scale_bar_value = bool(self.scale_bar_hide_common_value.isChecked())
        panel = self._panel_by_id(self._selected_panel_id) if self._selected_panel_id else None
        if panel is not None and panel.source_node_id is not None:
            for scale_bar in self.project.scale_bars.values():
                if scale_bar.image_node_id == panel.source_node_id:
                    scale_bar.physical_length = float(self.scale_bar_length.value())
                    scale_bar.width_px = float(self.scale_bar_height.value())
        self._update_caption(board)
        self._show_caption(board)
        self._figure_overlay_changed()

    def _figure_overlay_changed(self) -> None:
        self.project.touch()
        self.preview.update()
        if self.annotationOverlayChanged is not None:
            self.annotationOverlayChanged()
        elif self.boardChanged is not None:
            self.boardChanged()

    def _set_color_button(self, color_text: str) -> None:
        color = QColor(color_text)
        if not color.isValid():
            color = QColor("#ffffff")
        self.panel_label_color_button.setStyleSheet(
            f"background-color: {color.name()}; color: {_contrast_text_color(color)};"
        )


def _contrast_text_color(color: QColor) -> str:
    luminance = 0.2126 * color.redF() + 0.7152 * color.greenF() + 0.0722 * color.blueF()
    return "#000000" if luminance > 0.55 else "#ffffff"


def _label_style_id(panel: FigurePanel) -> str:
    if panel.label_bold and panel.label_italic:
        return "bold_italic"
    if panel.label_bold:
        return "bold"
    if panel.label_italic:
        return "italic"
    return "regular"


def _label_style_flags(style_id: str) -> tuple[bool, bool]:
    return style_id in {"bold", "bold_italic"}, style_id in {"italic", "bold_italic"}


def _style_id(bold: bool, italic: bool) -> str:
    if bold and italic:
        return "bold_italic"
    if bold:
        return "bold"
    if italic:
        return "italic"
    return "regular"
