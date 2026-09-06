"""Figure-board workspace and preview widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
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
from biopic.ui.workspaces.figure_board_captions import FigureBoardCaptionsMixin
from biopic.ui.workspaces.figure_board_dialogs import FigureBoardDialogsMixin
from biopic.ui.workspaces.figure_board_labels import (
    FigureBoardLabelsMixin,
    _label_style_id,
)
from biopic.ui.workspaces.figure_board_actions import (
    FigureBoardActionsMixin,
    _mergeable_union_rect,
)
from biopic.ui.workspaces.figure_board_preview import FigureBoardPreview
from biopic.ui.workspaces.figure_board_source_actions import FigureBoardSourceActionsMixin
from biopic.ui.workspaces.figure_board_state import FigureBoardStateMixin
from biopic.ui.workspaces.figure_board_strip import FigureBoardImageStrip, FigureBoardList

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


class FigureBoardWorkspace(
    FigureBoardActionsMixin,
    FigureBoardSourceActionsMixin,
    FigureBoardCaptionsMixin,
    FigureBoardDialogsMixin,
    FigureBoardLabelsMixin,
    FigureBoardStateMixin,
    QWidget,
):
    """Publication figure-board layout workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.boardChanged: Callable[[], None] | None = None
        self.annotationOverlayChanged: Callable[[], None] | None = None
        self._journal_presets = journal_presets()
        self._current_journal_preset_name = "Generic Biology"
        self._current_board_id: str | None = None
        self._selected_panel_id: str | None = None
        self._undo_stack: list[dict[str, Any]] = []
        self._redo_stack: list[dict[str, Any]] = []
        self._pending_preview_undo: dict[str, Any] | None = None
        self._updating_spacing_controls = False
        self._selected_figure_overlay: dict[str, object] | None = None
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)
        self.image_strip = FigureBoardImageStrip()
        self.board_list = FigureBoardList()
        top_splitter = QSplitter(Qt.Orientation.Horizontal)
        top_splitter.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sources_panel = QWidget()
        sources_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        sources_layout = QVBoxLayout(sources_panel)
        sources_layout.setContentsMargins(0, 0, 0, 0)
        sources_layout.setSpacing(2)
        sources_layout.addWidget(QLabel("Sources"))
        sources_layout.addWidget(self.image_strip)
        boards_panel = QWidget()
        boards_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        boards_layout = QVBoxLayout(boards_panel)
        boards_layout.setContentsMargins(0, 0, 0, 0)
        boards_layout.setSpacing(2)
        boards_layout.addWidget(QLabel("Figure Boards"))
        boards_layout.addWidget(self.board_list)
        top_splitter.addWidget(sources_panel)
        top_splitter.addWidget(boards_panel)
        top_splitter.setStretchFactor(0, 1)
        top_splitter.setStretchFactor(1, 1)
        top_splitter.setSizes([720, 420])
        top_splitter.setMaximumHeight(178)
        layout.addWidget(top_splitter)
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
        self.edit_annotation_button = QCheckBox("Edit Annotation Mode")
        self.edit_annotation_button.setCheckable(True)
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
        self.panel_fill_empty_background_button = QPushButton("Add Background to empty Region")
        self.panel_fill_empty_background_button.setEnabled(False)
        self.figure_edit_target_combo = QComboBox()
        self.figure_edit_target_combo.addItem("Letters", "letters")
        self.figure_edit_target_combo.addItem("Scale bars", "scale_bars")
        self.figure_edit_target_combo.addItem(
            "Measurements and annotations",
            "overlays",
        )
        self.panel_label_caption = QLabel("Letter")
        self.panel_label_text = QLineEdit()
        self.panel_label_text.setMaximumWidth(52)
        self.panel_label_color_button = QPushButton("Letter Color")
        self.panel_label_font_caption = QLabel("Letter Font")
        self.panel_label_font_family = QFontComboBox()
        configure_safe_font_combo(self.panel_label_font_family)
        self.panel_label_size_caption = QLabel("Size")
        self.panel_label_font_size = QDoubleSpinBox()
        self.panel_label_font_size.setRange(4.0, 144.0)
        self.panel_label_font_size.setValue(10.0)
        self.panel_label_font_size.setSuffix(" pt")
        self.panel_label_style_caption = QLabel("Style")
        self.panel_label_font_style = QComboBox()
        self.panel_label_font_style.addItem("Bold", "bold")
        self.panel_label_font_style.addItem("Regular", "regular")
        self.panel_label_font_style.addItem("Italic", "italic")
        self.panel_label_font_style.addItem("Bold Italic", "bold_italic")
        self.scale_bar_length = QDoubleSpinBox()
        self.scale_bar_length.setRange(0.001, 1_000_000.0)
        self.scale_bar_length.setDecimals(3)
        self.scale_bar_length.setValue(50.0)
        self.scale_bar_height = QDoubleSpinBox()
        self.scale_bar_height.setRange(1.0, 200.0)
        self.scale_bar_height.setValue(4.0)
        self.scale_bar_height.setSuffix(" px")
        self.scale_bar_hide_common_value = QCheckBox("Hide common value")
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
        spacing_widget = QWidget()
        spacing_layout = QGridLayout(spacing_widget)
        spacing_layout.setContentsMargins(0, 0, 0, 0)
        spacing_layout.setHorizontalSpacing(4)
        spacing_layout.setVerticalSpacing(2)
        spacing_layout.addWidget(QLabel("Panel Spacing"), 0, 0, 2, 1)
        spacing_layout.addWidget(QLabel("Horizontal"), 0, 1)
        spacing_layout.addWidget(self.horizontal_spacing, 0, 2)
        spacing_layout.addWidget(self.link_spacing, 0, 3, 2, 1)
        spacing_layout.addWidget(QLabel("Vertical"), 1, 1)
        spacing_layout.addWidget(self.vertical_spacing, 1, 2)
        controls.addWidget(spacing_widget)
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
        controls.addWidget(self.panel_fill_empty_background_button)
        controls.addWidget(self.figure_edit_target_combo)
        controls.addWidget(self.panel_label_caption)
        controls.addWidget(self.panel_label_text)
        controls.addWidget(self.panel_label_color_button)
        controls.addWidget(self.panel_label_font_caption)
        controls.addWidget(self.panel_label_font_family)
        controls.addWidget(self.panel_label_size_caption)
        controls.addWidget(self.panel_label_font_size)
        controls.addWidget(self.panel_label_style_caption)
        controls.addWidget(self.panel_label_font_style)
        controls.addWidget(QLabel("Scale length"))
        controls.addWidget(self.scale_bar_length)
        controls.addWidget(QLabel("Scale height"))
        controls.addWidget(self.scale_bar_height)
        controls.addWidget(self.scale_bar_hide_common_value)
        controls.addStretch(1)
        controls.addWidget(self.edit_annotation_button)
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
        self.edit_annotation_button.toggled.connect(self.preview.set_annotation_edit_enabled)
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
        self.preview.annotationEdited.connect(self._figure_board_annotation_edited)
        self.preview.overlaySelected.connect(self._figure_board_overlay_selected)
        self.board_list.boardSelected.connect(self._select_board)
        self.board_list.boardDeleteRequested.connect(self._delete_board)
        self.image_strip.assetDeleteRequested.connect(self._delete_source_asset)
        self.panel_image_scale.valueChanged.connect(self._panel_transform_changed)
        self.panel_offset_x.valueChanged.connect(self._panel_transform_changed)
        self.panel_offset_y.valueChanged.connect(self._panel_transform_changed)
        self.panel_rotation.valueChanged.connect(self._panel_transform_changed)
        self.panel_fill_empty_background_button.clicked.connect(
            self._add_background_to_selected_empty_region
        )
        self.panel_label_text.textChanged.connect(self._panel_label_text_changed)
        self.panel_label_color_button.clicked.connect(self._change_selected_panel_label_color)
        self.panel_label_font_family.currentFontChanged.connect(self._panel_label_style_changed)
        self.panel_label_font_size.valueChanged.connect(self._panel_label_style_changed)
        self.panel_label_font_style.currentIndexChanged.connect(self._panel_label_style_changed)
        self.figure_edit_target_combo.currentIndexChanged.connect(
            self._figure_edit_target_changed
        )
        self.scale_bar_length.valueChanged.connect(self._figure_scale_bar_controls_changed)
        self.scale_bar_height.valueChanged.connect(self._figure_scale_bar_controls_changed)
        self.scale_bar_hide_common_value.toggled.connect(
            self._figure_scale_bar_controls_changed
        )
        self.outline_width.valueChanged.connect(self._board_size_controls_changed)
        self.outline_height.valueChanged.connect(self._board_size_controls_changed)
        self.board_width.valueChanged.connect(self._page_size_controls_changed)
        self.board_height.valueChanged.connect(self._page_size_controls_changed)
        self._journal_changed(self._current_journal_preset_name)
        self._page_preset_changed(self.page_combo.currentText())
        self._figure_edit_target_changed()

    def refresh(self) -> None:
        """Refresh board records."""
        self.image_strip.set_project_assets(self.project)
        self.board_list.set_project_boards(self.project, self._current_board_id)
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
        self.board_list.set_project_boards(self.project, self._current_board_id)
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

