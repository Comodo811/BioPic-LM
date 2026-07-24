"""Figure-board workspace and preview widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.project_render import (
    asset_for_source_node,
)
from biopic.models.annotations import AnnotationDefinition, AnnotationKind
from biopic.models.figure_board import (
    FigureBoard,
    FigurePanel,
    PageFormat,
    PageUnit,
    PanelLabelMode,
    generate_layout_presets,
    journal_presets,
    page_format_presets,
    relabel_panels,
    visual_panel_order,
)
from biopic.models.project import Project
from biopic.pipeline.node import ProcessingNode
from biopic.ui.fonts import configure_safe_font_combo, safe_font_family
from biopic.ui.workspace_helpers.common import (
    biological_display_name as _biological_display_name,
)
from biopic.ui.workspace_helpers.common import (
    page_dimension_mm as _page_dimension_mm,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.figure_board_dialogs import FigureBoardDialogsMixin
from biopic.ui.workspaces.figure_board_preview import FigureBoardPreview
from biopic.ui.workspaces.figure_board_strip import FigureBoardImageStrip

_THEME_AWARE_SCROLL_AREA_STYLESHEET = """
QScrollArea {
    background: palette(window);
    border: 0;
}
QScrollArea > QWidget > QWidget {
    background: palette(window);
}
QScrollBar:horizontal, QScrollBar:vertical {
    background: palette(base);
}
QScrollBar::handle:horizontal, QScrollBar::handle:vertical {
    background: palette(mid);
    border-radius: 3px;
}
QScrollBar::add-line, QScrollBar::sub-line {
    width: 0;
    height: 0;
}
QScrollBar::add-page, QScrollBar::sub-page {
    background: transparent;
}
"""


class FigureBoardWorkspace(FigureBoardDialogsMixin, QWidget):
    """Publication figure-board layout workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.boardChanged: Callable[[], None] | None = None
        self._journal_presets = journal_presets()
        self._current_journal_preset_name = "Generic Biology"
        self._current_board_id: str | None = None
        self._selected_panel_id: str | None = None
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self._pending_preview_undo: dict[str, Any] | None = None
        self._updating_spacing_controls = False
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)
        self.image_strip = FigureBoardImageStrip()
        layout.addWidget(self.image_strip)
        controls = QHBoxLayout()
        controls_widget = QWidget()
        controls_widget.setLayout(controls)
        self.page_combo = QComboBox()
        self._page_presets = page_format_presets()
        self.page_combo.addItems(list(self._page_presets) + ["Custom"])
        self.page_width = QDoubleSpinBox()
        self.page_width.setRange(1.0, 5000.0)
        self.page_width.setValue(210.0)
        self.page_height = QDoubleSpinBox()
        self.page_height.setRange(1.0, 5000.0)
        self.page_height.setValue(297.0)
        self.page_unit = QComboBox()
        self.page_unit.addItems([PageUnit.MM.value, PageUnit.CM.value, PageUnit.INCH.value])
        self.margin_left = QDoubleSpinBox()
        self.margin_right = QDoubleSpinBox()
        self.margin_top = QDoubleSpinBox()
        self.margin_bottom = QDoubleSpinBox()
        for margin in (
            self.margin_left,
            self.margin_right,
            self.margin_top,
            self.margin_bottom,
        ):
            margin.setRange(0.0, 500.0)
            margin.setValue(8.0)
            margin.setSuffix(" mm")
        self.horizontal_spacing = QDoubleSpinBox()
        self.horizontal_spacing.setRange(0.0, 100.0)
        self.horizontal_spacing.setValue(4.0)
        self.horizontal_spacing.setSuffix(" mm")
        self.vertical_spacing = QDoubleSpinBox()
        self.vertical_spacing.setRange(0.0, 100.0)
        self.vertical_spacing.setValue(4.0)
        self.vertical_spacing.setSuffix(" mm")
        self.link_spacing = QPushButton("=")
        self.link_spacing.setCheckable(True)
        self.link_spacing.setChecked(True)
        self.panel_count = QSpinBox()
        self.panel_count.setRange(1, 8)
        self.panel_count.setValue(3)
        self.zoom_out_button = QPushButton("-")
        self.zoom_100_button = QPushButton("100%")
        self.zoom_in_button = QPushButton("+")
        self.zoom_spin = QSpinBox()
        self.zoom_spin.setRange(10, 400)
        self.zoom_spin.setValue(100)
        self.zoom_spin.setSuffix("%")
        self.panel_image_scale = QDoubleSpinBox()
        self.panel_image_scale.setRange(0.1, 10.0)
        self.panel_image_scale.setSingleStep(0.05)
        self.panel_image_scale.setValue(1.0)
        self.panel_offset_x = QDoubleSpinBox()
        self.panel_offset_y = QDoubleSpinBox()
        for offset in (self.panel_offset_x, self.panel_offset_y):
            offset.setRange(0.0, 100.0)
            offset.setValue(50.0)
            offset.setSuffix("%")
        self.panel_rotation = QDoubleSpinBox()
        self.panel_rotation.setRange(-180.0, 180.0)
        self.panel_rotation.setValue(0.0)
        self.panel_rotation.setSuffix(" deg")
        self.panel_label_text = QLineEdit()
        self.panel_label_text.setMaximumWidth(52)
        self.panel_label_color_button = QPushButton("Letter Color")
        self.panel_label_font_family = QFontComboBox()
        configure_safe_font_combo(self.panel_label_font_family)
        self.panel_label_font_size = QDoubleSpinBox()
        self.panel_label_font_size.setRange(4.0, 144.0)
        self.panel_label_font_size.setValue(10.0)
        self.panel_label_font_size.setSuffix(" pt")
        self.panel_label_font_style = QComboBox()
        self.panel_label_font_style.addItem("Bold", "bold")
        self.panel_label_font_style.addItem("Regular", "regular")
        self.panel_label_font_style.addItem("Italic", "italic")
        self.panel_label_font_style.addItem("Bold Italic", "bold_italic")
        self.board_width = QDoubleSpinBox()
        self.board_height = QDoubleSpinBox()
        self.outline_width = QDoubleSpinBox()
        self.outline_height = QDoubleSpinBox()
        for size_spin in (
            self.board_width,
            self.board_height,
            self.outline_width,
            self.outline_height,
        ):
            size_spin.setRange(1.0, 5000.0)
            size_spin.setSuffix(" mm")
        self.create_button = QPushButton("Create Figure Board")
        controls.addWidget(QLabel("Panel Spacing"))
        controls.addWidget(QLabel("Horizontal"))
        controls.addWidget(self.horizontal_spacing)
        controls.addWidget(self.link_spacing)
        controls.addWidget(QLabel("Vertical"))
        controls.addWidget(self.vertical_spacing)
        controls.addWidget(QLabel("Zoom"))
        controls.addWidget(self.zoom_out_button)
        controls.addWidget(self.zoom_spin)
        controls.addWidget(self.zoom_100_button)
        controls.addWidget(self.zoom_in_button)
        controls.addWidget(QLabel("Image"))
        controls.addWidget(QLabel("Scale"))
        controls.addWidget(self.panel_image_scale)
        controls.addWidget(QLabel("Rotate"))
        controls.addWidget(self.panel_rotation)
        controls.addWidget(QLabel("Letter"))
        controls.addWidget(self.panel_label_text)
        controls.addWidget(self.panel_label_color_button)
        controls.addWidget(QLabel("Letter Font"))
        controls.addWidget(self.panel_label_font_family)
        controls.addWidget(QLabel("Size"))
        controls.addWidget(self.panel_label_font_size)
        controls.addWidget(QLabel("Style"))
        controls.addWidget(self.panel_label_font_style)
        controls.addWidget(QLabel("Outline W"))
        controls.addWidget(self.outline_width)
        controls.addWidget(QLabel("Outline H"))
        controls.addWidget(self.outline_height)
        controls.addWidget(QLabel("Board W"))
        controls.addWidget(self.board_width)
        controls.addWidget(QLabel("Board H"))
        controls.addWidget(self.board_height)
        controls.addStretch(1)
        controls_scroll = QScrollArea()
        controls_scroll.setWidget(controls_widget)
        controls_scroll.setWidgetResizable(True)
        controls_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        controls_scroll.setMaximumHeight(92)
        layout.addWidget(controls_scroll)
        self.caption = QPlainTextEdit()
        self.caption.setPlaceholderText("Figure caption")
        self.caption.setMaximumHeight(120)
        self.lock_caption = QCheckBox("Lock edited caption")
        body = QSplitter(Qt.Orientation.Horizontal)
        self.preview = FigureBoardPreview(self.project)
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setWidget(self.preview)
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.preview_scroll.setStyleSheet(_THEME_AWARE_SCROLL_AREA_STYLESHEET)
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        side_panel = QWidget()
        side_layout = QVBoxLayout(side_panel)
        side_layout.addWidget(QLabel("Caption"))
        side_layout.addWidget(self.caption)
        side_layout.addWidget(self.lock_caption)
        side_layout.addWidget(QLabel("Board Details"))
        side_layout.addWidget(self.records)
        body.addWidget(self.preview_scroll)
        body.addWidget(side_panel)
        body.setStretchFactor(0, 1)
        body.setStretchFactor(1, 0)
        layout.addWidget(body)
        self.create_button.clicked.connect(lambda: self.create_board(show_dialog=True))
        self.caption.textChanged.connect(self._caption_edited)
        self.lock_caption.toggled.connect(self._caption_lock_toggled)
        self.page_combo.currentTextChanged.connect(self._page_preset_changed)
        self.horizontal_spacing.valueChanged.connect(self._sync_horizontal_spacing)
        self.vertical_spacing.valueChanged.connect(self._sync_vertical_spacing)
        self.link_spacing.toggled.connect(self._spacing_link_changed)
        self.zoom_spin.valueChanged.connect(self.preview.set_zoom_percent)
        self.zoom_out_button.clicked.connect(
            lambda: self.zoom_spin.setValue(self.zoom_spin.value() - 10)
        )
        self.zoom_in_button.clicked.connect(
            lambda: self.zoom_spin.setValue(self.zoom_spin.value() + 10)
        )
        self.zoom_100_button.clicked.connect(lambda: self.zoom_spin.setValue(100))
        self.preview.imageDropped.connect(self._image_dropped_on_preview)
        self.preview.panelSelected.connect(self._select_panel)
        self.preview.panelTransformed.connect(self._panel_transformed_on_canvas)
        self.preview.panelDivideRequested.connect(self._divide_panel)
        self.preview.panelDeleteRequested.connect(self._delete_panel)
        self.preview.panelsMergeRequested.connect(self._merge_panels)
        self.preview.panelImageClearRequested.connect(self._clear_panel_image)
        self.preview.panelLabelColorRequested.connect(self._change_panel_label_color)
        self.preview.boardEditStarted.connect(self._preview_board_edit_started)
        self.preview.undoRequested.connect(self.undo)
        self.preview.redoRequested.connect(self.redo)
        self.preview.imageScaleChanged.connect(self._sync_panel_scale_spin)
        self.preview.zoomChanged.connect(self._sync_zoom_spin)
        self.preview.captionClicked.connect(self._focus_caption_editor)
        self.panel_image_scale.valueChanged.connect(self._panel_transform_changed)
        self.panel_offset_x.valueChanged.connect(self._panel_transform_changed)
        self.panel_offset_y.valueChanged.connect(self._panel_transform_changed)
        self.panel_rotation.valueChanged.connect(self._panel_transform_changed)
        self.panel_label_text.textChanged.connect(self._panel_label_text_changed)
        self.panel_label_color_button.clicked.connect(self._change_selected_panel_label_color)
        self.panel_label_font_family.currentFontChanged.connect(self._panel_label_style_changed)
        self.panel_label_font_size.valueChanged.connect(self._panel_label_style_changed)
        self.panel_label_font_style.currentIndexChanged.connect(self._panel_label_style_changed)
        self.outline_width.valueChanged.connect(self._board_size_controls_changed)
        self.outline_height.valueChanged.connect(self._board_size_controls_changed)
        self.board_width.valueChanged.connect(self._page_size_controls_changed)
        self.board_height.valueChanged.connect(self._page_size_controls_changed)
        self._journal_changed(self._current_journal_preset_name)
        self._page_preset_changed(self.page_combo.currentText())

    def refresh(self) -> None:
        """Refresh board records."""
        self.image_strip.set_project_assets(self.project)
        self.preview.invalidate_render_cache()
        self._refresh_records()

    def create_board(self, *, show_dialog: bool = False) -> None:
        """Create a publication figure board with empty panel placeholders."""
        board = self._create_board_dialog() if show_dialog else None
        if board is None:
            preset = self._journal_presets[self._current_journal_preset_name]
            layout_preset = generate_layout_presets(self.panel_count.value())[0]
            board = self._board_from_settings(
                page=self._current_page(),
                panel_count=self.panel_count.value(),
                label_mode=PanelLabelMode.ALPHABETICAL,
                layout_preset=layout_preset,
                horizontal_gutter=self.horizontal_spacing.value(),
                vertical_gutter=self.vertical_spacing.value(),
                margins=self._current_margins(),
                journal_preset=preset,
            )
        self.project.figure_boards[board.id] = board
        self._current_board_id = board.id
        self._register_board_node(board)
        self._update_caption(board)
        self._show_caption(board)
        self._refresh_records()

    def _journal_changed(self, name: str) -> None:
        preset = self._journal_presets[name]
        self.horizontal_spacing.setValue(preset.horizontal_gutter)
        self.vertical_spacing.setValue(preset.vertical_gutter)
        self.margin_left.setValue(preset.margins.left)
        self.margin_right.setValue(preset.margins.right)
        self.margin_top.setValue(preset.margins.top)
        self.margin_bottom.setValue(preset.margins.bottom)

    def set_journal_preset(self, name: str) -> None:
        """Set the global journal preset used by new figure boards."""
        if name in self._journal_presets:
            self._current_journal_preset_name = name
            self._journal_changed(name)

    def journal_preset_names(self) -> list[str]:
        """Return available journal preset names."""
        return list(self._journal_presets)

    def _page_preset_changed(self, name: str) -> None:
        if name == "Custom":
            return
        page = self._page_presets[name]
        self.page_width.setValue(page.width)
        self.page_height.setValue(page.height)
        self.page_unit.setCurrentText(page.unit.value)
        self._sync_board_size_controls()

    def _sync_horizontal_spacing(self, value: float) -> None:
        if self._updating_spacing_controls:
            return
        if self.link_spacing.isChecked() and self.vertical_spacing.value() != value:
            self._updating_spacing_controls = True
            self.vertical_spacing.setValue(value)
            self._updating_spacing_controls = False
        self._apply_spacing_to_current_board()

    def _sync_vertical_spacing(self, value: float) -> None:
        if self._updating_spacing_controls:
            return
        if self.link_spacing.isChecked() and self.horizontal_spacing.value() != value:
            self._updating_spacing_controls = True
            self.horizontal_spacing.setValue(value)
            self._updating_spacing_controls = False
        self._apply_spacing_to_current_board()

    def _spacing_link_changed(self, linked: bool) -> None:
        self.link_spacing.setText("=" if linked else "free")
        if linked:
            self.vertical_spacing.setValue(self.horizontal_spacing.value())

    def _apply_spacing_to_current_board(self) -> None:
        board = self._current_board()
        if board is None:
            return
        horizontal = self.horizontal_spacing.value()
        vertical = self.vertical_spacing.value()
        if board.horizontal_gutter == horizontal and board.vertical_gutter == vertical:
            return
        self._push_board_undo(board)
        board.horizontal_gutter = horizontal
        board.vertical_gutter = vertical
        self.project.touch()
        self.preview.invalidate_render_cache()
        self.preview.update()
        self._refresh_records()
        if self.boardChanged is not None:
            self.boardChanged()

    def _sync_spacing_controls_from_board(self, board: FigureBoard) -> None:
        self._updating_spacing_controls = True
        self.horizontal_spacing.setValue(board.horizontal_gutter)
        self.vertical_spacing.setValue(board.vertical_gutter)
        self._updating_spacing_controls = False

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
        panel.crop = (
            self.panel_offset_x.value() / 100.0,
            self.panel_offset_y.value() / 100.0,
            self.panel_image_scale.value(),
        )
        panel.rotation = self.panel_rotation.value()
        self.project.touch()
        self.preview.update()

    def _panel_label_text_changed(self, text: str) -> None:
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

    def _panel_label_style_changed(self) -> None:
        if self._selected_panel_id is None:
            return
        panel = self._panel_by_id(self._selected_panel_id)
        if panel is None:
            return
        board = self._current_board()
        if board is not None:
            self._push_board_undo(board)
        bold, italic = _label_style_flags(str(self.panel_label_font_style.currentData()))
        panel.label_font_family = safe_font_family(
            self.panel_label_font_family.currentFont().family()
        )
        panel.label_font_size_pt = self.panel_label_font_size.value()
        panel.label_bold = bool(bold)
        panel.label_italic = bool(italic)
        self.project.touch()
        self.preview.update()
        if self.boardChanged is not None:
            self.boardChanged()

    def _update_panel_label_color_button(self, panel: FigurePanel | None = None) -> None:
        if panel is None and self._selected_panel_id is not None:
            panel = self._panel_by_id(self._selected_panel_id)
        enabled = panel is not None
        self.panel_label_text.setEnabled(enabled)
        self.panel_label_color_button.setEnabled(enabled)
        self.panel_label_font_family.setEnabled(enabled)
        self.panel_label_font_size.setEnabled(enabled)
        self.panel_label_font_style.setEnabled(enabled)
        color = QColor(panel.label_color if panel is not None else "#111111")
        if not color.isValid():
            color = QColor("#111111")
        self.panel_label_color_button.setStyleSheet(
            f"background-color: {color.name()}; color: {_contrast_text_color(color)};"
        )

    def _change_selected_panel_label_color(self) -> None:
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
        panel.source_node_id = None
        panel.crop = (0.5, 0.5, 1.0)
        panel.rotation = 0.0
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
        if board is not None and self._pending_preview_undo is not None:
            if board.to_dict() != self._pending_preview_undo:
                self._undo_stack.append(self._pending_preview_undo)
                self._redo_stack.clear()
            self._pending_preview_undo = None
        self._select_panel(panel_id)
        self.project.touch()
        self._sync_board_size_controls()

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
        panel.source_node_id = source_node_id
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

    def _update_caption(self, board: FigureBoard) -> None:
        parts = ["Figure."]
        scale_units: set[str] = set()
        for panel in visual_panel_order(board.panels):
            if panel.source_node_id is None:
                parts.append(f"{panel.label}. Empty panel.")
                continue
            asset = asset_for_source_node(self.project, panel.source_node_id)
            metadata = asset.metadata if asset is not None else {}
            scientific_name = metadata.get("scientific_name") or metadata.get("Scientific name")
            taxonomy = metadata.get("taxonomy")
            orientation = metadata.get("orientation") or metadata.get("Orientation")
            body_part = metadata.get("body_part")
            side = metadata.get("side")
            sex = metadata.get("sex")
            life_stage = metadata.get("life_stage")
            locality = metadata.get("locality")
            magnification = metadata.get("magnification")
            preparation = metadata.get("preparation")
            description = _biological_display_name(
                scientific_name,
                taxonomy,
                asset.filename if asset is not None else "Image",
            )
            if orientation:
                description = f"{description}, {orientation} view"
            if body_part:
                description = f"{description}, {body_part}"
            if side and side != "not applicable":
                description = f"{description}, {side} side"
            if sex:
                description = f"{description}, {sex}"
            if life_stage:
                description = f"{description}, {life_stage}"
            if magnification:
                description = f"{description}, {magnification}"
            if preparation:
                description = f"{description}, {preparation}"
            if locality:
                description = f"{description}, collected at {locality}"
            parts.append(f"{panel.label}. {description}.")
            for scale_bar in self.project.scale_bars.values():
                if scale_bar.image_node_id == panel.source_node_id:
                    scale_units.add(f"{scale_bar.physical_length:g} {scale_bar.unit}")
        if scale_units:
            parts.append(f"Scale bars: {', '.join(sorted(scale_units))}.")
        abbreviation_entries = self._board_abbreviation_legend_entries(board)
        if abbreviation_entries:
            parts.append(f"Abbreviations: {'; '.join(abbreviation_entries)}.")
        board.caption.update_auto_generated("\n".join(parts))

    def _board_abbreviation_legend_entries(self, board: FigureBoard) -> list[str]:
        source_ids = {
            panel.source_node_id
            for panel in board.panels
            if panel.source_node_id is not None
        }
        if not source_ids:
            return []
        definitions_by_id = self.project.annotation_definitions
        definitions_by_abbreviation = {
            definition.abbreviation.casefold(): definition
            for definition in definitions_by_id.values()
            if definition.include_in_legend
        }
        used: dict[str, AnnotationDefinition] = {}
        for annotation in self.project.annotations.values():
            if (
                annotation.image_node_id not in source_ids
                or not annotation.visible
                or not annotation.include_in_legend
                or annotation.kind is not AnnotationKind.TEXT
            ):
                continue
            definition = None
            if annotation.definition_id is not None:
                definition = definitions_by_id.get(annotation.definition_id)
            if definition is None and annotation.text:
                definition = definitions_by_abbreviation.get(annotation.text.casefold())
            if (
                definition is None
                or not definition.include_in_legend
                or not definition.abbreviation.strip()
                or not definition.full_definition.strip()
            ):
                continue
            used.setdefault(definition.abbreviation.casefold(), definition)
        return [
            f"{definition.abbreviation} = {definition.full_definition}"
            for definition in sorted(used.values(), key=lambda item: item.abbreviation.casefold())
        ]

    def _show_caption(self, board: FigureBoard) -> None:
        self.caption.blockSignals(True)
        self.caption.setPlainText(board.caption.visible_text())
        self.lock_caption.setChecked(board.caption.locked)
        self.caption.blockSignals(False)

    def _caption_edited(self) -> None:
        board = self._current_board()
        if board is None:
            return
        board.caption.user_text = self.caption.toPlainText()
        board.caption.user_modified = board.caption.user_text != board.caption.auto_generated
        self.project.touch()

    def _caption_lock_toggled(self, locked: bool) -> None:
        board = self._current_board()
        if board is None:
            return
        board.caption.locked = locked
        if locked:
            board.caption.user_modified = True
            board.caption.user_text = self.caption.toPlainText()
        self.project.touch()

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


