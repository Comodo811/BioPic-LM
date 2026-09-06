"""Scientific annotation workspace."""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from biopic.imaging.project_render import (
    editable_assets,
)
from biopic.models.annotations import (
    AbbreviationTablePreset,
    AnnotationDefinition,
)
from biopic.models.image_asset import ImageAsset
from biopic.models.project import Project
from biopic.ui.fonts import configure_safe_font_combo, safe_font_family
from biopic.ui.image_canvas import ImageCanvas
from biopic.ui.previews import asset_thumbnail
from biopic.ui.settings import settings_json
from biopic.ui.workspace_helpers.common import (
    project_asset_display_name as _project_asset_display_name,
)
from biopic.ui.workspace_styles import MEASURE_SCALE_STYLESHEET as _MEASURE_SCALE_STYLESHEET
from biopic.ui.workspaces.annotation_abbreviations import (
    COMMON_ABBREVIATION_LANGUAGES as _COMMON_ABBREVIATION_LANGUAGES,
)
from biopic.ui.workspaces.annotation_abbreviations import (
    AnnotationAbbreviationsMixin,
)
from biopic.ui.workspaces.annotation_actions import AnnotationActionsMixin
from biopic.ui.workspaces.annotation_shapes import AnnotationShapeActionsMixin


class AnnotationWorkspace(
    AnnotationShapeActionsMixin,
    AnnotationActionsMixin,
    AnnotationAbbreviationsMixin,
    QWidget,
):
    """Scientific annotation and legend workspace."""

    def __init__(self, project: Project) -> None:
        super().__init__()
        self.project = project
        self.annotationChanged: Callable[[], None] | None = None
        self._abbreviation_presets: dict[str, AbbreviationTablePreset] = {}
        self._active_abbreviation_table_id: str | None = None
        self._annotation_tool = "label"
        self._annotation_color = "#ffffff"
        self._editable_assets: list[ImageAsset] = []
        self._asset_list_signature: tuple[tuple[str, str, str], ...] | None = None
        self._moving_annotation_id: str | None = None
        self._selected_annotation_id: str | None = None
        self._annotation_undo_stack: list[dict[str, object]] = []
        self._annotation_redo_stack: list[dict[str, object]] = []
        self._annotation_transform_undo_open = False
        self._rendered_image_cache: dict[str, tuple[tuple[object, ...], np.ndarray]] = {}
        self._display_signature: tuple[object, ...] | None = None
        self._annotation_overlay_signature: tuple[object, ...] | None = None
        self._scale_bar_overlay_signature: tuple[object, ...] | None = None
        self._annotation_table_signature: tuple[object, ...] | None = None
        self._records_signature: tuple[object, ...] | None = None
        self.setStyleSheet(_MEASURE_SCALE_STYLESHEET)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.tabs = QTabWidget()
        label_tab = QWidget()
        controls = QHBoxLayout(label_tab)
        self.asset_combo = QComboBox()
        self.abbreviation_text = QPlainTextEdit()
        self.abbreviation_text.setMaximumHeight(32)
        self.definition_text = QPlainTextEdit()
        self.definition_text.setMaximumHeight(32)
        self.add_button = QPushButton("Add Label")
        controls.addWidget(QLabel("Image"))
        controls.addWidget(self.asset_combo)
        controls.addWidget(QLabel("Abbrev"))
        controls.addWidget(self.abbreviation_text)
        controls.addWidget(QLabel("Definition"))
        controls.addWidget(self.definition_text)
        controls.addWidget(self.add_button)
        self.tabs.addTab(label_tab, "Add Label")

        table_tab = QWidget()
        table_layout = QVBoxLayout(table_tab)
        table_controls = QHBoxLayout()
        self.abbreviation_table_button = QToolButton()
        self.abbreviation_table_button.setText("Abbreviation Table")
        self.abbreviation_table_button.setMinimumWidth(150)
        self.abbreviation_table_button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.abbreviation_table_menu = QMenu(self.abbreviation_table_button)
        self.abbreviation_table_button.setMenu(self.abbreviation_table_menu)
        self.abbreviation_language_combo = QComboBox()
        self.abbreviation_language_combo.setEditable(True)
        self.abbreviation_language_combo.addItems(_COMMON_ABBREVIATION_LANGUAGES)
        self.apply_abbreviation_table_button = QPushButton("Set Active")
        table_controls.addWidget(self.abbreviation_table_button)
        table_controls.addWidget(QLabel("Language"))
        table_controls.addWidget(self.abbreviation_language_combo)
        table_controls.addWidget(self.apply_abbreviation_table_button)
        table_controls.addStretch(1)
        table_layout.addLayout(table_controls)
        self.abbreviation_table = QTableWidget(0, 2)
        self.abbreviation_table.setHorizontalHeaderLabels(["Abbreviation", "Complete word"])
        self.abbreviation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        table_layout.addWidget(self.abbreviation_table)
        row_controls = QHBoxLayout()
        self.add_abbreviation_row_button = QPushButton("+")
        self.remove_abbreviation_row_button = QPushButton("-")
        row_controls.addWidget(self.add_abbreviation_row_button)
        row_controls.addWidget(self.remove_abbreviation_row_button)
        row_controls.addStretch(1)
        table_layout.addLayout(row_controls)
        self.tabs.addTab(table_tab, "Abbreviation Tables")

        splitter = QSplitter(Qt.Orientation.Horizontal)
        tools_panel = QWidget()
        tools_panel.setObjectName("annotationTools")
        tools_layout = QVBoxLayout(tools_panel)
        tools_layout.setContentsMargins(6, 6, 6, 6)
        self.asset_list = QListWidget()
        self.asset_list.setIconSize(QSize(170, 120))
        self.asset_list.setUniformItemSizes(True)
        self.asset_list.setFlow(QListWidget.Flow.LeftToRight)
        self.asset_list.setWrapping(False)
        self.asset_list.setFixedHeight(150)
        tools_layout.addWidget(QLabel("Tools"))
        self.annotation_tool_buttons: dict[str, QPushButton] = {}
        tools_grid = QGridLayout()
        for index, (tool_id, label) in enumerate(
            [
                ("move", "Move"),
                ("label", "Label"),
                ("arrow", "Arrow"),
                ("line", "Line"),
                ("wedge", "Wedge"),
            ]
        ):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setMinimumHeight(28)
            button.clicked.connect(
                lambda _checked=False, selected=tool_id: self.select_annotation_tool(
                    selected
                )
            )
            self.annotation_tool_buttons[tool_id] = button
            tools_grid.addWidget(button, index // 2, index % 2)
        tools_layout.addLayout(tools_grid)
        self.annotation_font_family = QFontComboBox()
        configure_safe_font_combo(self.annotation_font_family)
        self.annotation_font_family.setCurrentFont(QFont(safe_font_family("Arial")))
        self.annotation_font_family.currentFontChanged.connect(
            self._annotation_font_changed
        )
        self.annotation_font_size = QDoubleSpinBox()
        self.annotation_font_size.setRange(4.0, 144.0)
        self.annotation_font_size.setValue(14.0)
        self.annotation_font_size.setSuffix(" pt")
        tools_layout.addWidget(QLabel("Font family"))
        tools_layout.addWidget(self.annotation_font_family)
        tools_layout.addWidget(QLabel("Font size"))
        tools_layout.addWidget(self.annotation_font_size)
        tools_layout.addWidget(QLabel("Color"))
        self.annotation_color_button = QPushButton()
        self.annotation_color_button.setFixedSize(QSize(40, 32))
        self.annotation_color_button.setToolTip("Annotation color")
        self.annotation_color_button.clicked.connect(self._open_annotation_color_dialog)
        tools_layout.addWidget(self.annotation_color_button)
        self.annotation_width = QDoubleSpinBox()
        self.annotation_width.setRange(1.0, 20.0)
        self.annotation_width.setValue(2.0)
        self.annotation_width.setSuffix(" px")
        tools_layout.addWidget(QLabel("Line width"))
        tools_layout.addWidget(self.annotation_width)
        self._load_persistent_annotation_style()
        annotation_note = QLabel(
            "Note: Annotated objects do not appear as shown here in the figure board "
            "due to their size difference. They only appear at their position, but not "
            "with the selected font size or selected parameters. These can be changed "
            "in the figure board menu."
        )
        annotation_note.setWordWrap(True)
        tools_layout.addWidget(annotation_note)
        tools_layout.addStretch(1)
        layout.addWidget(self.asset_list)
        self.canvas = ImageCanvas()
        self.annotation_table = QTableWidget(0, 5)
        self.annotation_table.setHorizontalHeaderLabels(
            ["Label", "Kind", "Font", "Size", "Color"]
        )
        self.annotation_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.delete_annotation_button = QPushButton("Delete Annotation")
        self.delete_annotation_button.clicked.connect(self._delete_selected_annotation)
        self.records = QPlainTextEdit()
        self.records.setReadOnly(True)
        annotation_side = QWidget()
        annotation_side_layout = QVBoxLayout(annotation_side)
        annotation_side_layout.addWidget(QLabel("Elements"))
        annotation_side_layout.addWidget(self.annotation_table, 1)
        annotation_side_layout.addWidget(self.delete_annotation_button)
        annotation_side_layout.addWidget(QLabel("Legend"))
        annotation_side_layout.addWidget(self.records, 1)
        splitter.addWidget(tools_panel)
        splitter.addWidget(self.canvas)
        splitter.addWidget(annotation_side)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter)
        self.asset_combo.currentIndexChanged.connect(self._select_asset)
        self.asset_list.currentRowChanged.connect(self._select_asset_row)
        self.add_button.clicked.connect(self.add_label)
        self.canvas.pointClicked.connect(self._annotation_point_clicked)
        self.canvas.annotationShapeSelected.connect(self._annotation_shape_selected)
        self.canvas.rectangleSelected.connect(self._annotation_rectangle_selected)
        self.canvas.layerDragStarted.connect(self._annotation_move_started)
        self.canvas.layerDragFinished.connect(self._annotation_move_finished)
        self.canvas.annotationSelected.connect(self._select_annotation_by_id)
        self.canvas.annotationDeleteRequested.connect(self._delete_annotation_by_id)
        self.canvas.annotationTransformed.connect(self._annotation_transformed_on_canvas)
        self.canvas.annotationTransformFinished.connect(self._annotation_transform_finished)
        self.canvas.undoRequested.connect(self.undo)
        self.canvas.redoRequested.connect(self.redo)
        self.annotation_table.currentCellChanged.connect(
            self._annotation_table_selection_changed
        )
        self.annotation_table.cellChanged.connect(self._annotation_table_cell_changed)
        self.annotation_font_family.currentFontChanged.connect(
            self._apply_selected_annotation_style
        )
        self.annotation_font_size.valueChanged.connect(
            self._apply_selected_annotation_style
        )
        self.annotation_width.valueChanged.connect(self._apply_selected_annotation_style)
        self.abbreviation_table_menu.aboutToShow.connect(self._rebuild_abbreviation_table_menu)
        self.abbreviation_language_combo.currentTextChanged.connect(
            self._abbreviation_language_changed
        )
        self.apply_abbreviation_table_button.clicked.connect(self._apply_active_abbreviation_table)
        self.add_abbreviation_row_button.clicked.connect(self._add_abbreviation_row)
        self.remove_abbreviation_row_button.clicked.connect(self._remove_abbreviation_row)
        self.abbreviation_table.cellChanged.connect(self._abbreviation_table_cell_changed)
        self._load_persistent_abbreviation_tables()
        self._rebuild_abbreviation_table_menu()
        self._refresh_abbreviation_table_view()
        self._update_annotation_color_button()
        self.select_annotation_tool("label")

    def _load_persistent_annotation_style(self) -> None:
        style = settings_json("annotation/default_style", {})
        family = safe_font_family(str(style.get("font_family", "Arial")))
        self.annotation_font_family.setCurrentFont(QFont(family))
        try:
            font_size = float(style.get("font_size", 14.0))
            line_width = float(style.get("line_width", 2.0))
        except (TypeError, ValueError):
            font_size = 14.0
            line_width = 2.0
        self.annotation_font_size.setValue(font_size)
        color = str(style.get("color", "#ffffff"))
        self._annotation_color = color if QColor(color).isValid() else "#ffffff"
        self.annotation_width.setValue(line_width)

    def refresh(self) -> None:
        """Refresh image choices and annotation records."""
        if not self._abbreviation_presets:
            self._load_persistent_abbreviation_tables()
        current = self.asset_combo.currentData()
        assets = editable_assets(self.project)
        signature = tuple(
            (
                asset.id,
                _project_asset_display_name(asset, self.project.stacks),
                asset.checksum or asset.path,
            )
            for asset in assets
        )
        if signature != self._asset_list_signature:
            self.asset_combo.blockSignals(True)
            self.asset_list.blockSignals(True)
            self.asset_combo.clear()
            self.asset_list.clear()
            self._editable_assets = assets
            for asset in self._editable_assets:
                label = _project_asset_display_name(asset, self.project.stacks)
                self.asset_combo.addItem(label, asset.id)
                item = QListWidgetItem(
                    QIcon(asset_thumbnail(asset, QSize(170, 120))),
                    label,
                )
                item.setData(256, asset.id)
                self.asset_list.addItem(item)
            self.asset_combo.blockSignals(False)
            self.asset_list.blockSignals(False)
            self._asset_list_signature = signature
        else:
            self._editable_assets = assets
        if current is not None:
            index = self.asset_combo.findData(current)
            if index >= 0:
                self.asset_combo.setCurrentIndex(index)
                self.asset_list.setCurrentRow(index)
        if self.asset_combo.count() and self.asset_combo.currentIndex() < 0:
            self.asset_combo.setCurrentIndex(0)
        if self.asset_list.count() and self.asset_list.currentRow() < 0:
            self.asset_list.setCurrentRow(self.asset_combo.currentIndex())
        self._select_asset()
        self._refresh_records()
        self._refresh_annotation_table()
        self._refresh_abbreviation_table_view()

    def add_label(self) -> None:
        """Add a text annotation and definition."""
        node_id = self._current_source_node_id()
        if node_id is None:
            return
        abbreviation = self._label_text_from_user()
        if not abbreviation:
            return
        full_definition = self.definition_text.toPlainText().strip() or abbreviation
        self._add_text_annotation(node_id, (0.1, 0.1), abbreviation, full_definition)

    def select_annotation_tool(self, tool_id: str) -> None:
        """Select the active annotation placement tool."""
        self._annotation_tool = tool_id
        for current, button in self.annotation_tool_buttons.items():
            button.setChecked(current == tool_id)
        if tool_id == "label":
            self.canvas.set_tool_mode("text")
        elif tool_id == "move":
            self.canvas.set_tool_mode("move")
        else:
            self._configure_annotation_shape_preview()
            self.canvas.set_tool_mode("annotation_shape")

    def _definition_for_label(
        self, abbreviation: str, fallback_definition: str
    ) -> AnnotationDefinition:
        preset = self._active_abbreviation_table()
        if preset is not None:
            for entry in preset.entries:
                if entry.abbreviation.casefold() == abbreviation.casefold():
                    full_definition = entry.text_for_language(preset.active_language).strip()
                    if full_definition:
                        existing = self._existing_definition(abbreviation, full_definition)
                        if existing is not None:
                            return existing
                        return AnnotationDefinition(
                            abbreviation=abbreviation,
                            full_definition=full_definition,
                            category="scientific label",
                        )
        existing = self._existing_definition(abbreviation, fallback_definition)
        if existing is not None:
            return existing
        return AnnotationDefinition(
            abbreviation=abbreviation,
            full_definition=fallback_definition,
            category="scientific label",
        )

    def _existing_definition(
        self, abbreviation: str, full_definition: str
    ) -> AnnotationDefinition | None:
        for definition in self.project.annotation_definitions.values():
            if (
                definition.abbreviation.casefold() == abbreviation.casefold()
                and definition.full_definition == full_definition
            ):
                return definition
        return None

